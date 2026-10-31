# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Vercel entry point. Reuses the existing stdlib handler unchanged."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.web.server import App, make_handler  # noqa: E402

_Handler = make_handler(App())


def _restore_path(raw: str) -> str:
    """vercel.json rewrites every URL to /api/index?__path=<original>. Undo that."""
    parsed = urlparse(raw)
    query = parse_qs(parsed.query, keep_blank_values=True)
    original = query.pop("__path", [None])[0]
    if original is None:
        return raw
    path = "/" + original.lstrip("/")
    rest = urlencode(query, doseq=True)
    return path + ("?" + rest if rest else "")


class handler(_Handler):  # noqa: N801  (Vercel looks for this exact name)
    def do_GET(self) -> None:  # noqa: N802
        self.path = _restore_path(self.path)
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self.path = _restore_path(self.path)
        super().do_POST()
