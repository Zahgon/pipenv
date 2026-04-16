"""PipSession and supporting code, containing all pip-specific
network request configuration and behavior.
"""

from __future__ import annotations

import email.utils
import functools
import io
import ipaddress
import json
import logging
import mimetypes
import os
import platform
import shutil
import subprocess
import sys
import urllib.parse
import warnings
from collections.abc import Generator, Mapping, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    Union,
)

from pipenv.patched.pip._vendor import requests, urllib3
from pipenv.patched.pip._vendor.cachecontrol import CacheControlAdapter as _BaseCacheControlAdapter
from pipenv.patched.pip._vendor.requests.adapters import DEFAULT_POOLBLOCK, BaseAdapter
from pipenv.patched.pip._vendor.requests.adapters import HTTPAdapter as _BaseHTTPAdapter
from pipenv.patched.pip._vendor.requests.models import PreparedRequest, Response
from pipenv.patched.pip._vendor.requests.structures import CaseInsensitiveDict
from pipenv.patched.pip._vendor.urllib3.connectionpool import ConnectionPool
from pipenv.patched.pip._vendor.urllib3.exceptions import InsecureRequestWarning

from pipenv.patched.pip import __version__
from pipenv.patched.pip._internal.metadata import get_default_environment
from pipenv.patched.pip._internal.models.link import Link
from pipenv.patched.pip._internal.network.auth import MultiDomainBasicAuth
from pipenv.patched.pip._internal.network.cache import SafeFileCache

# Import ssl from compat so the initial import occurs in only one place.
from pipenv.patched.pip._internal.utils.compat import has_tls
from pipenv.patched.pip._internal.utils.glibc import libc_ver
from pipenv.patched.pip._internal.utils.misc import build_url_from_netloc, parse_netloc
from pipenv.patched.pip._internal.utils.urls import url_to_path

if TYPE_CHECKING:
    from ssl import SSLContext

    from pipenv.patched.pip._vendor.urllib3 import ProxyManager
    from pipenv.patched.pip._vendor.urllib3.poolmanager import PoolManager


logger = logging.getLogger(__name__)

SecureOrigin = tuple[str, str, Optional[Union[int, str]]]


# Ignore warning raised when using --trusted-host.
warnings.filterwarnings("ignore", category=InsecureRequestWarning)


SECURE_ORIGINS: list[SecureOrigin] = [
    # protocol, hostname, port
    # Taken from Chrome's list of secure origins (See: http://bit.ly/1qrySKC)
    ("https", "*", "*"),
    ("*", "localhost", "*"),
    ("*", "127.0.0.0/8", "*"),
    ("*", "::1/128", "*"),
    ("file", "*", None),
    # ssh is always secure.
    ("ssh", "*", "*"),
]


# These are environment variables present when running under various
# CI systems.  For each variable, some CI systems that use the variable
# are indicated.  The collection was chosen so that for each of a number
# of popular systems, at least one of the environment variables is used.
# This list is used to provide some indication of and lower bound for
# CI traffic to PyPI.  Thus, it is okay if the list is not comprehensive.
# For more background, see: https://github.com/pypa/pip/issues/5499
CI_ENVIRONMENT_VARIABLES = (
    # Azure Pipelines
    "BUILD_BUILDID",
    # Jenkins
    "BUILD_ID",
    # AppVeyor, CircleCI, Codeship, Gitlab CI, Shippable, Travis CI
    "CI",
    # Explicit environment variable.
    "PIP_IS_CI",
)


def looks_like_ci() -> bool:
    """
    Return whether it looks like pip is running under CI.
    """
    pass


@functools.lru_cache(maxsize=1)
def user_agent() -> str:
    """
    Return a string representing the user agent.
    """
    pass


