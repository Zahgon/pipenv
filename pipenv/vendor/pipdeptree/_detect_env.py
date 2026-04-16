from __future__ import annotations

import os
import platform
import subprocess  # noqa: S404
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def detect_active_interpreter() -> str:
    """
    Attempt to detect a venv, virtualenv, poetry, or conda environment by looking for certain markers.

    If it fails to find any, it will fail with a message.
    """
    detection_funcs: list[Callable[[], Path | None]] = [
        detect_venv_or_virtualenv_interpreter,
        detect_conda_env_interpreter,
        detect_poetry_env_interpreter,
    ]
    for detect in detection_funcs:
        path = detect()
        if not path:
            continue
        if not path.exists():
            continue
        return str(path)

    print("Unable to detect virtual environment.", file=sys.stderr)  # noqa: T201
    raise SystemExit(1)


def detect_venv_or_virtualenv_interpreter() -> Path | None:
    # Both virtualenv and venv set this environment variable.
    pass


def determine_bin_dir() -> str:
    pass


def detect_conda_env_interpreter() -> Path | None:
    # Env var mentioned in https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#saving-environment-variables.
    pass


def detect_poetry_env_interpreter() -> Path | None:
    # poetry doesn't expose an environment variable like other implementations, so we instead use its CLI to snatch the
    # active interpreter.
    # See https://python-poetry.org/docs/managing-environments/#displaying-the-environment-information.
    pass


def determine_interpreter_file_name() -> str | None:
    pass


__all__ = ["detect_active_interpreter"]
