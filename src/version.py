# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Build stamp for the footer and /api/health.

The SHA prefers the hosting environment (Vercel or GitHub Actions) and falls
back to ``git rev-parse``. Lab fingerprints are read from the committed
results files so the endpoint does not recompute the envelope.
"""

from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB_SAMPLE = ROOT / "data" / "sample" / "lab"
STAMP_PATH = ROOT / "src" / "build_stamp.json"


def _git(*args: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.strip()


def _sha() -> str:
    for key in ("VERCEL_GIT_COMMIT_SHA", "GITHUB_SHA"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return _git("rev-parse", "HEAD")


def _stamp_file() -> dict[str, str]:
    """Written by scripts/write_build_stamp.py during the Vercel build.

    The serverless function does not have a git checkout, and Vercel does not
    set VERCEL_GIT_COMMIT_DATE, so the build records the commit date here.
    """
    if not STAMP_PATH.is_file():
        return {}
    try:
        doc = json.loads(STAMP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(doc, dict):
        return {}
    return {key: str(doc.get(key) or "") for key in ("sha", "date")}


def _date(sha: str) -> str:
    for key in ("VERCEL_GIT_COMMIT_DATE", "GITHUB_COMMIT_DATE"):
        value = os.environ.get(key, "").strip()
        if value:
            return value[:10]
    stamped = _stamp_file().get("date", "").strip()
    if stamped:
        return stamped[:10]
    if sha:
        committed = _git("log", "-1", "--format=%cs", sha)
        if committed:
            return committed
    return _git("log", "-1", "--format=%cs")


def _fingerprints() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(LAB_SAMPLE.glob("results_*.json")):
        code = path.stem.replace("results_", "")
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stamp = str(doc.get("fingerprint") or "")
        if stamp:
            found[code] = stamp
    return found


@lru_cache(maxsize=1)
def build_info() -> dict[str, object]:
    sha = _sha() or "unknown"
    short = sha[:7] if sha != "unknown" else "unknown"
    return {
        "sha": sha,
        "short_sha": short,
        "date": _date(sha if sha != "unknown" else ""),
        "fingerprints": _fingerprints(),
    }


def stamp_text() -> str:
    info = build_info()
    date = info["date"] or "undated"
    return f"{info['short_sha']} · {date}"


def stamp_html() -> str:
    return escape(stamp_text())
