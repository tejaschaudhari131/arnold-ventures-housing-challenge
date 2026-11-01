# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Package resolution, unknown-not-zero, close calls, and MOE separation."""

import copy
import json

import pytest

from src.lab.config import SAMPLE_DIR, central_params, param_spec
from src.lab.data import build_state, load_state
from src.lab.engine import evaluate_county, evaluate_state, package_decomposition, package_variants
from src.lab.uncertainty import (
    ELASTICITY_TO_SIGMA,
    compare_pair,
    county_evaluator,
    envelope_params,
    run_envelope,
    run_moe,
    sample_params,
    summarize,
    switching_value,
    what_would_change,
    zoning_bounds,
    zoning_runs,
)

P = central_params()


@pytest.fixture(scope="module")
def pa_central():
    return evaluate_state(load_state("PA"), P, variants=package_variants(P))


@pytest.fixture(scope="module")
def nh_zoning():
    return zoning_runs(load_state("NH"), P)


# ------------------------------------------------ combined-package resolution
def test_package_legalization_is_resolved_not_summed(pa_central):
    d = package_decomposition(pa_central)
    # ADUs and 2–6 homes compete for the same lots, so legalizing both is
    # worth less than the two separate results added together.
    assert d["legalization_resolved"] < d["legalization_if_summed"]
    assert d["competition_loss"] < 0
    # Competition can put the resolved total under the larger standalone when
    # the worse option takes lots the better one would have used.
    steps = d["legalization_resolved"] + d["fee_cut_step"] + d["parking_step"]
    assert steps == pytest.approx(d["package"])
    assert d["interaction"] == pytest.approx(d["package"] - d["sum_of_separate"])


def test_package_resolution_holds_in_every_county(pa_central):
    for county in pa_central["counties"]:
        rows = county["scenarios"]
        legal = rows["package_legal_only"]["delta"]
        assert legal <= rows["adu"]["delta"] + rows["missing_middle"]["delta"] + 1e-6, county["name"]
        lots = sum(rows["package"]["lots_by_option"].values())
        assert lots <= county["hosts"] * 1.0000001  # one option per lot, at most


# ------------------------------------------------------- unknown is not zero
def test_unknown_zoning_counties_still_gain_and_carry_bounds(pa_central):
    state = load_state("PA")
    adams_index = [c.fips for c in state.counties].index("42001")
    adams = pa_central["counties"][adams_index]
    assert adams["coverage"]["adu"] == 0.0
    assert adams["scenarios"]["adu"]["delta"] > 0
    runs = zoning_runs(state, P)
    bounds = zoning_bounds(runs, index=adams_index)["adu"]
    assert bounds["low"] < adams["scenarios"]["adu"]["delta"] < bounds["high"]
    # Only if every unknown lot already allowed ADUs would the reform add nothing.
    assert bounds["logical_low"] == pytest.approx(0.0, abs=1e-6)
    assert bounds["logical_high"] > bounds["high"]


def test_observed_status_does_not_move_with_its_prior():
    state = load_state("PA")
    philly = state.county("42101")
    # Philadelphia's ADU status is observed, so the ADU prior cannot move its
    # ADU result. (The 2–6 home prior still can: ADUs compete with 2–6 homes
    # on lots where those may already be allowed.)
    low = evaluate_county(philly, state, P, ["baseline", "adu"], priors={"prior_adu_prohibited": 0.0})
    high = evaluate_county(philly, state, P, ["baseline", "adu"], priors={"prior_adu_prohibited": 1.0})
    assert low["scenarios"]["adu"]["delta"] == pytest.approx(high["scenarios"]["adu"]["delta"])
    adams = state.county("42001")
    low = evaluate_county(adams, state, P, ["baseline", "adu"], priors={"prior_adu_prohibited": 0.0})
    high = evaluate_county(adams, state, P, ["baseline", "adu"], priors={"prior_adu_prohibited": 1.0})
    assert high["scenarios"]["adu"]["delta"] > low["scenarios"]["adu"]["delta"]


def test_new_hampshire_bounds_are_narrow_where_law_is_statewide(nh_zoning):
    adu = zoning_bounds(nh_zoning)["adu"]
    mm = zoning_bounds(nh_zoning)["missing_middle"]
    # Statewide ADU law leaves a narrower absolute bound than unknown 2–6
    # zoning. Relative widths are a poor check once the ADU increment is small.
    assert (adu["high"] - adu["low"]) < (mm["high"] - mm["low"])
    assert mm["logical_low"] == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------------------ close calls
def _draws(values):
    return [{"a": a, "b": b} for a, b in values]


def test_close_call_flags_rank_flips_in_ten_percent_of_draws():
    central = {"a": 10.0, "b": 9.0}
    draws = _draws([(10, 9)] * 17 + [(8, 9)] * 3)  # 15% flips
    pair = compare_pair("a", "b", central, draws, {}, {}, 0.0, 0.10)
    assert pair["close_call"] and pair["flip_share"] == pytest.approx(0.15)
    assert pair["leader"] == "a"
    draws = _draws([(10, 9)] * 19 + [(8, 9)])  # 5% flips
    assert not compare_pair("a", "b", central, draws, {}, {}, 0.0, 0.10)["close_call"]


def test_close_call_from_zoning_bound_or_acs_band():
    central = {"a": 10.0, "b": 9.0}
    draws = _draws([(10, 9)] * 20)
    flipped = {"prior_high": {"a": 8.0, "b": 9.0}}
    assert compare_pair("a", "b", central, draws, {}, flipped, 0.0, 0.10)["zoning_flip"]
    pair = compare_pair("a", "b", central, draws, {}, {}, 1.5, 0.10)
    assert pair["moe_flip"] and pair["close_call"]
    assert pair["reasons"] == ["gap is inside the ACS sampling band"]


