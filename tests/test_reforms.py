# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Reform toggles change the package and leave the published all-on case alone."""

from __future__ import annotations

import pytest

from src.model.engine import REFORM_IDS, _combined_row, simulate_state


def _package(result):
    return result["scenarios"]["combined"]["incremental_completions"]


def test_full_weights_match_the_published_package(bundle):
    fixtures, assumptions = bundle
    plain = simulate_state(fixtures, assumptions, "NH")
    weighted = simulate_state(
        fixtures,
        assumptions,
        "NH",
        reform_weights={name: 1.0 for name in REFORM_IDS},
    )
    assert _package(weighted) == pytest.approx(_package(plain))
    assert weighted["components"]["combined_mm"] == pytest.approx(plain["components"]["combined_mm"])


def test_switching_every_reform_off_adds_nothing(bundle):
    fixtures, assumptions = bundle
    result = simulate_state(
        fixtures,
        assumptions,
        "PA",
        reform_weights={name: 0.0 for name in REFORM_IDS},
    )
    assert _package(result) == pytest.approx(0.0, abs=1e-6)
    assert result["scenarios"]["adu"]["incremental_completions"] > 0


def test_turning_transit_off_returns_walkshed_homes_to_missing_middle(bundle):
    fixtures, assumptions = bundle
    full = simulate_state(fixtures, assumptions, "VA")
    without_tod = simulate_state(fixtures, assumptions, "VA", reform_weights={"tod": 0.0})
    assert without_tod["components"]["combined_tod"] == pytest.approx(0.0, abs=1e-6)
    assert without_tod["components"]["combined_mm"] >= full["components"]["combined_mm"] - 1e-6


def test_partial_weight_scales_a_standalone_fee_piece(bundle):
    fixtures, assumptions = bundle
    full = simulate_state(fixtures, assumptions, "AZ", reform_weights={name: 0.0 for name in REFORM_IDS} | {"fees": 1.0})
    half = simulate_state(fixtures, assumptions, "AZ", reform_weights={name: 0.0 for name in REFORM_IDS} | {"fees": 0.5})
    assert half["components"]["combined_fees"] == pytest.approx(0.5 * full["components"]["combined_fees"], rel=1e-6)


def test_default_combined_row_still_removes_overlap():
    county = {
        "housing_units": 1000.0,
        "walkshed_units": 200.0,
        "mm_completions": 100.0,
        "mm_permits": 110.0,
        "mm_homes_used": 40.0,
        "tod_completions": 50.0,
        "tod_permits": 80.0,
        "tod_homes_removed": 20.0,
        "merchant_cap": 1000.0,
        "sf_stock": 500.0,
        "adu_completions": 30.0,
        "adu_permits": 32.0,
        "adu_capped": False,
        "parking_completions": 10.0,
        "parking_permits": 12.0,
        "fee_completions": 8.0,
        "fee_permits": 9.0,
    }
    row = _combined_row(county, county)
    assert row["mm"] == pytest.approx(80.0)
    assert row["tod"] == pytest.approx(50.0)
