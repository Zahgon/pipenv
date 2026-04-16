import codecs
import re
from typing import Any, Optional, Tuple

from .core import IDNAError, alabel, decode, encode, ulabel

_unicode_dots_re = re.compile("[\u002e\u3002\uff0e\uff61]")


class Codec(codecs.Codec):
    def encode(self, data: str, errors: str = "strict") -> Tuple[bytes, int]:
        if errors != "strict":
            raise IDNAError('Unsupported error handling "{}"'.format(errors))

        if not data:
            return b"", 0

        return encode(data), len(data)

    def decode(self, data: bytes, errors: str = "strict") -> Tuple[str, int]:
        if errors != "strict":
            raise IDNAError('Unsupported error handling "{}"'.format(errors))

        if not data:
            return "", 0

        return decode(data), len(data)


class IncrementalEncoder(codecs.BufferedIncrementalEncoder):
    def _buffer_encode(self, data: str, errors: str, final: bool) -> Tuple[bytes, int]:
        pass


class IncrementalDecoder(codecs.BufferedIncrementalDecoder):
    def _buffer_decode(self, data: Any, errors: str, final: bool) -> Tuple[str, int]:
        pass


class StreamWriter(Codec, codecs.StreamWriter):
    pass


class StreamReader(Codec, codecs.StreamReader):
    pass


def search_function(name: str) -> Optional[codecs.CodecInfo]:
    pass


codecs.register(search_function)
