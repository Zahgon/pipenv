"""
shared options and groups

The principle here is to define options once, but *not* instantiate them
globally. One reason being that options with action='append' can carry state
between parses. pip parses general options twice internally, and shouldn't
pass on state. To be consistent, all options will follow this design.
"""

# The following comment should be removed at some point in the future.
# mypy: strict-optional=False
from __future__ import annotations

import logging
import os
import pathlib
import textwrap
from functools import partial
from optparse import SUPPRESS_HELP, Option, OptionGroup, OptionParser, Values
from textwrap import dedent
from typing import Any, Callable

from pipenv.patched.pip._vendor.packaging.utils import canonicalize_name

from pipenv.patched.pip._internal.cli.parser import ConfigOptionParser
from pipenv.patched.pip._internal.exceptions import CommandError
from pipenv.patched.pip._internal.locations import USER_CACHE_DIR, get_src_prefix
from pipenv.patched.pip._internal.models.format_control import FormatControl
from pipenv.patched.pip._internal.models.index import PyPI
from pipenv.patched.pip._internal.models.release_control import ReleaseControl
from pipenv.patched.pip._internal.models.target_python import TargetPython
from pipenv.patched.pip._internal.utils.datetime import parse_iso_datetime
from pipenv.patched.pip._internal.utils.hashes import STRONG_HASHES
from pipenv.patched.pip._internal.utils.misc import strtobool

logger = logging.getLogger(__name__)


def raise_option_error(parser: OptionParser, option: Option, msg: str) -> None:
    """
    Raise an option parsing error using parser.error().

    Args:
      parser: an OptionParser instance.
      option: an Option instance.
      msg: the error text.
    """
    pass


def make_option_group(group: dict[str, Any], parser: ConfigOptionParser) -> OptionGroup:
    """
    Return an OptionGroup object
    group  -- assumed to be dict with 'name' and 'options' keys
    parser -- an optparse Parser
    """
    option_group = OptionGroup(parser, group["name"])
    for option in group["options"]:
        option_group.add_option(option())
    return option_group


def check_dist_restriction(options: Values, check_target: bool = False) -> None:
    """Function for determining if custom platform options are allowed.

    :param options: The OptionParser options.
    :param check_target: Whether or not to check if --target is being used.
    """
    dist_restriction_set = any(
        [
            options.python_version,
            options.platforms,
            options.abis,
            options.implementation,
        ]
    )

    binary_only = FormatControl(set(), {":all:"})
    sdist_dependencies_allowed = (
        options.format_control != binary_only and not options.ignore_dependencies
    )

    # Installations or downloads using dist restrictions must not combine
    # source distributions and dist-specific wheels, as they are not
    # guaranteed to be locally compatible.
    if dist_restriction_set and sdist_dependencies_allowed:
        raise CommandError(
            "When restricting platform and interpreter constraints using "
            "--python-version, --platform, --abi, or --implementation, "
            "either --no-deps must be set, or --only-binary=:all: must be "
            "set and --no-binary must not be set (or must be set to "
            ":none:)."
        )

    if check_target:
        if not options.dry_run and dist_restriction_set and not options.target_dir:
            raise CommandError(
                "Can not use any platform or abi specific options unless "
                "installing via '--target' or using '--dry-run'"
            )


def check_build_constraints(options: Values) -> None:
    """Function for validating build constraints options.

    :param options: The OptionParser options.
    """
    if hasattr(options, "build_constraints") and options.build_constraints:
        if not options.build_isolation:
            raise CommandError(
                "--build-constraint cannot be used with --no-build-isolation."
            )

        # Import here to avoid circular imports
        from pipenv.patched.pip._internal.network.session import PipSession
        from pipenv.patched.pip._internal.req.req_file import get_file_content

        # Eagerly check build constraints file contents
        # is valid so that we don't fail in when trying
        # to check constraints in isolated build process
        with PipSession() as session:
            for constraint_file in options.build_constraints:
                get_file_content(constraint_file, session)


