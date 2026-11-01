# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Arithmetic checks for the Lab engine: pro formas, timing, resolution, pipeline, totals."""

import json
import math
from statistics import NormalDist

import pytest

from src.lab.config import SAMPLE_DIR, central_params, load_scenarios
from src.lab.data import LegalSegment, build_state, load_state
from src.lab.engine import (
    LotDist,
    evaluate_county,
    evaluate_state,
    expand_segment,
    implied_cost_elasticity,
    resolve_hosts,
    scenario_econ,
    timing_share,
)
from src.lab.options import Econ, OptionResult, adu_economics_gate, evaluate_option, provided_parking, unit_value
from src.model.equations import normal_cdf

P = central_params()


@pytest.fixture(scope="module")
def pa():
    return evaluate_state(load_state("PA"))


@pytest.fixture(scope="module")
def nh():
    return evaluate_state(load_state("NH"))


def test_all_67_counties_under_every_scenario(pa):
    assert len(pa["counties"]) == 67
    sids = set(load_scenarios()["scenarios"])
    for county in pa["counties"]:
        assert set(county["scenarios"]) == sids
        for row in county["scenarios"].values():
            assert math.isfinite(row["delivery"]) and row["delivery"] >= 0


def test_statewide_is_sum_of_counties(pa):
    for sid, row in pa["statewide"].items():
        for field in ("delivery", "delta"):
            assert row[field] == pytest.approx(sum(c["scenarios"][sid][field] for c in pa["counties"]))
        assert row["delivery"] == pytest.approx(pa["statewide"]["baseline"]["delivery"] + row["delta"])


def test_delta_is_host_plus_pipeline(pa):
    for sid, row in pa["statewide"].items():
        if sid != "baseline":
            assert row["delta"] == pytest.approx(row["host_delta"] + row["pipeline_delta"])


def test_baseline_pipeline_matches_hand_calculation():
    state = load_state("PA")
    county = state.county("Allegheny")
    avg = county.bps_avg
    expected = 5 * (
        avg["u1"] * P["completion_share_1"]
        + (avg["u2"] + avg["u34"]) * P["completion_share_2to4"]
        + avg["u5"] * P["completion_share_5plus"]
    )
    result = evaluate_county(county, state, P, ["baseline"])
    assert result["scenarios"]["baseline"]["pipeline_baseline"] == pytest.approx(expected)


def test_adu_pro_forma_closed_form():
    econ = scenario_econ("adu", P)
    r = evaluate_option("adu", "detached", "suburban", 965, 1201, 227600, econ, 1.0, P, None)
    value = 965 * P["new_unit_rent_premium"] * 12 * (1 - P["opex_share"]) / P["cap_rate"]
    cost = P["adu_sqft"] * P["adu_cost_psf"] * (1 + P["soft_cost_share"]) + 50000
    assert r.value == pytest.approx(value)
    assert r.cost == pytest.approx(cost)  # benchmark: no parking even though 1 space was passed
    assert r.spaces == 0
    assert r.margin == pytest.approx(value / cost - 1)
    assert r.excess == pytest.approx(r.margin - P["hurdle_owner"])
    ref_cost = P["adu_sqft"] * P["adu_cost_psf"] * (1 + P["soft_cost_share"])
    assert r.ref_excess == pytest.approx(value / ref_cost - 1 - P["hurdle_owner"])
    mm2 = evaluate_option("mm2", "detached", "suburban", 965, 1201, 227600, Econ(fee=50000), 0.0, P, None)
    assert mm2.hazard == pytest.approx(P["hazard_homeowner_feasible"])


def test_rebuild_pro_forma_includes_lot_and_demolition():
    econ = scenario_econ("baseline", P)
    r = evaluate_option("mm4", "detached", "suburban", 965, 1201, 200000, econ, 0.0, P, None)
    spaces = 4 * max(P["parking_min_suburban"], P["parking_market_suburban"])
    hard = 4 * (P["mm_unit_sqft"] * P["newbuild_cost_psf"] * (1 + P["soft_cost_share"]) + 50000)
    expected = hard + spaces * P["stall_cost_surface"] + 200000 * P["teardown_value_factor"] + P["demolition_cost"]
    assert r.cost == pytest.approx(expected)
    assert r.value == pytest.approx(4 * unit_value(1201, P))
    assert r.net == 3


