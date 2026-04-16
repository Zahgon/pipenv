from __future__ import annotations

import functools
import sys
from collections.abc import Generator, Iterable, Iterator
from typing import Any, Callable, Literal, TypeVar

from pipenv.patched.pip._vendor.rich.progress import (
    BarColumn,
    DownloadColumn,
    FileSizeColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from pipenv.patched.pip._internal.cli.spinners import RateLimiter
from pipenv.patched.pip._internal.utils.logging import get_console, get_indentation

T = TypeVar("T")
ProgressRenderer = Callable[[Iterable[T]], Iterator[T]]
InstallRequirement = Any
BarType = Literal["on", "off", "raw"]


def _rich_download_progress_bar(
    iterable: Iterable[bytes],
    *,
    bar_type: BarType,
    size: int | None,
    initial_progress: int | None = None,
) -> Generator[bytes, None, None]:
    pass


def _rich_install_progress_bar(
    iterable: Iterable[InstallRequirement], *, total: int
) -> Iterator[InstallRequirement]:
    pass


def _raw_progress_bar(
    iterable: Iterable[bytes],
    *,
    size: int | None,
    initial_progress: int | None = None,
) -> Generator[bytes, None, None]:
    pass


def get_download_progress_renderer(
    *, bar_type: BarType, size: int | None = None, initial_progress: int | None = None
) -> ProgressRenderer[bytes]:
    """Get an object that can be used to render the download progress.

    Returns a callable, that takes an iterable to "wrap".
    """
    if bar_type == "on":
        return functools.partial(
            _rich_download_progress_bar,
            bar_type=bar_type,
            size=size,
            initial_progress=initial_progress,
        )
    elif bar_type == "raw":
        return functools.partial(
            _raw_progress_bar,
            size=size,
            initial_progress=initial_progress,
        )
    else:
        return iter  # no-op, when passed an iterator


def get_install_progress_renderer(
    *, bar_type: BarType, total: int
) -> ProgressRenderer[InstallRequirement]:
    """Get an object that can be used to render the install progress.
    Returns a callable, that takes an iterable to "wrap".
    """
    if bar_type == "on":
        return functools.partial(_rich_install_progress_bar, total=total)
    else:
        return iter
