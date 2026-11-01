# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Small Homes Policy Lab engine.

For each county c and scenario s the Lab reports three numbers:

  eligible capacity   homes that become legal and physically fit
  feasible capacity   of those, homes whose pro forma clears the hurdle
  delivery            expected completions inside the five-year window

Host delivery is N = sum_j H_j * F_j * p_j(T) * d_j over host groups j,
except ADU: N_ADU = sum_j H_j * gate_j * p_j(T) * d_j. The ADU hazard is
an all-lots rate from CA permits / SF stock. The gate is
min(1, Phi(x_ADU / sigma) / Phi(x_ref / sigma)), with x_ref the same ADU
at fee 0 and no parking (CA Gov. Code 65852.2(f)(3), now 66311.5(c)(1);
the Lab prototype is 600 sq ft). mm2 uses a feasible-lot hazard and still
multiplies by F.

  H  observed single-family lots in the group (ACS B25024 by tract context)
  F  Phi(x_best / sigma): share of lots whose own margin clears the hurdle,
     where x_best is the largest excess margin among options that are legal
     AND fit the lot. Each lot takes at most one option. ADU delivery uses
     the gate, not F.
  p  1 - exp(-lambda * max(0, T - legal lag - build lag)): chance a lot
     finishes inside the window (feasible lots for mm2/rebuilds; all lots
     times the gate for ADU)
  d  net homes the chosen option adds

Legal status is resolved by partition. A lot whose zoning is unknown is
split into "prohibited today" (prior probability) and "allowed today". It
is never treated as zero and never as allowed outright.

The existing permit pipeline (Building Permits Survey 2023–2025) is Baseline.
Homes that are already legal and already flowing are inside that pipeline,
so the host model only counts what the pipeline cannot contain:

  baseline host adjustment = N(L0, e0) - N(L0_pre, e0)
  scenario increment       = N(L1, e1) - N(L0_pre, e1) - baseline adjustment

L0 is today's legal set, L0_pre the part that was legal during the permit
window, L1 the set under the scenario, e0/e1 the economics. Fee, parking,
and approval changes reach the existing pipeline through a threshold model
(``pipeline_effect``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from statistics import NormalDist
from typing import Any

from src.lab.config import CONTEXTS, OPTIONS, central_params, load_assumptions, load_scenarios
from src.lab.data import County, HostCell, LegalSegment, StateData, post_window
from src.lab.options import Econ, OptionResult, adu_economics_gate, evaluate_option, rebuild_space_cost
from src.model.equations import normal_cdf

STD_NORMAL = NormalDist()
MM_OPTIONS = ("mm2", "mm4", "mm6")
PIPELINE_TYPES = ("sf", "small", "mf")


# --------------------------------------------------------------------- lots
class LotDist:
    """Lot-area distribution for one host group.

    Lognormal (assumed median and spread) unless observed bins are given,
    in which case area is uniform inside each bin.
    """

    def __init__(self, median: float, sigma: float, bins: list[tuple[float, float, float]] | None = None):
        self.median = median
        self.sigma = sigma
        self.bins = bins

    def survival(self, area: float) -> float:
        if area <= 0:
            return 1.0
        if self.bins:
            total = 0.0
            for low, high, share in self.bins:
                if area <= low:
                    total += share
                elif area < high:
                    total += share * (high - area) / (high - low)
            return total
        return 1.0 - normal_cdf((math.log(area) - math.log(self.median)) / self.sigma)


def lot_dist(cell: HostCell, p: dict[str, float]) -> LotDist:
    median = p[f"lot_median_{cell.host_type}_{cell.context}"]
    return LotDist(median, p["lot_log_sigma"], cell.lot_bins)


# ------------------------------------------------------------- scenarios
def scenario_econ(sid: str, p: dict[str, float]) -> Econ:
    levers = load_scenarios()["scenarios"][sid]["levers"]
    fee = p["fee_per_unit"] * (1.0 - levers.get("fee_cut_share", 0.0))
    return Econ(
        fee=fee,
        parking="market" if levers.get("parking_minimums") == "eliminated" else "minimum",
        adu_no_parking=levers.get("adu_parking_spaces") == 0,
        approval=bool(levers.get("approval_reform")),
    )


def scenario_ids() -> list[str]:
    return list(load_scenarios()["scenarios"])


def timing_share(hazard: float, horizon: float, legal_lag: float, build_lag: float) -> float:
    """p(T) = 1 - exp(-lambda * max(0, T - legal lag - build lag))."""
    return 1.0 - math.exp(-hazard * max(0.0, horizon - legal_lag - build_lag))


def years_between(start: str, end: str) -> float:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days / 365.25


# ------------------------------------------------------- host resolution
@dataclass
class HostOutcome:
    eligible: float = 0.0
    feasible: float = 0.0
    delivered: float = 0.0
    by_option: dict[str, float] = field(default_factory=dict)
    lots_by_option: dict[str, float] = field(default_factory=dict)

    def add(self, other: "HostOutcome", weight: float) -> None:
        self.eligible += weight * other.eligible
        self.feasible += weight * other.feasible
        self.delivered += weight * other.delivered
        for key, value in other.by_option.items():
            self.by_option[key] = self.by_option.get(key, 0.0) + weight * value
        for key, value in other.lots_by_option.items():
            self.lots_by_option[key] = self.lots_by_option.get(key, 0.0) + weight * value

    def as_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "feasible": self.feasible,
            "delivered": self.delivered,
            "by_option": dict(self.by_option),
            "lots_by_option": dict(self.lots_by_option),
        }