def _path_option_check(option: Option, opt: str, value: str) -> str:
    pass


def _package_name_option_check(option: Option, opt: str, value: str) -> str:
    pass


class PipOption(Option):
    TYPES = Option.TYPES + ("path", "package_name")
    TYPE_CHECKER = Option.TYPE_CHECKER.copy()
    TYPE_CHECKER["package_name"] = _package_name_option_check
    TYPE_CHECKER["path"] = _path_option_check


###########
# options #
###########

help_: Callable[..., Option] = partial(
    Option,
    "-h",
    "--help",
    dest="help",
    action="help",
    help="Show help.",
)

debug_mode: Callable[..., Option] = partial(
    Option,
    "--debug",
    dest="debug_mode",
    action="store_true",
    default=False,
    help=(
        "Let unhandled exceptions propagate outside the main subroutine, "
        "instead of logging them to stderr."
    ),
)

isolated_mode: Callable[..., Option] = partial(
    Option,
    "--isolated",
    dest="isolated_mode",
    action="store_true",
    default=False,
    help=(
        "Run pip in an isolated mode, ignoring environment variables and user "
        "configuration."
    ),
)

require_virtualenv: Callable[..., Option] = partial(
    Option,
    "--require-virtualenv",
    "--require-venv",
    dest="require_venv",
    action="store_true",
    default=False,
    help=(
        "Allow pip to only run in a virtual environment; exit with an error otherwise."
    ),
)

override_externally_managed: Callable[..., Option] = partial(
    Option,
    "--break-system-packages",
    dest="override_externally_managed",
    action="store_true",
    help="Allow pip to modify an EXTERNALLY-MANAGED Python installation",
)

python: Callable[..., Option] = partial(
    Option,
    "--python",
    dest="python",
    help="Run pip with the specified Python interpreter.",
)

verbose: Callable[..., Option] = partial(
    Option,
    "-v",
    "--verbose",
    dest="verbose",
    action="count",
    default=0,
    help="Give more output. Option is additive, and can be used up to 3 times.",
)

no_color: Callable[..., Option] = partial(
    Option,
    "--no-color",
    dest="no_color",
    action="store_true",
    default=False,
    help="Suppress colored output.",
)

version: Callable[..., Option] = partial(
    Option,
    "-V",
    "--version",
    dest="version",
    action="store_true",
    help="Show version and exit.",
)

quiet: Callable[..., Option] = partial(
    Option,
    "-q",
    "--quiet",
    dest="quiet",
    action="count",
    default=0,
    help=(
        "Give less output. Option is additive, and can be used up to 3"
        " times (corresponding to WARNING, ERROR, and CRITICAL logging"
        " levels)."
    ),
)

progress_bar: Callable[..., Option] = partial(
    Option,
    "--progress-bar",
    dest="progress_bar",
    type="choice",
    choices=["auto", "on", "off", "raw"],
    default="auto",
    help=(
        "Specify whether the progress bar should be used. In 'auto'"
        " mode, --quiet will suppress all progress bars."
        " [auto, on, off, raw] (default: auto)"
    ),
)

log: Callable[..., Option] = partial(
    PipOption,
    "--log",
    "--log-file",
    "--local-log",
    dest="log",
    metavar="path",
    type="path",
    help="Path to a verbose appending log.",
)

no_input: Callable[..., Option] = partial(
    Option,
    # Don't ask for input
    "--no-input",
    dest="no_input",
    action="store_true",
    default=False,
    help="Disable prompting for input.",
)

keyring_provider: Callable[..., Option] = partial(
    Option,
    "--keyring-provider",
    dest="keyring_provider",
    choices=["auto", "disabled", "import", "subprocess"],
    default="auto",
    help=(
        "Enable the credential lookup via the keyring library if user input is allowed."
        " Specify which mechanism to use [auto, disabled, import, subprocess]."
        " (default: %default)"
    ),
)

