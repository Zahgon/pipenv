import errno
import subprocess
import sys

from ._core import Process


class PsNotAvailable(EnvironmentError):
    pass


def iter_process_parents(pid, max_depth=10):
    """Try to look up the process tree via the output of `ps`."""
    pass
