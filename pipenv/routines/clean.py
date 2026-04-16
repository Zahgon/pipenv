import sys

from pipenv.patched.pip._internal.build_env import get_runnable_pip
from pipenv.routines.lock import do_lock
from pipenv.utils import console, err
from pipenv.utils.processes import run_command
from pipenv.utils.project import ensure_project
from pipenv.utils.requirements import BAD_PACKAGES
from pipenv.utils.shell import project_python


def do_clean(
    project,
    python=None,
    dry_run=False,
    bare=False,
    pypi_mirror=None,
    system=False,
):
    # Ensure that virtualenv is available.
    pass


def ensure_lockfile(project, pypi_mirror=None):
    """Ensures that a lockfile exists. If one exists but is out of date, warn
    the user but do NOT re-lock -- ``pipenv clean`` should use the current
    Pipfile.lock as-is.  Only create a new lock file when none exists at all."""
    pass
