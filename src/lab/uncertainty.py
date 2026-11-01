# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Three separate uncertainty layers, close calls, and switching values.

1. Assumption envelope. Every ``ui`` assumption is drawn from a triangular
   distribution on its Low / Central / High band with a fixed seed. Every
   scenario in a draw uses the same parameter set (common random numbers),
   so differences between scenarios are not noise from separate draws.
   Zoning priors stay at central here; they are layer 2.
2. Zoning-evidence bound. Unknown-zoning lots are re-run with the priors at
   their low and at their high values, and at the logical extremes (every
   unknown lot prohibited / allowed today).
3. ACS sampling band. ACS host counts, rents, and median values are moved
   by their published 90 percent margins of error, one input at a time, with
   assumptions at central. Effects are combined in quadrature across inputs
   and across counties. This band is never mixed into layer 1.

A comparison of two scenarios is a **close call** when the order flips in
at least ``close_call_flip_share`` of envelope draws, or at either end of the
zoning bound, or when the gap is smaller than the ACS band on the gap.
"""

from __future__ import annotations

import math
import random
from itertools import combinations
from typing import Any, Callable

from src.lab.config import central_params, load_assumptions, param_spec, ui_params
from src.lab.data import County, StateData
from src.lab.engine import (
    CountyInputs,
    evaluate_county,
    evaluate_state,
    implied_cost_elasticity,
    package_decomposition,
    package_variants,
    scenario_ids,
    state_unit_values,
)

MOE_INPUTS = ("detached", "attached", "rent_1br", "rent_2br", "median_value")
ZONING_PRIORS = (
    "prior_adu_prohibited",
    "prior_adu_prohibited_nh_attached",
    "prior_mm_prohibited",
    "prior_adu_parking_required",
)
ELASTICITY_ZERO_SIGMA = 1000.0
ELASTICITY_TO_SIGMA = 0.918  # φ(z0)/F0 × (1+h) at F0=0.5, h=0.15; ε = 0.918 / σ_p


def compared_scenarios() -> list[str]:
    return [sid for sid in scenario_ids() if sid != "baseline"]


def envelope_params() -> list[str]:
    return [name for name in ui_params() if not param_spec(name).get("zoning_bound")]


def sample_params(draws: int, seed: int, base: dict[str, float] | None = None) -> list[dict[str, float]]:
    """Seeded triangular draws for every envelope parameter."""
    rng = random.Random(seed)
    names = envelope_params()
    base = dict(base or central_params())
    samples = []
    for _ in range(draws):
        p = dict(base)
        for name in names:
            spec = param_spec(name)
            if spec.get("envelope_on") == "elasticity":
                eps = rng.triangular(
                    float(spec.get("elasticity_low", 0.25)),
                    float(spec.get("elasticity_high", 3.0)),
                    float(spec.get("elasticity_central", 1.75)),
                )
                p[name] = ELASTICITY_TO_SIGMA / max(eps, 1e-9)
            else:
                p[name] = rng.triangular(float(spec["low"]), float(spec["high"]), float(spec["central"]))
        samples.append(p)
    return samples


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = q * (len(ordered) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def summarize(values: list[float], seed: int | None = None, boots: int = 200) -> dict[str, float]:
    out = {"p10": _quantile(values, 0.10), "p50": _quantile(values, 0.50), "p90": _quantile(values, 0.90)}
    if seed is None or len(values) < 2:
        return out
    rng = random.Random(seed)
    n = len(values)
    p10s: list[float] = []
    p50s: list[float] = []
    p90s: list[float] = []
    for _ in range(boots):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        p10s.append(_quantile(sample, 0.10))
        p50s.append(_quantile(sample, 0.50))
        p90s.append(_quantile(sample, 0.90))

    def se(series: list[float]) -> float:
        mean = sum(series) / len(series)
        var = sum((x - mean) ** 2 for x in series) / (len(series) - 1)
        return math.sqrt(var)

    out["p10_se"] = se(p10s)
    out["p50_se"] = se(p50s)
    out["p90_se"] = se(p90s)
    return out


# ---------------------------------------------------------- layer 1
def run_envelope(state: StateData, draws: int | None = None, seed: int | None = None) -> dict[str, Any]:
    doc = load_assumptions()
    draws = draws if draws is not None else int(doc["monte_carlo_draws"])
    seed = seed if seed is not None else int(doc["monte_carlo_seed"])
    sids = compared_scenarios()
    statewide: list[dict[str, float]] = []
    county: list[list[dict[str, float]]] = []
    for p in sample_params(draws, seed):
        result = evaluate_state(state, p)
        statewide.append({sid: result["statewide"][sid]["delta"] for sid in sids})
        statewide[-1]["baseline"] = result["statewide"]["baseline"]["delivery"]
        county.append(
            [
                {**{sid: c["scenarios"][sid]["delta"] for sid in sids}, "baseline": c["scenarios"]["baseline"]["delivery"]}
                for c in result["counties"]
            ]
        )
    return {"draws": draws, "seed": seed, "params": envelope_params(), "statewide": statewide, "county": county}


# ---------------------------------------------------------- layer 2
def zoning_runs(state: StateData, p: dict[str, float] | None = None) -> dict[str, dict[str, Any]]:
    p = p or central_params()
    runs = {}
    for label, values in (
        ("prior_low", {k: float(param_spec(k)["low"]) for k in ZONING_PRIORS}),
        ("prior_high", {k: float(param_spec(k)["high"]) for k in ZONING_PRIORS}),
        ("all_allowed", {k: 0.0 for k in ZONING_PRIORS}),
        ("all_prohibited", {k: 1.0 for k in ZONING_PRIORS}),
    ):
        runs[label] = evaluate_state(state, p, priors=values)
    return runs


def zoning_bounds(runs: dict[str, dict[str, Any]], key: str = "statewide", index: int | None = None) -> dict[str, dict[str, float]]:
    out = {}
    for sid in compared_scenarios() + ["baseline"]:
        field = "delivery" if sid == "baseline" else "delta"

        def pick(run: dict[str, Any]) -> float:
            if index is None:
                return run["statewide"][sid][field]
            return run["counties"][index]["scenarios"][sid][field]

        prior = [pick(runs["prior_low"]), pick(runs["prior_high"])]
        logical = [pick(runs["all_allowed"]), pick(runs["all_prohibited"])]
        out[sid] = {"low": min(prior), "high": max(prior), "logical_low": min(logical), "logical_high": max(logical)}
    return out


# ---------------------------------------------------------- layer 3
def county_moe_sensitivities(
    county: County,
    state: StateData,
    p: dict[str, float],
    values: dict[str, float] | None = None,
    moe_scale: float = 1.0,
) -> dict[str, dict[str, float]]:
    """Half the change in each scenario's result when one ACS input moves by -MOE and +MOE."""
    values = values or state_unit_values(state)
    sids = scenario_ids()
    out: dict[str, dict[str, float]] = {}
    for name in MOE_INPUTS:
        source = getattr(county, name)
        moe = source.moe * moe_scale
        if moe <= 0 or source.value <= 0:
            out[name] = {sid: 0.0 for sid in sids}
            continue
        ends = []
        for sign in (-1.0, 1.0):
            if name in ("detached", "attached"):
                scale = max(0.0, 1.0 + sign * moe / source.value)
                inputs = CountyInputs(**{f"{name}_scale": scale})
            else:
                inputs = CountyInputs(**{name: max(1.0, source.value + sign * moe)})
            ends.append(evaluate_county(county, state, p, sids, inputs=inputs, state_values=values))
        out[name] = {}
        for sid in sids:
            field = "delivery" if sid == "baseline" else "delta"
            out[name][sid] = 0.5 * (ends[1]["scenarios"][sid][field] - ends[0]["scenarios"][sid][field])
    return out


