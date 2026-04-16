import json
import logging
import os
import sys
from pathlib import Path

from pipenv import pep508checker
from pipenv.utils import Confirm, console, err
from pipenv.utils.processes import run_command
from pipenv.utils.project import ensure_project
from pipenv.utils.shell import project_python
from pipenv.vendor import plette


def build_safety_options(
    audit_and_monitor=True,
    exit_code=True,
    output="screen",
    save_json="",
    policy_file="",
    safety_project=None,
    temp_requirements_name="",
    quiet=False,
):
    pass


def run_pep508_check(project, system, python):
    pass


def check_pep508_requirements(project, results, quiet):
    pass


def get_requirements(project, use_installed, categories):
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


def create_temp_requirements(project, requirements, quiet=False):
    """Create a temporary requirements file that safety can access."""
    pass


def is_safety_installed(project=None, system=False):
    """Check if safety is installed by trying to run it."""
    pass


def install_safety(project, system=False, auto_install=False, quiet=False):
    """Install safety and its dependencies."""
    pass


def run_safety_check(cmd, quiet):
    """Run safety check with the given command."""
    pass


def parse_safety_output(output, quiet):
    pass


def do_check(  # noqa: PLR0913
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
    auto_install=False,
    scan=False,
):
    pass
