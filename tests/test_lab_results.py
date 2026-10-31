# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""The committed Lab results must be current and reproducible."""

import json

import pytest

from src.lab.config import LAB_STATES
from src.lab.data import load_state
from src.lab.engine import evaluate_state
from src.lab.results import fingerprint, sample_path


@pytest.mark.parametrize("code", sorted(LAB_STATES))
def test_committed_results_match_current_inputs(code):
    doc = json.loads(sample_path(code).read_text())
    assert doc["fingerprint"] == fingerprint(code), (
        f"data/sample/lab/results_{code}.json is stale; run python -m src.lab.results --write-sample"
    )


@pytest.mark.parametrize("code", sorted(LAB_STATES))
def test_committed_central_values_reproduce(code):
    doc = json.loads(sample_path(code).read_text())
    fresh = evaluate_state(load_state(code))
    for sid, row in doc["statewide"]["results"].items():
        field = "delivery" if sid == "baseline" else "delta"
        assert row["central"] == pytest.approx(fresh["statewide"][sid][field], abs=0.1)
    for county, fresh_county in zip(doc["counties"], fresh["counties"]):
        assert county["fips"] == fresh_county["fips"]
        assert county["results"]["adu"]["central"] == pytest.approx(fresh_county["scenarios"]["adu"]["delta"], abs=0.1)


@pytest.mark.parametrize("code", sorted(LAB_STATES))
def test_result_layers_are_reported_separately(code):
    doc = json.loads(sample_path(code).read_text())
    assert doc["draws"] >= 100
    for row in doc["statewide"]["results"].values():
        assert row["p10"] <= row["p50"] <= row["p90"]
        assert row["zoning_low"] <= row["zoning_high"]
        assert row["logical_low"] <= row["zoning_low"] + 0.1 and row["zoning_high"] <= row["logical_high"] + 0.1
        assert row["acs_moe"] >= 0
    top = doc["statewide"]["top_benchmark_pair"]
    assert top["leader"] == doc["statewide"]["benchmark_ranking"][0]
    assert len(doc["counties"]) == (67 if code == "PA" else 10)


def test_results_files_stay_small():
    total = sum(sample_path(code).stat().st_size for code in LAB_STATES)
    assert total < 400 * 1024