def resolve_hosts(
    results: list[OptionResult],
    lags: dict[str, float],
    lots: LotDist,
    hosts: float,
    sigma: float,
    horizon: float,
) -> HostOutcome:
    """One best option per lot.

    Lots are split at each option's required area. In each slice the lot
    takes the fitting option with the largest excess margin (ties go to the
    option that adds more homes). Each lot's own margin is the group margin
    plus a common lot shock with spread sigma, so the same option is best
    for every lot in the slice and F = Phi(x_best / sigma).

    Transition: if the best option only becomes legal later than another
    fitting option (an incumbent, e.g. an ADU already allowed when a reform
    adds 2–6 homes), lots keep building the incumbent until the new option's
    lag ends, and the lots not yet built then switch. Legalizing a better
    option therefore never strands lots that were already building.

    The ADU hazard is an all-lots rate (CA permits / SF stock). ADU delivery
    multiplies by a fee/parking gate normalized to CA conditions (fee 0 and
    no parking) instead of by F. When a non-ADU option is also legal, lots
    are split by a common shock: the overlap stays with the ADU and the
    other option takes only lots that work for it but not for an ADU.
    """
    out = HostOutcome()
    if not results or hosts <= 0:
        return out
    thresholds = sorted({r.area for r in results})
    survivals = [lots.survival(a) for a in thresholds] + [0.0]
    for k, area in enumerate(thresholds):
        mass = survivals[k] - survivals[k + 1]
        if mass <= 0:
            continue
        fitting = [r for r in results if r.area <= area]
        best = max(fitting, key=lambda r: (r.excess, r.net))
        share_feasible = normal_cdf(best.excess / sigma)
        best_lag = lags[best.option]
        lots_here = hosts * mass
        out.eligible += lots_here * max(r.net for r in fitting)
        out.feasible += lots_here * share_feasible * best.net
        adu = next((r for r in fitting if r.option == "adu"), None)
        gate = adu_economics_gate(adu.excess, adu.ref_excess, sigma) if adu is not None else 1.0
        earlier = [r for r in fitting if lags[r.option] < best_lag - 1e-12]
        if best.option == "adu":
            timing = timing_share(best.hazard, horizon, best_lag, best.build_lag)
            if earlier:
                incumbent = max(earlier, key=lambda r: (r.excess, r.net))
                share_inc = 1.0 if incumbent.option == "adu" else normal_cdf(incumbent.excess / sigma)
                start = lags[incumbent.option]
                stop = min(best_lag, horizon - incumbent.build_lag)
                built = 1.0 - math.exp(-incumbent.hazard * max(0.0, stop - start))
                inc_scale = gate if incumbent.option == "adu" else 1.0
                phase_one = lots_here * share_inc * built * incumbent.net * inc_scale
                remaining = max(0.0, 1.0 - share_inc * built)
                out.by_option[incumbent.option] = out.by_option.get(incumbent.option, 0.0) + phase_one
                delivered = lots_here * remaining * timing * best.net * gate
                out.delivered += phase_one + delivered
                out.by_option["adu"] = out.by_option.get("adu", 0.0) + delivered
            else:
                delivered = lots_here * gate * timing * best.net
                out.delivered += delivered
                out.by_option["adu"] = out.by_option.get("adu", 0.0) + delivered
            out.lots_by_option["adu"] = out.lots_by_option.get("adu", 0.0) + lots_here
        elif adu is not None:
            # All-lots ADU (times the gate) until the other option's lag ends;
            # then lots that work for that option but not for an ADU switch,
            # and the overlap stays on the ADU path.
            start = lags[adu.option]
            stop = min(best_lag, horizon - adu.build_lag)
            built = 1.0 - math.exp(-adu.hazard * max(0.0, stop - start))
            phase_one = lots_here * built * adu.net * gate
            unbuilt = max(0.0, 1.0 - built)
            timing_best = timing_share(best.hazard, horizon, best_lag, best.build_lag)
            timing_adu_rest = timing_share(adu.hazard, horizon, stop, adu.build_lag)
            share_adu = normal_cdf(adu.excess / sigma)
            take = max(0.0, share_feasible - share_adu)
            delivered_best = lots_here * unbuilt * take * timing_best * best.net
            delivered_adu = lots_here * unbuilt * (1.0 - take) * timing_adu_rest * adu.net * gate
            out.by_option["adu"] = out.by_option.get("adu", 0.0) + phase_one + delivered_adu
            out.by_option[best.option] = out.by_option.get(best.option, 0.0) + delivered_best
            out.delivered += phase_one + delivered_best + delivered_adu
            out.lots_by_option[best.option] = out.lots_by_option.get(best.option, 0.0) + lots_here * take
            out.lots_by_option["adu"] = out.lots_by_option.get("adu", 0.0) + lots_here * (1.0 - take)
        else:
            timing = timing_share(best.hazard, horizon, best_lag, best.build_lag)
            if earlier:
                incumbent = max(earlier, key=lambda r: (r.excess, r.net))
                share_inc = normal_cdf(incumbent.excess / sigma)
                start = lags[incumbent.option]
                stop = min(best_lag, horizon - incumbent.build_lag)
                built = 1.0 - math.exp(-incumbent.hazard * max(0.0, stop - start))
                phase_one = lots_here * share_inc * built * incumbent.net
                remaining = max(0.0, share_feasible - share_inc * built)
                out.by_option[incumbent.option] = out.by_option.get(incumbent.option, 0.0) + phase_one
                delivered = lots_here * remaining * timing * best.net
                out.delivered += phase_one + delivered
                out.by_option[best.option] = out.by_option.get(best.option, 0.0) + delivered
            else:
                delivered = lots_here * share_feasible * timing * best.net
                out.delivered += delivered
                out.by_option[best.option] = out.by_option.get(best.option, 0.0) + delivered
            out.lots_by_option[best.option] = out.lots_by_option.get(best.option, 0.0) + lots_here
    return out


