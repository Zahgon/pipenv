"""Network Authentication Helpers

Contains interface (MultiDomainBasicAuth) and associated glue code for
providing credentials in the context of network requests.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sysconfig
import typing
import urllib.parse
from abc import ABC, abstractmethod
from functools import cache
from os.path import commonprefix
from pathlib import Path
from typing import Any, NamedTuple

from pipenv.patched.pip._vendor.requests.auth import AuthBase, HTTPBasicAuth
from pipenv.patched.pip._vendor.requests.utils import get_netrc_auth

from pipenv.patched.pip._internal.utils.logging import getLogger
from pipenv.patched.pip._internal.utils.misc import (
    ask,
    ask_input,
    ask_password,
    remove_auth_from_url,
    split_auth_netloc_from_url,
)
from pipenv.patched.pip._internal.vcs.versioncontrol import AuthInfo

if typing.TYPE_CHECKING:
    from pipenv.patched.pip._vendor.requests import PreparedRequest
    from pipenv.patched.pip._vendor.requests.models import Response

logger = getLogger(__name__)

KEYRING_DISABLED = False


class Credentials(NamedTuple):
    url: str
    username: str
    password: str


class KeyRingBaseProvider(ABC):
    """Keyring base provider interface"""

    has_keyring: bool

    @abstractmethod
    def get_auth_info(self, url: str, username: str | None) -> AuthInfo | None: ...

    @abstractmethod
    def save_auth_info(self, url: str, username: str, password: str) -> None: ...


class KeyRingNullProvider(KeyRingBaseProvider):
    """Keyring null provider"""

    has_keyring = False

    def get_auth_info(self, url: str, username: str | None) -> AuthInfo | None:
        pass

    def save_auth_info(self, url: str, username: str, password: str) -> None:
        pass


class KeyRingPythonProvider(KeyRingBaseProvider):
    """Keyring interface which uses locally imported `keyring`"""

    has_keyring = True

    def __init__(self) -> None:
        import keyring

        self.keyring = keyring

    def get_auth_info(self, url: str, username: str | None) -> AuthInfo | None:
        # Support keyring's get_credential interface which supports getting
        # credentials without a username. This is only available for
        # keyring>=15.2.0.
        pass

    def save_auth_info(self, url: str, username: str, password: str) -> None:
        pass


class KeyRingCliProvider(KeyRingBaseProvider):
    """Provider which uses `keyring` cli

    Instead of calling the keyring package installed alongside pip
    we call keyring on the command line which will enable pip to
    use which ever installation of keyring is available first in
    PATH.
    """

    has_keyring = True

    def __init__(self, cmd: str) -> None:
        self.keyring = cmd

    def get_auth_info(self, url: str, username: str | None) -> AuthInfo | None:
        # This is the default implementation of keyring.get_credential
        # https://github.com/jaraco/keyring/blob/97689324abcf01bd1793d49063e7ca01e03d7d07/keyring/backend.py#L134-L139
        pass

    def save_auth_info(self, url: str, username: str, password: str) -> None:
        pass

    def _get_password(self, service_name: str, username: str) -> str | None:
        """Mirror the implementation of keyring.get_password using cli"""
        pass

    def _set_password(self, service_name: str, username: str, password: str) -> None:
        """Mirror the implementation of keyring.set_password using cli"""
        pass


@cache
def get_keyring_provider(provider: str) -> KeyRingBaseProvider:
    pass


class MultiDomainBasicAuth(AuthBase):
    def __init__(
        self,
        prompting: bool = True,
        index_urls: list[str] | None = None,
        keyring_provider: str = "auto",
    ) -> None:
        self.prompting = prompting
        self.index_urls = index_urls
        self.keyring_provider = keyring_provider
        self.passwords: dict[str, AuthInfo] = {}
        # When the user is prompted to enter credentials and keyring is
        # available, we will offer to save them. If the user accepts,
        # this value is set to the credentials they entered. After the
        # request authenticates, the caller should call
        # ``save_credentials`` to save these.
        self._credentials_to_save: Credentials | None = None

    @property
    def keyring_provider(self) -> KeyRingBaseProvider:
        pass

    @keyring_provider.setter
    def keyring_provider(self, provider: str) -> None:
        # The free function get_keyring_provider has been decorated with
        # functools.cache. If an exception occurs in get_keyring_auth that
        # cache will be cleared and keyring disabled, take that into account
        # if you want to remove this indirection.
        pass

    @property
    def use_keyring(self) -> bool:
        # We won't use keyring when --no-input is passed unless
        # a specific provider is requested because it might require
        # user interaction
        pass

    def _get_keyring_auth(
        self,
        url: str | None,
        username: str | None,
    ) -> AuthInfo | None:
        """Return the tuple auth for a given url from keyring."""
        pass

    def _get_index_url(self, url: str) -> str | None:
        """Return the original index URL matching the requested URL.

        Cached or dynamically generated credentials may work against
        the original index URL rather than just the netloc.

        The provided url should have had its username and password
        removed already. If the original index url had credentials then
        they will be included in the return value.

        Returns None if no matching index was found, or if --no-index
        was specified by the user.
        """
        pass

    def _get_new_credentials(
        self,
        original_url: str,
        *,
        allow_netrc: bool = True,
        allow_keyring: bool = False,
    ) -> AuthInfo:
        """Find and return credentials for the specified URL."""
        pass

    def _get_url_and_credentials(
        self, original_url: str
    ) -> tuple[str, str | None, str | None]:
        """Return the credentials to use for the provided URL.

        If allowed, netrc and keyring may be used to obtain the
        correct credentials.

        Returns (url_without_credentials, username, password). Note
        that even if the original URL contains credentials, this
        function may return a different username and password.
        """
        pass

    def __call__(self, req: PreparedRequest) -> PreparedRequest:
        # Get credentials for this request
        assert req.url is not None
        url, username, password = self._get_url_and_credentials(req.url)

        # Set the url of the request to the url without any credentials
        req.url = url

        if username is not None and password is not None:
            # Send the basic auth with this request
            req = HTTPBasicAuth(username, password)(req)

        # Attach a hook to handle 401 responses
        req.register_hook("response", self.handle_401)

        return req

    # Factored out to allow for easy patching in tests
    def _prompt_for_password(self, netloc: str) -> tuple[str | None, str | None, bool]:
        pass

    # Factored out to allow for easy patching in tests
    def _should_save_password_to_keyring(self) -> bool:
        pass

    def handle_401(self, resp: Response, **kwargs: Any) -> Response:
        # We only care about 401 responses, anything else we want to just
        #   pass through the actual response
        pass

    def warn_on_401(self, resp: Response, **kwargs: Any) -> None:
        """Response callback to warn about incorrect credentials."""
        pass

    def save_credentials(self, resp: Response, **kwargs: Any) -> None:
        """Response callback to save credentials on success."""
        pass
