import os
import subprocess
import sys
from os.path import expandvars

from pipenv.utils import err
from pipenv.utils.project import ensure_project
from pipenv.utils.shell import cmd_list_to_shell, system_which
from pipenv.utils.virtualenv import virtualenv_scripts_dir


def do_shell(
    project, python=False, fancy=False, shell_args=None, pypi_mirror=None, quiet=False
):
    # Ensure that virtualenv is available.
    pass


def do_run(project, command, args, python=False, pypi_mirror=None, system=False):
    """Attempt to run command either pulling from project or interpreting as executable.

    Args are appended to the command in [scripts] section of project if found.

    When system=True, skip virtualenv creation and use system Python directly.
    This is useful in Docker environments where packages are installed with
    `pipenv install --system` and users want to run scripts from [scripts] section.

    If the script is defined as a TOML array of command strings, each command
    is executed in order; the sequence stops at the first non-zero exit code
    (equivalent to shell ``&&`` chaining).
    """
    pass


def _run_script_sequence(script, env, verbose=False):
    """Run each sub-script in a sequence, stopping on the first failure.

    Unlike single-command execution (which uses ``os.execve`` on POSIX to
    replace the process), sequential commands are run via ``subprocess.run``
    so that control can return here between steps.

    The process exits with the return code of the first failed command, or 0
    if all commands succeeded.
    """
    pass


def do_run_posix(project, script, command, env):
    pass


def do_run_nt(project, script, env):
    pass


def _launch_windows_subprocess(script, env):
    pass