proxy: Callable[..., Option] = partial(
    Option,
    "--proxy",
    dest="proxy",
    type="str",
    default="",
    help="Specify a proxy in the form scheme://[user:passwd@]proxy.server:port.",
)

retries: Callable[..., Option] = partial(
    Option,
    "--retries",
    dest="retries",
    type="int",
    default=5,
    help="Maximum attempts to establish a new HTTP connection. (default: %default)",
)

resume_retries: Callable[..., Option] = partial(
    Option,
    "--resume-retries",
    dest="resume_retries",
    type="int",
    default=5,
    help="Maximum attempts to resume or restart an incomplete download. "
    "(default: %default)",
)

timeout: Callable[..., Option] = partial(
    Option,
    "--timeout",
    "--default-timeout",
    metavar="sec",
    dest="timeout",
    type="float",
    default=15,
    help="Set the socket timeout (default %default seconds).",
)


def exists_action() -> Option:
    pass


cert: Callable[..., Option] = partial(
    PipOption,
    "--cert",
    dest="cert",
    type="path",
    metavar="path",
    help=(
        "Path to PEM-encoded CA certificate bundle. "
        "If provided, overrides the default. "
        "See 'SSL Certificate Verification' in pip documentation "
        "for more information."
    ),
)

client_cert: Callable[..., Option] = partial(
    PipOption,
    "--client-cert",
    dest="client_cert",
    type="path",
    default=None,
    metavar="path",
    help="Path to SSL client certificate, a single file containing the "
    "private key and the certificate in PEM format.",
)

index_url: Callable[..., Option] = partial(
    Option,
    "-i",
    "--index-url",
    "--pypi-url",
    dest="index_url",
    metavar="URL",
    default=PyPI.simple_url,
    help="Base URL of the Python Package Index (default %default). "
    "This should point to a repository compliant with PEP 503 "
    "(the simple repository API) or a local directory laid out "
    "in the same format.",
)


def extra_index_url() -> Option:
    pass


no_index: Callable[..., Option] = partial(
    Option,
    "--no-index",
    dest="no_index",
    action="store_true",
    default=False,
    help="Ignore package index (only looking at --find-links URLs instead).",
)


def find_links() -> Option:
    pass


def _handle_uploaded_prior_to(
    option: Option, opt: str, value: str, parser: OptionParser
) -> None:
    """
    This is an optparse.Option callback for the --uploaded-prior-to option.

    Parses an ISO 8601 datetime string. If no timezone is specified in the string,
    local timezone is used.

    Note: This option only works with indexes that provide upload-time metadata
    as specified in the simple repository API:
    https://packaging.python.org/en/latest/specifications/simple-repository-api/
    """
    pass


def uploaded_prior_to() -> Option:
    pass


def trusted_host() -> Option:
    pass


def constraints() -> Option:
    pass


def build_constraints() -> Option:
    pass


def requirements() -> Option:
    return Option(
        "-r",
        "--requirement",
        dest="requirements",
        action="append",
        default=[],
        metavar="file",
        help="Install from the given requirements file. "
        "This option can be used multiple times.",
    )


def requirements_from_scripts() -> Option:
    pass


def editable() -> Option:
    pass


def _handle_src(option: Option, opt_str: str, value: str, parser: OptionParser) -> None:
    pass


src: Callable[..., Option] = partial(
    PipOption,
    "--src",
    "--source",
    "--source-dir",
    "--source-directory",
    dest="src_dir",
    type="path",
    metavar="dir",
    default=get_src_prefix(),
    action="callback",
    callback=_handle_src,
    help="Directory to check out editable projects into. "
    'The default in a virtualenv is "<venv path>/src". '
    'The default for global installs is "<current dir>/src".',
)


def _get_format_control(values: Values, option: Option) -> Any:
    """Get a format_control object."""
    pass


def _handle_no_binary(
    option: Option, opt_str: str, value: str, parser: OptionParser
) -> None:
    pass