# ----------------------------------------------------------- partitions
@dataclass(frozen=True)
class Partition:
    """One legal state of a segment after unknown statuses are split."""

    weight: float
    legal_now: frozenset[str]
    legal_pre: frozenset[str]
    lags: tuple[tuple[str, float], ...]  # remaining adoption lag for options legal now
    adu_spaces: float
    label: str


def expand_segment(
    segment: LegalSegment,
    p: dict[str, float],
    window_start: str,
    bps_years: list[int],
    priors: dict[str, float] | None = None,
    state_code: str = "",
    host_type: str = "",
) -> list[Partition]:
    priors = priors or {}
    pa = priors.get("prior_adu_prohibited", p["prior_adu_prohibited"])
    if state_code == "NH" and host_type == "attached":
        pa = priors.get(
            "prior_adu_prohibited_nh_attached",
            p.get("prior_adu_prohibited_nh_attached", pa),
        )
    pm = priors.get("prior_mm_prohibited", p["prior_mm_prohibited"])
    pq = priors.get("prior_adu_parking_required", p["prior_adu_parking_required"])
    lag = p["adoption_lag_years"]

    def remaining(effective: str | None) -> float:
        if not effective:
            return 0.0
        return max(0.0, lag - years_between(effective, window_start))

    # (weight, legal?, spaces, effective, label)
    if segment.adu == "unknown":
        adu_states = [(pa, False, 0.0, None, "ADU prohibited (prior)"), (1 - pa, True, 0.0, None, "ADU allowed (prior)")]
    elif segment.adu == "allowed":
        adu_states = [(1.0, True, segment.adu_parking or 0.0, segment.adu_effective, "ADU allowed (observed)")]
    elif segment.adu == "allowed_with_parking":
        spaces = segment.adu_parking if segment.adu_parking is not None else 1.0
        if state_code == "NH":
            spaces = min(spaces, 1.0)
        adu_states = [
            (pq, True, spaces, segment.adu_effective, "ADU allowed, parking required (prior)"),
            (1 - pq, True, 0.0, segment.adu_effective, "ADU allowed, no parking (prior)"),
        ]
    else:
        adu_states = [(1.0, False, 0.0, None, "ADU prohibited (observed)")]
    if segment.mm == "unknown":
        mm_states = [(pm, False, None, "2–6 prohibited (prior)"), (1 - pm, True, None, "2–6 allowed (prior)")]
    elif segment.mm == "allowed":
        mm_states = [(1.0, True, segment.mm_effective, "2–6 allowed (observed)")]
    else:
        mm_states = [(1.0, False, None, "2–6 prohibited (observed)")]

    parts = []
    for wa, adu_ok, spaces, adu_eff, adu_label in adu_states:
        for wm, mm_ok, mm_eff, mm_label in mm_states:
            weight = wa * wm
            if weight <= 0:
                continue
            now: set[str] = set()
            pre: set[str] = set()
            lags: dict[str, float] = {}
            if adu_ok:
                now.add("adu")
                lags["adu"] = remaining(adu_eff)
                if not post_window(adu_eff, lag, bps_years):
                    pre.add("adu")
            if mm_ok:
                for opt in MM_OPTIONS:
                    now.add(opt)
                    lags[opt] = remaining(mm_eff)
                    if not post_window(mm_eff, lag, bps_years):
                        pre.add(opt)
            parts.append(
                Partition(
                    weight=weight,
                    legal_now=frozenset(now),
                    legal_pre=frozenset(pre),
                    lags=tuple(sorted(lags.items())),
                    adu_spaces=spaces,
                    label=f"{adu_label}; {mm_label}",
                )
            )
    return parts


