from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import operator
import os
import re
import sys
import urllib.parse

from functools import cached_property
from json.decoder import JSONDecodeError
from pathlib import Path
from urllib import parse
from urllib.parse import unquote, urljoin

from pipenv.utils.constants import VCS_LIST
from pipenv.utils.dependencies import extract_vcs_url, normalize_editable_path_for_pip
from pipenv.utils.exceptions import LockfileCorruptException
from pipenv.vendor.tomlkit.items import SingleKey, Table

try:
    import tomllib as toml
except ImportError:
    from pipenv.patched.pip._vendor import tomli as toml

import contextlib

from pipenv.cmdparse import Script
from pipenv.environment import Environment
from pipenv.environments import Setting, is_in_virtualenv, normalize_pipfile_path
from pipenv.patched.pip._internal.commands.install import InstallCommand
from pipenv.patched.pip._internal.configuration import Configuration
from pipenv.patched.pip._internal.exceptions import ConfigurationError
from pipenv.patched.pip._internal.models.link import Link
from pipenv.patched.pip._internal.req.req_install import InstallRequirement
from pipenv.patched.pip._internal.utils.hashes import FAVORITE_HASH
from pipenv.utils import err
from pipenv.utils.constants import is_type_checking
from pipenv.utils.dependencies import (
    clean_pkg_version,
    determine_package_name,
    determine_path_specifier,
    determine_vcs_specifier,
    expansive_install_req_from_line,
    get_canonical_names,
    is_editable,
    pep423_name,
    python_version,
)
from pipenv.utils.fileutils import open_file
from pipenv.utils.internet import (
    PackageIndexHTMLParser,
    get_requests_session,
    get_url_name,
    is_pypi_url,
    is_valid_url,
    proper_case,
)
from pipenv.utils.locking import atomic_open_for_write
from pipenv.utils.pylock import PylockFile, find_pylock_file
from pipenv.utils.project import get_default_pyproject_backend
from pipenv.utils.requirements import normalize_name
from pipenv.utils.shell import (
    expand_url_credentials,
    find_requirements,
    find_windows_executable,
    get_workon_home,
    is_virtual_environment,
    looks_like_dir,
    safe_expandvars,
    system_which,
)
from pipenv.utils.toml import cleanup_toml, convert_toml_outline_tables
from pipenv.utils.virtualenv import virtualenv_scripts_dir
from pipenv.vendor import plette, tomlkit

if sys.version_info < (3, 10):
    from pipenv.vendor import importlib_metadata
else:
    import importlib.metadata as importlib_metadata

if is_type_checking():
    from typing import Dict, List, Union

    TSource = Dict[str, Union[str, bool]]
    TPackageEntry = Dict[str, Union[bool, str, List[str]]]
    TPackage = Dict[str, TPackageEntry]
    TScripts = Dict[str, str]
    TPipenv = Dict[str, bool]
    TPipfile = Dict[str, Union[TPackage, TScripts, TPipenv, List[TSource]]]


DEFAULT_NEWLINES = "\n"
NON_CATEGORY_SECTIONS = {
    "build-system",
    "pipenv",
    "requires",
    "scripts",
    "source",
}


class _LockFileEncoder(json.JSONEncoder):
    """A specialized JSON encoder to convert loaded TOML data into a lock file.

    This adds a few characteristics to the encoder:

    * The JSON is always prettified with indents and spaces.
    * TOMLKit's container elements are seamlessly encodable.
    * The output is always UTF-8-encoded text, never binary, even on Python 2.
    """

    def __init__(self):
        super().__init__(indent=4, separators=(",", ": "), sort_keys=True)

    def default(self, obj):
        if isinstance(obj, Path):
            obj = obj.as_posix()
        return super().default(obj)

    def encode(self, obj):
        content = super().encode(obj)
        if not isinstance(content, str):
            content = content.decode("utf-8")
        return content


def preferred_newlines(f):
    if isinstance(f.newlines, str):
        return f.newlines
    return DEFAULT_NEWLINES


class SourceNotFound(KeyError):
    pass


def _parse_pip_conf_indexes(
    configuration: Configuration,
) -> tuple[list[dict], list[dict]]:
    """Parse ``index-url`` and ``extra-index-url`` entries from a loaded pip
    :class:`Configuration` object.

    Returns a 2-tuple ``(pip_conf_indexes, pip_conf_extra_indexes)`` where:

    * *pip_conf_indexes* – sources built from ``index-url`` keys.
    * *pip_conf_extra_indexes* – sources built from ``extra-index-url`` keys.

    Each source dict has the shape ``{"url": str, "verify_ssl": bool, "name": str}``.

    The ``trusted-host`` value for a section is handled correctly whether pip
    returns a single hostname, a whitespace/newline-separated list, or a Python
    list (future-proof).
    """
    pass