def _handle_only_binary(
    option: Option, opt_str: str, value: str, parser: OptionParser
) -> None:
    pass


def no_binary() -> Option:
    pass


def only_binary() -> Option:
    pass


def _get_release_control(values: Values, option: Option) -> Any:
    """Get a release_control object."""
    pass


def _handle_all_releases(
    option: Option, opt_str: str, value: str, parser: OptionParser
) -> None:
    pass


def _handle_only_final(
    option: Option, opt_str: str, value: str, parser: OptionParser
) -> None:
    pass


def all_releases() -> Option:
    pass


def only_final() -> Option:
    pass


def check_release_control_exclusive(options: Values) -> None:
    """
    Raise an error if --pre is used with --all-releases or --only-final,
    and transform --pre into --all-releases :all: if used alone.
    """
    if not hasattr(options, "pre") or not options.pre:
        return

    release_control = options.release_control
    if release_control.all_releases or release_control.only_final:
        raise CommandError("--pre cannot be used with --all-releases or --only-final.")

    # Transform --pre into --all-releases :all:
    release_control.all_releases.add(":all:")


platforms: Callable[..., Option] = partial(
    Option,
    "--platform",
    dest="platforms",
    metavar="platform",
    action="append",
    default=None,
    help=(
        "Only use wheels compatible with <platform>. Defaults to the "
        "platform of the running system. Use this option multiple times to "
        "specify multiple platforms supported by the target interpreter."
    ),
)


# This was made a separate function for unit-testing purposes.
def _convert_python_version(value: str) -> tuple[tuple[int, ...], str | None]:
    """
    Convert a version string like "3", "37", or "3.7.3" into a tuple of ints.

    :return: A 2-tuple (version_info, error_msg), where `error_msg` is
        non-None if and only if there was a parsing error.
    """
    pass


def _handle_python_version(
    option: Option, opt_str: str, value: str, parser: OptionParser
) -> None:
    """
    Handle a provided --python-version value.
    """
    pass


python_version: Callable[..., Option] = partial(
    Option,
    "--python-version",
    dest="python_version",
    metavar="python_version",
    action="callback",
    callback=_handle_python_version,
    type="str",
    default=None,
    help=dedent(
        """\
    The Python interpreter version to use for wheel and "Requires-Python"
    compatibility checks. Defaults to a version derived from the running
    interpreter. The version can be specified using up to three dot-separated
    integers (e.g. "3" for 3.0.0, "3.7" for 3.7.0, or "3.7.3"). A major-minor
    version can also be given as a string without dots (e.g. "37" for 3.7.0).
    """
    ),
)


implementation: Callable[..., Option] = partial(
    Option,
    "--implementation",
    dest="implementation",
    metavar="implementation",
    default=None,
    help=(
        "Only use wheels compatible with Python "
        "implementation <implementation>, e.g. 'pp', 'jy', 'cp', "
        " or 'ip'. If not specified, then the current "
        "interpreter implementation is used.  Use 'py' to force "
        "implementation-agnostic wheels."
    ),
)


abis: Callable[..., Option] = partial(
    Option,
    "--abi",
    dest="abis",
    metavar="abi",
    action="append",
    default=None,
    help=(
        "Only use wheels compatible with Python abi <abi>, e.g. 'pypy_41'. "
        "If not specified, then the current interpreter abi tag is used. "
        "Use this option multiple times to specify multiple abis supported "
        "by the target interpreter. Generally you will need to specify "
        "--implementation, --platform, and --python-version when using this "
        "option."
    ),
)


def add_target_python_options(cmd_opts: OptionGroup) -> None:
    pass


def make_target_python(options: Values) -> TargetPython:
    target_python = TargetPython(
        platforms=options.platforms,
        py_version_info=options.python_version,
        abis=options.abis,
        implementation=options.implementation,
    )

    return target_python


def prefer_binary() -> Option:
    pass


