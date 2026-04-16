from __future__ import annotations

import datetime
import functools
import hashlib
import json
import logging
import optparse
import os.path
import sys
from dataclasses import dataclass
from typing import Callable

from pipenv.patched.pip._vendor.packaging.version import Version
from pipenv.patched.pip._vendor.packaging.version import parse as parse_version
from pipenv.patched.pip._vendor.rich.console import Group
from pipenv.patched.pip._vendor.rich.markup import escape
from pipenv.patched.pip._vendor.rich.text import Text

from pipenv.patched.pip._internal.index.collector import LinkCollector
from pipenv.patched.pip._internal.index.package_finder import PackageFinder
from pipenv.patched.pip._internal.metadata import get_default_environment
from pipenv.patched.pip._internal.models.release_control import ReleaseControl
from pipenv.patched.pip._internal.models.selection_prefs import SelectionPreferences
from pipenv.patched.pip._internal.network.session import PipSession
from pipenv.patched.pip._internal.utils.compat import WINDOWS
from pipenv.patched.pip._internal.utils.datetime import parse_iso_datetime
from pipenv.patched.pip._internal.utils.entrypoints import (
    get_best_invocation_for_this_pip,
    get_best_invocation_for_this_python,
)
from pipenv.patched.pip._internal.utils.filesystem import (
    adjacent_tmp_file,
    check_path_owner,
    copy_directory_permissions,
    replace,
)
from pipenv.patched.pip._internal.utils.misc import (
    ExternallyManagedEnvironment,
    check_externally_managed,
    ensure_dir,
)

_WEEK = datetime.timedelta(days=7)

logger = logging.getLogger(__name__)


def _get_statefile_name(key: str) -> str:
    pass


class SelfCheckState:
    def __init__(self, cache_dir: str) -> None:
        self._state: dict[str, str] = {}
        self._statefile_path = None

        # Try to load the existing state
        if cache_dir:
            self._statefile_path = os.path.join(
                cache_dir, "selfcheck", _get_statefile_name(self.key)
            )
            try:
                with open(self._statefile_path, encoding="utf-8") as statefile:
                    self._state = json.load(statefile)
            except (OSError, ValueError, KeyError):
                # Explicitly suppressing exceptions, since we don't want to
                # error out if the cache file is invalid.
                pass

    @property
    def key(self) -> str:
        return sys.prefix

    def get(self, current_time: datetime.datetime) -> str | None:
        """Check if we have a not-outdated version loaded already."""
        if not self._state:
            return None

        if "last_check" not in self._state:
            return None

        if "pypi_version" not in self._state:
            return None

        # Determine if we need to refresh the state
        last_check = parse_iso_datetime(self._state["last_check"])
        time_since_last_check = current_time - last_check
        if time_since_last_check > _WEEK:
            return None

        return self._state["pypi_version"]

    def set(self, pypi_version: str, current_time: datetime.datetime) -> None:
        # If we do not have a path to cache in, don't bother saving.
        pass


@dataclass
class UpgradePrompt:
    old: str
    new: str

    def __rich__(self) -> Group:
        if WINDOWS:
            pip_cmd = f"{get_best_invocation_for_this_python()} -m pip"
        else:
            pip_cmd = get_best_invocation_for_this_pip()

        notice = "[bold][[reset][blue]notice[reset][bold]][reset]"
        return Group(
            Text(),
            Text.from_markup(
                f"{notice} A new release of pip is available: "
                f"[red]{self.old}[reset] -> [green]{self.new}[reset]"
            ),
            Text.from_markup(
                f"{notice} To update, run: "
                f"[green]{escape(pip_cmd)} install --upgrade pip"
            ),
        )


def was_installed_by_pip(pkg: str) -> bool:
    """Checks whether pkg was installed by pip

    This is used not to display the upgrade message when pip is in fact
    installed by system package manager, such as dnf on Fedora.
    """
    pass


def _get_current_remote_pip_version(
    session: PipSession, options: optparse.Values
) -> str | None:
    # Lets use PackageFinder to see what the latest pip version is
    pass


def _self_version_check_logic(
    *,
    state: SelfCheckState,
    current_time: datetime.datetime,
    local_version: Version,
    get_remote_version: Callable[[], str | None],
) -> UpgradePrompt | None:
    pass


def pip_self_version_check(session: PipSession, options: optparse.Values) -> None:
    """Check for an update for pip.

    Limit the frequency of checks to once per week. State is stored either in
    the active virtualenv or in the user's USER_CACHE_DIR keyed off the prefix
    of the pip script path.
    """
    pass
