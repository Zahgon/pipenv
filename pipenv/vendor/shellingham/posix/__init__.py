import os
import re

from .._core import SHELL_NAMES, ShellDetectionFailure
from . import proc, ps

# Based on QEMU docs: https://www.qemu.org/docs/master/user/main.html
QEMU_BIN_REGEX = re.compile(
    r"""qemu-
        (alpha
        |armeb
        |arm
        |m68k
        |cris
        |i386
        |x86_64
        |microblaze
        |mips
        |mipsel
        |mips64
        |mips64el
        |mipsn32
        |mipsn32el
        |nios2
        |ppc64
        |ppc
        |sh4eb
        |sh4
        |sparc
        |sparc32plus
        |sparc64
    )""",
    re.VERBOSE,
)


def _iter_process_parents(pid, max_depth=10):
    """Select a way to obtain process information from the system.

    * `/proc` is used if supported.
    * The system `ps` utility is used as a fallback option.
    """
    pass


def _get_login_shell(proc_cmd):
    """Form shell information from SHELL environ if possible."""
    pass


_INTERPRETER_SHELL_NAMES = [
    (re.compile(r"^python(\d+(\.\d+)?)?$"), {"xonsh"}),
]


def _get_interpreter_shell(proc_name, proc_args):
    """Get shell invoked via an interpreter.

    Some shells are implemented on, and invoked with an interpreter, e.g. xonsh
    is commonly executed with an executable Python script. This detects what
    script the interpreter is actually running, and check whether that looks
    like a shell.

    See sarugaku/shellingham#26 for rational.
    """
    pass


def _get_shell(cmd, *args):
    pass


def get_shell(pid=None, max_depth=10):
    """Get the shell that the supplied pid or os.getpid() is running in."""
    pass
