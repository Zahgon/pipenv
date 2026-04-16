import collections
import contextlib
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from shutil import get_terminal_size

from pipenv.utils.shell import temp_environ
from pipenv.vendor import shellingham

ShellDetectionFailure = shellingham.ShellDetectionFailure


def _build_info(value):
    pass


def detect_info(project):
    pass


def _get_activate_script(cmd, venv):
    """Returns the string to activate a virtualenv.

    This is POSIX-only at the moment since the compat (pexpect-based) shell
    does not work elsewhere anyway.
    """
    # Suffix and source command for various shells.
    command = "source"

    # Extract the shell executable name from the path, handling both POSIX
    # forward-slash paths and Windows backslash paths on any host OS.
    # e.g. "C:\Program Files\PowerShell\7\pwsh.exe" -> "pwsh"
    #      "/usr/bin/zsh"                            -> "zsh"
    # See: https://github.com/pypa/pipenv/issues/6532
    shell_name = re.split(r"[\\/]", cmd)[-1].split(".")[0].lower()

    if shell_name == "fish":
        suffix = ".fish"
    elif shell_name in ("csh", "tcsh"):
        suffix = ".csh"
    elif shell_name == "xonsh":
        suffix = ".xsh"
    elif shell_name == "nu":
        suffix = ".nu"
        command = "overlay use"
    elif shell_name in ("pwsh", "powershell"):
        suffix = ".ps1"
        command = "."
    elif shell_name in ("sh", "bash", "zsh", "dash", "ash", "ksh"):
        suffix = ""
    else:
        sys.exit(f"unknown shell {cmd}")

    # Escape any special characters located within the virtualenv path to allow
    # for proper activation.
    venv_location = re.sub(r"([ &$()\[\]])", r"\\\1", str(venv))

    if suffix == "nu":
        return f"overlay use {venv_location}"
    elif suffix == ".ps1" and os.name == "nt":
        return f". {venv_location}\\Scripts\\Activate{suffix}"

    # The leading space can make history cleaner in some shells.
    return f" {command} {venv_location}/bin/activate{suffix}"


def _get_deactivate_wrapper_script(cmd):
    """Returns a script to wrap the deactivate function to also unset PIPENV_ACTIVE.

    This ensures that when a user runs 'deactivate' in a pipenv shell, the
    PIPENV_ACTIVE environment variable is also cleared, allowing subsequent
    'pipenv shell' commands to work without the 'already activated' error.
    """
    # Extract the shell executable name from the path, handling both POSIX
    # forward-slash paths and Windows backslash paths on any host OS.
    # e.g. "C:\Program Files\PowerShell\7\pwsh.exe" -> "pwsh"
    #      "/usr/bin/zsh"                            -> "zsh"
    # See: https://github.com/pypa/pipenv/issues/6532
    shell_name = re.split(r"[\\/]", cmd)[-1].split(".")[0].lower()

    if shell_name == "fish":
        # Fish shell uses 'functions' and 'set -e' to unset variables
        return (
            "functions -c deactivate _pipenv_old_deactivate; "
            "function deactivate; _pipenv_old_deactivate; set -e PIPENV_ACTIVE; end"
        )
    elif shell_name in ("csh", "tcsh"):
        # C shell uses 'unsetenv'
        return (
            "alias _pipenv_old_deactivate deactivate; "
            "alias deactivate '_pipenv_old_deactivate; unsetenv PIPENV_ACTIVE'"
        )
    elif shell_name == "xonsh":
        # Xonsh uses Python-like syntax
        return (
            "_pipenv_old_deactivate = deactivate; "
            "def deactivate(): _pipenv_old_deactivate(); del $PIPENV_ACTIVE"
        )
    elif shell_name == "nu":
        # Nushell - deactivate is typically handled differently
        # For now, return empty as nu has different paradigm
        return ""
    elif shell_name in ("pwsh", "powershell"):
        # PowerShell
        return (
            "$_pipenv_old_deactivate = $function:deactivate; "
            "function deactivate { & $_pipenv_old_deactivate; "
            "Remove-Item Env:PIPENV_ACTIVE -ErrorAction SilentlyContinue }"
        )
    elif shell_name == "zsh":
        # Zsh uses 'functions -c' to copy function definitions
        return (
            "functions -c deactivate _pipenv_old_deactivate; "
            "deactivate() { _pipenv_old_deactivate; unset PIPENV_ACTIVE; }"
        )
    elif shell_name == "bash":
        # Bash uses 'declare -f' to copy function definitions
        return (
            'eval "_pipenv_old_deactivate() { $(declare -f deactivate | tail -n +2) }"; '
            "deactivate() { _pipenv_old_deactivate; unset PIPENV_ACTIVE; }"
        )
    elif shell_name in ("sh", "dash", "ash", "ksh"):
        # Plain POSIX sh doesn't have 'declare -f', use a simpler approach
        # Just redefine deactivate to call the original via sourcing and add unset
        return "deactivate() { command deactivate 2>/dev/null; unset PIPENV_ACTIVE; }"
    else:
        # Unknown shell - return empty string
        return ""