def test_parking_provided_is_never_below_market():
    mandate = Econ(fee=50000)
    free = Econ(fee=50000, parking="market")
    for ctx in ("urban", "suburban", "rural"):
        assert provided_parking(ctx, free, P, None) == P[f"parking_market_{ctx}"]
        assert provided_parking(ctx, mandate, P, None) >= provided_parking(ctx, free, P, None)
    # A 1-space cap (NH SB 284) cannot push suburban below its 1.25 market ratio.
    assert provided_parking("suburban", mandate, P, 1.0) == P["parking_market_suburban"]


def test_timing_share():
    assert timing_share(0.01, 5, 1, 1) == pytest.approx(1 - math.exp(-0.03))
    assert timing_share(0.01, 5, 3, 3) == 0.0


def _opt(name, excess, area, net=1, hazard=0.01, lag=0.5):
    return OptionResult(name, 0, 0, excess, 0, excess, area, net, hazard, lag, 0)


def test_one_best_option_per_host_is_not_a_sum():
    lots = LotDist(5000, 0.6)
    lags = {"adu": 1.0, "mm2": 1.0}
    a = _opt("adu", -0.2, 1000)
    b = _opt("mm2", -0.1, 1000)
    both = resolve_hosts([a, b], lags, lots, 1000, 0.25, 5)
    only_a = resolve_hosts([a], lags, lots, 1000, 0.25, 5)
    only_b = resolve_hosts([b], lags, lots, 1000, 0.25, 5)
    # ADU is all-lots; mm2 takes only the feasible lots. Combined is not a sum.
    assert both.delivered < only_a.delivered + only_b.delivered
    assert "mm2" in both.by_option and "adu" in both.by_option
    assert both.delivered > only_b.delivered
    assert both.feasible == pytest.approx(1000 * lots.survival(1000) * normal_cdf(-0.1 / 0.25))


def test_adu_delivery_does_not_multiply_by_feasibility():
    lots = LotDist(5000, 0.6)
    adu = _opt("adu", -0.5, 1000, hazard=0.01)
    out = resolve_hosts([adu], {"adu": 1.0}, lots, 1000, 0.25, 5)
    hosts = 1000 * lots.survival(1000)
    timing = timing_share(0.01, 5, 1.0, 0.5)
    assert out.delivered == pytest.approx(hosts * timing)
    assert out.feasible == pytest.approx(hosts * normal_cdf(-0.5 / 0.25))
    mm2 = _opt("mm2", -0.5, 1000, hazard=0.01)
    rebuild = resolve_hosts([mm2], {"mm2": 1.0}, lots, 1000, 0.25, 5)
    assert rebuild.delivered == pytest.approx(hosts * normal_cdf(-0.5 / 0.25) * timing)


def test_legalizing_a_better_option_does_not_strand_lots_already_building():
    lots = LotDist(5000, 0.6)
    adu = _opt("adu", -0.2, 1000, hazard=0.01)
    mm2 = _opt("mm2", -0.2, 1000, hazard=0.01)
    lags = {"adu": 0.0, "mm2": 1.5, "mm6": 1.5}
    alone = resolve_hosts([adu], lags, lots, 1000, 0.25, 5)
    # Same net, later lag: the all-lots ADU path continues on leftover lots,
    # so delivery stays near the ADU-only total.
    tie = resolve_hosts([adu, _opt("mm2", -0.2 + 1e-9, 1000, hazard=0.01)], lags, lots, 1000, 0.25, 5)
    assert tie.by_option["adu"] > 0
    assert tie.delivered == pytest.approx(alone.delivered, rel=0.2)
    better = resolve_hosts([adu, _opt("mm6", 0.0, 1000, net=5, hazard=0.01)], lags, lots, 1000, 0.25, 5)
    assert better.delivered > alone.delivered
    assert better.by_option["adu"] > 0 and better.by_option["mm6"] > 0
    assert mm2.option == "mm2"


def test_lots_too_small_for_the_best_option_take_the_next_one():
    lots = LotDist(3000, 0.6)
    adu = _opt("adu", -0.3, 2000)
    mm6 = _opt("mm6", 0.1, 4000, net=5)
    out = resolve_hosts([adu, mm6], {"adu": 1, "mm6": 1}, lots, 100, 0.25, 5)
    small = lots.survival(2000) - lots.survival(4000)
    large = lots.survival(4000)
    take_mm = max(0.0, normal_cdf(0.1 / 0.25) - normal_cdf(-0.3 / 0.25))
    assert out.lots_by_option["mm6"] == pytest.approx(100 * large * take_mm)
    assert out.lots_by_option["adu"] == pytest.approx(100 * small + 100 * large * (1 - take_mm))
    assert out.eligible == pytest.approx(100 * (small * 1 + large * 5))