class LocalFSAdapter(BaseAdapter):
    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float, float] | tuple[float, None] | None = None,
        verify: bool | str = True,
        cert: bytes | str | tuple[bytes | str, bytes | str] | None = None,
        proxies: Mapping[str, str] | None = None,
    ) -> Response:
        assert request.url is not None
        pathname = url_to_path(request.url)

        resp = Response()
        resp.status_code = 200
        resp.url = request.url

        try:
            stats = os.stat(pathname)
        except OSError as exc:
            # format the exception raised as a io.BytesIO object,
            # to return a better error message:
            resp.status_code = 404
            resp.reason = type(exc).__name__
            resp.raw = io.BytesIO(f"{resp.reason}: {exc}".encode())
        else:
            modified = email.utils.formatdate(stats.st_mtime, usegmt=True)
            content_type = mimetypes.guess_type(pathname)[0] or "text/plain"
            resp.headers = CaseInsensitiveDict(
                {
                    "Content-Type": content_type,
                    "Content-Length": str(stats.st_size),
                    "Last-Modified": modified,
                }
            )

            resp.raw = open(pathname, "rb")
            resp.close = resp.raw.close  # type: ignore[method-assign]

        return resp

    def close(self) -> None:
        pass


class _SSLContextAdapterMixin:
    """Mixin to add the ``ssl_context`` constructor argument to HTTP adapters.

    The additional argument is forwarded directly to the pool manager. This allows us
    to dynamically decide what SSL store to use at runtime, which is used to implement
    the optional ``truststore`` backend.
    """

    def __init__(
        self,
        *,
        ssl_context: SSLContext | None = None,
        **kwargs: Any,
    ) -> None:
        self._ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = DEFAULT_POOLBLOCK,
        **pool_kwargs: Any,
    ) -> PoolManager:
        pass

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> ProxyManager:
        # Proxy manager replaces the pool manager, so inject our SSL
        # context here too. https://github.com/pypa/pip/issues/13288
        if self._ssl_context is not None:
            proxy_kwargs.setdefault("ssl_context", self._ssl_context)
        return super().proxy_manager_for(proxy, **proxy_kwargs)  # type: ignore[misc, no-any-return]


class HTTPAdapter(_SSLContextAdapterMixin, _BaseHTTPAdapter):
    pass


class CacheControlAdapter(_SSLContextAdapterMixin, _BaseCacheControlAdapter):
    pass


class InsecureHTTPAdapter(HTTPAdapter):
    def cert_verify(
        self,
        conn: ConnectionPool,
        url: str,
        verify: bool | str,
        cert: str | tuple[str, str] | None,
    ) -> None:
        super().cert_verify(conn=conn, url=url, verify=False, cert=cert)


class InsecureCacheControlAdapter(CacheControlAdapter):
    def cert_verify(
        self,
        conn: ConnectionPool,
        url: str,
        verify: bool | str,
        cert: str | tuple[str, str] | None,
    ) -> None:
        super().cert_verify(conn=conn, url=url, verify=False, cert=cert)


