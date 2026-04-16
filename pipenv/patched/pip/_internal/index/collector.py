"""
The main purpose of this module is to expose LinkCollector.collect_sources().
"""

from __future__ import annotations

import collections
import email.message
import functools
import itertools
import json
import logging
import os
import urllib.parse
from collections.abc import Iterable, MutableMapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from optparse import Values
from typing import (
    Callable,
    NamedTuple,
    Protocol,
)

from pipenv.patched.pip._vendor import requests
from pipenv.patched.pip._vendor.requests import Response
from pipenv.patched.pip._vendor.requests.exceptions import RetryError, SSLError

from pipenv.patched.pip._internal.exceptions import NetworkConnectionError
from pipenv.patched.pip._internal.models.link import Link
from pipenv.patched.pip._internal.models.search_scope import SearchScope
from pipenv.patched.pip._internal.network.session import PipSession
from pipenv.patched.pip._internal.network.utils import raise_for_status
from pipenv.patched.pip._internal.utils.filetypes import is_archive_file
from pipenv.patched.pip._internal.utils.misc import redact_auth_from_url
from pipenv.patched.pip._internal.utils.urls import url_to_path
from pipenv.patched.pip._internal.vcs import vcs

from .sources import CandidatesFromPage, LinkSource, build_source

logger = logging.getLogger(__name__)

ResponseHeaders = MutableMapping[str, str]


def _match_vcs_scheme(url: str) -> str | None:
    """Look for VCS schemes in the URL.

    Returns the matched VCS scheme, or None if there's no match.
    """
    pass


class _NotAPIContent(Exception):
    def __init__(self, content_type: str, request_desc: str) -> None:
        super().__init__(content_type, request_desc)
        self.content_type = content_type
        self.request_desc = request_desc


def _ensure_api_header(response: Response) -> None:
    """
    Check the Content-Type header to ensure the response contains a Simple
    API Response.

    Raises `_NotAPIContent` if the content type is not a valid content-type.
    """
    pass


class _NotHTTP(Exception):
    pass


def _ensure_api_response(url: str, session: PipSession) -> None:
    """
    Send a HEAD request to the URL, and ensure the response contains a simple
    API Response.

    Raises `_NotHTTP` if the URL is not available for a HEAD request, or
    `_NotAPIContent` if the content type is not a valid content type.
    """
    pass


def _get_simple_response(url: str, session: PipSession) -> Response:
    """Access an Simple API response with GET, and return the response.

    This consists of three parts:

    1. If the URL looks suspiciously like an archive, send a HEAD first to
       check the Content-Type is HTML or Simple API, to avoid downloading a
       large file. Raise `_NotHTTP` if the content type cannot be determined, or
       `_NotAPIContent` if it is not HTML or a Simple API.
    2. Actually perform the request. Raise HTTP exceptions on network failures.
    3. Check the Content-Type header to make sure we got a Simple API response,
       and raise `_NotAPIContent` otherwise.
    """
    pass


def _get_encoding_from_headers(headers: ResponseHeaders) -> str | None:
    """Determine if we have any encoding information in our headers."""
    pass


class CacheablePageContent:
    def __init__(self, page: IndexContent) -> None:
        assert page.cache_link_parsing
        self.page = page

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self.page.url == other.page.url

    def __hash__(self) -> int:
        return hash(self.page.url)


class ParseLinks(Protocol):
    def __call__(self, page: IndexContent) -> Iterable[Link]: ...


def with_cached_index_content(fn: ParseLinks) -> ParseLinks:
    """
    Given a function that parses an Iterable[Link] from an IndexContent, cache the
    function's result (keyed by CacheablePageContent), unless the IndexContent
    `page` has `page.cache_link_parsing == False`.
    """
    pass


@with_cached_index_content
def parse_links(page: IndexContent) -> Iterable[Link]:
    """
    Parse a Simple API's Index Content, and yield its anchor elements as Link objects.
    """

    content_type_l = page.content_type.lower()
    if content_type_l.startswith("application/vnd.pypi.simple.v1+json"):
        data = json.loads(page.content)
        for file in data.get("files", []):
            link = Link.from_json(file, page.url)
            if link is None:
                continue
            yield link
        return

    parser = HTMLLinkParser(page.url)
    encoding = page.encoding or "utf-8"
    parser.feed(page.content.decode(encoding))

    url = page.url
    base_url = parser.base_url or url
    for anchor in parser.anchors:
        link = Link.from_element(anchor, page_url=url, base_url=base_url)
        if link is None:
            continue
        yield link