def test_unknown_zoning_splits_into_prior_partitions():
    seg = LegalSegment(share=1.0, adu="unknown", mm="unknown")
    parts = expand_segment(seg, P, "2027-01-01", [2023, 2024, 2025])
    assert len(parts) == 4
    assert sum(part.weight for part in parts) == pytest.approx(1.0)
    prohibited_both = [x for x in parts if not x.legal_now]
    assert prohibited_both[0].weight == pytest.approx(P["prior_adu_prohibited"] * P["prior_mm_prohibited"])


def test_nh_attached_hosts_use_the_townhouse_prior():
    seg = LegalSegment(share=1.0, adu="unknown", mm="prohibited")
    pa = expand_segment(seg, P, "2027-01-01", [2023, 2024, 2025], state_code="PA", host_type="attached")
    nh = expand_segment(seg, P, "2027-01-01", [2023, 2024, 2025], state_code="NH", host_type="attached")
    det = expand_segment(seg, P, "2027-01-01", [2023, 2024, 2025], state_code="NH", host_type="detached")
    pa_prohibited = sum(part.weight for part in pa if "adu" not in part.legal_now)
    nh_prohibited = sum(part.weight for part in nh if "adu" not in part.legal_now)
    det_prohibited = sum(part.weight for part in det if "adu" not in part.legal_now)
    assert pa_prohibited == pytest.approx(P["prior_adu_prohibited"])
    assert nh_prohibited == pytest.approx(P["prior_adu_prohibited_nh_attached"])
    assert nh_prohibited < pa_prohibited
    assert det_prohibited == pytest.approx(P["prior_adu_prohibited"])


def test_nh_adu_parking_is_capped_at_one_space():
    seg = LegalSegment(share=1.0, adu="allowed_with_parking", mm="prohibited", adu_parking=2.0)
    nh = expand_segment(seg, P, "2027-01-01", [2023, 2024, 2025], state_code="NH")
    pa = expand_segment(seg, P, "2027-01-01", [2023, 2024, 2025], state_code="PA")
    assert max(part.adu_spaces for part in nh) == 1.0
    assert max(part.adu_spaces for part in pa) == 2.0


def test_post_window_rule_is_baseline_not_reform():
    seg = LegalSegment(share=1.0, adu="allowed", mm="prohibited", adu_parking=0.0, adu_effective="2026-10-29")
    (part,) = expand_segment(seg, P, "2027-01-01", [2023, 2024, 2025])
    assert part.legal_now == {"adu"} and part.legal_pre == frozenset()
    assert dict(part.lags)["adu"] == pytest.approx(P["adoption_lag_years"] - 64 / 365.25)


def test_pittsburgh_adus_are_in_baseline_not_in_the_adu_reform():
    state = load_state("PA")
    county = state.county("Allegheny")
    result = evaluate_county(county, state, P, ["baseline", "adu"])
    assert result["scenarios"]["baseline"]["host_adjustment"]["delivered"] > 0
    # Without Pittsburgh's rule the ADU reform has more lots to legalize.
    raw = json.loads((SAMPLE_DIR / "PA.json").read_text())
    raw["places"] = []
    fresh = build_state(raw, None, "test").county("Allegheny")
    without = evaluate_county(fresh, state, P, ["baseline", "adu"])
    assert without["scenarios"]["baseline"]["host_adjustment"]["delivered"] == pytest.approx(0)
    assert without["scenarios"]["adu"]["delta"] > result["scenarios"]["adu"]["delta"]


def test_philadelphia_benchmark_adu_counts_in_full(pa):
    philly = [c for c in pa["counties"] if c["fips"] == "42101"][0]
    assert philly["coverage"]["adu"] == pytest.approx(1.0)
    assert philly["scenarios"]["adu"]["delta"] > 0


def test_fee_pipeline_threshold_closed_form():
    f0, sigma, h = P["pipeline_f0"], P["pipeline_sigma"], P["hurdle_developer"]
    elasticity = implied_cost_elasticity(P)
    # ε = φ(z0)/F0 × (1+h)/σ_p. F0 is fixed at 0.5; central σ_p = 0.52 → ε ≈ 1.75 (Saiz).
    assert f0 == pytest.approx(0.5)
    assert elasticity == pytest.approx(
        NormalDist().pdf(NormalDist().inv_cdf(f0)) / f0 * (1 + h) / sigma, rel=1e-9
    )
    assert elasticity == pytest.approx(1.75, abs=0.02)
    z0 = NormalDist().inv_cdf(f0)
    cost = 500000.0
    f1 = normal_cdf(z0 + (1 + h) * 25000 / cost / sigma)
    assert f1 / f0 - 1 == pytest.approx(elasticity * 25000 / cost, rel=0.05)
    zero = dict(P)
    zero["pipeline_sigma"] = 1000.0
    assert implied_cost_elasticity(zero) < 0.01


