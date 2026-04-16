from __future__ import annotations

import contextlib
import errno
import logging
import logging.handlers
import os
import sys
import threading
from collections.abc import Generator
from dataclasses import dataclass
from io import StringIO, TextIOWrapper
from logging import Filter
from typing import Any, ClassVar

from pipenv.patched.pip._vendor.rich.console import (
    Console,
    ConsoleOptions,
    ConsoleRenderable,
    RenderableType,
    RenderResult,
    RichCast,
)
from pipenv.patched.pip._vendor.rich.highlighter import NullHighlighter
from pipenv.patched.pip._vendor.rich.logging import RichHandler
from pipenv.patched.pip._vendor.rich.segment import Segment
from pipenv.patched.pip._vendor.rich.style import Style

from pipenv.patched.pip._internal.utils._log import VERBOSE, getLogger
from pipenv.patched.pip._internal.utils.compat import WINDOWS
from pipenv.patched.pip._internal.utils.deprecation import DEPRECATION_MSG_PREFIX
from pipenv.patched.pip._internal.utils.misc import StreamWrapper, ensure_dir

_log_state = threading.local()
_stdout_console = None
_stderr_console = None
subprocess_logger = getLogger("pip.subprocessor")


class BrokenStdoutLoggingError(Exception):
    """
    Raised if BrokenPipeError occurs for the stdout stream while logging.
    """


def _is_broken_pipe_error(exc_class: type[BaseException], exc: BaseException) -> bool:
    pass


@contextlib.contextmanager
def capture_logging() -> Generator[StringIO, None, None]:
    """Capture all pip logs in a buffer temporarily."""
    # Patching sys.std(out|err) directly is not viable as the caller
    # may want to emit non-logging output (e.g. a rich spinner). To
    # avoid capturing that, temporarily patch the root logging handlers
    # to use new rich consoles that write to a StringIO.
    handlers = {}
    for handler in logging.getLogger().handlers:
        if isinstance(handler, RichPipStreamHandler):
            # Also store the handler's original console so it can be
            # restored on context exit.
            handlers[handler] = handler.console

    fake_stream = StreamWrapper.from_stream(sys.stdout)
    if not handlers:
        yield fake_stream
        return

    # HACK: grab no_color attribute from a random handler console since
    # it's a global option anyway.
    no_color = next(iter(handlers.values())).no_color
    fake_console = PipConsole(file=fake_stream, no_color=no_color, soft_wrap=True)
    try:
        for handler in handlers:
            handler.console = fake_console
        yield fake_stream
    finally:
        for handler, original_console in handlers.items():
            handler.console = original_console


@contextlib.contextmanager
def indent_log(num: int = 2) -> Generator[None, None, None]:
    """
    A context manager which will cause the log output to be indented for any
    log messages emitted inside it.
    """
    # For thread-safety
    _log_state.indentation = get_indentation()
    _log_state.indentation += num
    try:
        yield
    finally:
        _log_state.indentation -= num


def get_indentation() -> int:
    return getattr(_log_state, "indentation", 0)


class IndentingFormatter(logging.Formatter):
    default_time_format = "%Y-%m-%dT%H:%M:%S"

    def __init__(
        self,
        *args: Any,
        add_timestamp: bool = False,
        **kwargs: Any,
    ) -> None:
        """
        A logging.Formatter that obeys the indent_log() context manager.

        :param add_timestamp: A bool indicating output lines should be prefixed
            with their record's timestamp.
        """
        self.add_timestamp = add_timestamp
        super().__init__(*args, **kwargs)

    def get_message_start(self, formatted: str, levelno: int) -> str:
        """
        Return the start of the formatted log message (not counting the
        prefix to add to each line).
        """
        pass

    def format(self, record: logging.LogRecord) -> str:
        """
        Calls the standard formatter, but will indent all of the log message
        lines by our current indentation level.
        """
        pass


@dataclass
class IndentedRenderable:
    renderable: RenderableType
    indent: int

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        segments = console.render(self.renderable, options)
        lines = Segment.split_lines(segments)
        for line in lines:
            yield Segment(" " * self.indent)
            yield from line
            yield Segment("\n")


class PipConsole(Console):
    def on_broken_pipe(self) -> None:
        # Reraise the original exception, rich 13.8.0+ exits by default
        # instead, preventing our handler from firing.
        raise BrokenPipeError() from None


def get_console(*, stderr: bool = False) -> Console:
    if stderr:
        assert _stderr_console is not None, "stderr rich console is missing!"
        return _stderr_console
    else:
        assert _stdout_console is not None, "stdout rich console is missing!"
        return _stdout_console


