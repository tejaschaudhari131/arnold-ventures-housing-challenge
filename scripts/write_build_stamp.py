#!/usr/bin/env python3
# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Record the git SHA and commit date for the Vercel function bundle.

Run during the build, before the serverless function is packaged. The
function itself often has neither git nor VERCEL_GIT_COMMIT_DATE.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = ROOT / "src" / "build_stamp.json"


def _git(*args: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.strip()


def main() -> int:
    sha = (
        os.environ.get("VERCEL_GIT_COMMIT_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or _git("rev-parse", "HEAD")
    )
    date = (
        os.environ.get("VERCEL_GIT_COMMIT_DATE", "").strip()
        or os.environ.get("GITHUB_COMMIT_DATE", "").strip()
    )
    if sha and not date:
        date = _git("log", "-1", "--format=%cs", sha)
    if not date:
        date = _git("log", "-1", "--format=%cs")
    date = date[:10]
    if not sha or not date:
        print("Could not record a build stamp (missing sha or commit date).", file=sys.stderr)
        return 1
    STAMP.write_text(json.dumps({"sha": sha, "date": date}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {STAMP} ({sha[:7]} {date})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
