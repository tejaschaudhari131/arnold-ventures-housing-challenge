# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""The footer date stays filled when Vercel does not set VERCEL_GIT_COMMIT_DATE."""

from __future__ import annotations

import src.version as version


def _clear():
    version.build_info.cache_clear()


def test_date_uses_the_build_stamp_when_git_and_env_are_missing(monkeypatch):
    monkeypatch.delenv("VERCEL_GIT_COMMIT_DATE", raising=False)
    monkeypatch.delenv("GITHUB_COMMIT_DATE", raising=False)
    monkeypatch.setattr(version, "_git", lambda *_args: "")
    monkeypatch.setattr(version, "_stamp_file", lambda: {"sha": "abc1234def", "date": "2026-11-01"})
    monkeypatch.setattr(version, "_sha", lambda: "abc1234def")
    _clear()
    try:
        info = version.build_info()
        assert info["date"] == "2026-11-01"
        assert version.stamp_text() == "abc1234 · 2026-11-01"
    finally:
        _clear()


def test_date_uses_git_when_there_is_no_build_stamp(monkeypatch):
    monkeypatch.delenv("VERCEL_GIT_COMMIT_DATE", raising=False)
    monkeypatch.delenv("GITHUB_COMMIT_DATE", raising=False)
    monkeypatch.setattr(version, "_stamp_file", lambda: {})
    monkeypatch.setattr(version, "_sha", lambda: "deadbeef")
    monkeypatch.setattr(version, "_git", lambda *args: "2026-10-25" if "log" in args else "")
    _clear()
    try:
        assert version.build_info()["date"] == "2026-10-25"
    finally:
        _clear()
