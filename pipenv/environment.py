from __future__ import annotations

import contextlib
import importlib.metadata as importlib_metadata
import importlib.util
import json
import os
import site
import sys
import typing
from collections.abc import Iterable
from functools import cached_property
from itertools import chain
from pathlib import Path
from sysconfig import get_paths, get_python_version, get_scheme_names
from urllib.parse import urlparse

import pipenv
from pipenv.patched.pip._internal.commands.install import InstallCommand
from pipenv.patched.pip._internal.index.package_finder import PackageFinder
from pipenv.patched.pip._internal.req.req_install import InstallRequirement
from pipenv.patched.pip._vendor.packaging.markers import UndefinedEnvironmentName
from pipenv.patched.pip._vendor.packaging.specifiers import SpecifierSet
from pipenv.patched.pip._vendor.packaging.utils import canonicalize_name
from pipenv.patched.pip._vendor.packaging.version import Version
from pipenv.patched.pip._vendor.packaging.version import parse as parse_version
from pipenv.utils import console
from pipenv.utils.fileutils import normalize_path, temp_path
from pipenv.utils.funktools import chunked, unnest
from pipenv.utils.indexes import prepare_pip_source_args
from pipenv.utils.processes import subprocess_run
from pipenv.utils.shell import temp_environ
from pipenv.utils.virtualenv import virtualenv_scripts_dir
from pipenv.vendor.pipdeptree._models.dag import PackageDAG
from pipenv.vendor.pipdeptree._models.package import InvalidRequirementError
from pipenv.vendor.pythonfinder.utils import is_in_path

if typing.TYPE_CHECKING:
    from types import ModuleType
    from typing import ContextManager, Generator

    from pipenv.project import Project, TPipfile, TSource
    from pipenv.vendor import tomlkit

BASE_WORKING_SET = importlib_metadata.distributions()


