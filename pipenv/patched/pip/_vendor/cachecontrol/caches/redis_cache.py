# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations


from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pipenv.patched.pip._vendor.cachecontrol.cache import BaseCache

if TYPE_CHECKING:
    from redis import Redis


class RedisCache(BaseCache):
    def __init__(self, conn: Redis[bytes]) -> None:
        self.conn = conn

    def get(self, key: str) -> bytes | None:
        return self.conn.get(key)

    def set(
        self, key: str, value: bytes, expires: int | datetime | None = None
    ) -> None:
        pass

    def delete(self, key: str) -> None:
        self.conn.delete(key)

    def clear(self) -> None:
        """Helper for clearing all the keys in a database. Use with
        caution!"""
        for key in self.conn.keys():
            self.conn.delete(key)

    def close(self) -> None:
        """Redis uses connection pooling, no need to close the connection."""
        pass
