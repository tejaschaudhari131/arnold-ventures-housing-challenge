# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""HTTPS downloads that re-check the host allowlist after every redirect."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse


class FetchDenied(Exception):
    """The URL, or a redirect, is not an allowlisted HTTPS host."""


def assert_allowed(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in allowed_hosts:
        raise FetchDenied("Download URL is not an allowlisted HTTPS host.")


def _opener(allowed_hosts: frozenset[str]) -> urllib.request.OpenerDirector:
    class _Handler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
            assert_allowed(newurl, allowed_hosts)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(_Handler)


def open_url(
    url: str,
    allowed_hosts: frozenset[str],
    timeout: int,
    user_agent: str,
) -> Any:
    assert_allowed(url, allowed_hosts)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        response = _opener(allowed_hosts).open(request, timeout=timeout)
    except FetchDenied:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchDenied("Download failed.") from exc
    assert_allowed(response.geturl(), allowed_hosts)
    return response


def fetch_bytes(
    url: str,
    allowed_hosts: frozenset[str],
    timeout: int,
    user_agent: str,
    *,
    require_status: int | None = None,
) -> bytes:
    with open_url(url, allowed_hosts, timeout, user_agent) as response:
        if require_status is not None and response.status != require_status:
            raise FetchDenied("Download returned an unexpected status.")
        return response.read()
