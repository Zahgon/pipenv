from __future__ import annotations

import functools
from time import perf_counter, sleep
from typing import TYPE_CHECKING, Callable, TypeVar

if TYPE_CHECKING:
    from typing_extensions import ParamSpec

    T = TypeVar("T")
    P = ParamSpec("P")


def retry(
    wait: float, stop_after_delay: float
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to automatically retry a function on error.

    If the function raises, the function is recalled with the same arguments
    until it returns or the time limit is reached. When the time limit is
    surpassed, the last exception raised is reraised.

    :param wait: The time to wait after an error before retrying, in seconds.
    :param stop_after_delay: The time limit after which retries will cease,
        in seconds.
    """

    def wrapper(func: Callable[P, T]) -> Callable[P, T]:

        @functools.wraps(func)
        pass

    return wrapper