class Project:
    """docstring for Project"""

    _lockfile_encoder = _LockFileEncoder()

    def __init__(self, python_version=None, chdir=True):
        self._name = None
        self._virtualenv_location = None
        self._download_location = None
        self._proper_names_db_path = None
        self._pipfile_location = None
        self._pipfile_newlines = DEFAULT_NEWLINES
        self._lockfile_newlines = DEFAULT_NEWLINES
        self._requirements_location = None
        self._original_dir = Path.cwd().resolve()
        self._environment = None
        self._build_system = {"requires": ["setuptools", "wheel"]}
        self.python_version = python_version
        self.sessions = {}  # pip requests sessions
        self.s = Setting()
        # Load Pip configuration and merge index-url / extra-index-url entries.
        self.configuration = Configuration(isolated=False, load_only=None)
        self.configuration.load()
        pip_conf_indexes, pip_conf_extra_indexes = _parse_pip_conf_indexes(self.configuration)

        if pip_conf_indexes:
            self.default_source = None
            for pip_conf_index in pip_conf_indexes:
                if self.default_source is None:
                    self.default_source = pip_conf_index
                if is_pypi_url(pip_conf_index["url"]):
                    self.default_source = pip_conf_index
            pip_conf_indexes.remove(self.default_source)
        elif self.s.PIPENV_TEST_INDEX:
            self.default_source = {
                "url": self.s.PIPENV_TEST_INDEX,
                "verify_ssl": True,
                "name": "custom",
            }
        else:
            self.default_source = {
                "url": "https://pypi.org/simple",
                "verify_ssl": True,
                "name": "pypi",
            }

        default_sources_toml = f"[[source]]\n{tomlkit.dumps(self.default_source)}"
        for pip_conf_index in pip_conf_indexes:
            default_sources_toml += f"\n\n[[source]]\n{tomlkit.dumps(pip_conf_index)}"
        for pip_conf_extra_index in pip_conf_extra_indexes:
            default_sources_toml += f"\n\n[[source]]\n{tomlkit.dumps(pip_conf_extra_index)}"
        plette.pipfiles.DEFAULT_SOURCE_TOML = default_sources_toml

        # Hack to skip this during pipenv run, or -r.
        if ("run" not in sys.argv) and chdir:
            with contextlib.suppress(TypeError, AttributeError):
                os.chdir(self.project_directory)

    def path_to(self, p: str) -> Path:
        """Returns the absolute path to a given relative path."""
        pass

    def get_pipfile_section(self, section):
        """Returns the details from the section of the Project's Pipfile."""
        return self.parsed_pipfile.get(section, {})

    def get_package_categories(self, for_lockfile=False):
        """Ensure we get only package categories and that the default packages section is first."""
        categories = set(self.parsed_pipfile.keys())
        package_categories = categories - NON_CATEGORY_SECTIONS - {"packages", "dev-packages"}
        if for_lockfile:
            return ["default", "develop"] + list(package_categories)
        else:
            return ["packages", "dev-packages"] + list(package_categories)

    def get_requests_session_for_source(self, source):
        if not (source and source.get("name")):
            return None
        if self.sessions.get(source["name"]):
            session = self.sessions[source["name"]]
        else:
            session = get_requests_session(
                self.s.PIPENV_MAX_RETRIES,
                source.get("verify_ssl", True),
                cache_dir=self.s.PIPENV_CACHE_DIR,
                source=source.get("url"),
            )
            self.sessions[source["name"]] = session
        return session

    @classmethod
    def prepend_hash_types(cls, checksums, hash_type):
        cleaned_checksums = set()
        for checksum in checksums:
            if not checksum:
                continue
            if not checksum.startswith(f"{hash_type}:"):
                checksum = f"{hash_type}:{checksum}"
            cleaned_checksums.add(checksum)
        return sorted(cleaned_checksums)

    def get_hash_from_link(self, hash_cache, link):
        if link.hash and link.hash_name == FAVORITE_HASH:
            return f"{link.hash_name}:{link.hash}"

        return hash_cache.get_hash(link)

    def get_hashes_from_pypi(self, ireq, source):
        pkg_url = f"https://pypi.org/pypi/{ireq.name}/json"
        session = self.get_requests_session_for_source(source)
        if not session:
            return None
        try:
            collected_hashes = set()
            # Grab the hashes from the new warehouse API.
            r = session.get(pkg_url, timeout=self.s.PIPENV_REQUESTS_TIMEOUT)
            api_releases = r.json()["releases"]
            cleaned_releases = {}
            for api_version, api_info in api_releases.items():
                api_version = clean_pkg_version(api_version)
                cleaned_releases[api_version] = api_info
            version = ""
            if ireq.specifier:
                spec = next(iter(s for s in ireq.specifier), None)
                if spec:
                    version = spec.version
            for release in cleaned_releases[version]:
                collected_hashes.add(release["digests"][FAVORITE_HASH])
            return self.prepend_hash_types(collected_hashes, FAVORITE_HASH)
        except (ValueError, KeyError, ConnectionError):
            return None

    def get_hashes_from_remote_index_urls(self, ireq, source):
        normalized_name = normalize_name(ireq.name)
        url_name = normalized_name.replace(".", "-")
        pkg_url = f"{source['url']}/{url_name}/"
        session = self.get_requests_session_for_source(source)

        try:
            collected_hashes = set()
            response = session.get(pkg_url, timeout=self.s.PIPENV_REQUESTS_TIMEOUT)
            parser = PackageIndexHTMLParser()
            parser.feed(response.text)
            hrefs = parser.urls

            version = ""
            if ireq.specifier:
                spec = next(iter(s for s in ireq.specifier), None)
                if spec:
                    version = spec.version

            # We'll check if the href looks like a version-specific page (i.e., ends with '/')
            for package_url in hrefs:
                parsed_url = parse.urlparse(package_url)
                if version in parsed_url.path and parsed_url.path.endswith("/"):
                    # This might be a version-specific page. Fetch and parse it
                    version_url = urljoin(pkg_url, package_url)
                    version_response = session.get(version_url, timeout=self.s.PIPENV_REQUESTS_TIMEOUT)
                    version_parser = PackageIndexHTMLParser()
                    version_parser.feed(version_response.text)
                    version_hrefs = version_parser.urls

                    # Process these new hrefs as potential wheels
                    for v_package_url in version_hrefs:
                        url_params = parse.urlparse(v_package_url).fragment
                        params_dict = parse.parse_qs(url_params)
                        if params_dict.get(FAVORITE_HASH):
                            collected_hashes.add(params_dict[FAVORITE_HASH][0])
                        else:  # Fallback to downloading the file to obtain hash
                            v_package_full_url = urljoin(version_url, v_package_url)
                            link = Link(v_package_full_url)
                            file_hash = self.get_file_hash(session, link)
                            if file_hash:
                                collected_hashes.add(file_hash)
                elif version in parse.unquote(package_url):
                    # Process the current href as a potential wheel from the main page
                    url_params = parse.urlparse(package_url).fragment
                    params_dict = parse.parse_qs(url_params)
                    if params_dict.get(FAVORITE_HASH):
                        collected_hashes.add(params_dict[FAVORITE_HASH][0])
                    else:  # Fallback to downloading the file to obtain hash
                        package_full_url = urljoin(pkg_url, package_url)
                        link = Link(package_full_url)
                        file_hash = self.get_file_hash(session, link)
                        if file_hash:
                            collected_hashes.add(file_hash)

            return self.prepend_hash_types(collected_hashes, FAVORITE_HASH)

        except Exception:
            return None

    @staticmethod
    def get_file_hash(session, link):
        h = hashlib.new(FAVORITE_HASH)
        err.print(f"Downloading file {link.filename} to obtain hash...")
        with open_file(link.url, session) as fp:
            if fp is None:
                return None
            for chunk in iter(lambda: fp.read(8096), b""):
                h.update(chunk)
        return f"{h.name}:{h.hexdigest()}"

    @property
    def name(self) -> str:
        if self._name is None:
            self._name = Path(self.pipfile_location).parent.name
        return self._name

    @property
    def pipfile_exists(self) -> bool:
        pass

    @property
    def required_python_version(self) -> str:
        pass

    @property
    def project_directory(self) -> str:
        pass

    @property
    def requirements_exists(self) -> bool:
        pass

    def _pipfile_venv_in_project(self) -> bool | None:
        """Check the [pipenv] section of the Pipfile for venv_in_project setting.

        Returns True/False if explicitly set, None if not set.
        """
        if self.pipfile_exists:
            value = self.parsed_pipfile.get("pipenv", {}).get("venv_in_project")
            if value is not None:
                return bool(value)
        return None

    def is_venv_in_project(self) -> bool:
        # Environment variable takes precedence over Pipfile setting.
        if self.s.PIPENV_VENV_IN_PROJECT is False:
            return False
        if self.s.PIPENV_VENV_IN_PROJECT is True:
            return True
        # If env var is not set, check Pipfile [pipenv] section.
        pipfile_setting = self._pipfile_venv_in_project()
        if pipfile_setting is not None:
            return pipfile_setting
        # Fall back to auto-detection of .venv directory.
        return bool(self.project_directory and Path(self.project_directory, ".venv").is_dir())

    @property
    def virtualenv_exists(self) -> bool:
        pass

    def get_location_for_virtualenv(self) -> Path:
        # If there's no project yet, set location based on config.
        if not self.project_directory:
            if self.is_venv_in_project():
                return Path(".venv").absolute()
            return get_workon_home().joinpath(self.virtualenv_name)

        dot_venv = Path(self.project_directory) / ".venv"

        # If there's no .venv in project root or it is a folder, set location based on config.
        if not dot_venv.exists() or dot_venv.is_dir():
            if self.is_venv_in_project():
                # When PIPENV_VENV_IN_PROJECT is not explicitly set, the .venv dir
                # was detected automatically. If a pipenv-managed virtualenv already
                # exists in WORKON_HOME (e.g. created before the user independently
                # ran `python -m venv .venv`), prefer that one so that `pipenv --rm`
                # does not accidentally remove the user-created .venv directory.
                if not self.s.PIPENV_VENV_IN_PROJECT and not self._pipfile_venv_in_project():
                    workon_home_venv = get_workon_home() / self.virtualenv_name
                    if workon_home_venv.exists():
                        return workon_home_venv
                return dot_venv
            return get_workon_home().joinpath(self.virtualenv_name)

        # Now we assume .venv in project root is a file. Use its content.
        name = dot_venv.read_text().strip()

        # If .venv file is empty, set location based on config.
        if not name:
            return get_workon_home().joinpath(self.virtualenv_name)

        # If content looks like a path, use it as a relative path.
        # Otherwise, use directory named after content in WORKON_HOME.
        if looks_like_dir(name):
            path = Path(self.project_directory) / name
            return path.absolute()
        return get_workon_home().joinpath(name)

    @property
    def installed_packages(self):
        pass

    @property
    def installed_package_names(self):
        pass

    @property
    def lockfile_package_names(self) -> dict[str, set[str]]:
        pass

    @property
    def pipfile_package_names(self) -> dict[str, set[str]]:
        pass

    def get_environment(self, allow_global: bool = False) -> Environment:
        is_venv = is_in_virtualenv()
        if allow_global and not is_venv:
            prefix = sys.prefix
            python = sys.executable
        else:
            prefix = self.virtualenv_location
            python = None
        sources = self.sources if self.sources else [self.default_source]
        environment = Environment(
            prefix=prefix,
            python=python,
            is_venv=is_venv,
            sources=sources,
            pipfile=self.parsed_pipfile,
            project=self,
        )
        return environment

    @property
    def environment(self) -> Environment:
        pass

    def get_outdated_packages(self) -> list[importlib_metadata.Distribution]:
        return self.environment.get_outdated_packages(pre=self.pipfile.get("pre", False))

    @classmethod
    def _sanitize(cls, name: str) -> tuple[str, str]:
        # Replace dangerous characters into '_'. The length of the sanitized
        # project name is limited as 42 because of the limit of linux kernel
        #
        # 42 = 127 - len('/home//.local/share/virtualenvs//bin/python2') - 32 - len('-HASHHASH')
        #
        #      127 : BINPRM_BUF_SIZE - 1
        #       32 : Maximum length of username
        #
        # References:
        #   https://www.gnu.org/software/bash/manual/html_node/Double-Quotes.html
        #   http://www.tldp.org/LDP/abs/html/special-chars.html#FIELDREF
        #   https://github.com/torvalds/linux/blob/2bfe01ef/include/uapi/linux/binfmts.h#L18
        pass

    def _get_virtualenv_hash(self, name: str) -> str:
        """Get the name of the virtualenv adjusted for windows if needed

        Returns (name, encoded_hash)
        """
        pass

    @property
    def virtualenv_name(self) -> str:
        pass

    @property
    def virtualenv_location(self) -> str:
        # if VIRTUAL_ENV is set, use that.
        pass

    @property
    def virtualenv_src_location(self) -> Path:
        pass

    @property
    def virtualenv_scripts_location(self) -> Path:
        pass

    @property
    def download_location(self) -> Path:
        pass

    @property
    def proper_names_db_path(self) -> str:
        pass

    @property
    def proper_names(self) -> str:
        pass

    def register_proper_name(self, name: str) -> None:
        """Registers a proper name to the database."""
        with self.proper_names_db_path.open("a") as f:
            f.write(f"{name}\n")

    @property
    def pipfile_location(self) -> str:
        pass

    @property
    def requirements_location(self) -> str | None:
        pass

    @property
    def parsed_pipfile(self) -> tomlkit.toml_document.TOMLDocument | TPipfile:
        """Parse Pipfile into a TOMLFile"""
        pass

    def read_pipfile(self) -> str:
        # Open the pipfile, read it into memory.
        pass

    def _parse_pipfile(self, contents: str) -> tomlkit.toml_document.TOMLDocument | TPipfile:
        pass

    def _read_pyproject(self) -> None:
        pass

    @property
    def build_requires(self) -> list[str]:
        pass

    @property
    def build_backend(self) -> str:
        pass

    @property
    def pipfile_build_requires(self) -> list[str]:
        """Returns a list of build-system requirements from the Pipfile [build-system] section.

        Reads the 'requires' key from the [build-system] section of the Pipfile.
        This allows specifying packages that must be installed before other packages
        can be resolved or installed (e.g., custom setuptools wrappers used in setup.py).

        Example Pipfile::

            [build-system]
            requires = ["stwrapper", "setuptools>=40.8.0", "wheel"]

        Returns an empty list if no [build-system] section or requires key is present.
        """
        pass

    @property
    def settings(self) -> tomlkit.items.Table | dict[str, str | bool]:
        """A dictionary of the settings added to the Pipfile."""
        pass

    def has_script(self, name: str) -> bool:
        pass

    def build_script(self, name: str, extra_args: list[str] | None = None) -> Script:
        pass

    def update_settings(self, d: dict[str, str | bool]) -> None:
        pass

    def lockfile(self, categories=None):
        """Pipfile.lock divided by PyPI and external dependencies."""
        lockfile_loaded = False
        if self.lockfile_exists:
            try:
                lockfile = self.load_lockfile(expand_env_vars=False)
                lockfile_loaded = True
            except LockfileCorruptException:
                raise
            except Exception:
                pass
        if not lockfile_loaded and self.pylock_exists:
            # Try loading from pylock.toml when Pipfile.lock isn't available.
            try:
                pylock = PylockFile.from_path(self.pylock_location)
                lockfile = pylock.convert_to_pipenv_lockfile()
                lockfile_loaded = True
            except Exception:
                pass
        if not lockfile_loaded:
            with open(self.pipfile_location) as pf:
                lockfile = plette.Lockfile.with_meta_from(plette.Pipfile.load(pf), categories=categories)
                lockfile = lockfile._data

        if categories is None:
            categories = self.get_package_categories(for_lockfile=True)
        for category in categories:
            lock_section = lockfile.get(category)
            if lock_section is None:
                lockfile[category] = {}

        return lockfile

    @property
    def _pipfile(self):
        pass

    @property
    def pylock_location(self):
        """Returns the location of the pylock.toml file, if it exists."""
        pass

    @property
    def pylock_exists(self):
        """Returns True if a pylock.toml file exists."""
        pass

    @property
    def lockfile_location(self):
        pass

    @property
    def lockfile_exists(self):
        pass

    @property
    def any_lockfile_exists(self):
        """Returns True if either Pipfile.lock or pylock.toml exists."""
        pass

    @property
    def lockfile_content(self):
        """Returns the content of the lockfile, checking for pylock.toml first."""
        pass

    def get_editable_packages(self, category):
        pass

    def _get_vcs_packages(self, dev=False):
        pass

    @property
    def all_packages(self):
        """Returns a list of all packages."""
        pass

    @property
    def packages(self):
        """Returns a list of packages."""
        return self.get_pipfile_section("packages")

    @property
    def dev_packages(self):
        """Returns a list of dev-packages."""
        pass

    @property
    def pipfile_is_empty(self):
        pass

    def create_pipfile(self, python=None):
        """Creates the Pipfile, filled with juicy defaults."""
        # Inherit the pip's index configuration of install command.
        command = InstallCommand(name="InstallCommand", summary="pip Install command.")
        indexes = command.cmd_opts.get_option("--extra-index-url").default
        sources = [self.default_source]
        for i, index in enumerate(indexes):
            if not index:
                continue

            source_name = f"pip_index_{i}"
            verify_ssl = index.startswith("https")
            sources.append({"url": index, "verify_ssl": verify_ssl, "name": source_name})

        data = {
            "source": sources,
            # Default packages.
            "packages": {},
            "dev-packages": {},
        }
        # Default requires.
        required_python = python
        if not python:
            # When the virtualenv already exists (created moments ago by
            # ensure_virtualenv, or pre-existing), ask *its* interpreter for
            # the version.  Using self.which("python") instead resolves
            # "python" via PATH / pyenv shims and can return a *different*
            # Python than the one actually inside the virtualenv (e.g. the
            # pyenv global vs. the highest installed version that
            # find_all_python_versions() chose).  That disagreement causes a
            # spurious "Pipfile requires X but you are using Y" warning on
            # every subsequent pipenv invocation.  See GH-6571.
            if self.virtualenv_exists:
                required_python = self._which("python") or self.which("python")
            else:
                required_python = self.which("python")
        version = python_version(required_python) or self.s.PIPENV_DEFAULT_PYTHON_VERSION
        if version:
            data["requires"] = {"python_version": ".".join(version.split(".")[:2])}
        if python and version and len(version.split(".")) > 2:
            data["requires"].update({"python_full_version": version})
        self.write_toml(data)

    @classmethod
    def populate_source(cls, source):
        """Derive missing values of source from the existing fields."""
        # Only URL parameter is mandatory, let the KeyError be thrown.
        if "name" not in source:
            source["name"] = get_url_name(source["url"])
        if "verify_ssl" not in source:
            source["verify_ssl"] = "https://" in source["url"]
        if not isinstance(source["verify_ssl"], bool):
            source["verify_ssl"] = str(source["verify_ssl"]).lower() == "true"
        return source

    def get_or_create_lockfile(self, categories, from_pipfile=False):
        from pipenv.utils.locking import Lockfile as Req_Lockfile

        if from_pipfile and self.pipfile_exists:
            lockfile_dict = {}
            categories = self.get_package_categories(for_lockfile=True)
            _lockfile = self.lockfile(categories=categories)
            for category in categories:
                lockfile_dict[category] = _lockfile.get(category, {}).copy()
            lockfile_dict.update({"_meta": self.get_lockfile_meta()})
            lockfile = Req_Lockfile.from_data(path=self.lockfile_location, data=lockfile_dict, meta_from_project=False)
        elif self.lockfile_exists:
            try:
                lockfile = Req_Lockfile.load(self.lockfile_location)
            except OSError:
                lockfile = Req_Lockfile.from_data(self.lockfile_location, self.lockfile_content)
        elif self.pylock_exists:
            # Load from pylock.toml when no Pipfile.lock exists.
            # lockfile_content already handles pylock.toml → internal format conversion.
            lockfile_dict = self.lockfile_content.copy()
            sources = lockfile_dict.get("_meta", {}).get("sources", [])
            if not sources and self.pipfile_exists:
                sources = self.pipfile_sources(expand_vars=False)
            elif not isinstance(sources, list):
                sources = [sources]
            if sources:
                lockfile_dict["_meta"]["sources"] = [self.populate_source(s) for s in sources]
            lockfile = Req_Lockfile.from_data(path=self.lockfile_location, data=lockfile_dict, meta_from_project=False)
        else:
            lockfile = Req_Lockfile.from_data(
                path=self.lockfile_location,
                data=self.lockfile(),
                meta_from_project=False,
            )
        if lockfile.lockfile is not None:
            return lockfile
        if self.any_lockfile_exists and self.lockfile_content:
            lockfile_dict = self.lockfile_content.copy()
            sources = lockfile_dict.get("_meta", {}).get("sources", [])
            if not sources and self.pipfile_exists:
                sources = self.pipfile_sources(expand_vars=False)
            elif not isinstance(sources, list):
                sources = [sources]
            if sources:
                lockfile_dict["_meta"]["sources"] = [self.populate_source(s) for s in sources]
            _created_lockfile = Req_Lockfile.from_data(path=self.lockfile_location, data=lockfile_dict, meta_from_project=False)
            lockfile.lockfile = lockfile.projectfile.model = _created_lockfile
            return lockfile
        else:
            return self.get_or_create_lockfile(categories=categories, from_pipfile=True)

    def get_lockfile_meta(self):
        from .vendor.plette.lockfiles import PIPFILE_SPEC_CURRENT

        if "source" in self.parsed_pipfile:
            sources = [dict(source) for source in self.parsed_pipfile["source"]]
        else:
            sources = self.pipfile_sources(expand_vars=False)
        if not isinstance(sources, list):
            sources = [sources]
        return {
            "hash": {"sha256": self.calculate_pipfile_hash()},
            "pipfile-spec": PIPFILE_SPEC_CURRENT,
            "sources": [self.populate_source(s) for s in sources],
            "requires": self.parsed_pipfile.get("requires", {}),
        }

    def write_toml(self, data, path=None):
        """Writes the given data structure out as TOML."""
        if path is None:
            path = self.pipfile_location
        data = convert_toml_outline_tables(data, self)
        try:
            formatted_data = tomlkit.dumps(data).rstrip()
        except Exception:
            document = tomlkit.document()
            for category in self.get_package_categories():
                document[category] = tomlkit.table()
                # Convert things to inline tables — fancy :)
                for package in data.get(category, {}):
                    if hasattr(data[category][package], "keys"):
                        table = tomlkit.inline_table()
                        table.update(data[category][package])
                        document[category][package] = table
                    else:
                        document[category][package] = tomlkit.string(data[category][package])
            formatted_data = tomlkit.dumps(document).rstrip()

        if Path(path).absolute() == Path(self.pipfile_location).absolute():
            newlines = self._pipfile_newlines
        else:
            newlines = DEFAULT_NEWLINES
        formatted_data = cleanup_toml(formatted_data)
        with open(path, "w", newline=newlines) as f:
            f.write(formatted_data)

    @property
    def use_pylock(self) -> bool:
        """Returns True if pylock.toml should be generated."""
        pass

    @property
    def pylock_output_path(self) -> str:
        """Returns the path where pylock.toml should be written."""
        pass

    def write_lockfile(self, content):
        """Write out the lockfile."""
        # Always write the Pipfile.lock
        s = self._lockfile_encoder.encode(content)
        open_kwargs = {"newline": self._lockfile_newlines, "encoding": "utf-8"}
        with atomic_open_for_write(self.lockfile_location, **open_kwargs) as f:
            f.write(s)
            # Write newline at end of document. GH-319.
            # Only need '\n' here; the file object handles the rest.
            if not s.endswith("\n"):
                f.write("\n")

        # If use_pylock is enabled, also write a pylock.toml file
        if self.use_pylock:
            try:
                from pipenv.utils.pylock import PylockFile

                pylock = PylockFile.from_lockfile(
                    lockfile_path=self.lockfile_location,
                    pylock_path=self.pylock_output_path,
                )
                pylock.write()
                err.print(f"[bold green]Generated pylock.toml at {self.pylock_output_path}[/bold green]")
            except Exception as e:
                err.print(f"[bold red]Error generating pylock.toml: {e}[/bold red]")

    def pipfile_sources(self, expand_vars=True):
        if self.pipfile_is_empty or "source" not in self.parsed_pipfile:
            sources = [self.default_source]
            if os.environ.get("PIPENV_PYPI_MIRROR"):
                sources[0]["url"] = os.environ["PIPENV_PYPI_MIRROR"]
            return sources
        # Expand environment variables in the source URLs.
        # For the "url" field we use expand_url_credentials() which URL-encodes
        # the expanded credential values so that passwords with special characters
        # (e.g. '@', ':', '%') produce a valid URL (#4868).
        sources = [
            {k: ((expand_url_credentials(v) if k == "url" else safe_expandvars(v)) if expand_vars else v) for k, v in source.items()}
            for source in self.parsed_pipfile["source"]
        ]
        for source in sources:
            if os.environ.get("PIPENV_PYPI_MIRROR") and is_pypi_url(source.get("url")):
                source["url"] = os.environ["PIPENV_PYPI_MIRROR"]
        return sources

    def get_default_index(self):
        return self.populate_source(self.pipfile_sources()[0])

    def get_index_by_name(self, index_name):
        pass

    def get_index_by_url(self, index_url):
        pass

    @property
    def sources(self):
        pass

    @property
    def sources_default(self):
        pass

    @property
    def index_urls(self):
        pass

    def find_source(self, source):
        """
        Given a source, find it.

        source can be a url or an index name.
        """
        if not is_valid_url(source):
            try:
                source = self.get_source(name=source)
            except SourceNotFound:
                source = self.get_source(url=source)
        else:
            source = self.get_source(url=source)
        return source

    def get_source(self, name=None, url=None, refresh=False):
        from pipenv.utils.internet import is_url_equal

        def find_source(sources, name=None, url=None):
            source = None
            if name:
                source = next(iter(s for s in sources if "name" in s and s["name"] == name), None)
            elif url:
                source = next(
                    iter(s for s in sources if "url" in s and is_url_equal(url, s.get("url", ""))),
                    None,
                )
            if source is not None:
                return source

        sources = (self.sources, self.pipfile_sources())
        if refresh:
            sources = reversed(sources)
        # Iterate explicitly so that a None result from the first source list
        # does not short-circuit the search in the second list.
        # (Avoids the walrus operator to stay compatible with Python 3.7.)
        found = None
        for _src in sources:
            _result = find_source(_src, name=name, url=url)
            if _result is not None:
                found = _result
                break
        target = next(iter(t for t in (name, url) if t is not None))
        if found is None:
            raise SourceNotFound(target)
        return found

    def get_package_name_in_pipfile(self, package_name, category):
        section = self.parsed_pipfile.get(category, {})
        normalized_name = pep423_name(package_name)
        for name in section:
            if pep423_name(name) == normalized_name:
                return name
        return package_name  # Return original name if not found

    def get_pipfile_entry(self, package_name, category):
        name = self.get_package_name_in_pipfile(package_name, category)
        return self.parsed_pipfile.get(category, {}).get(name)

    def _sort_category(self, category) -> Table:
        # copy table or create table from dict-like object
        table = tomlkit.table()
        if isinstance(category, Table):
            table.update(category.value)
        else:
            table.update(category)

        # sort the table internally
        table._value._body.sort(key=lambda t: t[0] and t[0].key or "")
        for index, (key, _) in enumerate(table._value._body):
            assert isinstance(key, SingleKey)
            indices = table._value._map[key]
            if isinstance(indices, tuple):
                table._value._map[key] = (index,) + indices[1:]
            else:
                table._value._map[key] = index

        return table

    def remove_package_from_pipfile(self, package_name, category):
        # Read and append Pipfile.
        pass

    def reset_category_in_pipfile(self, category):
        # Read and append Pipfile.
        pass

    def remove_packages_from_pipfile(self, packages):
        pass

    def generate_package_pipfile_entry(self, package, pip_line, category=None, index_name=None, no_binary=False):
        """Generate a package entry from pip install line
        given the installreq package and the pip line that generated it.
        """
        # Don't re-capitalize file URLs or VCSs.
        if not isinstance(package, InstallRequirement):
            package, req_name = expansive_install_req_from_line(package.strip())
        else:
            _, req_name = expansive_install_req_from_line(pip_line.strip())

        if req_name is None:
            req_name = determine_package_name(package)
        path_specifier = determine_path_specifier(package)
        vcs_specifier = determine_vcs_specifier(package)
        name = self.get_package_name_in_pipfile(req_name, category=category)
        normalized_name = normalize_name(req_name)

        extras = package.extras
        specifier = "*"
        if package.req and package.specifier:
            specifier = str(package.specifier)

        # Construct package requirement
        entry = {}
        if extras:
            entry["extras"] = list(extras)
        if path_specifier:
            editable = pip_line.startswith("-e")
            # Strip "-e" prefix to get the raw package reference from the install line.
            raw_ref = pip_line[2:].strip() if editable else pip_line.strip()
            raw_ref = raw_ref.strip('"').strip("'")
            # Use "file" for remote HTTP/HTTPS URLs and explicit file:// URLs;
            # use "path" for plain local filesystem paths (e.g. ".", "./lib").
            is_http_url = path_specifier.startswith(("http:", "https:"))
            is_file_url = raw_ref.startswith("file:")
            key = "file" if (is_http_url or is_file_url) else "path"
            if is_file_url:
                # Preserve the original file:// URL exactly as the user typed it.
                entry[key] = unquote(raw_ref)
            else:
                entry[key] = unquote(normalize_editable_path_for_pip(path_specifier) if editable else str(path_specifier))
            if editable:
                entry["editable"] = editable
        elif vcs_specifier:
            for vcs in VCS_LIST:
                if vcs in package.link.scheme:
                    if pip_line.startswith("-e"):
                        entry["editable"] = True
                        pip_line = pip_line.replace("-e ", "")
                    if "[" in pip_line and "]" in pip_line:
                        extras_section = pip_line.split("[")[1].split("]")[0]
                        entry["extras"] = sorted([extra.strip() for extra in extras_section.split(",")])
                    if "@ " in pip_line:
                        vcs_part = pip_line.split("@ ", 1)[1]
                    else:
                        vcs_part = pip_line
                    vcs_parts = vcs_part.rsplit("@", 1)
                    if len(vcs_parts) > 1:
                        entry["ref"] = vcs_parts[1].split("#", 1)[0].strip()
                    vcs_url = vcs_parts[0].strip()
                    vcs_url = extract_vcs_url(vcs_url)
                    entry[vcs] = vcs_url

                    # Check and extract subdirectory fragment
                    if package.link.subdirectory_fragment:
                        entry["subdirectory"] = package.link.subdirectory_fragment
                    break
        else:
            entry["version"] = specifier

        if index_name:
            entry["index"] = index_name
        elif hasattr(package, "index"):
            entry["index"] = package.index

        # Include markers (e.g., sys_platform == 'win32') if present
        if package.markers:
            entry["markers"] = str(package.markers)

        # Store no_binary flag so pipenv re-applies --no-binary on future installs
        if no_binary:
            entry["no_binary"] = True

        if len(entry) == 1 and "version" in entry:
            return name, normalized_name, specifier
        else:
            return name, normalized_name, entry

    def add_package_to_pipfile(self, package, pip_line, dev=False, category=None, no_binary=False):
        pass

    def add_pipfile_entry_to_pipfile(self, name, normalized_name, entry, category=None):
        newly_added = False

        # Read and append Pipfile.
        parsed_pipfile = self.parsed_pipfile

        # Set empty group if it doesn't exist yet.
        if category not in parsed_pipfile:
            parsed_pipfile[category] = {}

        section = parsed_pipfile.get(category, {})
        for entry_name in section.copy().keys():
            if entry_name.lower() == normalized_name.lower():
                del parsed_pipfile[category][entry_name]

        # Add the package to the group.
        if normalized_name not in parsed_pipfile[category]:
            newly_added = True

        parsed_pipfile[category][normalized_name] = entry

        if self.settings.get("sort_pipfile"):
            parsed_pipfile[category] = self._sort_category(parsed_pipfile[category])

        # Write Pipfile.
        self.write_toml(parsed_pipfile)
        return newly_added, category, normalized_name

    def add_packages_to_pipfile_batch(self, packages_data, dev=False, categories=None):
        """
        Add multiple packages to Pipfile in a single operation for better performance.

        Args:
            packages_data: List of tuples (package, pip_line) or list of dicts with package info
            dev: Whether to add to dev-packages section
            categories: List of categories to add packages to

        Returns:
            List of tuples (newly_added, category, normalized_name) for each package
        """
        if not packages_data:
            return []

        # Determine target categories
        if categories is None or (isinstance(categories, list) and len(categories) == 0):
            categories = ["dev-packages" if dev else "packages"]
        elif isinstance(categories, str):
            categories = [categories]

        # Read Pipfile once
        parsed_pipfile = self.parsed_pipfile
        results = []

        # Ensure all categories exist
        for category in categories:
            if category not in parsed_pipfile:
                parsed_pipfile[category] = {}

        # Process all packages
        for package_data in packages_data:
            if isinstance(package_data, tuple) and len(package_data) == 2:
                package, pip_line = package_data

                # Generate entry for this package
                name, normalized_name, entry = self.generate_package_pipfile_entry(package, pip_line, category=categories[0])

                # Add to each specified category
                for category in categories:
                    newly_added = False

                    # Remove any existing entries with different casing
                    section = parsed_pipfile.get(category, {})
                    for entry_name in section.copy().keys():
                        if entry_name.lower() == normalized_name.lower():
                            del parsed_pipfile[category][entry_name]

                    # Check if this is a new package
                    if normalized_name not in parsed_pipfile[category]:
                        newly_added = True

                    # Add the package
                    parsed_pipfile[category][normalized_name] = entry
                    results.append((newly_added, category, normalized_name))

            elif isinstance(package_data, dict):
                # Handle pre-processed package data
                name = package_data.get("name")
                normalized_name = package_data.get("normalized_name")
                entry = package_data.get("entry")

                if name and normalized_name and entry:
                    for category in categories:
                        newly_added = False

                        # Remove any existing entries with different casing
                        section = parsed_pipfile.get(category, {})
                        for entry_name in section.copy().keys():
                            if entry_name.lower() == normalized_name.lower():
                                del parsed_pipfile[category][entry_name]

                        # Check if this is a new package
                        if normalized_name not in parsed_pipfile[category]:
                            newly_added = True

                        # Add the package
                        parsed_pipfile[category][normalized_name] = entry
                        results.append((newly_added, category, normalized_name))

        # Sort categories if requested
        if self.settings.get("sort_pipfile"):
            for category in categories:
                if category in parsed_pipfile:
                    parsed_pipfile[category] = self._sort_category(parsed_pipfile[category])

        # Write Pipfile once at the end
        self.write_toml(parsed_pipfile)
        return results

    def src_name_from_url(self, index_url):
        location = urllib.parse.urlsplit(index_url).netloc
        if "." in location:
            name, _, tld_guess = location.rpartition(".")
        else:
            name = location
        src_name = name.replace(".", "").replace(":", "")
        try:
            self.get_source(name=src_name)
        except SourceNotFound:
            name = src_name
        else:
            from random import randint

            name = f"{src_name}-{randint(1, 1000)}"
        return name

    def add_index_to_pipfile(self, index, verify_ssl=True):
        """
        Adds a given index to the Pipfile if it doesn't already exist.
        Returns the source name regardless of whether it was newly added or already existed.

        Raises PipenvUsageError if the index is not a valid URL and doesn't exist
        as a named source in the Pipfile.
        """
        from pipenv.exceptions import PipenvUsageError

        # Read and append Pipfile.
        p = self.parsed_pipfile
        source = None

        # Try to find existing source by URL or name
        try:
            source = self.get_source(url=index)
        except SourceNotFound:
            with contextlib.suppress(SourceNotFound):
                source = self.get_source(name=index)

        # If we found an existing source with a name, return it
        if source is not None and source.get("name"):
            return source["name"]

        # Check if the URL already exists in any source
        if "source" in p:
            for existing_source in p["source"]:
                if existing_source.get("url") == index:
                    return existing_source.get("name")

        # If we reach here, the source doesn't exist - validate it's a valid URL
        if not is_valid_url(index):
            available_sources = ", ".join(f"'{s.get('name')}'" for s in self.sources if s.get("name"))
            raise PipenvUsageError(
                f"Index '{index}' was not found in Pipfile sources and is not a valid URL.\n"
                f"Available sources: {available_sources or 'none'}\n"
                f"Hint: Use a valid URL or add the index to your Pipfile [[source]] section."
            )

        # Create and add the new source
        source = {
            "url": index,
            "verify_ssl": verify_ssl,
            "name": self.src_name_from_url(index),
        }

        # Add the source to the group
        if "source" not in p:
            p["source"] = [tomlkit.item(source)]
        else:
            p["source"].append(tomlkit.item(source))

        # Write Pipfile
        self.write_toml(p)
        return source["name"]

    def recase_pipfile(self):
        if self.ensure_proper_casing():
            self.write_toml(self.parsed_pipfile)

    def load_lockfile(self, expand_env_vars=True):
        lockfile_modified = False
        lockfile_path = Path(self.lockfile_location)
        pipfile_path = Path(self.pipfile_location)

        try:
            with lockfile_path.open(encoding="utf-8") as lock:
                try:
                    j = json.load(lock)
                    self._lockfile_newlines = preferred_newlines(lock)
                except JSONDecodeError as e:
                    raise LockfileCorruptException(str(lockfile_path)) from e
        except FileNotFoundError:
            j = {}

        if not j.get("_meta"):
            if pipfile_path.exists():
                with pipfile_path.open() as pf:
                    default_lockfile = plette.Lockfile.with_meta_from(plette.Pipfile.load(pf), categories=[])
                    j["_meta"] = default_lockfile._data["_meta"]
                    lockfile_modified = True
            else:
                # No Pipfile available; provide minimal _meta so callers
                # don't break.  This can happen when only pylock.toml exists.
                j["_meta"] = {
                    "hash": {"sha256": ""},
                    "pipfile-spec": 6,
                    "requires": {},
                    "sources": [],
                }
                lockfile_modified = True

        if j.get("default") is None:
            j["default"] = {}
            lockfile_modified = True

        if j.get("develop") is None:
            j["develop"] = {}
            lockfile_modified = True

        if lockfile_modified:
            self.write_lockfile(j)

        if expand_env_vars:
            # Expand environment variables in Pipfile.lock at runtime.
            # Use expand_url_credentials() so that passwords with special
            # characters are URL-encoded after expansion (#4868).
            for i, _ in enumerate(j["_meta"].get("sources", {})):
                j["_meta"]["sources"][i]["url"] = expand_url_credentials(j["_meta"]["sources"][i]["url"])

        return j

    def get_lockfile_hash(self):
        lockfile_path = Path(self.lockfile_location)
        if not lockfile_path.exists():
            return

        try:
            lockfile = self.load_lockfile(expand_env_vars=False)
        except LockfileCorruptException:
            # Lockfile corrupted
            return ""
        if "_meta" in lockfile and hasattr(lockfile, "keys"):
            return lockfile["_meta"].get("hash", {}).get("sha256") or ""
        # Lockfile exists but has no hash at all
        return ""

    def calculate_pipfile_hash(self):
        """Compute a SHA-256 hash of the Pipfile that is stable regardless of
        package-name casing or separator style (PEP 503 / #4699).

        ``Sphinx`` and ``sphinx``, ``my_pkg`` and ``my-pkg``, etc. all hash to
        the same value so that minor edits to a Pipfile that don't change the
        resolved environment don't trigger unnecessary re-locks.

        The hash algorithm mirrors plette's ``Pipfile.get_hash()`` exactly,
        except that every package-name key in ``[packages]``, ``[dev-packages]``
        and any custom categories is replaced by its PEP 503 canonical form
        before serialisation.
        """
        import hashlib
        import json

        from pipenv.patched.pip._vendor.packaging.utils import canonicalize_name

        _PIPFILE_SECTIONS = frozenset(
            (
                "source",
                "packages",
                "dev-packages",
                "requires",
                "scripts",
                "pipfile",
                "pipenv",
            )
        )

        def _normalize_section(section):
            """Return a new dict with all keys canonicalized (PEP 503)."""
            return {canonicalize_name(k): v for k, v in section.items()}

        with open(self.pipfile_location) as pf:
            p = plette.Pipfile.load(pf)

        raw = p._data
        data = {
            "_meta": {
                "sources": raw.get("source", {}),
                "requires": raw.get("requires", {}),
            },
            "default": _normalize_section(raw.get("packages", {})),
            "develop": _normalize_section(raw.get("dev-packages", {})),
        }
        for category, values in raw.items():
            if category in _PIPFILE_SECTIONS or category in (
                "default",
                "develop",
                "pipenv",
            ):
                continue
            data[category] = _normalize_section(values)

        content = json.dumps(data, sort_keys=True, separators=(",", ":"))
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def ensure_proper_casing(self):
        """Ensures proper casing of Pipfile packages"""
        pfile = self.parsed_pipfile
        casing_changed = self.proper_case_section(pfile.get("packages", {}))
        casing_changed |= self.proper_case_section(pfile.get("dev-packages", {}))
        return casing_changed

    def proper_case_section(self, section):
        """Verify proper casing is retrieved, when available, for each
        dependency in the section.
        """
        # Casing for section.
        changed_values = False
        unknown_names = [k for k in section if k not in set(self.proper_names)]
        # Replace each package with proper casing.
        for dep in unknown_names:
            try:
                # Get new casing for package name.
                new_casing = proper_case(dep)
            except OSError:
                # Unable to normalize package name.
                continue

            if new_casing != dep:
                changed_values = True
                self.register_proper_name(new_casing)
                # Replace old value with new value.
                old_value = section[dep]
                section[new_casing] = old_value
                del section[dep]
        # Return whether or not values have been changed.
        return changed_values

    @cached_property
    def finders(self):
        pass

    @property
    def finder(self):
        return next(iter(self.finders), None)

    def which(self, search):
        find = operator.methodcaller("which", search)
        result = next(iter(filter(None, (find(finder) for finder in self.finders))), None)
        if not result:
            result = self._which(search)
        return result

    def python(self, system=False) -> str:
        """Path to the project python"""
        from pipenv.utils.shell import project_python

        return project_python(self, system=system)

    def _which(self, command, location=None, allow_global=False):
        if not allow_global and location is None:
            if self.virtualenv_exists:
                location = self.virtualenv_location
            else:
                location = os.environ.get("VIRTUAL_ENV", None)

        location_path = Path(location) if location else None

        if not (location_path and location_path.exists()) and not allow_global:
            raise RuntimeError("location not created nor specified")

        version_str = f"python{'.'.join([str(v) for v in sys.version_info[:2]])}"
        is_python = command in ("python", Path(sys.executable).name, version_str)

        if not allow_global:
            scripts_location = virtualenv_scripts_dir(location_path)

            if os.name == "nt":
                p = find_windows_executable(str(scripts_location), command)
                # Convert to Path object if it's a string
                p = Path(p) if isinstance(p, str) else p
            else:
                p = scripts_location / command
        elif is_python:
            p = Path(sys.executable)
        else:
            p = None

        if p is None or not p.exists():
            if is_python:
                p = Path(sys.executable) if sys.executable else Path(system_which("python"))
            else:
                p = Path(system_which(command)) if system_which(command) else None

        return p
