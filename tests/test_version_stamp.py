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


def test_sha_comes_from_the_stamp_when_env_and_git_are_missing(monkeypatch):
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.delenv("VERCEL_GIT_COMMIT_DATE", raising=False)
    monkeypatch.delenv("GITHUB_COMMIT_DATE", raising=False)
    monkeypatch.setattr(version, "_git", lambda *_args: "")
    monkeypatch.setattr(version, "_stamp_file", lambda: {"sha": "abc1234def", "date": "2026-11-01"})
    _clear()
    try:
        info = version.build_info()
        assert info["sha"] == "abc1234def"
        assert info["short_sha"] == "abc1234"
        assert info["date"] == "2026-11-01"
    finally:
        _clear()


def test_garbage_date_is_rejected(monkeypatch):
    monkeypatch.setenv("VERCEL_GIT_COMMIT_DATE", "garbage")
    monkeypatch.delenv("GITHUB_COMMIT_DATE", raising=False)
    monkeypatch.setattr(version, "_stamp_file", lambda: {"sha": "abc1234", "date": "2026-11-01"})
    monkeypatch.setattr(version, "_sha", lambda: "abc1234")
    monkeypatch.setattr(version, "_git", lambda *_args: "1999-01-01")
    _clear()
    try:
        assert version.build_info()["date"] == "2026-11-01"
        assert "garbage" not in version.stamp_text()
    finally:
        _clear()


def test_unknown_sha_does_not_use_the_head_date(monkeypatch):
    monkeypatch.delenv("VERCEL_GIT_COMMIT_DATE", raising=False)
    monkeypatch.delenv("GITHUB_COMMIT_DATE", raising=False)
    monkeypatch.setattr(version, "_stamp_file", lambda: {})
    monkeypatch.setattr(version, "_sha", lambda: "not-in-this-repo")

    def git(*args):
        if args[:3] == ("log", "-1", "--format=%cs") and len(args) == 3:
            return "1999-01-01"
        return ""

    monkeypatch.setattr(version, "_git", git)
    _clear()
    try:
        assert version.build_info()["date"] == ""
        assert "1999-01-01" not in version.stamp_text()
        assert version.stamp_text().endswith("undated")
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