def test_scenario_levers_map_to_economics():
    assert scenario_econ("baseline", P) == Econ(fee=50000)
    assert scenario_econ("fees", P).fee == 25000
    assert scenario_econ("parking", P).parking == "market"
    assert scenario_econ("parking", P).approval is False
    assert scenario_econ("adu", P).adu_no_parking is True
    pkg = scenario_econ("package", P)
    assert (pkg.fee, pkg.parking, pkg.adu_no_parking, pkg.approval) == (25000, "market", True, False)
    assert scenario_econ("approval", P).approval is True


def test_new_hampshire_adu_is_mostly_already_legal(nh, pa):
    assert nh["coverage"]["adu"] > 0.8
    nh_share = nh["statewide"]["adu"]["delta"] / nh["statewide"]["baseline"]["delivery"]
    pa_share = pa["statewide"]["adu"]["delta"] / pa["statewide"]["baseline"]["delivery"]
    assert nh_share < pa_share
    assert nh["statewide"]["baseline"]["pipeline_adjustment"] > 0  # SB 284 cap response


def test_every_benchmark_adds_homes(pa, nh):
    for result in (pa, nh):
        for sid in ("adu", "missing_middle", "parking", "fees", "package", "approval"):
            assert result["statewide"][sid]["delta"] > 0, (result["state"], sid)


# Greenaway-McGrevy & Phillips 2023, JUE 136:103555: 21,808 extra dwellings
# over five years ≈ 4.11% of Auckland's regional dwelling stock. Published
# figure (the working paper said 5.13%). Gross permits, not net completions.
AUCKLAND_STOCK_CEILING = 0.041


def test_adu_economics_gate_normalizes_to_the_ca_reference():
    assert adu_economics_gate(0.1, 0.1, 0.25) == pytest.approx(1.0)
    assert adu_economics_gate(0.2, 0.1, 0.25) == pytest.approx(1.0)
    assert 0.0 < adu_economics_gate(-0.2, 0.1, 0.25) < 1.0
    assert adu_economics_gate(-0.5, None, 0.25) == pytest.approx(1.0)


def test_adu_output_falls_as_fee_per_unit_rises():
    state = load_state("PA")
    county = state.county("42101")
    zero = dict(P)
    zero["fee_per_unit"] = 0.0
    low = evaluate_county(county, state, zero, ["baseline", "adu"])
    high = evaluate_county(county, state, P, ["baseline", "adu"])
    assert high["scenarios"]["adu"]["delta"] < low["scenarios"]["adu"]["delta"]


def test_missing_middle_stays_under_the_auckland_stock_ceiling(pa, nh):
    for result, code in ((pa, "PA"), (nh, "NH")):
        state = load_state(code)
        stock = sum(county.housing_units.value for county in state.counties)
        assert stock > 0
        statewide_mm = result["statewide"]["missing_middle"]["delta"] / stock
        statewide_combo = (
            result["statewide"]["adu"]["delta"] + result["statewide"]["missing_middle"]["delta"]
        ) / stock
        statewide_pkg = result["statewide"]["package"]["delta"] / stock
        assert statewide_mm <= AUCKLAND_STOCK_CEILING, (code, "mm", statewide_mm)
        assert statewide_combo <= AUCKLAND_STOCK_CEILING, (code, "adu+mm", statewide_combo)
        assert statewide_pkg <= AUCKLAND_STOCK_CEILING, (code, "package", statewide_pkg)
        for county, row in zip(state.counties, result["counties"]):
            units = county.housing_units.value
            if units <= 0:
                continue
            mm = row["scenarios"]["missing_middle"]["delta"] / units
            combo = (row["scenarios"]["adu"]["delta"] + row["scenarios"]["missing_middle"]["delta"]) / units
            pkg = row["scenarios"]["package"]["delta"] / units
            assert mm <= AUCKLAND_STOCK_CEILING, (code, county.name, "mm", mm)
            assert combo <= AUCKLAND_STOCK_CEILING, (code, county.name, "adu+mm", combo)
            assert pkg <= AUCKLAND_STOCK_CEILING, (code, county.name, "package", pkg)
