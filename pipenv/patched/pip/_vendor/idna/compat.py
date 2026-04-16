from typing import Any, Union

from .core import decode, encode


def ToASCII(label: str) -> bytes:
    pass


def ToUnicode(label: Union[bytes, bytearray]) -> str:
    pass


def nameprep(s: Any) -> None:
    raise NotImplementedError("IDNA 2008 does not utilise nameprep protocol")
