# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Phase 4 checks that the reference patch left behind flags (PHASE4_SPEC §7)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src.bundle import load_bundle
from src.lab.config import ROOT
from src.lab.options import adu_hazard_rate
from src.lab.engine import timing_share as lab_timing_share
from src.model.engine import _active_window, _pipeline_fraction, segment_fee_savings, simulate_state

FX, ASSUMPTIONS = load_bundle()


def _package(state: str, overrides: dict | None = None, include_build_lags: bool = True) -> tuple[float, dict]:
    result = simulate_state(
        FX,
        ASSUMPTIONS,
        state,
        overrides,
        include_build_lags=include_build_lags,
    )
    return float(result["scenarios"]["combined"]["incremental_completions"]), result


def test_option_b_reference():
    """Rejected D7 alternative: keep the ratios and drop the build lags."""
    value, _result = _package("PA", include_build_lags=False)
    assert abs(value - 58002) <= 1


def test_mf_bound():
    at_090, _result = _package("PA")
    at_084, _ignored = _package("PA", {"completion_ratio_mf": 0.84})
    assert abs(at_090 - 46219) <= 1
    assert abs(at_090 - at_084) / at_084 < 0.01


@pytest.mark.parametrize(
    ("state", "expected"),
    [("PA", "BPS 2023-2025"), ("NH", "BPS 2023-2025"), ("VA", "BPS 2022-2024")],
)
def test_permit_vintage_label(state, expected):
    _value, result = _package(state)
    assert result["meta"]["permit_vintage"] == expected
    assert result["meta"]["permit_source"]


def test_lab_parking_range():
    document = yaml.safe_load((ROOT / "config" / "lab" / "assumptions.yaml").read_text(encoding="utf-8"))
    parking = document["params"]["parking_market_urban"]
    assert parking["high"] == 1.35
    assert parking["low"] <= parking["central"] <= parking["high"]
    text = (ROOT / "config" / "lab" / "scenarios.yaml").read_text(encoding="utf-8")
    assert not re.search(r"0\.5 spaces per home in\s+urban", text)
    assert re.search(r"0\.9 spaces per home in\s+urban", text)


def test_windows_are_zero_when_the_horizon_is_inside_the_lags():
    params = ASSUMPTIONS.resolve("PA")
    params["horizon_years"] = 1.0
    assert _active_window(params, "adoption_lag_years", "build_lag_adu_years") == 0.0
    assert _pipeline_fraction(params, "mf") == 0.0
    assert lab_timing_share(0.2, 1.0, 1.0, 0.75) == 0.0


def test_fee_savings_are_half_the_segment_fee():
    params = ASSUMPTIONS.resolve("PA")
    assert params["fee_reduction_fraction"] == pytest.approx(0.5)
    for name in ("sf_fee_per_unit", "mm_fee_per_unit", "tod_fee_per_unit"):
        assert segment_fee_savings(params[name], params) == pytest.approx(0.5 * params[name])


def test_f_ca_scales_the_adu_hazard_as_one_over_x():
    from src.lab.config import central_params

    params = central_params()
    base = adu_hazard_rate(params)
    wider = dict(params)
    wider["adu_feasible_share_ca"] = 0.25
    assert adu_hazard_rate(wider) == pytest.approx(base * (params["adu_feasible_share_ca"] / 0.25))


def test_methods_name_county_level_best_use():
    text = Path("docs/MODEL_AND_ASSUMPTIONS.md").read_text(encoding="utf-8")
    assert "county-level best use" in text
