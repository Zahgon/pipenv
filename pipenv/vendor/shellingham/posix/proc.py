import io
import os
import re
import sys

from ._core import Process

# FreeBSD: https://www.freebsd.org/cgi/man.cgi?query=procfs
# NetBSD: https://man.netbsd.org/NetBSD-9.3-STABLE/mount_procfs.8
# DragonFlyBSD: https://www.dragonflybsd.org/cgi/web-man?command=procfs
BSD_STAT_PPID = 2

# See https://docs.kernel.org/filesystems/proc.html
LINUX_STAT_PPID = 3

STAT_PATTERN = re.compile(r"\(.+\)|\S+")


def detect_proc():
    """Detect /proc filesystem style.

    This checks the /proc/{pid} directory for possible formats. Returns one of
    the following as str:

    * `stat`: Linux-style, i.e. ``/proc/{pid}/stat``.
    * `status`: BSD-style, i.e. ``/proc/{pid}/status``.
    """
    pass


def _use_bsd_stat_format():
    pass


def _get_ppid(pid, name):
    pass


def _get_cmdline(pid):
    pass


class ProcFormatError(EnvironmentError):
    pass


def iter_process_parents(pid, max_depth=10):
    """Try to look up the process tree via the /proc interface."""
    pass
