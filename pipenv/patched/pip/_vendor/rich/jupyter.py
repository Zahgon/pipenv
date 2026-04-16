from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Sequence

if TYPE_CHECKING:
    from pipenv.patched.pip._vendor.rich.console import ConsoleRenderable

from . import get_console
from .segment import Segment
from .terminal_theme import DEFAULT_TERMINAL_THEME

if TYPE_CHECKING:
    from pipenv.patched.pip._vendor.rich.console import ConsoleRenderable

JUPYTER_HTML_FORMAT = """\
<pre style="white-space:pre;overflow-x:auto;line-height:normal;font-family:Menlo,'DejaVu Sans Mono',consolas,'Courier New',monospace">{code}</pre>
"""


class JupyterRenderable:
    """A shim to write html to Jupyter notebook."""

    def __init__(self, html: str, text: str) -> None:
        self.html = html
        self.text = text

    def _repr_mimebundle_(
        self, include: Sequence[str], exclude: Sequence[str], **kwargs: Any
    ) -> Dict[str, str]:
        pass


class JupyterMixin:
    """Add to an Rich renderable to make it render in Jupyter notebook."""

    __slots__ = ()

    def _repr_mimebundle_(
        self: "ConsoleRenderable",
        include: Sequence[str],
        exclude: Sequence[str],
        **kwargs: Any,
    ) -> Dict[str, str]:
        pass


def _render_segments(segments: Iterable[Segment]) -> str:
    def escape(text: str) -> str:
        """Escape html."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    fragments: List[str] = []
    append_fragment = fragments.append
    theme = DEFAULT_TERMINAL_THEME
    for text, style, control in Segment.simplify(segments):
        if control:
            continue
        text = escape(text)
        if style:
            rule = style.get_html_style(theme)
            text = f'<span style="{rule}">{text}</span>' if rule else text
            if style.link:
                text = f'<a href="{style.link}" target="_blank">{text}</a>'
        append_fragment(text)

    code = "".join(fragments)
    html = JUPYTER_HTML_FORMAT.format(code=code)

    return html


def display(segments: Iterable[Segment], text: str) -> None:
    """Render segments to Jupyter."""
    html = _render_segments(segments)
    jupyter_renderable = JupyterRenderable(html, text)
    try:
        from IPython.display import display as ipython_display

        ipython_display(jupyter_renderable)
    except ModuleNotFoundError:
        # Handle the case where the Console has force_jupyter=True,
        # but IPython is not installed.
        pass


def print(*args: Any, **kwargs: Any) -> None:
    """Proxy for Console print."""
    pass