def _handover(cmd, args):
    args = [cmd] + args
    if os.name != "nt":
        os.execvp(cmd, args)
    else:
        sys.exit(subprocess.call(args, universal_newlines=True))


class Shell:
    def __init__(self, cmd):
        self.cmd = cmd
        self.args = []

    def __repr__(self):
        return f"{type(self).__name__}(cmd={repr(self.cmd)}, args={repr(self.args)})"

    @contextlib.contextmanager
    def inject_path(self, venv):
        venv_path = Path(venv)
        with temp_environ():
            os.environ["PATH"] = (
                f"{os.pathsep.join(str(p.parent) for p in _iter_python(venv_path))}{os.pathsep}{os.environ['PATH']}"
            )
            yield

    def fork(self, venv, cwd, args):
        # FIXME: This isn't necessarily the correct prompt. We should read the
        # actual prompt by peeking into the activation script.
        venv_path = Path(venv)
        name = venv_path.name
        os.environ["VIRTUAL_ENV"] = str(venv_path)
        if "PROMPT" in os.environ:
            os.environ["PROMPT"] = f"({name}) {os.environ['PROMPT']}"
        if "PS1" in os.environ:
            os.environ["PS1"] = f"({name}) {os.environ['PS1']}"
        with self.inject_path(venv):
            os.chdir(str(cwd) if isinstance(cwd, Path) else cwd)
            _handover(self.cmd, self.args + list(args))

    def fork_compat(self, venv, cwd, args, quiet=False):
        pass


POSSIBLE_ENV_PYTHON = [Path("bin", "python"), Path("Scripts", "python.exe")]


def _iter_python(venv):
    for path in POSSIBLE_ENV_PYTHON:
        full_path = Path(venv, path)
        if full_path.is_file():
            yield full_path


class Bash(Shell):
    def _format_path(self, python):
        return python.parent.as_posix()

    # The usual PATH injection technique does not work with Bash.
    # https://github.com/berdario/pew/issues/58#issuecomment-102182346
    @contextlib.contextmanager
    def inject_path(self, venv):
        from tempfile import NamedTemporaryFile

        bashrc_path = Path.home().joinpath(".bashrc")
        with NamedTemporaryFile("w+") as rcfile:
            if bashrc_path.is_file():
                base_rc_src = f'source "{bashrc_path.as_posix()}"\n'
                rcfile.write(base_rc_src)

            export_path = 'export PATH="{}:$PATH"\n'.format(
                ":".join(self._format_path(python) for python in _iter_python(venv))
            )
            rcfile.write(export_path)
            rcfile.flush()
            self.args.extend(["--rcfile", rcfile.name])
            yield


class MsysBash(Bash):
    def _format_path(self, python):
        s = super()._format_path(python)
        if not python.drive:
            return s
        # Convert "C:/something" to "/c/something".
        return f"/{s[0].lower()}{s[2:]}"


class CmderEmulatedShell(Shell):
    def fork(self, venv, cwd, args):
        if cwd:
            os.environ["CMDER_START"] = cwd
        super().fork(venv, cwd, args)


class CmderCommandPrompt(CmderEmulatedShell):
    def fork(self, venv, cwd, args):
        rc_path = Path(os.path.expandvars("%CMDER_ROOT%\\vendor\\init.bat"))
        if rc_path.exists():
            self.args.extend(["/k", str(rc_path)])
        super().fork(venv, cwd, args)


class CmderPowershell(Shell):
    def fork(self, venv, cwd, args):
        rc_path = Path(os.path.expandvars("%CMDER_ROOT%\\vendor\\profile.ps1"))
        if rc_path.exists():
            self.args.extend(
                [
                    "-ExecutionPolicy",
                    "Bypass",
                    "-NoLogo",
                    "-NoProfile",
                    "-NoExit",
                    "-Command",
                    f"Invoke-Expression '. ''{rc_path}'''",
                ]
            )
        super().fork(venv, cwd, args)


# Two dimensional dict. First is the shell type, second is the emulator type.
# Example: SHELL_LOOKUP['powershell']['cmder'] => CmderPowershell.
SHELL_LOOKUP = collections.defaultdict(
    lambda: collections.defaultdict(lambda: Shell),
    {
        "bash": collections.defaultdict(
            lambda: Bash,
            {"msys": MsysBash},
        ),
        "cmd": collections.defaultdict(
            lambda: Shell,
            {"cmder": CmderCommandPrompt},
        ),
        "powershell": collections.defaultdict(
            lambda: Shell,
            {"cmder": CmderPowershell},
        ),
        "pwsh": collections.defaultdict(
            lambda: Shell,
            {"cmder": CmderPowershell},
        ),
    },
)


def _detect_emulator():
    pass


def choose_shell(project):
    pass