class Environment:
    def __init__(
        self,
        prefix: str | None = None,
        python: str | None = None,
        is_venv: bool = False,
        base_working_set: list[importlib_metadata.Distribution] = None,
        pipfile: tomlkit.toml_document.TOMLDocument | TPipfile | None = None,
        sources: list[TSource] | None = None,
        project: Project | None = None,
    ):
        super().__init__()
        self._modules = {"pipenv": pipenv}
        self.base_working_set = base_working_set if base_working_set else BASE_WORKING_SET
        prefix = normalize_path(prefix)
        self._python = None
        if python is not None:
            self._python = Path(python).absolute().as_posix()
        self.is_venv = is_venv or prefix != normalize_path(sys.prefix)
        if not sources:
            sources = []
        self.project = project
        if project and not sources:
            sources = project.sources
        self.sources = sources
        if project and not pipfile:
            pipfile = project.parsed_pipfile
        self.pipfile = pipfile
        self.extra_dists = []
        if self.is_venv and prefix is not None and not Path(prefix).exists():
            return
        self.prefix = Path(prefix if prefix else sys.prefix)
        self._base_paths = {}
        if self.is_venv:
            self._base_paths = self.get_paths()
        self.sys_paths = get_paths()

    def safe_import(self, name: str) -> ModuleType:
        """Helper utility for reimporting previously imported modules while inside the env"""
        pass

    @cached_property
    def python_version(self) -> str | None:
        with self.activated() as active:
            if active:
                # Extract version parts
                version_str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
                python_version = Version(version_str)  # Create PEP 440 compliant version
                return str(python_version)  # Return the string representation
            else:
                return None

    @property
    def python_info(self) -> dict[str, str]:
        pass

    def _replace_parent_version(self, path: str, replace_version: str) -> str:
        pass

    @cached_property
    def install_scheme(self):
        pass

    @cached_property
    def base_paths(self) -> dict[str, str]:
        """
        Returns the context appropriate paths for the environment.

        :return: A dictionary of environment specific paths to be used for installation operations
        :rtype: dict

        .. note:: The implementation of this is borrowed from a combination of pip and
           virtualenv and is likely to change at some point in the future.

        {'PATH': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW/bin::/bin:/usr/bin',
        'PYTHONPATH': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW/lib/python3.7/site-packages',
        'data': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW',
        'include': '/home/hawk/.pyenv/versions/3.7.1/include/python3.7m',
        'libdir': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW/lib/python3.7/site-packages',
        'platinclude': '/home/hawk/.pyenv/versions/3.7.1/include/python3.7m',
        'platlib': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW/lib/python3.7/site-packages',
        'platstdlib': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW/lib/python3.7',
        'prefix': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW',
        'purelib': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW/lib/python3.7/site-packages',
        'scripts': '/home/hawk/.virtualenvs/pipenv-MfOPs1lW/bin',
        'stdlib': '/home/hawk/.pyenv/versions/3.7.1/lib/python3.7'}
        """
        pass

    @cached_property
    def script_basedir(self) -> str:
        """Path to the environment scripts dir"""
        pass

    @property
    def python(self) -> str:
        """Path to the environment python"""
        if self._python is None:
            self._python = (
                (virtualenv_scripts_dir(self.prefix) / "python").absolute().as_posix()
            )

        return self._python

    @cached_property
    def sys_path(self) -> list[str]:
        """
        The system path inside the environment

        :return: The :data:`sys.path` from the environment
        :rtype: list
        """
        pass

    def build_command(
        self,
        python_lib: bool = False,
        python_inc: bool = False,
        scripts: bool = False,
        py_version: bool = False,
    ) -> str:
        """Build the text for running a command in the given environment

        :param python_lib: Whether to include the python lib dir commands, defaults to False
        :type python_lib: bool, optional
        :param python_inc: Whether to include the python include dir commands, defaults to False
        :type python_inc: bool, optional
        :param scripts: Whether to include the scripts directory, defaults to False
        :type scripts: bool, optional
        :param py_version: Whether to include the python version info, defaults to False
        :type py_version: bool, optional
        :return: A string representing the command to run
        """
        pylib_lines = []
        pyinc_lines = []
        py_command = (
            "import sysconfig, json; paths = {%s};"
            "value = u'{0}'.format(json.dumps(paths)); print(value)"
        )
        sysconfig_line = "sysconfig.get_path('{0}')"

        if python_lib:
            pylib_lines += [
                f"u'{key}': u'{{0}}'.format({sysconfig_line.format(key)})"
                for key in ("purelib", "platlib", "stdlib", "platstdlib")
            ]
        if python_inc:
            pyinc_lines += [
                f"u'{key}': u'{{0}}'.format({sysconfig_line.format(key)})"
                for key in ("include", "platinclude")
            ]
        lines = pylib_lines + pyinc_lines
        if scripts:
            lines.append(
                "u'scripts': u'{{0}}'.format({})".format(sysconfig_line.format("scripts"))
            )
        if py_version:
            lines.append(
                "u'py_version_short': u'{0}'.format(sysconfig.get_python_version()),"
            )
        lines_as_str = ",".join(lines)
        py_command = py_command % lines_as_str
        return py_command

    def get_paths(self) -> dict[str, str] | None:
        """
        Get the paths for the environment by running a subcommand

        :return: The python paths for the environment
        :rtype: Dict[str, str]
        """
        py_command = self.build_command(
            python_lib=True, python_inc=True, scripts=True, py_version=True
        )
        command = [self.python, "-c", py_command]
        c = subprocess_run(command)
        if c.returncode == 0:
            paths = json.loads(c.stdout)
            if "purelib" in paths:
                paths["libdir"] = paths["purelib"] = Path(paths["purelib"])
            for key in (
                "platlib",
                "scripts",
                "platstdlib",
                "stdlib",
                "include",
                "platinclude",
            ):
                if key in paths:
                    paths[key] = Path(paths[key])
            return paths
        else:
            console.print(f"Failed to load paths: {c.stderr}", style="yellow")
            console.print(f"Output: {c.stdout}", style="yellow")
        return None

    def get_lib_paths(self) -> dict[str, str]:
        """Get the include path for the environment

        :return: The python include path for the environment
        :rtype: Dict[str, str]
        """
        pass

    def get_include_path(self) -> dict[str, str] | None:
        """Get the include path for the environment

        :return: The python include path for the environment
        :rtype: Dict[str, str]
        """
        pass

    @cached_property
    def sys_prefix(self) -> str:
        """
        The prefix run inside the context of the environment

        :return: The python prefix inside the environment
        :rtype: :data:`sys.prefix`
        """
        pass

    @cached_property
    def paths(self) -> dict[str, str]:
        pass

    @property
    def scripts_dir(self) -> str:
        pass

    @property
    def libdir(self) -> str:
        pass

    def expand_egg_links(self) -> None:
        """
        Expand paths specified in egg-link files to prevent pip errors during
        reinstall
        """
        pass

    def get_distributions(self) -> Generator[importlib_metadata.Distribution, None, None]:
        """
        Retrieves the distributions installed on the library path of the environment

        :return: A set of distributions found on the library path
        :rtype: iterator
        """

        libdirs = self.base_paths["libdirs"]
        for libdir in libdirs:
            dists = importlib_metadata.distributions(path=[str(libdir)])
            yield from dists

    def find_egg(self, egg_dist: importlib_metadata.Distribution) -> str:
        """Find an egg by name in the given environment"""
        site_packages = self.libdir[1]
        search_filename = f"{egg_dist._normalized_name}.egg-link"
        try:
            user_site = site.getusersitepackages()
        except AttributeError:
            user_site = site.USER_SITE
        search_locations = [site_packages, user_site]
        for site_directory in search_locations:
            egg = os.path.join(site_directory, search_filename)
            if os.path.isfile(egg):
                return egg

    def locate_dist(self, dist: importlib_metadata.Distribution) -> str:
        """Given a distribution, try to find a corresponding egg link first.

        If the egg - link doesn 't exist, return the supplied distribution."""

        location = self.find_egg(dist)
        return location or dist._path

    def dist_is_in_project(self, dist: importlib_metadata.Distribution) -> bool:
        """Determine whether the supplied distribution is in the environment."""
        libdirs = self.base_paths["libdirs"]
        location = Path(self.locate_dist(dist))

        if not location:
            return False

        # Since is_relative_to is not available in Python 3.8, we use a workaround
        if sys.version_info < (3, 9):
            location_str = str(location)
            return any(location_str.startswith(str(libdir)) for libdir in libdirs)
        else:
            return any(location.is_relative_to(libdir) for libdir in libdirs)

    def get_installed_packages(self) -> list[importlib_metadata.Distribution]:
        """Returns all of the installed packages in a given environment"""
        workingset = self.get_working_set()
        packages = [
            pkg
            for pkg in workingset
            if self.dist_is_in_project(pkg) and pkg._normalized_name != "python"
        ]
        return packages

    @contextlib.contextmanager
    def get_finder(self, pre: bool = False) -> ContextManager[PackageFinder]:
        from .utils.resolver import get_package_finder

        pip_command = InstallCommand(
            name="InstallCommand", summary="pip Install command."
        )
        pip_args = prepare_pip_source_args(self.sources)
        pip_options, _ = pip_command.parser.parse_args(pip_args)
        pip_options.cache_dir = self.project.s.PIPENV_CACHE_DIR
        pip_options.pre = self.pipfile.get("pre", pre)
        keyring_provider = self.project.s.PIPENV_KEYRING_PROVIDER
        if keyring_provider:
            pip_options.keyring_provider = keyring_provider
        session = pip_command._build_session(pip_options)
        finder = get_package_finder(
            install_cmd=pip_command, options=pip_options, session=session
        )
        yield finder

    def get_package_info(
        self, pre: bool = False
    ) -> Generator[importlib_metadata.Distribution, None, None]:
        packages = self.get_installed_packages()

        with self.get_finder() as finder:
            for dist in packages:
                name = dist._normalized_name
                all_candidates = finder.find_all_candidates(name)
                allow_prereleases = self.pipfile.get("pre", False)
                if not allow_prereleases and finder.release_control is not None:
                    allow_prereleases = finder.release_control.allows_prereleases(
                        canonicalize_name(name)
                    )
                if not allow_prereleases:
                    # Remove prereleases
                    all_candidates = [
                        candidate
                        for candidate in all_candidates
                        if not candidate.version.is_prerelease
                    ]

                if not all_candidates:
                    continue
                candidate_evaluator = finder.make_candidate_evaluator(project_name=name)
                best_candidate_result = candidate_evaluator.compute_best_candidate(
                    all_candidates
                )
                remote_version = parse_version(
                    str(best_candidate_result.best_candidate.version)
                )
                if best_candidate_result.best_candidate.link.is_wheel:
                    pass
                else:
                    pass
                # This is dirty but makes the rest of the code much cleaner
                dist.latest_version = remote_version
                yield dist

    def get_outdated_packages(
        self, pre: bool = False
    ) -> list[importlib_metadata.Distribution]:
        return [
            pkg
            for pkg in self.get_package_info(pre=pre)
            if pkg.latest_version > parse_version(pkg.version)
        ]

    @classmethod
    def _get_requirements_for_package(cls, node, key_tree, parent=None, chain=None):
        if chain is None:
            chain = [node.project_name]

        d = node.as_dict()
        if parent:
            d["required_version"] = node.version_spec if node.version_spec else "Any"
        else:
            d["required_version"] = d["installed_version"]

        get_children = lambda n: key_tree.get(n.key, [])  # noqa

        d["dependencies"] = [
            cls._get_requirements_for_package(
                c, key_tree, parent=node, chain=chain + [c.project_name]
            )
            for c in get_children(node)
            if c.project_name not in chain
        ]

        return d

    def get_package_requirements(self, pkg=None):
        flatten = chain.from_iterable

        packages = self.get_installed_packages()
        if pkg:
            packages = [p for p in packages if p._normalized_name == pkg]

        try:
            tree = PackageDAG.from_pkgs(packages)
        except InvalidRequirementError as e:
            console.print(f"Invalid requirement: {e}", style="yellow")
            tree = PackageDAG({})
        except UndefinedEnvironmentName:
            # Handle the case when 'extra' environment variable is not defined
            tree = PackageDAG({})
        except Exception as e:
            # Handle any other exceptions that may occur during PackageDAG initialization
            console.print(f"Failed to create PackageDAG: {e}", style="yellow")
            tree = PackageDAG({})

        tree = tree.sort()
        branch_keys = {r.project_name for r in flatten(tree.values())}
        if pkg is None:
            nodes = [p for p in tree if p.project_name not in branch_keys]
        else:
            nodes = [p for p in tree if p.project_name == pkg]
        key_tree = {k.project_name: v for k, v in tree.items()}

        return [self._get_requirements_for_package(p, key_tree) for p in nodes]

    @classmethod
    def reverse_dependency(cls, node):
        new_node = {
            "package_name": node["package_name"],
            "installed_version": node["installed_version"],
            "required_version": node["required_version"],
        }
        for dependency in node.get("dependencies", []):
            for dep in cls.reverse_dependency(dependency):
                new_dep = dep.copy()
                new_dep["parent"] = (node["package_name"], node["installed_version"])
                yield new_dep
        yield new_node

    def reverse_dependencies(self):
        rdeps = {}
        for req in self.get_package_requirements():
            for d in self.reverse_dependency(req):
                parents = None
                name = d["package_name"]
                pkg = {
                    name: {
                        "installed": d["installed_version"],
                        "required": d["required_version"],
                    }
                }
                parents = tuple(d.get("parent", ()))
                pkg[name]["parents"] = parents
                if rdeps.get(name):
                    if not (rdeps[name].get("required") or rdeps[name].get("installed")):
                        rdeps[name].update(pkg[name])
                    rdeps[name]["parents"] = rdeps[name].get("parents", ()) + parents
                else:
                    rdeps[name] = pkg[name]
        for k in list(rdeps.keys()):
            entry = rdeps[k]
            if entry.get("parents"):
                rdeps[k]["parents"] = {
                    p for p, version in chunked(2, unnest(entry["parents"]))
                }
        return rdeps

    def get_working_set(self) -> Iterable:
        """Retrieve the working set of installed packages for the environment."""
        if not hasattr(self, "sys_path"):
            return []
        return importlib_metadata.distributions(path=self.sys_path)

    def is_installed(self, pkgname):
        """Given a package name, returns whether it is installed in the environment

        :param str pkgname: The name of a package
        :return: Whether the supplied package is installed in the environment
        :rtype: bool
        """
        pass

    def is_satisfied(self, req: InstallRequirement):
        match = next(
            iter(
                d
                for d in self.get_distributions()
                if req.name
                and canonicalize_name(d._normalized_name) == canonicalize_name(req.name)
            ),
            None,
        )
        if match is not None:
            # For VCS dependencies (editable or not), we cannot reliably determine
            # if the installed version matches the requested ref/commit. Always return
            # False to force reinstall, which will ensure the correct commit is checked out.
            # See: https://github.com/pypa/pipenv/issues/5791
            if req.link and req.link.is_vcs:
                return False
            if req.specifier is not None:
                return SpecifierSet(str(req.specifier)).contains(
                    match.version, prereleases=True
                )
            if req.link is None:
                return True
            elif req.editable and req.link.is_file:
                requested_path = req.link.file_path
                if os.path.exists(requested_path):
                    local_path = requested_path
                else:
                    parsed_url = urlparse(requested_path)
                    local_path = parsed_url.path
                return requested_path and os.path.samefile(local_path, match.location)
            elif match.has_metadata("direct_url.json"):
                # Direct URL installs we assume are not satisfied since we may be
                # installing from Pipfile and have insufficient information to determine
                # if the content has changed.
                return False
            return True
        return False

    def run_activate_this(self):
        """Runs the environment's inline activation script"""
        pass

    @contextlib.contextmanager
    def activated(self):
        """Helper context manager to activate the environment.

        This context manager will set the following variables for the duration
        of its activation:

            * sys.prefix
            * sys.path
            * os.environ["VIRTUAL_ENV"]
            * os.environ["PATH"]

        In addition, it will make any distributions passed into `extra_dists` available
        on `sys.path` while inside the context manager, as well as making `passa` itself
        available.

        The environment's `prefix` as well as `scripts_dir` properties are both prepended
        to `os.environ["PATH"]` to ensure that calls to `~Environment.run()` use the
        environment's path preferentially.
        """

        # Fail if the virtualenv is needed but cannot be found
        if self.is_venv and (
            hasattr(self, "prefix")
            and not self.prefix.exists()
            or not hasattr(self, "prefix")
        ):
            yield False
            return

        original_path = sys.path
        original_prefix = sys.prefix
        prefix = self.prefix.as_posix()
        with temp_environ(), temp_path():
            os.environ["PATH"] = os.pathsep.join(
                [
                    self.script_basedir,
                    self.prefix.as_posix(),
                    os.environ.get("PATH", ""),
                ]
            )
            os.environ["PYTHONIOENCODING"] = "utf-8"
            os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
            if self.is_venv:
                os.environ["PYTHONPATH"] = self.base_paths["PYTHONPATH"]
                os.environ["VIRTUAL_ENV"] = prefix
            elif not self.project.s.PIPENV_USE_SYSTEM and not os.environ.get(
                "VIRTUAL_ENV"
            ):
                os.environ["PYTHONPATH"] = self.base_paths["PYTHONPATH"]
                os.environ.pop("PYTHONHOME", None)
            sys.path = self.sys_path
            sys.prefix = self.sys_prefix
            try:
                yield True
            finally:
                sys.path = original_path
                sys.prefix = original_prefix
