import shutil
import sys

from pipenv import exceptions
from pipenv.patched.pip._internal.build_env import get_runnable_pip
from pipenv.project import Project
from pipenv.routines.lock import do_lock
from pipenv.utils import console
from pipenv.utils.dependencies import (
    expansive_install_req_from_line,
    get_lockfile_section_using_pipfile_category,
    get_pipfile_category_using_lockfile_section,
    pep423_name,
)
from pipenv.utils.processes import run_command, subprocess_run
from pipenv.utils.requirements import BAD_PACKAGES
from pipenv.utils.resolver import venv_resolve_deps
from pipenv.utils.shell import cmd_list_to_shell, project_python


def _uninstall_from_environment(project: Project, package, system=False):
    # Execute the uninstall command for the package
    pass


def do_uninstall(
    project: Project,
    packages=None,
    editable_packages=None,
    python=False,
    system=False,
    lock=False,
    all_dev=False,
    all=False,
    pre=False,
    pypi_mirror=None,
    ctx=None,
    categories=None,
):
    # Initialization similar to the upgrade function
    pass


def do_purge(project, bare=False, downloads=False, allow_global=False):
    """Executes the purge functionality."""
    pass
