from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

# Environment variables and constants
PYENV_ROOT = os.path.expanduser(
    os.path.expandvars(os.environ.get("PYENV_ROOT", "~/.pyenv"))
)
PYENV_ROOT = Path(PYENV_ROOT)
PYENV_INSTALLED = shutil.which("pyenv") is not None

ASDF_DATA_DIR = os.path.expanduser(
    os.path.expandvars(os.environ.get("ASDF_DATA_DIR", "~/.asdf"))
)
ASDF_INSTALLED = shutil.which("asdf") is not None

SYSTEM_ARCH = platform.architecture()[0]
IS_64BIT_OS = None

if sys.maxsize > 2**32:
    IS_64BIT_OS = platform.machine() == "AMD64"
else:
    IS_64BIT_OS = False

IGNORE_UNSUPPORTED = bool(os.environ.get("PYTHONFINDER_IGNORE_UNSUPPORTED", False))
SUBPROCESS_TIMEOUT = int(os.environ.get("PYTHONFINDER_SUBPROCESS_TIMEOUT", 5))


def get_python_paths() -> list[str]:
    """
    Get a list of paths where Python executables might be found.

    Returns:
        A list of paths to search for Python executables.
    """
    pass


def get_pyenv_paths() -> list[str]:
    """
    Get a list of paths where pyenv Python executables might be found.

    Returns:
        A list of paths to search for pyenv Python executables.
    """
    pass


def get_asdf_paths() -> list[str]:
    """
    Get a list of paths where asdf Python executables might be found.

    Returns:
        A list of paths to search for asdf Python executables.
    """
    pass
