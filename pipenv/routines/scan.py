import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from pipenv import pep508checker
from pipenv.utils import Confirm, console, err
from pipenv.utils.processes import run_command
from pipenv.utils.project import ensure_project
from pipenv.utils.shell import project_python
from pipenv.vendor import plette


def build_safety_check_options(
    audit_and_monitor=True,
    exit_code=True,
    output="screen",
    save_json="",
    policy_file="",
    safety_project=None,
    temp_requirements_path="",
    ignore=None,
    key=None,
    db=None,
    project=None,
):
    """Build command line options for the safety check command."""
    pass


def build_safety_scan_options(
    output="screen",
    save_json="",
    policy_file="",
    temp_requirements_path="",
    key=None,
    db=None,
    project=None,
):
    """Build command line options for the safety scan command."""
    pass


def run_pep508_check(project, system, python):
    """Run PEP 508 environment marker checks."""
    pass


def check_pep508_requirements(project, results, quiet):
    """Verify PEP 508 environment markers in Pipfile match the current environment."""
    pass


def get_requirements(project, use_installed, categories):
    """Get package requirements from either installed packages or Pipfile.lock."""
    _cmd = [project_python(project, system=False)]
    if use_installed:
        return run_command(
            _cmd + ["-m", "pip", "list", "--format=freeze"],
            is_verbose=project.s.is_verbose(),
        )
    # Use sys.executable -m pipenv to ensure pipenv is found even if not on PATH
    # See: https://github.com/pypa/pipenv/issues/6042
    elif categories:
        return run_command(
            [sys.executable, "-m", "pipenv", "requirements", "--categories", categories],
            is_verbose=project.s.is_verbose(),
        )
    else:
        return run_command(
            [sys.executable, "-m", "pipenv", "requirements"],
            is_verbose=project.s.is_verbose(),
        )


def create_temp_requirements_file(requirements_content):
    """Create a temporary requirements file for safety to scan.

    Uses the tempfile module to ensure proper cleanup.
    """
    pass


def is_safety_installed(project=None, system=False):
    """Check if safety is installed by trying to run it."""
    pass


def install_safety(project, system=False, auto_install=False):
    """Install safety and its dependencies."""
    pass


def run_safety_scan(cmd, quiet):
    """Run safety scan with the given command."""
    pass


def parse_safety_output(output, quiet):
    """Parse and display safety scan output in a user-friendly format."""
    pass


def do_scan(  # noqa: PLR0913
    project,
    python=False,
    system=False,
    db=None,
    ignore=None,
    output="screen",
    key=None,
    quiet=False,
    verbose=False,
    exit_code=True,
    policy_file="",
    save_json="",
    audit_and_monitor=True,
    safety_project=None,
    pypi_mirror=None,
    use_installed=False,
    categories="",
    legacy_mode=False,
    auto_install=False,
):
    """Run a security vulnerability scan on dependencies.

    This is the new, improved version of the check command.
    """
    pass
