# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Quant QA: shared 5+ completion share, baseline identity, Lab assumptions, recompute funnel."""

from __future__ import annotations

import pytest

from src.bundle import load_bundle
from src.lab.config import central_params
from src.lab.data import load_state
from src.lab.engine import evaluate_state
from src.lab.explain import _layer_row, assumption_catalog, recompute
from src.lab.results import _funnel
from src.model.engine import simulate_state
from src.web.server import App

P = central_params()


def test_lab_pipeline_reads_screening_mf_ratio():
    assert P["completion_ratio_mf"] == pytest.approx(0.90)
    assert P["completion_share_5plus"] == pytest.approx(0.84)
    state = load_state("PA")
    at_screening = evaluate_state(state, P)["statewide"]["baseline"]["pipeline_baseline"]
    old = dict(P)
    old["completion_ratio_mf"] = 0.84
    at_old = evaluate_state(state, old)["statewide"]["baseline"]["pipeline_baseline"]
    assert at_screening > at_old


def test_screening_baseline_matches_lab_pipeline():
    fixtures, assumptions = load_bundle()
    for code in ("PA", "NH"):
        screen = simulate_state(fixtures, assumptions, code)["baseline_completions_5yr"]
        pipeline = evaluate_state(load_state(code))["statewide"]["baseline"]["pipeline_baseline"]
        assert pipeline == pytest.approx(screen, abs=0.05)
    screen_pa = simulate_state(fixtures, assumptions, "PA")["baseline_completions_5yr"]
    assert round(screen_pa) == 113269


def test_lab_assumptions_publish_the_decided_mapping():
    lab = assumption_catalog()
    screen = App().assumption_catalog("PA")
    assert lab["completion_ratios"] == screen["completion_ratios"]
    assert lab["lab_completion_lot"]["status"] == "decided"
    assert lab["lab_completion_lot"]["mapping"] == screen["lab_completion_lot"]["mapping"]
    assert lab["completion_ratios"]["completion_ratio_mf"]["central"] == pytest.approx(0.90)
    assert lab["completion_ratios"]["completion_ratio_mf"]["tag"] == "assumed"


def test_recompute_funnel_matches_the_published_shape():
    state = load_state("PA")
    central = evaluate_state(state, P)
    row = _layer_row(
        "adu",
        central["statewide"],
        {"low": 0.0, "high": 1.0, "logical_low": 0.0, "logical_high": 1.0},
        0.0,
    )
    published = _funnel(central["statewide"]["adu"]["funnel"])
    assert row["funnel"] == published
    assert "go_ahead_share" in row["funnel"]
    assert "baseline_gross" in row["funnel"]
    county = _layer_row(
        "adu",
        central["counties"][0]["scenarios"],
        {"low": 0.0, "high": 1.0, "logical_low": 0.0, "logical_high": 1.0},
        0.0,
        keep_baseline=False,
    )
    assert "gross" in county["funnel"]
    assert "baseline_gross" not in county["funnel"]
    fees = _layer_row(
        "fees",
        central["statewide"],
        {"low": 0.0, "high": 1.0, "logical_low": 0.0, "logical_high": 1.0},
        0.0,
    )
    assert fees["funnel"] is None
    base = _layer_row(
        "baseline",
        central["statewide"],
        {"low": 0.0, "high": 1.0, "logical_low": 0.0, "logical_high": 1.0},
        0.0,
    )
    assert "funnel" not in base


def test_recompute_api_includes_the_funnel():
    doc = recompute("PA")
    funnel = doc["statewide"]["results"]["package"]["funnel"]
    assert funnel["scope"] == "package_combined_lots"
    assert abs(funnel["delivered"] + funnel["other_channels"] - doc["statewide"]["results"]["package"]["central"]) <= 0.2
    assert doc["statewide"]["results"]["parking"]["funnel"] is None
    assert "funnel" not in doc["statewide"]["results"]["baseline"]
    county = doc["counties"][0]["results"]["adu"]["funnel"]
    assert county is not None and "baseline_gross" not in county