cache_dir: Callable[..., Option] = partial(
    PipOption,
    "--cache-dir",
    dest="cache_dir",
    default=USER_CACHE_DIR,
    metavar="dir",
    type="path",
    help="Store the cache data in <dir>.",
)


def _handle_no_cache_dir(
    option: Option, opt: str, value: str, parser: OptionParser
) -> None:
    """
    Process a value provided for the --no-cache-dir option.

    This is an optparse.Option callback for the --no-cache-dir option.
    """
    pass


no_cache: Callable[..., Option] = partial(
    Option,
    "--no-cache-dir",
    dest="cache_dir",
    action="callback",
    callback=_handle_no_cache_dir,
    help="Disable the cache.",
)

no_deps: Callable[..., Option] = partial(
    Option,
    "--no-deps",
    "--no-dependencies",
    dest="ignore_dependencies",
    action="store_true",
    default=False,
    help="Don't install package dependencies.",
)


def _handle_dependency_group(
    option: Option, opt: str, value: str, parser: OptionParser
) -> None:
    """
    Process a value provided for the --group option.

    Splits on the rightmost ":", and validates that the path (if present) ends
    in `pyproject.toml`. Defaults the path to `pyproject.toml` when one is not given.

    `:` cannot appear in dependency group names, so this is a safe and simple parse.

    This is an optparse.Option callback for the dependency_groups option.
    """
    pass


dependency_groups: Callable[..., Option] = partial(
    Option,
    "--group",
    dest="dependency_groups",
    default=[],
    type=str,
    action="callback",
    callback=_handle_dependency_group,
    metavar="[path:]group",
    help='Install a named dependency-group from a "pyproject.toml" file. '
    'If a path is given, the name of the file must be "pyproject.toml". '
    'Defaults to using "pyproject.toml" in the current directory.',
)

ignore_requires_python: Callable[..., Option] = partial(
    Option,
    "--ignore-requires-python",
    dest="ignore_requires_python",
    action="store_true",
    help="Ignore the Requires-Python information.",
)


no_build_isolation: Callable[..., Option] = partial(
    Option,
    "--no-build-isolation",
    dest="build_isolation",
    action="store_false",
    default=True,
    help="Disable isolation when building a modern source distribution. "
    "Build dependencies specified by PEP 518 must be already installed "
    "if this option is used.",
)

check_build_deps: Callable[..., Option] = partial(
    Option,
    "--check-build-dependencies",
    dest="check_build_deps",
    action="store_true",
    default=False,
    help="Check the build dependencies.",
)


use_pep517: Any = partial(
    Option,
    "--use-pep517",
    dest="use_pep517",
    action="store_true",
    default=True,
    help=SUPPRESS_HELP,
)


def _handle_config_settings(
    option: Option, opt_str: str, value: str, parser: OptionParser
) -> None:
    pass


config_settings: Callable[..., Option] = partial(
    Option,
    "-C",
    "--config-settings",
    dest="config_settings",
    type=str,
    action="callback",
    callback=_handle_config_settings,
    metavar="settings",
    help="Configuration settings to be passed to the build backend. "
    "Settings take the form KEY=VALUE. Use multiple --config-settings options "
    "to pass multiple keys to the backend.",
)

no_clean: Callable[..., Option] = partial(
    Option,
    "--no-clean",
    action="store_true",
    default=False,
    help="Don't clean up build directories.",
)

pre: Callable[..., Option] = partial(
    Option,
    "--pre",
    action="store_true",
    default=False,
    help="Include pre-release and development versions. By default, "
    "pip only finds stable versions.",
)

json: Callable[..., Option] = partial(
    Option,
    "--json",
    action="store_true",
    default=False,
    help="Output data in a machine-readable JSON format.",
)

disable_pip_version_check: Callable[..., Option] = partial(
    Option,
    "--disable-pip-version-check",
    dest="disable_pip_version_check",
    action="store_true",
    default=False,
    help="Don't periodically check PyPI to determine whether a new version "
    "of pip is available for download. Implied with --no-index.",
)

