"""
Audit command implementation using pip-audit for vulnerability scanning.

This module provides the preferred way to audit Python packages for known
security vulnerabilities using pip-audit, which queries the Python Packaging
Advisory Database (PyPI) or Open Source Vulnerabilities (OSV) database.
"""

import logging
import subprocess
import sys
import tempfile

from pipenv.utils import console, err
from pipenv.utils.processes import run_command
from pipenv.utils.project import ensure_project
from pipenv.utils.shell import project_python


def is_pip_audit_installed(project=None, system=False):
    """Check if pip-audit is installed by trying to run it."""
    pass


def install_pip_audit(project, system=False):
    """Install pip-audit."""
    pass


def build_audit_options(
    output="columns",
    strict=False,
    ignore=None,
    fix=False,
    dry_run=False,
    skip_editable=False,
    no_deps=False,
    local_only=False,
    vulnerability_service="pypi",
    descriptions=False,
    aliases=False,
    output_file=None,
    requirements_file=None,
    use_lockfile=False,
):
    """Build command line options for pip-audit."""
    pass


def do_audit(  # noqa: PLR0913
    project,
    python=False,
    system=False,
    output="columns",
    quiet=False,
    verbose=False,
    strict=False,
    ignore=None,
    fix=False,
    dry_run=False,
    skip_editable=False,
    no_deps=False,
    local_only=False,
    vulnerability_service="pypi",
    descriptions=False,
    aliases=False,
    output_file=None,
    pypi_mirror=None,
    categories="",
    use_installed=False,
    use_lockfile=False,
):
    """Audit packages for known security vulnerabilities using pip-audit.

    This is the preferred method for vulnerability scanning in pipenv.
    It uses the Python Packaging Advisory Database (PyPI) or OSV database.

    Supports auditing from:
    - The current virtualenv (default)
    - Pipfile.lock (with --locked flag, converted to requirements format for pip-audit)
    """
    pass