class RichPipStreamHandler(RichHandler):
    KEYWORDS: ClassVar[list[str] | None] = []

    def __init__(self, console: Console) -> None:
        super().__init__(
            console=console,
            show_time=False,
            show_level=False,
            show_path=False,
            highlighter=NullHighlighter(),
        )

    # Our custom override on Rich's logger, to make things work as we need them to.
    def emit(self, record: logging.LogRecord) -> None:
        pass

    def handleError(self, record: logging.LogRecord) -> None:
        """Called when logging is unable to log some output."""
        pass


class BetterRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def _open(self) -> TextIOWrapper:
        pass


class MaxLevelFilter(Filter):
    def __init__(self, level: int) -> None:
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        pass


class ExcludeLoggerFilter(Filter):
    """
    A logging Filter that excludes records from a logger (or its children).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # The base Filter class allows only records from a logger (or its
        # children).
        pass


def setup_logging(verbosity: int, no_color: bool, user_log_file: str | None) -> int:
    """Configures and sets up all of the logging

    Returns the requested logging level, as its integer value.
    """

    # Determine the level to be logging at.
    if verbosity >= 2:
        level_number = logging.DEBUG
    elif verbosity == 1:
        level_number = VERBOSE
    elif verbosity == -1:
        level_number = logging.WARNING
    elif verbosity == -2:
        level_number = logging.ERROR
    elif verbosity <= -3:
        level_number = logging.CRITICAL
    else:
        level_number = logging.INFO

    level = logging.getLevelName(level_number)

    # The "root" logger should match the "console" level *unless* we also need
    # to log to a user log file.
    include_user_log = user_log_file is not None
    if include_user_log:
        additional_log_file = user_log_file
        root_level = "DEBUG"
    else:
        additional_log_file = "/dev/null"
        root_level = level

    # Disable any logging besides WARNING unless we have DEBUG level logging
    # enabled for vendored libraries.
    vendored_log_level = "WARNING" if level in ["INFO", "ERROR"] else "DEBUG"

    # Shorthands for clarity
    handler_classes = {
        "stream": "pipenv.patched.pip._internal.utils.logging.RichPipStreamHandler",
        "file": "pipenv.patched.pip._internal.utils.logging.BetterRotatingFileHandler",
    }
    handlers = ["console", "console_errors", "console_subprocess"] + (
        ["user_log"] if include_user_log else []
    )
    global _stdout_console, stderr_console
    _stdout_console = PipConsole(file=sys.stdout, no_color=no_color, soft_wrap=True)
    _stderr_console = PipConsole(file=sys.stderr, no_color=no_color, soft_wrap=True)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "exclude_warnings": {
                    "()": "pipenv.patched.pip._internal.utils.logging.MaxLevelFilter",
                    "level": logging.WARNING,
                },
                "restrict_to_subprocess": {
                    "()": "logging.Filter",
                    "name": subprocess_logger.name,
                },
                "exclude_subprocess": {
                    "()": "pipenv.patched.pip._internal.utils.logging.ExcludeLoggerFilter",
                    "name": subprocess_logger.name,
                },
            },
            "formatters": {
                "indent": {
                    "()": IndentingFormatter,
                    "format": "%(message)s",
                },
                "indent_with_timestamp": {
                    "()": IndentingFormatter,
                    "format": "%(message)s",
                    "add_timestamp": True,
                },
            },
            "handlers": {
                "console": {
                    "level": level,
                    "class": handler_classes["stream"],
                    "console": _stdout_console,
                    "filters": ["exclude_subprocess", "exclude_warnings"],
                    "formatter": "indent",
                },
                "console_errors": {
                    "level": "WARNING",
                    "class": handler_classes["stream"],
                    "console": _stderr_console,
                    "filters": ["exclude_subprocess"],
                    "formatter": "indent",
                },
                # A handler responsible for logging to the console messages
                # from the "subprocessor" logger.
                "console_subprocess": {
                    "level": level,
                    "class": handler_classes["stream"],
                    "console": _stderr_console,
                    "filters": ["restrict_to_subprocess"],
                    "formatter": "indent",
                },
                "user_log": {
                    "level": "DEBUG",
                    "class": handler_classes["file"],
                    "filename": additional_log_file,
                    "encoding": "utf-8",
                    "delay": True,
                    "formatter": "indent_with_timestamp",
                },
            },
            "root": {
                "level": root_level,
                "handlers": handlers,
            },
            "loggers": {"pipenv.patched.pip._vendor": {"level": vendored_log_level}},
        }
    )

    return level_number