def run_moe(state: StateData, p: dict[str, float] | None = None, moe_scale: float = 1.0) -> dict[str, Any]:
    p = p or central_params()
    values = state_unit_values(state)
    sensitivities = [county_moe_sensitivities(c, state, p, values, moe_scale) for c in state.counties]
    sids = scenario_ids()

    def combine(county_index: int | None, weights: dict[str, float]) -> float:
        rows = sensitivities if county_index is None else [sensitivities[county_index]]
        total = 0.0
        for row in rows:
            for name in MOE_INPUTS:
                g = sum(weight * row[name][sid] for sid, weight in weights.items())
                total += g * g
        return math.sqrt(total)

    return {
        "sensitivities": sensitivities,
        "statewide": {sid: combine(None, {sid: 1.0}) for sid in sids},
        "county": [{sid: combine(i, {sid: 1.0}) for sid in sids} for i in range(len(state.counties))],
        "gap": lambda a, b, county_index=None: combine(county_index, {a: 1.0, b: -1.0}),
    }


# ---------------------------------------------------------- close calls
def _flip_share(draw_values: list[dict[str, float]], a: str, b: str, central_gap: float) -> float:
    if not draw_values:
        return 0.0
    sign = 1.0 if central_gap >= 0 else -1.0
    flips = sum(1 for row in draw_values if (row[a] - row[b]) * sign < 0)
    return flips / len(draw_values)