root_user_action: Callable[..., Option] = partial(
    Option,
    "--root-user-action",
    dest="root_user_action",
    default="warn",
    choices=["warn", "ignore"],
    help="Action if pip is run as a root user [warn, ignore] (default: warn)",
)


def _handle_merge_hash(
    option: Option, opt_str: str, value: str, parser: OptionParser
) -> None:
    """Given a value spelled "algo:digest", append the digest to a list
    pointed to in a dict by the algo name."""
    pass


hash: Callable[..., Option] = partial(
    Option,
    "--hash",
    # Hash values eventually end up in InstallRequirement.hashes due to
    # __dict__ copying in process_line().
    dest="hashes",
    action="callback",
    callback=_handle_merge_hash,
    type="string",
    help="Verify that the package's archive matches this "
    "hash before installing. Example: --hash=sha256:abcdef...",
)


require_hashes: Callable[..., Option] = partial(
    Option,
    "--require-hashes",
    dest="require_hashes",
    action="store_true",
    default=False,
    help="Require a hash to check each requirement against, for "
    "repeatable installs. This option is implied when any package in a "
    "requirements file has a --hash option.",
)


list_path: Callable[..., Option] = partial(
    PipOption,
    "--path",
    dest="path",
    type="path",
    action="append",
    help="Restrict to the specified installation path for listing "
    "packages (can be used multiple times).",
)


def check_list_path_option(options: Values) -> None:
    if options.path and (options.user or options.local):
        raise CommandError("Cannot combine '--path' with '--user' or '--local'")


list_exclude: Callable[..., Option] = partial(
    PipOption,
    "--exclude",
    dest="excludes",
    action="append",
    metavar="package",
    type="package_name",
    help="Exclude specified package from the output",
)


no_python_version_warning: Callable[..., Option] = partial(
    Option,
    "--no-python-version-warning",
    dest="no_python_version_warning",
    action="store_true",
    default=False,
    help=SUPPRESS_HELP,  # No-op, a hold-over from the Python 2->3 transition.
)


# Features that are now always on. A warning is printed if they are used.
ALWAYS_ENABLED_FEATURES = [
    "truststore",  # always on since 24.2
    "no-binary-enable-wheel-cache",  # always on since 23.1
]

use_new_feature: Callable[..., Option] = partial(
    Option,
    "--use-feature",
    dest="features_enabled",
    metavar="feature",
    action="append",
    default=[],
    choices=[
        "fast-deps",
        "build-constraint",
        "inprocess-build-deps",
    ]
    + ALWAYS_ENABLED_FEATURES,
    help="Enable new functionality, that may be backward incompatible.",
)

use_deprecated_feature: Callable[..., Option] = partial(
    Option,
    "--use-deprecated",
    dest="deprecated_features_enabled",
    metavar="feature",
    action="append",
    default=[],
    choices=[
        "legacy-resolver",
        "legacy-certs",
    ],
    help=("Enable deprecated functionality, that will be removed in the future."),
)

##########
# groups #
##########

general_group: dict[str, Any] = {
    "name": "General Options",
    "options": [
        help_,
        debug_mode,
        isolated_mode,
        require_virtualenv,
        python,
        verbose,
        version,
        quiet,
        log,
        no_input,
        keyring_provider,
        proxy,
        retries,
        timeout,
        exists_action,
        trusted_host,
        cert,
        client_cert,
        cache_dir,
        no_cache,
        disable_pip_version_check,
        no_color,
        no_python_version_warning,
        use_new_feature,
        use_deprecated_feature,
        resume_retries,
    ],
}

index_group: dict[str, Any] = {
    "name": "Package Index Options",
    "options": [
        index_url,
        extra_index_url,
        no_index,
        find_links,
        uploaded_prior_to,
    ],
}

package_selection_group: dict[str, Any] = {
    "name": "Package Selection Options",
    "options": [
        pre,
        all_releases,
        only_final,
        no_binary,
        only_binary,
        prefer_binary,
    ],
}