# -------------------------------------------------------------- pipeline
def pipeline_parking(ctx: str, econ: Econ, p: dict[str, float], cap: float | None) -> float:
    minimum = p[f"parking_min_{ctx}"]
    if cap is not None:
        minimum = min(minimum, cap)
    market = p[f"parking_market_{ctx}"]
    return market if econ.parking == "market" else max(minimum, market)


def implied_cost_elasticity(p: dict[str, float]) -> float:
    """-dlnN/dlnC at the margin: phi(z0)/F0 * (1+h)/sigma_p."""
    f0 = p["pipeline_f0"]
    z0 = STD_NORMAL.inv_cdf(f0)
    return STD_NORMAL.pdf(z0) / f0 * (1.0 + p["hurdle_developer"]) / p["pipeline_sigma"]


def _shrunk_value(units: float, value: float, state_per_unit: float, shrink: float) -> float:
    if units <= 0 or value <= 0:
        return state_per_unit
    weight = min(1.0, units / shrink)
    return weight * (value / units) + (1.0 - weight) * state_per_unit


def pipeline_effect(
    county: County,
    state_values: dict[str, float],
    econ_new: Econ,
    econ_base: Econ,
    p: dict[str, float],
    horizon: float,
    cap: float | None,
    cap_lag: float | None,
) -> dict[str, Any]:
    """Baseline completions and the response of the existing pipeline.

    For a candidate project the margin is V/C - 1. Projects clear the
    developer hurdle h when the margin exceeds a project shock with spread
    sigma_p; today a share F0 clears it. A saving s per home moves the
    margin of the marginal project by (1 + h) * s / C, so the share that
    clears becomes F1 = Phi(Phi^-1(F0) + (1 + h) * s / C / sigma_p).
    Pipeline completions scale by F1 / F0. On parking-capped multifamily
    sites, fewer required spaces also add homes per site (yield channel).
    Approval reform saves carrying cost and finishes homes sooner, but only
    on the share of the pipeline that goes through discretionary review;
    the sooner-finished homes are reported separately as ``timing``.
    """
    avg = county.bps_avg
    trend = p["permit_trend"]
    window = sum((1.0 + trend) ** t for t in range(1, int(horizon) + 1))
    annual = {"sf": avg["u1"], "small": avg["u2"] + avg["u34"], "mf": avg["u5"]}
    values = {"sf": avg["v1"], "small": avg["v2"] + avg["v34"], "mf": avg["v5"]}
    completion = {"sf": p["completion_share_1"], "small": p["completion_share_2to4"], "mf": p["completion_share_5plus"]}
    build = {"sf": p["build_lag_sf_years"], "small": p["build_lag_newbuild_years"], "mf": p["build_lag_newbuild_years"]}
    soft = 1.0 + p["soft_cost_share"]
    h = p["hurdle_developer"]
    z0 = STD_NORMAL.inv_cdf(p["pipeline_f0"])
    f0 = p["pipeline_f0"]
    sigma = p["pipeline_sigma"]
    lag_new = p["adoption_lag_years"]
    response = p["pipeline_response_lag_years"]
    unit_area = p["mm_unit_sqft"] / 3.0

    out = {"baseline": 0.0, "cap_adjustment": 0.0, "delta": 0.0, "timing": 0.0, "by_type": {}}
    for t in PIPELINE_TYPES:
        base_t = annual[t] * window * completion[t]
        out["baseline"] += base_t
        per_unit = _shrunk_value(annual[t], values[t], state_values[t], p["bps_value_shrink_units"])
        frac_new = max(0.0, horizon - lag_new - response - build[t]) / horizon
        frac_cap = max(0.0, horizon - (cap_lag or 0.0) - response - build[t]) / horizon
        detail = {"baseline": base_t, "value_per_home": per_unit, "delta": 0.0, "cap_adjustment": 0.0}
        for ctx in CONTEXTS:
            weight = county.context_units.get(ctx, 0.0)
            if weight <= 0 or base_t <= 0:
                continue
            if t == "mf":
                stall, surface = rebuild_space_cost(ctx, p)
            else:
                stall, surface = p["stall_cost_surface"], 1.0
            pre = pipeline_parking(ctx, econ_base, p, None)
            cur = pipeline_parking(ctx, econ_base, p, cap)
            new = pipeline_parking(ctx, econ_new, p, cap)
            cost = (per_unit * soft + econ_base.fee + pre * stall) / (1.0 - p["land_share"])
            gap = p["parking_sf_gap_share"] if t == "sf" else 1.0

            def saving(provided: float, econ: Econ) -> float:
                s = (econ_base.fee - econ.fee) + gap * max(0.0, pre - provided) * stall
                if econ.approval:
                    s += p["carry_rate"] * p["approval_time_saved_years"] * p["carry_base_share"] * cost
                return s

            def yield_gain(provided: float) -> float:
                if t == "sf" or provided >= pre:
                    return 0.0
                kappa = p[f"parking_constrained_share_{ctx}"]
                return kappa * ((unit_area + pre * stall_area_of(p) * surface) / (unit_area + provided * stall_area_of(p) * surface) - 1.0)

            def multiplier(s: float, provided: float) -> float:
                return normal_cdf(z0 + (1.0 + h) * s / cost / sigma) / f0 * (1.0 + yield_gain(provided))

            m_cur = multiplier(saving(cur, econ_base), cur)
            m_new = multiplier(saving(new, econ_new), new)
            timing = 0.0
            if econ_new.approval and not econ_base.approval:
                share = p["approval_discretionary_share"]
                plain = Econ(econ_new.fee, econ_new.parking, econ_new.adu_no_parking, False)
                m_new = share * m_new + (1.0 - share) * multiplier(saving(new, plain), new)
                pulled = min(p["approval_time_saved_years"], max(0.0, horizon - lag_new))
                timing = base_t * weight / horizon * pulled * share * m_new
            cap_adj = base_t * weight * frac_cap * (m_cur - 1.0)
            delta = base_t * weight * frac_new * (m_new - m_cur) + timing
            detail["cap_adjustment"] += cap_adj
            detail["delta"] += delta
            out["cap_adjustment"] += cap_adj
            out["delta"] += delta
            out["timing"] += timing
        out["by_type"][t] = detail
    return out


