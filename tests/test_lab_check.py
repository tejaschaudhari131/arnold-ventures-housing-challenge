# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""The Lab fingerprint check exits nonzero when the committed file is stale."""

from __future__ import annotations

from pathlib import Path

from src.lab.check import check_codes, main


def test_check_matches_committed_fingerprints():
    assert main(["--states", "PA,NH"]) == 0


def test_readme_documents_regen_time_and_hud_fmr():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    provenance = (Path(__file__).resolve().parents[1] / "docs" / "DATA_PROVENANCE.md").read_text(encoding="utf-8")
    assert "about 7 minutes" in readme
    assert "python -m src.lab.check" in readme
    assert "https://www.huduser.gov/portal/datasets/fmr/fmr2026/FY26_FMRs.xlsx" in readme
    assert "2026-10-31" in readme
    assert "not a model input" in readme
    assert "https://www.huduser.gov/portal/datasets/fmr/fmr2026/FY26_FMRs.xlsx" in provenance
    assert "not a model input" in provenance


def test_check_exits_nonzero_when_the_hash_changes(monkeypatch, capsys):
    monkeypatch.setattr("src.lab.check.fingerprint", lambda _code: "0" * 16)
    assert check_codes(["PA"]) == 1
    assert "MISMATCH" in capsys.readouterr().out