def test_dominant_pair_never_flips():
    state = load_state("NH")
    env = run_envelope(state, draws=15, seed=7)
    flips = sum(1 for row in env["statewide"] if row["package"] < row["parking"])
    assert flips == 0


# ------------------------------------------------------- MOE separation
def test_envelope_never_reads_acs_margins():
    raw = json.loads((SAMPLE_DIR / "NH.json").read_text())
    zeroed = copy.deepcopy(raw)
    for county in zeroed["counties"]:
        for cell in county["acs"].values():
            if cell.get("m") is not None:
                cell["m"] = 0.0
    a = run_envelope(build_state(raw, None, "a"), draws=6, seed=3)
    b = run_envelope(build_state(zeroed, None, "b"), draws=6, seed=3)
    assert a["statewide"] == b["statewide"]
    assert run_moe(build_state(zeroed, None, "b"))["statewide"]["missing_middle"] == 0.0


def test_acs_band_scales_with_margins_and_not_with_assumption_bands():
    state = load_state("NH")
    one = run_moe(state, P)["statewide"]["missing_middle"]
    two = run_moe(state, P, moe_scale=2.0)["statewide"]["missing_middle"]
    assert one > 0
    assert two == pytest.approx(2 * one, rel=0.15)
    zero = run_moe(state, P, moe_scale=0.0)["statewide"]
    assert all(value == 0.0 for value in zero.values())


def test_pa_top_pair_tie_clause_reads_draw_medians():
    from src.lab.results import load_results
    from src.plain import homes, ranking_phrase, top_pair_tie_clause

    pa = load_results("PA", allow_compute=False)
    sw = pa["statewide"]
    pair = sw["top_benchmark_pair"]
    clause = top_pair_tie_clause(pair, sw["results"])
    assert homes(sw["results"][pair["leader"]]["p50"]) in clause
    assert homes(sw["results"][pair["trailer"]]["p50"]) in clause
    assert "Central estimate favors" in clause
    assert "ahead in" in clause
    assert ranking_phrase(sw["benchmark_ranking"], pair).startswith("Missing middle")


def test_envelope_params_exclude_zoning_priors_and_locked_constants():
    names = set(envelope_params())
    assert "prior_adu_prohibited" not in names and "prior_mm_prohibited" not in names
    assert "prior_adu_prohibited_nh_attached" not in names
    assert "fee_per_unit" not in names and "fee_cut_share" not in names
    assert "pipeline_f0" not in names
    assert "hazard_homeowner" in names
    assert "adu_feasible_share_ca" in names
    assert "hazard_homeowner_feasible" not in names
    assert "completion_ratio_adu" in names
    assert "completion_ratio_small" in names
    assert "completion_ratio_mf" in names
    assert "pipeline_sigma" in names
    assert param_spec("pipeline_sigma").get("envelope_on") == "elasticity"


def test_envelope_is_seeded_and_inside_bands():
    a = sample_params(25, 11)
    b = sample_params(25, 11)
    assert a == b
    assert a != sample_params(25, 12)
    for draw in a:
        for name in envelope_params():
            spec = param_spec(name)
            if spec.get("envelope_on") == "elasticity":
                lo = ELASTICITY_TO_SIGMA / float(spec["elasticity_high"])
                hi = ELASTICITY_TO_SIGMA / float(spec["elasticity_low"])
                assert lo - 1e-9 <= draw[name] <= hi + 1e-9
            else:
                assert spec["low"] <= draw[name] <= spec["high"]
        assert draw["prior_adu_prohibited"] == P["prior_adu_prohibited"]
        assert "hazard_homeowner_feasible" in draw
        assert draw["hazard_homeowner_feasible"] == pytest.approx(
            draw["hazard_homeowner"] / draw["adu_feasible_share_ca"]
        )


# ------------------------------------------------ what would change it
def test_switching_value_ties_the_pair():
    state = load_state("PA")
    county = state.county("Allegheny")
    evaluate = county_evaluator(state, county)
    central = evaluate(P)
    assert central["fees"] > central["missing_middle"]
    found = what_would_change(evaluate, P, "fees", "missing_middle")
    assert found, "some single assumption inside its band reverses fees over missing middle"
    for row in found:
        low, high = row["band"]
        assert low <= row["switch_at"] <= high
        p = dict(P)
        p[row["param"]] = row["switch_at"]
        at = evaluate(p)
        assert abs(at["fees"] - at["missing_middle"]) < 0.02 * central["fees"]


def test_switching_value_is_none_when_band_cannot_flip():
    state = load_state("NH")
    evaluate = county_evaluator(state, state.counties[0])
    assert switching_value(evaluate, P, "parking_market_urban", "package", "parking", "high") is None


def test_summarize_reports_bootstrap_sampling_error():
    values = [float(i) for i in range(40)]
    bare = summarize(values)
    assert set(bare) == {"p10", "p50", "p90"}
    with_se = summarize(values, seed=20261107)
    assert with_se["p10_se"] >= 0 and with_se["p50_se"] >= 0 and with_se["p90_se"] >= 0
    again = summarize(values, seed=20261107)
    assert again == with_se


def test_evaluate_county_variants_do_not_change_named_scenarios():
    state = load_state("NH")
    county = state.counties[0]
    plain = evaluate_county(county, state, P)
    with_variants = evaluate_county(county, state, P, variants=package_variants(P))
    for sid, row in plain["scenarios"].items():
        assert with_variants["scenarios"][sid]["delta"] == pytest.approx(row["delta"])