def stall_area_of(p: dict[str, float]) -> float:
    return p["stall_area_sqft"]


def state_unit_values(state: StateData) -> dict[str, float]:
    totals = {"sf": [0.0, 0.0], "small": [0.0, 0.0], "mf": [0.0, 0.0]}
    for county in state.counties:
        avg = county.bps_avg
        totals["sf"][0] += avg["u1"]
        totals["sf"][1] += avg["v1"]
        totals["small"][0] += avg["u2"] + avg["u34"]
        totals["small"][1] += avg["v2"] + avg["v34"]
        totals["mf"][0] += avg["u5"]
        totals["mf"][1] += avg["v5"]
    return {k: (v[1] / v[0] if v[0] > 0 else 0.0) for k, v in totals.items()}


# ------------------------------------------------------------- counties
@dataclass
class CountyInputs:
    """Inputs the ACS margin-of-error band perturbs."""

    detached_scale: float = 1.0
    attached_scale: float = 1.0
    rent_1br: float | None = None
    rent_2br: float | None = None
    median_value: float | None = None


def evaluate_county(
    county: County,
    state: StateData,
    p: dict[str, float],
    scenarios: list[str] | None = None,
    inputs: CountyInputs | None = None,
    priors: dict[str, float] | None = None,
    state_values: dict[str, float] | None = None,
    variants: dict[str, tuple[Econ, frozenset[str]]] | None = None,
) -> dict[str, Any]:
    """Evaluate one county. ``variants`` adds ad hoc (economics, legalized options) runs."""
    doc = load_scenarios()
    adoc = load_assumptions()
    horizon = float(doc["horizon_years"])
    window_start = adoc["window_start"]
    bps_years = adoc["bps_years"]
    scenarios = scenarios or scenario_ids()
    inputs = inputs or CountyInputs()
    state_values = state_values or state_unit_values(state)
    rent_1br = inputs.rent_1br if inputs.rent_1br is not None else county.rent_1br.value
    rent_2br = inputs.rent_2br if inputs.rent_2br is not None else county.rent_2br.value
    median_value = inputs.median_value if inputs.median_value is not None else county.median_value.value
    cap = state.parking_cap
    cap_lag = None
    if cap is not None and state.parking_cap_effective:
        cap_lag = max(0.0, p["adoption_lag_years"] - years_between(state.parking_cap_effective, window_start))
    e0 = scenario_econ("baseline", p)
    sigma = p["host_margin_sigma"]

    option_cache: dict[tuple, OptionResult] = {}

    def option(opt: str, cell: HostCell, econ: Econ, spaces: float) -> OptionResult:
        key = (opt, cell.host_type, cell.context, econ, spaces if opt == "adu" else 0.0)
        hit = option_cache.get(key)
        if hit is None:
            hit = evaluate_option(opt, cell.host_type, cell.context, rent_1br, rent_2br, median_value, econ, spaces, p, cap)
            option_cache[key] = hit
        return hit

    resolve_cache: dict[tuple, HostOutcome] = {}

    lag_new = p["adoption_lag_years"]
    full_lags = {opt: lag_new for opt in OPTIONS}

    def outcome(cell_index: int, cell: HostCell, hosts: float, legal: frozenset[str], econ: Econ, part: Partition) -> HostOutcome:
        key = (cell_index, hosts, legal, econ, part.adu_spaces, part.lags)
        hit = resolve_cache.get(key)
        if hit is None:
            lags = dict(full_lags)
            lags.update(part.lags)
            results = [option(opt, cell, econ, part.adu_spaces) for opt in OPTIONS if opt in legal]
            hit = resolve_hosts(results, lags, lot_dist(cell, p), hosts, sigma, horizon)
            resolve_cache[key] = hit
        return hit

    # Host-level economics ignore the approval flag; a scenario that adds no
    # legal option and leaves host economics unchanged has no host term.
    specs: dict[str, tuple[Econ, frozenset[str]]] = {}
    for sid in scenarios:
        if sid != "baseline":
            specs[sid] = (scenario_econ(sid, p), frozenset(doc["scenarios"][sid].get("legalize", [])))
    specs.update(variants or {})
    host_econ = {}
    for sid, (e1, legalize) in specs.items():
        e1_host = Econ(e1.fee, e1.parking, e1.adu_no_parking, False)
        host_econ[sid] = (e1_host, legalize, not legalize and e1_host == e0)

    host_base = HostOutcome()
    host_delta: dict[str, HostOutcome] = {}
    coverage = {"adu": 0.0, "mm": 0.0, "hosts": 0.0}
    background_adu = {"homes": 0.0, "lots": 0.0}
    for index, cell in enumerate(county.cells):
        scale = inputs.detached_scale if cell.host_type == "detached" else inputs.attached_scale
        hosts = cell.hosts.value * scale
        coverage["hosts"] += hosts
        for segment in cell.segments:
            seg_hosts = hosts * segment.share
            if segment.adu != "unknown":
                coverage["adu"] += seg_hosts
            if segment.mm != "unknown":
                coverage["mm"] += seg_hosts
            for part in expand_segment(
                segment, p, window_start, bps_years, priors, state.code, cell.host_type
            ):
                now = outcome(index, cell, seg_hosts, part.legal_now, e0, part)
                pre0 = outcome(index, cell, seg_hosts, part.legal_pre, e0, part)
                if "adu" in part.legal_pre:
                    background_adu["homes"] += part.weight * pre0.by_option.get("adu", 0.0)
                    background_adu["lots"] += part.weight * pre0.lots_by_option.get("adu", 0.0)
                adj = HostOutcome()
                adj.add(now, 1.0)
                adj.add(pre0, -1.0)
                host_base.add(adj, part.weight)
                for sid, (e1, legalize, unchanged) in host_econ.items():
                    host_delta.setdefault(sid, HostOutcome())
                    if unchanged:
                        continue
                    new = outcome(index, cell, seg_hosts, part.legal_now | legalize, e1, part)
                    pre1 = outcome(index, cell, seg_hosts, part.legal_pre, e1, part)
                    inc = HostOutcome()
                    inc.add(new, 1.0)
                    inc.add(pre1, -1.0)
                    inc.add(adj, -1.0)
                    host_delta[sid].add(inc, part.weight)

    base_pipe = pipeline_effect(county, state_values, e0, e0, p, horizon, cap, cap_lag)
    baseline_total = base_pipe["baseline"] + base_pipe["cap_adjustment"] + host_base.delivered
    results: dict[str, Any] = {}
    for sid in list(scenarios) + [v for v in (variants or {}) if v not in scenarios]:
        if sid == "baseline":
            results[sid] = {
                "delivery": baseline_total,
                "delta": 0.0,
                "pipeline_baseline": base_pipe["baseline"],
                "pipeline_adjustment": base_pipe["cap_adjustment"],
                "host_adjustment": host_base.as_dict(),
                "pipeline": base_pipe,
            }
            continue
        e1 = specs[sid][0]
        pipe = pipeline_effect(county, state_values, e1, e0, p, horizon, cap, cap_lag)
        hd = host_delta.get(sid, HostOutcome())
        delta = hd.delivered + pipe["delta"]
        results[sid] = {
            "delivery": baseline_total + delta,
            "delta": delta,
            "eligible": hd.eligible,
            "feasible": hd.feasible,
            "host_delta": hd.delivered,
            "pipeline_delta": pipe["delta"],
            "timing_delta": pipe["timing"],
            "by_option": dict(hd.by_option),
            "lots_by_option": dict(hd.lots_by_option),
            "pipeline": pipe,
        }
    hosts_total = coverage["hosts"] or 1.0
    return {
        "fips": county.fips,
        "name": county.name,
        "hosts": coverage["hosts"],
        "coverage": {"adu": coverage["adu"] / hosts_total, "mm": coverage["mm"] / hosts_total},
        "coverage_hosts": {"adu": coverage["adu"], "mm": coverage["mm"]},
        "background_adu_flow": background_adu,
        "scenarios": results,
    }


