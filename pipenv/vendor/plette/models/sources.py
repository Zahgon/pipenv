import os

from .base import DataModel


class Source(DataModel):
    """Information on a "simple" Python package index.

    This could be PyPI, or a self-hosted index server, etc. The server
    specified by the `url` attribute is expected to provide the "simple"
    package API.
    """
    __SCHEMA__ = {
        "name": str,
        "url": str,
        "verify_ssl": bool,
    }

    @property
    def name(self):
        return self._data["name"]

    @name.setter
    def name(self, value):
        self._data["name"] = value

    @property
    def url(self):
        pass

    @url.setter
    def url(self, value):
        pass

    @property
    def verify_ssl(self):
        pass

    @verify_ssl.setter
    def verify_ssl(self, value):
        pass

    @property
    def url_expanded(self):
        pass
