# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Identities the model overview promises."""

from __future__ import annotations

import pytest

from src.data.schema import CHALLENGE_STATES
from src.model.crossval import cross_validate_state
from src.model.engine import _combined_row, evaluate_county, simulate_state
from src.model.sensitivity import monte_carlo


def _incremental(result, scenario):
    return result["scenarios"][scenario]["incremental_completions"]


def test_neutral_policy_adds_nothing(bundle):
    fixtures, assumptions = bundle
    result = simulate_state(fixtures, assumptions, "PA", neutral=True)
    for scenario in ("adu", "missing_middle", "tod", "parking", "fees", "combined"):
        assert abs(_incremental(result, scenario)) < 1e-6
        assert abs(result["scenarios"][scenario]["incremental_permits"]) < 1e-6


def test_baseline_is_five_times_the_permit_run_rate(bundle):
    fixtures, assumptions = bundle
    for code in CHALLENGE_STATES:
        state = fixtures["states"][code]
        result = simulate_state(fixtures, assumptions, code)
        annual = state["bps_sf"] + state["bps_two"] + state["bps_three_four"] + state["bps_five_plus"]
        assert result["baseline_permits_5yr"] == pytest.approx(annual * 5, rel=1e-9)
        assert result["scenarios"]["baseline"]["completions_5yr"] == pytest.approx(result["baseline_completions_5yr"])
        assert result["scenarios"]["baseline"]["annualized_completions"] == pytest.approx(
            result["baseline_completions_5yr"] / 5
        )
        assert result["baseline_completions_5yr"] < result["baseline_permits_5yr"]


@pytest.mark.parametrize("code", CHALLENGE_STATES)
def test_every_state_is_finite_and_counties_sum_to_the_state(bundle, code):
    fixtures, assumptions = bundle
    result = simulate_state(fixtures, assumptions, code)
    columns = {
        "baseline_completions": round(result["baseline_completions_5yr"]),
        "adu": round(_incremental(result, "adu")),
        "missing_middle": round(_incremental(result, "missing_middle")),
        "tod": round(_incremental(result, "tod")),
        "parking": round(_incremental(result, "parking")),
        "fees": round(_incremental(result, "fees")),
        "combined": round(_incremental(result, "combined")),
    }
    for column, expected in columns.items():
        assert sum(county[column] for county in result["counties"]) == expected
    for scenario in result["scenarios"]:
        for key in ("permits_5yr", "completions_5yr", "incremental_completions", "lift_pct"):
            value = result["scenarios"][scenario][key]
            assert value == value and abs(value) < 1e12
    for scenario in ("adu", "missing_middle", "tod", "parking", "fees", "combined"):
        assert _incremental(result, scenario) >= -1e-6
    parts = result["components"]
    assembled = parts["combined_adu"] + parts["combined_mm"] + parts["combined_tod"]
    assembled += parts["combined_parking"] + parts["combined_fees"]
    assert assembled == pytest.approx(_incremental(result, "combined"), abs=1e-4)


def test_fee_cut_and_elasticity_raise_production(bundle):
    fixtures, assumptions = bundle
    low = simulate_state(fixtures, assumptions, "PA", {"fee_reduction_fraction": 0.25})
    high = simulate_state(fixtures, assumptions, "PA", {"fee_reduction_fraction": 0.75})
    assert _incremental(high, "fees") > _incremental(low, "fees")
    inelastic = simulate_state(fixtures, assumptions, "VA", {"supply_elasticity": 0.35})
    elastic = simulate_state(fixtures, assumptions, "VA", {"supply_elasticity": 1.60})
    assert _incremental(elastic, "fees") > _incremental(inelastic, "fees")
    assert _incremental(elastic, "parking") > _incremental(inelastic, "parking")


def test_higher_far_raises_uncapped_tod(bundle):
    """The absorption cap can hide the FAR response. The county pro forma itself rises."""
    fixtures, assumptions = bundle
    state = fixtures["states"]["VA"]
    county = max(state["counties"], key=lambda item: item["median_value"])
    params = assumptions.resolve("VA")
    indexes = {"sf": state["cost_index_sf"], "mf": state["cost_index_mf"]}
    national = fixtures["national"]
    low_params = dict(params)
    low_params["tod_far_policy"] = 2.2
    high_params = dict(params)
    high_params["tod_far_policy"] = 5.5
    low = evaluate_county(county, low_params, indexes, national, 0.9, 8000.0, False, False)
    high = evaluate_county(county, high_params, indexes, national, 0.9, 8000.0, False, False)
    assert high["tod_completions"] > low["tod_completions"]


def test_higher_prices_raise_adu_adoption(bundle):
    fixtures, assumptions = bundle
    soft = simulate_state(fixtures, assumptions, "TN", {"price_shock": 0.80})
    firm = simulate_state(fixtures, assumptions, "TN", {"price_shock": 1.25})
    assert _incremental(firm, "adu") > _incremental(soft, "adu")


def test_combined_row_removes_walkshed_overlap():
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
    assert row["parking"] == pytest.approx(8.0)
    assert row["fees"] == pytest.approx(8.0)
    assert row["adu"] == pytest.approx(30.0 * (1.0 - 52.0 / 500.0))
    assert row["mm"] < county["mm_completions"]
    assert row["parking"] < county["parking_completions"]
    assert row["completions"] == pytest.approx(
        row["adu"] + row["mm"] + row["tod"] + row["parking"] + row["fees"]
    )


def test_new_hampshire_has_almost_no_transit_oriented_yield(bundle):
    fixtures, assumptions = bundle
    result = simulate_state(fixtures, assumptions, "NH")
    assert result["walkshed_sqmi"] < 5
    assert _incremental(result, "tod") < 50


def test_cross_validation_runs_on_connecticut(bundle):
    fixtures, assumptions = bundle
    report = cross_validate_state(fixtures, assumptions, "CT", draws=12)
    assert "adu" in report["scenarios"]
    assert report["lot_full"] > 0
    assert report["band_width_full"] >= 0
    assert report["combined_band_imputed"]["draws"] == 12


def test_monte_carlo_is_deterministic(bundle):
    fixtures, assumptions = bundle
    first = monte_carlo(fixtures, assumptions, "RI", "fees", draws=20, seed=7)
    second = monte_carlo(fixtures, assumptions, "RI", "fees", draws=20, seed=7)
    assert first["p50"] == second["p50"]
    assert first["p10"] <= first["p50"] <= first["p90"]