SUM_FIELDS = ("delivery", "delta", "eligible", "feasible", "host_delta", "pipeline_delta", "timing_delta")


def evaluate_state(
    state: StateData,
    params: dict[str, float] | None = None,
    scenarios: list[str] | None = None,
    priors: dict[str, float] | None = None,
    variants: dict[str, tuple[Econ, frozenset[str]]] | None = None,
) -> dict[str, Any]:
    p = dict(central_params())
    if params:
        p.update(params)
    scenarios = scenarios or scenario_ids()
    values = state_unit_values(state)
    counties = [
        evaluate_county(c, state, p, scenarios, priors=priors, state_values=values, variants=variants)
        for c in state.counties
    ]
    totals: dict[str, dict[str, float]] = {}
    for sid in list(scenarios) + [v for v in (variants or {}) if v not in scenarios]:
        row: dict[str, Any] = {f: 0.0 for f in SUM_FIELDS}
        by_option: dict[str, float] = {}
        for county in counties:
            res = county["scenarios"][sid]
            for f in SUM_FIELDS:
                row[f] += res.get(f, 0.0)
            for opt, value in res.get("by_option", {}).items():
                by_option[opt] = by_option.get(opt, 0.0) + value
        if sid == "baseline":
            row["pipeline_baseline"] = sum(c["scenarios"]["baseline"]["pipeline_baseline"] for c in counties)
            row["pipeline_adjustment"] = sum(c["scenarios"]["baseline"]["pipeline_adjustment"] for c in counties)
            row["host_adjustment"] = sum(c["scenarios"]["baseline"]["host_adjustment"]["delivered"] for c in counties)
        row["by_option"] = by_option
        totals[sid] = row
    hosts = sum(c["hosts"] for c in counties) or 1.0
    background_adu = {
        "homes": sum(c.get("background_adu_flow", {}).get("homes", 0.0) for c in counties),
        "lots": sum(c.get("background_adu_flow", {}).get("lots", 0.0) for c in counties),
    }
    return {
        "state": state.code,
        "params": p,
        "statewide": totals,
        "coverage": {
            "adu": sum(c["coverage_hosts"]["adu"] for c in counties) / hosts,
            "mm": sum(c["coverage_hosts"]["mm"] for c in counties) / hosts,
        },
        "implied_cost_elasticity": implied_cost_elasticity(p),
        "background_adu_flow": background_adu,
        "counties": counties,
    }