@dataclass(frozen=True)
class IndexContent:
    """Represents one response (or page), along with its URL.

    :param encoding: the encoding to decode the given content.
    :param url: the URL from which the HTML was downloaded.
    :param cache_link_parsing: whether links parsed from this page's url
                               should be cached. PyPI index urls should
                               have this set to False, for example.
    """

    content: bytes
    content_type: str
    encoding: str | None
    url: str
    cache_link_parsing: bool = True

    def __str__(self) -> str:
        return redact_auth_from_url(self.url)


class HTMLLinkParser(HTMLParser):
    """
    HTMLParser that keeps the first base HREF and a list of all anchor
    elements' attributes.
    """

    def __init__(self, url: str) -> None:
        super().__init__(convert_charrefs=True)

        self.url: str = url
        self.base_url: str | None = None
        self.anchors: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pass

    def get_href(self, attrs: list[tuple[str, str | None]]) -> str | None:
        pass


def _handle_get_simple_fail(
    link: Link,
    reason: str | Exception,
    meth: Callable[..., None] | None = None,
) -> None:
    pass


def _make_index_content(
    response: Response, cache_link_parsing: bool = True
) -> IndexContent:
    pass


def _get_index_content(link: Link, *, session: PipSession) -> IndexContent | None:
    pass


class CollectedSources(NamedTuple):
    find_links: Sequence[LinkSource | None]
    index_urls: Sequence[LinkSource | None]


class LinkCollector:
    """
    Responsible for collecting Link objects from all configured locations,
    making network requests as needed.

    The class's main method is its collect_sources() method.
    """

    def __init__(
        self,
        session: PipSession,
        search_scope: SearchScope,
        index_lookup: dict[str, list[str]] | None = None,
    ) -> None:
        self.search_scope = search_scope
        self.session = session
        self.index_lookup = index_lookup or {}

    @classmethod
    def create(
        cls,
        session: PipSession,
        options: Values,
        suppress_no_index: bool = False,
        index_lookup: dict[str, list[str]] | None = None,
    ) -> LinkCollector:
        """
        :param session: The Session to use to make requests.
        :param suppress_no_index: Whether to ignore the --no-index option
            when constructing the SearchScope object.
        """
        index_urls = [options.index_url] + options.extra_index_urls
        if options.no_index and not suppress_no_index:
            logger.debug(
                "Ignoring indexes: %s",
                ",".join(redact_auth_from_url(url) for url in index_urls),
            )
            index_urls = []

        # Make sure find_links is a list before passing to create().
        find_links = options.find_links or []

        search_scope = SearchScope.create(
            find_links=find_links,
            index_urls=index_urls,
            no_index=options.no_index,
            index_lookup=index_lookup,
        )
        link_collector = LinkCollector(
            session=session,
            search_scope=search_scope,
            index_lookup=index_lookup,
        )
        return link_collector

    @property
    def find_links(self) -> list[str]:
        pass

    def fetch_response(self, location: Link) -> IndexContent | None:
        """
        Fetch an HTML page containing package links.
        """
        pass

    def collect_sources(
        self,
        project_name: str,
        candidates_from_page: CandidatesFromPage,
    ) -> CollectedSources:
        # The OrderedDict calls deduplicate sources by URL.
        index_url_sources = collections.OrderedDict(
            build_source(
                loc,
                candidates_from_page=candidates_from_page,
                page_validator=self.session.is_secure_origin,
                expand_dir=False,
                cache_link_parsing=False,
                project_name=project_name,
            )
            for loc in self.search_scope.get_index_urls_locations(project_name)
        ).values()
        find_links_sources = collections.OrderedDict(
            build_source(
                loc,
                candidates_from_page=candidates_from_page,
                page_validator=self.session.is_secure_origin,
                expand_dir=True,
                cache_link_parsing=True,
                project_name=project_name,
            )
            for loc in self.find_links
        ).values()

        if logger.isEnabledFor(logging.DEBUG):
            lines = [
                f"* {s.link}"
                for s in itertools.chain(find_links_sources, index_url_sources)
                if s is not None and s.link is not None
            ]
            lines = [
                f"{len(lines)} location(s) to search "
                f"for versions of {project_name}:"
            ] + lines
            logger.debug("\n".join(lines))

        return CollectedSources(
            find_links=list(find_links_sources),
            index_urls=list(index_url_sources),
        )