def compare_pair(
    a: str,
    b: str,
    central: dict[str, float],
    draws: list[dict[str, float]],
    zoning: dict[str, dict[str, float]],
    zoning_values: dict[str, dict[str, float]],
    moe_gap: float,
    threshold: float,
) -> dict[str, Any]:
    gap = central[a] - central[b]
    share = _flip_share(draws, a, b, gap)
    zoning_flip = any((values[a] - values[b]) * gap < 0 for values in zoning_values.values())
    moe_flip = abs(gap) < moe_gap
    reasons = []
    if share >= threshold:
        reasons.append(f"order flips in {share:.0%} of assumption draws")
    if zoning_flip:
        reasons.append("order flips at an end of the zoning-evidence bound")
    if moe_flip:
        reasons.append("gap is inside the ACS sampling band")
    leader, trailer = (a, b) if gap >= 0 else (b, a)
    return {
        "leader": leader,
        "trailer": trailer,
        "gap": abs(gap),
        "flip_share": share,
        "zoning_flip": zoning_flip,
        "moe_gap": moe_gap,
        "moe_flip": moe_flip,
        "close_call": bool(reasons),
        "reasons": reasons,
    }


def ranking(values: dict[str, float], sids: list[str]) -> list[str]:
    return sorted(sids, key=lambda sid: -values[sid])


# ------------------------------------------------- one at a time, switching
def one_at_a_time(
    evaluate: Callable[[dict[str, float]], dict[str, float]],
    base: dict[str, float],
    names: list[str] | None = None,
) -> dict[str, dict[str, dict[str, float]]]:
    """Result at each parameter's low and high end with everything else at base."""
    names = names or ui_params()
    out = {}
    for name in names:
        spec = param_spec(name)
        row = {}
        for end in ("low", "high"):
            p = dict(base)
            p[name] = float(spec[end])
            row[end] = evaluate(p)
        out[name] = row
    return out


def switching_value(
    evaluate: Callable[[dict[str, float]], dict[str, float]],
    base: dict[str, float],
    name: str,
    a: str,
    b: str,
    end: str,
    iterations: int = 14,
) -> float | None:
    """Value of ``name`` between central and ``end`` where a and b tie, or None."""
    spec = param_spec(name)
    lo_value, hi_value = float(base[name]), float(spec[end])

    def gap(value: float) -> float:
        p = dict(base)
        p[name] = value
        result = evaluate(p)
        return result[a] - result[b]

    g_lo, g_hi = gap(lo_value), gap(hi_value)
    if g_lo == 0:
        return lo_value
    if g_lo * g_hi > 0:
        return None
    for _ in range(iterations):
        mid = 0.5 * (lo_value + hi_value)
        g_mid = gap(mid)
        if g_mid * g_lo > 0:
            lo_value, g_lo = mid, g_mid
        else:
            hi_value = mid
    return 0.5 * (lo_value + hi_value)


def what_would_change(
    evaluate: Callable[[dict[str, float]], dict[str, float]],
    base: dict[str, float],
    a: str,
    b: str,
    oat: dict[str, dict[str, dict[str, float]]] | None = None,
) -> list[dict[str, Any]]:
    """Every single assumption that, moved inside its band, reverses a over b."""
    central_result = evaluate(base)
    gap0 = central_result[a] - central_result[b]
    oat = oat or one_at_a_time(evaluate, base)
    found = []
    for name, ends in oat.items():
        spec = param_spec(name)
        for end in ("low", "high"):
            if (ends[end][a] - ends[end][b]) * gap0 < 0:
                value = switching_value(evaluate, base, name, a, b, end)
                if value is None:
                    continue
                found.append(
                    {
                        "param": name,
                        "label": spec["label"],
                        "unit": spec["unit"],
                        "central": float(base[name]),
                        "switch_at": value,
                        "direction": end,
                        "band": [float(spec["low"]), float(spec["high"])],
                    }
                )
    found.sort(key=lambda row: abs(row["switch_at"] - row["central"]) / max(1e-9, abs(row["band"][1] - row["band"][0])))
    return found


def state_evaluator(state: StateData) -> Callable[[dict[str, float]], dict[str, float]]:
    def evaluate(p: dict[str, float]) -> dict[str, float]:
        result = evaluate_state(state, p)
        return {sid: row["delta"] for sid, row in result["statewide"].items()}

    return evaluate


def county_evaluator(state: StateData, county: County) -> Callable[[dict[str, float]], dict[str, float]]:
    values = state_unit_values(state)

    def evaluate(p: dict[str, float]) -> dict[str, float]:
        result = evaluate_county(county, state, p, state_values=values)
        return {sid: row["delta"] for sid, row in result["scenarios"].items()}

    return evaluate


