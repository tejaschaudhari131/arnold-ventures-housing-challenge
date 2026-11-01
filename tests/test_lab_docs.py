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
    from src.adu_fee_note import note_text
    from src.lab.policy_tables import (
        allegheny_table,
        nh_background_adu_sentence,
        nh_table,
        pa_ranking_sentence,
        pa_statewide_table,
        sampling_error_sentence,
    )
    from src.lab.results import load_results
    from src.plain import homes, top_pair_tie_clause

    pa = load_results("PA", allow_compute=False)
    assert homes(pa["statewide"]["results"]["baseline"]["central"]) in text
    assert homes(pa["statewide"]["results"]["adu"]["central"], signed=True) in text
    assert homes(pa["statewide"]["results"]["missing_middle"]["central"], signed=True) in text
    assert note_text("docs") in text
    assert pa_statewide_table() in text
    assert allegheny_table() in text
    assert nh_table() in text
    assert sampling_error_sentence("PA") in text
    assert pa_ranking_sentence() in text
    from src.plain import is_draw_tie

    if is_draw_tie(pa["statewide"]["top_benchmark_pair"]):
        assert "Statistical tie" in text
    method = (ROOT / "docs" / "SMALL_HOMES_LAB.md").read_text(encoding="utf-8")
    clause = top_pair_tie_clause(pa["statewide"]["top_benchmark_pair"], pa["statewide"]["results"])
    assert clause in text
    assert clause in method
    nh_port = (ROOT / "docs" / "NH_PORTABILITY.md").read_text(encoding="utf-8")
    assert nh_background_adu_sentence() in nh_port
    assert "Saiz 2010" in text
    assert "core baseline (113,269)" in text
    draws = pa["draws"]
    n_flip = int(round(pa["statewide"]["top_benchmark_pair"]["flip_share"] * draws))
    assert f"{n_flip} of {draws:,}" in method or f"{n_flip} of {draws}" in method
    assert f"{draws:,} assumption draws" in method or f"{draws} assumption draws" in method
    assert "This 10% is the flag threshold" in method
    assert "4.1%" in method and "Auckland" in method
    model = (ROOT / "docs" / "MODEL_AND_ASSUMPTIONS.md").read_text(encoding="utf-8")
    assert "250 draws" in model and "defaults to 60" in model
    assert "the Lab uses 2,000" in model
    assert "Lab envelope is 2,000" in model
    disclosures = (ROOT / "docs" / "DISCLOSURES.md").read_text(encoding="utf-8")
    assert "Building Permits Survey 2023-2025 county files (Lab)" in disclosures


def test_sbom_matches_requirements_pins():
    committed = json.loads(SBOM.read_text(encoding="utf-8"))
    generated = document(committed["metadata"]["timestamp"])
    assert generated["components"] == committed["components"]
    assert generated["metadata"]["component"]["licenses"] == [{"license": {"id": "Apache-2.0"}}]
    assert generated["dependencies"] == committed["dependencies"]
    by_name = {row["name"]: row for row in committed["components"]}
    assert by_name["PyYAML"]["scope"] == "required"
    assert by_name["pytest"]["scope"] == "optional"
    assert by_name["ruff"]["scope"] == "optional"
    for dev_name in ("pluggy", "iniconfig", "packaging"):
        assert by_name[dev_name]["scope"] == "optional"
        assert by_name[dev_name]["licenses"]
