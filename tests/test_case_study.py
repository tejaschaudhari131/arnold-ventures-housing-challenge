# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""The Allegheny walkthrough matches the engine and the committed note."""

from __future__ import annotations

from pathlib import Path

from src.model.case_study import build_case_study, render_markdown
from src.model.provenance import TAGS, untagged_numbers

ROOT = Path(__file__).resolve().parents[1]
NOTE = ROOT / "docs" / "CASE_STUDY_PA_ALLEGHENY.md"


def test_allegheny_case_separates_observed_assumed_and_calculated(bundle):
    fixtures, assumptions = bundle
    study = build_case_study(fixtures, assumptions)
    assert study["state"] == "PA"
    assert study["county_fips"] == "42003"
    assert study["county_name"] == "Allegheny County"
    assert study["focus_county"] == "Philadelphia County"
    assert study["counties_sum_to_state"] is True
    assert study["value_imputed"] is False
    assert study["observed"]["provenance"]["housing_units"] == "observed"
    assert study["observed"]["provenance"]["median_value"] == "observed"
    assert study["assumed"]["provenance"]["imputed_lot_feasible_share"] == "assumed"
    assert study["assumed"]["provenance"]["fee_challenge_baseline"] == "assumed"
    assert study["calculated"]["provenance"]["state_package"] == "calculated"
    assert study["calculated"]["county_sum_package"] == round(study["calculated"]["state_package"])
    assert study["calculated"]["allegheny_package"] > 0
    assert study["calculated"]["allegheny_share_of_package"] < 1
    tags = {field["tag"] for field in study["fields"]}
    assert {"observed", "assumed", "calculated"} <= tags
    assert tags <= set(TAGS)
    assert untagged_numbers(study) == []
    text = render_markdown(study)
    assert "Allegheny County" in text
    assert "Tejas Chaudhari" in text
    assert "Yoon Yik Ng" in text
    assert "Christopher Severns" in text
    assert "PlayHouse" in text
    assert "observed" in text and "assumed" in text and "calculated" in text
    assert NOTE.read_text(encoding="utf-8") == text


def test_map_points_cover_every_fixture_county():
    import json

    points = json.loads((ROOT / "data" / "sample" / "county_points.json").read_text(encoding="utf-8"))
    from src.data.schema import load_fixtures

    fixtures = load_fixtures()
    indexed = {point["fips"]: point for point in points["points"]}
    for state in fixtures["states"].values():
        for county in state["counties"]:
            point = indexed[county["fips"]]
            assert 18 <= point["lat"] <= 48
            assert -162 <= point["lon"] <= -66
            assert point["state"] == state["code"]