# ---------------------------------------------------------- full analysis
def analyze(state: StateData, draws: int | None = None, seed: int | None = None, with_oat: bool = True) -> dict[str, Any]:
    """Central result plus all three layers, close calls, and switching values."""
    threshold = float(load_assumptions()["close_call_flip_share"])
    p = central_params()
    central = evaluate_state(state, p, variants=package_variants(p))
    env = run_envelope(state, draws, seed)
    zruns = zoning_runs(state, p)
    moe = run_moe(state, p)
    sids = compared_scenarios()

    def summarize_layer(index: int | None) -> dict[str, Any]:
        if index is None:
            central_vals = {sid: central["statewide"][sid]["delta"] for sid in sids}
            draws_vals = env["statewide"]
            z_vals = {k: {sid: run["statewide"][sid]["delta"] for sid in sids} for k, run in zruns.items() if k.startswith("prior")}
            moe_vals = moe["statewide"]
            baseline = central["statewide"]["baseline"]["delivery"]
        else:
            row = central["counties"][index]["scenarios"]
            central_vals = {sid: row[sid]["delta"] for sid in sids}
            draws_vals = [draw[index] for draw in env["county"]]
            z_vals = {
                k: {sid: run["counties"][index]["scenarios"][sid]["delta"] for sid in sids}
                for k, run in zruns.items()
                if k.startswith("prior")
            }
            moe_vals = moe["county"][index]
            baseline = row["baseline"]["delivery"]
        bounds = zoning_bounds(zruns, index=index)
        scen = {}
        for sid in ["baseline"] + sids:
            values = [d[sid] for d in draws_vals]
            scen[sid] = {
                "central": baseline if sid == "baseline" else central_vals[sid],
                "envelope": summarize(values, seed=env["seed"] if index is None else None),
                "zoning": bounds[sid],
                "acs_moe": moe_vals[sid],
            }
        order = ranking(central_vals, sids)
        pairs = {}
        for a, b in combinations(sids, 2):
            pairs[f"{a}|{b}"] = compare_pair(
                a, b, central_vals, draws_vals, bounds, z_vals, moe["gap"](a, b, index), threshold
            )
        top = pairs.get(f"{order[0]}|{order[1]}") or pairs[f"{order[1]}|{order[0]}"]
        benchmarks = [sid for sid in order if sid in ("adu", "missing_middle", "parking", "fees")]
        top_b = pairs.get(f"{benchmarks[0]}|{benchmarks[1]}") or pairs[f"{benchmarks[1]}|{benchmarks[0]}"]
        return {
            "scenarios": scen,
            "ranking": order,
            "benchmark_ranking": benchmarks,
            "pairs": pairs,
            "top_pair": top,
            "top_benchmark_pair": top_b,
        }

    out: dict[str, Any] = {
        "state": state.code,
        "draws": env["draws"],
        "seed": env["seed"],
        "envelope_params": env["params"],
        "close_call_flip_share": threshold,
        "coverage": central["coverage"],
        "implied_cost_elasticity": central["implied_cost_elasticity"],
        "statewide": summarize_layer(None),
        "counties": [],
        "central": central,
    }
    out["statewide"]["package_decomposition"] = package_decomposition(central)
    for index, county in enumerate(state.counties):
        row = summarize_layer(index)
        row.update({"fips": county.fips, "name": county.name, "coverage": central["counties"][index]["coverage"]})
        row["package_decomposition"] = package_decomposition(central["counties"][index]["scenarios"], key="county")
        out["counties"].append(row)
    if with_oat:
        evaluate = state_evaluator(state)
        oat = one_at_a_time(evaluate, p)
        out["one_at_a_time"] = oat
        top_b = out["statewide"]["top_benchmark_pair"]
        switches = what_would_change(evaluate, p, top_b["leader"], top_b["trailer"], oat)
        zero_p = dict(p)
        zero_p["pipeline_sigma"] = ELASTICITY_ZERO_SIGMA
        zero_run = evaluate_state(state, zero_p)
        zero_vals = {sid: zero_run["statewide"][sid]["delta"] for sid in sids}
        zero_vals["baseline"] = zero_run["statewide"]["baseline"]["delivery"]
        switches.append(
            {
                "param": "implied_cost_elasticity",
                "label": "Cost elasticity of 0 (pipeline_sigma → ∞; probit cannot reach 0)",
                "unit": "elasticity",
                "central": float(central["implied_cost_elasticity"]),
                "switch_at": 0.0,
                "direction": "low",
                "band": [0.0, float(central["implied_cost_elasticity"])],
                "zero_pipeline": {sid: zero_vals[sid] for sid in sids},
            }
        )
        out["what_would_change"] = {
            "pair": [top_b["leader"], top_b["trailer"]],
            "switches": switches,
        }
        out["elasticity_zero"] = {
            "pipeline_sigma": ELASTICITY_ZERO_SIGMA,
            "implied_cost_elasticity": implied_cost_elasticity(zero_p),
            "statewide": zero_vals,
        }
    return out
