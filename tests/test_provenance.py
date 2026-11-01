# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Every published number carries an observed, assumed, or calculated tag."""

from __future__ import annotations

import csv
import io
import json

from src.data.schema import CHALLENGE_STATES
from src.export.report import comparison_rows, simulate_many, to_csv, to_json, to_markdown
from src.model.crossval import cross_validate_state
from src.model.engine import simulate_state
from src.model.provenance import TAGS, untagged_numbers
from src.model.sensitivity import monte_carlo, tornado


def test_every_simulation_field_is_tagged(bundle):
    fixtures, assumptions = bundle
    for code in CHALLENGE_STATES:
        result = simulate_state(fixtures, assumptions, code)
        missing = untagged_numbers(result)
        assert missing == [], missing
        assert result["provenance"]["baseline_completions_5yr"] == "calculated"
        assert result["provenance"]["tier"] == "classification"
        assert result["provenance"]["completeness"] == "calculated"
        for scenario in result["scenarios"].values():
            assert scenario["provenance"]["incremental_completions"] == "calculated"
            for step in scenario["trace"]:
                assert step["provenance"]["result"] == "calculated"
                assert step["inputs"]
                assert {item["tag"] for item in step["inputs"]} <= set(TAGS)
        for county in result["counties"]:
            assert county["provenance"]["housing_units"] == "observed"
            assert county["provenance"]["baseline_completions"] == "calculated"
            if county["value_imputed"]:
                assert county["provenance"]["median_value"] == "assumed"
            else:
                assert county["provenance"]["median_value"] == "observed"


def test_pennsylvania_lot_screen_is_assumed_and_connecticut_is_calculated(bundle):
    fixtures, assumptions = bundle
    pennsylvania = simulate_state(fixtures, assumptions, "PA")
    connecticut = simulate_state(fixtures, assumptions, "CT")
    assert pennsylvania["lot_feasible_tag"] == "assumed"
    assert pennsylvania["provenance"]["lot_feasible_share"] == "assumed"
    assert connecticut["lot_feasible_tag"] == "calculated"
    assert connecticut["provenance"]["lot_feasible_share"] == "calculated"


def test_csv_and_json_exports_tag_every_number(bundle):
    fixtures, assumptions = bundle
    results = simulate_many(fixtures, assumptions, ["RI", "PA"])
    rows = comparison_rows(results)
    table = list(csv.DictReader(io.StringIO(to_csv(results))))
    assert table
    for row in rows:
        for key, value in row.items():
            if key.endswith("_provenance") or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            assert row[f"{key}_provenance"] in TAGS
    assert any(row.get("completeness_source") == "docs/DATA_PROVENANCE.md" for row in rows)
    assert any(row.get("tier_provenance") == "classification" for row in rows)
    assert any(row.get("completeness_provenance") == "calculated" for row in rows)
    assert any("annualized_level" in row and "annualized_increment" in row for row in rows)
    for exported in table:
        for key, value in exported.items():
            if key.endswith("_provenance") or value in {"True", "False"}:
                continue
            try:
                float(value)
            except ValueError:
                continue
            assert exported[f"{key}_provenance"] in TAGS
    payload = json.loads(to_json(results))
    assert set(payload["provenance_legend"]) == set(TAGS)
    for result in payload["results"]:
        assert untagged_numbers(result) == []
    markdown = to_markdown(results)
    assert "[calculated]" in markdown
    assert "[observed]" in markdown


def test_sensitivity_and_crosscheck_numbers_are_tagged(bundle):
    fixtures, assumptions = bundle
    chart = tornado(fixtures, assumptions, "RI", "fees")
    band = monte_carlo(fixtures, assumptions, "RI", "fees", draws=8, seed=3)
    report = cross_validate_state(fixtures, assumptions, "RI", draws=4)
    assert untagged_numbers(chart) == []
    assert untagged_numbers(band) == []
    assert untagged_numbers(report) == []
    assert band["provenance"]["p10"] == "calculated"
    assert band["provenance"]["seed"] == "assumed"
    assert "crosses_zero" in band