class PipSession(requests.Session):
    timeout: int | None = None

    def __init__(
        self,
        *args: Any,
        retries: int = 0,
        resume_retries: int = 0,
        cache: str | None = None,
        trusted_hosts: Sequence[str] = (),
        index_urls: list[str] | None = None,
        ssl_context: SSLContext | None = None,
        **kwargs: Any,
    ) -> None:
        """
        :param trusted_hosts: Domains not to emit warnings for when not using
            HTTPS.
        """
        super().__init__(*args, **kwargs)

        # Namespace the attribute with "pip_" just in case to prevent
        # possible conflicts with the base class.
        self.pip_trusted_origins: list[tuple[str, int | None]] = []
        self.pip_proxy = None

        # Attach our User Agent to the request
        self.headers["User-Agent"] = user_agent()

        # Attach our Authentication handler to the session
        self.auth: MultiDomainBasicAuth = MultiDomainBasicAuth(index_urls=index_urls)

        # Create our urllib3.Retry instance which will allow us to customize
        # how we handle retries.
        retries = urllib3.Retry(
            # Set the total number of retries that a particular request can
            # have.
            total=retries,
            # A 503 error from PyPI typically means that the Fastly -> Origin
            # connection got interrupted in some way. A 503 error in general
            # is typically considered a transient error so we'll go ahead and
            # retry it.
            # A 500 may indicate transient error in Amazon S3
            # A 502 may be a transient error from a CDN like CloudFlare or CloudFront
            # A 520 or 527 - may indicate transient error in CloudFlare
            status_forcelist=[500, 502, 503, 520, 527],
            # Add a small amount of back off between failed requests in
            # order to prevent hammering the service.
            backoff_factor=0.25,
        )  # type: ignore
        self.resume_retries = resume_retries

        # Our Insecure HTTPAdapter disables HTTPS validation. It does not
        # support caching so we'll use it for all http:// URLs.
        # If caching is disabled, we will also use it for
        # https:// hosts that we've marked as ignoring
        # TLS errors for (trusted-hosts).
        insecure_adapter = InsecureHTTPAdapter(max_retries=retries)

        # We want to _only_ cache responses on securely fetched origins or when
        # the host is specified as trusted. We do this because
        # we can't validate the response of an insecurely/untrusted fetched
        # origin, and we don't want someone to be able to poison the cache and
        # require manual eviction from the cache to fix it.
        self._trusted_host_adapter: InsecureCacheControlAdapter | InsecureHTTPAdapter
        if cache:
            secure_adapter: _BaseHTTPAdapter = CacheControlAdapter(
                cache=SafeFileCache(cache),
                max_retries=retries,
                ssl_context=ssl_context,
            )
            self._trusted_host_adapter = InsecureCacheControlAdapter(
                cache=SafeFileCache(cache),
                max_retries=retries,
            )
        else:
            secure_adapter = HTTPAdapter(max_retries=retries, ssl_context=ssl_context)
            self._trusted_host_adapter = insecure_adapter

        self.mount("https://", secure_adapter)
        self.mount("http://", insecure_adapter)

        # Enable file:// urls
        self.mount("file://", LocalFSAdapter())

        for host in trusted_hosts:
            self.add_trusted_host(host, suppress_logging=True)

    def update_index_urls(self, new_index_urls: list[str]) -> None:
        """
        :param new_index_urls: New index urls to update the authentication
            handler with.
        """
        self.auth.index_urls = new_index_urls

    def add_trusted_host(
        self, host: str, source: str | None = None, suppress_logging: bool = False
    ) -> None:
        """
        :param host: It is okay to provide a host that has previously been
            added.
        :param source: An optional source string, for logging where the host
            string came from.
        """
        if not suppress_logging:
            msg = f"adding trusted host: {host!r}"
            if source is not None:
                msg += f" (from {source})"
            logger.info(msg)

        parsed_host, parsed_port = parse_netloc(host)
        if parsed_host is None:
            raise ValueError(f"Trusted host URL must include a host part: {host!r}")
        if (parsed_host, parsed_port) not in self.pip_trusted_origins:
            self.pip_trusted_origins.append((parsed_host, parsed_port))

        self.mount(
            build_url_from_netloc(host, scheme="http") + "/", self._trusted_host_adapter
        )
        self.mount(build_url_from_netloc(host) + "/", self._trusted_host_adapter)
        if not parsed_port:
            self.mount(
                build_url_from_netloc(host, scheme="http") + ":",
                self._trusted_host_adapter,
            )
            # Mount wildcard ports for the same host.
            self.mount(build_url_from_netloc(host) + ":", self._trusted_host_adapter)

    def iter_secure_origins(self) -> Generator[SecureOrigin, None, None]:
        pass

    def is_secure_origin(self, location: Link) -> bool:
        # Determine if this url used a secure transport mechanism
        pass

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        # Allow setting a default timeout on a session
        kwargs.setdefault("timeout", self.timeout)
        # Allow setting a default proxies on a session
        kwargs.setdefault("proxies", self.proxies)

        # Dispatch the actual request
        return super().request(method, url, *args, **kwargs)
