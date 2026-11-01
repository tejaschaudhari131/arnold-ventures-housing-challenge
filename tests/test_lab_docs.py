# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""The policy write-up stays on four pages and the SBOM matches the pins."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("write_sbom", ROOT / "scripts" / "write_sbom.py")
_SBOM = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_SBOM)
document = _SBOM.document
POLICY = ROOT / "docs" / "POLICY_SCENARIO_COMPARISON.md"
SBOM = ROOT / "docs" / "sbom.cdx.json"

# Four single-spaced pages is about 2,000–2,200 words. The test fails if the
# Lab comparison grows past a fourth page.
WORD_BUDGET = 2200


def test_policy_comparison_stays_within_four_pages():
    text = POLICY.read_text(encoding="utf-8")
    words = re.findall(r"[A-Za-z0-9+]+", text)
    assert len(words) <= WORD_BUDGET, f"{len(words)} words; budget is {WORD_BUDGET}"
    assert "Small Homes Policy Lab" in text
    assert "New Hampshire" in text
    assert "unknown" in text.lower()
    assert "close call" in text.lower()
    assert "111,016" in text
    assert "+6,048" in text
    assert "+12,916" in text
    from src.adu_fee_note import note_text
    from src.lab.policy_tables import allegheny_table, nh_table, pa_statewide_table

    assert note_text("docs") in text
    assert pa_statewide_table() in text
    assert allegheny_table() in text
    assert nh_table() in text
    assert "ADU vs parking flips in 20 percent" in text
    assert "core baseline (108,950)" in text
    method = (ROOT / "docs" / "SMALL_HOMES_LAB.md").read_text(encoding="utf-8")
    assert "fees come out ahead in 19% of the 200 assumption draws (38 of 200)" in method
    assert "This 10% is the flag threshold" in method
    model = (ROOT / "docs" / "MODEL_AND_ASSUMPTIONS.md").read_text(encoding="utf-8")
    assert "250 draws" in model and "defaults to 60" in model
    assert "the Lab uses 2,000" in model
    disclosures = (ROOT / "docs" / "DISCLOSURES.md").read_text(encoding="utf-8")
    assert "Building Permits Survey 2023-2025 county files (Lab)" in disclosures


def test_sbom_matches_requirements_pins():
    committed = json.loads(SBOM.read_text(encoding="utf-8"))
    generated = document(committed["metadata"]["timestamp"])
    assert generated["components"] == committed["components"]
    assert generated["metadata"]["component"]["licenses"] == [{"license": {"id": "Apache-2.0"}}]
    names = {row["name"] for row in committed["components"]}
    assert names == {"PyYAML", "pytest", "ruff"}