def package_variants(p: dict[str, float]) -> dict[str, tuple[Econ, frozenset[str]]]:
    """Steps that build the package: legalization only, then the fee cut, then parking."""
    e0 = scenario_econ("baseline", p)
    package = scenario_econ("package", p)
    legal = frozenset(load_scenarios()["scenarios"]["package"]["legalize"])
    return {
        "package_legal_only": (Econ(e0.fee, e0.parking, True, False), legal),
        "package_legal_fees": (Econ(package.fee, e0.parking, True, False), legal),
    }


def package_decomposition(result: dict[str, Any], key: str = "statewide") -> dict[str, float]:
    """Waterfall from Baseline to the package, and the sum of separate scenarios."""
    rows = result[key] if key == "statewide" else result
    legal = rows["package_legal_only"]["delta"]
    fees = rows["package_legal_fees"]["delta"]
    package = rows["package"]["delta"]
    separate = sum(rows[sid]["delta"] for sid in ("adu", "missing_middle", "parking", "fees"))
    separate_legal = rows["adu"]["delta"] + rows["missing_middle"]["delta"]
    return {
        "legalization_resolved": legal,
        "legalization_if_summed": separate_legal,
        "competition_loss": legal - separate_legal,
        "fee_cut_step": fees - legal,
        "parking_step": package - fees,
        "package": package,
        "sum_of_separate": separate,
        "interaction": package - separate,
    }
