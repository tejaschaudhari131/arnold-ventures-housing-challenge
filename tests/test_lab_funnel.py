# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Lab lot funnel (PHASE4_SPEC §6b) with the D12 completion ratios inside the solve."""

from __future__ import annotations

import pytest

from src.lab.data import load_state
from src.lab.engine import evaluate_state
from src.lab.results import compute

SCENARIOS = ["baseline", "adu", "missing_middle", "parking", "fees", "package"]
_CACHE: dict = {}
_DOCS: dict = {}


def run(state: str) -> dict:
    if state not in _CACHE:
        _CACHE[state] = evaluate_state(load_state(state), scenarios=SCENARIOS)
    return _CACHE[state]


def close(left: float, right: float, rel: float = 1e-9, abs_: float = 1e-6) -> bool:
    return abs(left - right) <= max(abs_, rel * max(abs(left), abs(right)))


@pytest.mark.parametrize("state", ["PA", "NH"])
@pytest.mark.parametrize("sid", ["adu", "missing_middle", "package"])
def test_delivered_plus_other_equals_delta(state, sid):
    row = run(state)["statewide"][sid]
    funnel = row["funnel"]
    assert close(funnel["delivered"] + funnel["other_channels"], row["delta"])


@pytest.mark.parametrize("state", ["PA", "NH"])
@pytest.mark.parametrize("sid", ["adu", "missing_middle"])
def test_standalone_lot_reform_delivered_is_full_delta(state, sid):
    row = run(state)["statewide"][sid]
    funnel = row["funnel"]
    assert funnel["other_channels"] == 0.0
    assert close(funnel["delivered"], row["delta"])


@pytest.mark.parametrize("state", ["PA", "NH"])
@pytest.mark.parametrize("sid", ["adu", "missing_middle", "package"])
@pytest.mark.parametrize("level", [None, "gross", "baseline_gross"])
def test_identity_go_completion_timing(state, sid, level):
    funnel = run(state)["statewide"][sid]["funnel"]
    stage = funnel if level is None else funnel[level]
    assert close(
        stage["go_ahead"] * stage["completion"] * stage["timing"] * stage["homes_per_lot"],
        stage["delivered"],
    )
    assert close(stage["go_ahead_share"] * stage["pays"], stage["go_ahead"])


@pytest.mark.parametrize("state", ["PA", "NH"])
@pytest.mark.parametrize("sid", ["adu", "missing_middle", "package"])
def test_gross_funnel_monotone(state, sid):
    gross = run(state)["statewide"][sid]["funnel"]["gross"]
    assert gross["legal_fits"] >= gross["pays"] >= gross["go_ahead"] >= gross["finishing"] >= 0
    assert 0 < gross["timing"] <= 1


@pytest.mark.parametrize("state", ["PA", "NH"])
@pytest.mark.parametrize("sid", ["parking", "fees"])
def test_null_for_non_lot_reforms(state, sid):
    assert run(state)["statewide"][sid]["funnel"] is None
    assert all(county["scenarios"][sid]["funnel"] is None for county in run(state)["counties"])


@pytest.mark.parametrize("state", ["PA", "NH"])
def test_county_sum_matches_state(state):
    result = run(state)
    for sid in ["adu", "missing_middle", "package"]:
        county_sum = sum(county["scenarios"][sid]["funnel"]["delivered"] for county in result["counties"])
        assert close(county_sum, result["statewide"][sid]["funnel"]["delivered"])


def test_lab_packages_after_lot_completion():
    """D12 re-solves inside the engine. PA matches the first-order 13,128.
    NH is higher because the detached-ADU effective date is 2025-07-01.
    """
    assert round(run("PA")["statewide"]["package"]["delta"]) == 13128
    assert round(run("NH")["statewide"]["package"]["delta"]) == 2109


def doc(state: str) -> dict:
    if state not in _DOCS:
        _DOCS[state] = compute(state, draws=20)
    return _DOCS[state]


@pytest.mark.parametrize("state", ["PA", "NH"])
def test_published_paths(state):
    published = doc(state)
    for sid in ["adu", "missing_middle", "package"]:
        funnel = published["statewide"]["results"][sid]["funnel"]
        central = published["statewide"]["results"][sid]["central"]
        assert abs(funnel["delivered"] + funnel["other_channels"] - central) <= 0.2
        assert abs(funnel["go_ahead"] * funnel["completion"] * funnel["timing"] * funnel["homes_per_lot"] - funnel["delivered"]) <= 0.2
        assert "go_ahead_share" in funnel
        for county in published["counties"]:
            county_funnel = county["results"][sid]["funnel"]
            assert county_funnel is not None
            assert abs(county_funnel["delivered"] + county_funnel["other_channels"] - county["results"][sid]["central"]) <= 0.2
    for sid in ["parking", "fees"]:
        assert published["statewide"]["results"][sid]["funnel"] is None
        assert all(county["results"][sid]["funnel"] is None for county in published["counties"])
    assert "funnel" not in published["statewide"]["results"]["baseline"]
