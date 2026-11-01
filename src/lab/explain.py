# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Why-drawer payloads, live recomputes, and Lab briefs.

The browser reads locked results (``load_results(..., allow_compute=False)``)
so Vercel never runs the 2,000-draw envelope. Changing one assumption
recomputes the central case, the zoning bound, and the ACS band. The
envelope stays on the locked file; the response says so.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from src.lab.config import (
    LAB_STATES,
    SAMPLE_DIR,
    central_params,
    load_assumptions,
    load_scenarios,
    param_spec,
    ui_params,
)
from src.lab.data import Value, load_state
from src.lab.engine import (
    evaluate_county,
    evaluate_state,
    package_decomposition,
    package_variants,
    scenario_econ,
    state_unit_values,
)
from src.lab.options import evaluate_option
from src.lab.results import load_results
from src.lab.uncertainty import compared_scenarios, run_moe, zoning_bounds, zoning_runs
from src.model.assumptions import AssumptionError

BENCHMARKS = ("adu", "missing_middle", "parking", "fees")
FORMULAS = [
    {
        "id": "value",
        "label": "Value of one new home",
        "formula": "V = rent × new-home premium × 12 × (1 − operating share) / cap rate",
        "tags": ["observed", "assumed", "calculated"],
        "note": "Rent is the ACS county median. The premium, operating share, and cap rate are assumed.",
    },
    {
        "id": "margin",
        "label": "Excess margin",
        "formula": "m = V / C − 1;   x = m − hurdle",
        "tags": ["calculated"],
        "note": "C is hard cost × (1 + soft) + fee + parking. Homeowners use the owner hurdle; rebuilds use the developer hurdle.",
    },
    {
        "id": "feasibility",
        "label": "Feasible share of a lot slice",
        "formula": "F = Φ(x_best / σ)",
        "tags": ["calculated"],
        "note": "The lot shock is common across options, so the same option is best for the whole slice.",
    },
    {
        "id": "timing",
        "label": "Chance a feasible lot finishes in the window",
        "formula": "p(T) = 1 − exp(−λ × max(0, T − legal lag − build lag))",
        "tags": ["assumed", "calculated"],
        "note": "T is five years. λ is the homeowner or developer hazard.",
    },
    {
        "id": "adu_gate",
        "label": "ADU economics gate",
        "formula": "gate = min(1, Φ(x_ADU / σ) / Φ(x_ADU,ref / σ))",
        "tags": ["calculated", "assumed"],
        "note": "x_ref is the same ADU with fee = 0 and no parking. CA Gov. Code 65852.2(f)(3) (now 66311.5(c)(1)) exempts ADUs of 750 sq ft or less from impact fees. The Lab prototype is 600 sq ft.",
    },
    {
        "id": "delivery",
        "label": "Host delivery",
        "formula": "N = Σ H × F × p(T) × d  (ADU: N = Σ H × gate × p(T) × d)",
        "tags": ["calculated"],
        "note": "Each lot takes at most one option. d is net homes that option adds. ADUs use the CA all-lots rate times a fee/parking gate normalized to CA conditions (fee 0 and no parking). mm2 uses a feasible-lot hazard and F.",
    },
    {
        "id": "increment",
        "label": "Scenario increment",
        "formula": "N(L1, e1) − N(L0_pre, e1) − [N(L0, e0) − N(L0_pre, e0)]",
        "tags": ["calculated"],
        "note": "Homes already legal and flowing during the permit window stay in Baseline.",
    },
]


def check_state(code: str) -> str:
    key = code.strip().upper()
    if key not in LAB_STATES:
        raise AssumptionError(f"Lab state must be one of {', '.join(LAB_STATES)}")
    return key


def clamp_overrides(raw: Any) -> dict[str, float]:
    """Accept only published UI parameters, clamped to their band."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise AssumptionError("overrides must be an object")
    allowed = set(ui_params())
    out: dict[str, float] = {}
    for key, value in raw.items():
        if key not in allowed:
            raise AssumptionError(f"Unknown or locked Lab assumption '{key}'")
        spec = param_spec(key)
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise AssumptionError(f"Assumption '{key}' must be a number") from exc
        out[key] = min(float(spec["high"]), max(float(spec["low"]), number))
    return out


def assumption_catalog() -> dict[str, Any]:
    doc = load_assumptions()
    params = []
    for name in ui_params():
        spec = doc["params"][name]
        params.append(
            {
                "name": name,
                "label": spec["label"],
                "group": spec["group"],
                "unit": spec["unit"],
                "low": spec["low"],
                "central": spec["central"],
                "high": spec["high"],
                "rationale": spec["rationale"],
                "zoning_bound": bool(spec.get("zoning_bound")),
                "tag": "assumed",
            }
        )
    return {
        "version": doc["version"],
        "locked": doc["locked"],
        "window_start": doc["window_start"],
        "horizon_years": doc["horizon_years"],
        "draws": doc["monte_carlo_draws"],
        "seed": doc["monte_carlo_seed"],
        "parameters": params,
        "scenarios": [
            {
                "id": sid,
                "label": row["label"],
                "short": row["short"],
                "kind": row["kind"],
                "definition": row["definition"],
            }
            for sid, row in load_scenarios()["scenarios"].items()
        ],
    }


def locked_results(code: str) -> dict[str, Any]:
    """Committed results only. Vercel and the GET route never compute."""
    doc = dict(load_results(check_state(code), allow_compute=False))
    # Display label only. The JSON key close_call_flip_share stays 0.10.
    doc["close_call_flip_share_label"] = "close-call threshold"
    return doc


def geo(code: str) -> dict[str, Any]:
    path = SAMPLE_DIR / f"{check_state(code)}_counties.geo.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _value_row(name: str, label: str, item: Value) -> dict[str, Any]:
    return {
        "id": name,
        "label": label,
        "value": item.value,
        "moe": item.moe,
        "tag": item.tag,
        "source": item.source,
        "note": item.note,
    }


def _option_row(result: Any, illustrative: bool) -> dict[str, Any]:
    return {
        "option": result.option,
        "value": round(result.value, 1),
        "cost": round(result.cost, 1),
        "margin": round(result.margin, 4),
        "hurdle": round(result.hurdle, 4),
        "excess": round(result.excess, 4),
        "area": round(result.area, 1),
        "net": result.net,
        "spaces": round(result.spaces, 3),
        "illustrative": illustrative,
        "tag": "calculated",
    }


def why_county(code: str, county_key: str, scenario: str = "adu", overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Observed / assumed / calculated inputs for one county and scenario."""
    code = check_state(code)
    state = load_state(code)
    county = state.county(county_key)
    scenarios = load_scenarios()["scenarios"]
    if scenario not in scenarios:
        raise AssumptionError(f"Unknown scenario '{scenario}'")
    p = central_params()
    p.update(overrides or {})
    values = state_unit_values(state)
    evaluated = evaluate_county(
        county, state, p, state_values=values, variants=package_variants(p)
    )
    econ = scenario_econ(scenario if scenario != "baseline" else "baseline", p)
    adu_spaces = 1.0
    options = []
    for opt in ("adu", "mm2", "mm4", "mm6"):
        row = evaluate_option(
            opt, "detached", "urban", county.rent_1br.value, county.rent_2br.value,
            county.median_value.value, econ, adu_spaces, p, state.parking_cap,
        )
        options.append(_option_row(row, illustrative=opt == "adu"))
    evidence = []
    for rule in state.evidence.get("rules", []):
        place = rule.get("county") or rule.get("place")
        if place in {None, county.fips, county.name} or (rule.get("county") == county.fips):
            evidence.append(
                {
                    "id": rule["id"],
                    "option": rule["option"],
                    "status": rule["status"],
                    "tag": "observed",
                    "sources": rule.get("sources", []),
                    "note": rule.get("note", ""),
                }
            )
    inputs = [
        _value_row("detached", "1-unit detached homes (ACS B25024)", county.detached),
        _value_row("attached", "1-unit attached homes (ACS B25024)", county.attached),
        _value_row("rent_1br", "Median 1-bedroom rent (ACS B25031)", county.rent_1br),
        _value_row("rent_2br", "Median 2-bedroom rent (ACS B25031)", county.rent_2br),
        _value_row("median_value", "Median owner-occupied value (ACS B25077)", county.median_value),
        _value_row("housing_units", "Housing units (ACS B25001)", county.housing_units),
    ]
    bps = county.bps_avg
    inputs.append(
        {
            "id": "bps",
            "label": "Building Permits Survey 2023–2025 average, 1-unit permits",
            "value": bps["u1"],
            "moe": 0.0,
            "tag": "observed",
            "source": "Census Building Permits Survey 2023-2025 county files",
            "note": "",
        }
    )
    if county.hud_fmr:
        inputs.append(
            {
                "id": "hud_fmr_1br",
                "label": "HUD Fair Market Rent, 1-BR (optional context)",
                "value": county.hud_fmr.get("fmr_1br") or county.hud_fmr.get("1br") or 0.0,
                "moe": 0.0,
                "tag": "observed",
                "source": "HUD FMR FY2026 workbook, downloaded manually",
                "note": "Context only. The model uses ACS rents.",
            }
        )
    lots_note = None
    if county.fips == "42003" and state.allegheny_lots:
        lots_note = (
            "Allegheny lot-area bins are from WPRDC (Allegheny County parcel assessments). "
            "They are 2012 base-year assessed lot areas, not current transactions. "
            "Urban hosts use Pittsburgh bins; suburban and rural hosts use the rest of the county."
        )
    used = []
    for name in (
        "cap_rate", "opex_share", "new_unit_rent_premium", "adu_cost_psf", "adu_sqft",
        "conversion_cost_per_unit", "fee_per_unit", "hazard_homeowner", "hazard_homeowner_feasible",
        "host_margin_sigma",
        "adoption_lag_years", "prior_adu_prohibited", "prior_mm_prohibited",
    ):
        spec = param_spec(name)
        used.append(
            {
                "id": name,
                "label": spec["label"],
                "value": p[name],
                "tag": "assumed",
                "unit": spec["unit"],
                "rationale": spec["rationale"],
                "locked": bool(spec.get("locked")),
            }
        )
    row = evaluated["scenarios"][scenario]
    from src.plain import snap_tree

    decomp = package_decomposition(evaluated["scenarios"], key="scenarios")
    coverage = dict(evaluated["coverage"])
    coverage["tag"] = "calculated"
    coverage["source"] = "src/lab/engine.py evaluate_county coverage"
    decomp = dict(decomp)
    decomp["tag"] = "calculated"
    decomp["source"] = "src/lab/engine.py package_decomposition"
    payload = {
        "state": code,
        "county": {"fips": county.fips, "name": county.name},
        "scenario": scenario,
        "overrides": overrides or {},
        "inputs": inputs,
        "assumptions": used,
        "options": options,
        "option_note": (
            "The ADU pro forma is illustrative: urban detached lot, one parking space "
            "if the scenario still requires one, current ACS rents and the published assumptions. "
            "It is not a construction bid."
        ),
        "formulas": FORMULAS,
        "result": {
            "delivery": row.get("delivery", 0.0) if scenario == "baseline" else row.get("delta", 0.0),
            "eligible": row.get("eligible", 0.0),
            "feasible": row.get("feasible", 0.0),
            "host_delta": row.get("host_delta", 0.0) if scenario != "baseline" else row.get("host_adjustment", {}).get("delivered", 0.0),
            "pipeline_delta": row.get("pipeline_delta", 0.0) if scenario != "baseline" else row.get("pipeline_adjustment", 0.0),
            "by_option": row.get("by_option", {}),
            "tag": "calculated",
        },
        "coverage": coverage,
        "evidence": evidence,
        "lots_note": lots_note,
        "imputed": county.imputed,
        "package_decomposition": decomp,
    }
    return snap_tree(payload)


def _layer_row(sid: str, central: dict[str, Any], bounds: dict[str, float], moe: float) -> dict[str, Any]:
    field = "delivery" if sid == "baseline" else "delta"
    source = central[sid]
    out = {
        "central": source[field],
        "zoning_low": bounds["low"],
        "zoning_high": bounds["high"],
        "logical_low": bounds["logical_low"],
        "logical_high": bounds["logical_high"],
        "acs_moe": moe,
    }
    if sid == "baseline":
        out["pipeline_baseline"] = source["pipeline_baseline"]
        out["pipeline_adjustment"] = source["pipeline_adjustment"]
        host = source["host_adjustment"]
        out["host_adjustment"] = host["delivered"] if isinstance(host, dict) else host
    else:
        for key in ("eligible", "feasible", "host_delta", "pipeline_delta", "timing_delta"):
            out[key] = source.get(key, 0.0)
        out["by_option"] = {k: v for k, v in source.get("by_option", {}).items() if abs(v) >= 0.05}
    return out


def _pair_from_layers(
    a: str,
    b: str,
    central: dict[str, float],
    zoning_values: dict[str, dict[str, float]],
    moe_gap: float,
    flip_share: float,
    threshold: float,
) -> dict[str, Any]:
    gap = central[a] - central[b]
    zoning_flip = any((values[a] - values[b]) * gap < 0 for values in zoning_values.values())
    moe_flip = abs(gap) < moe_gap
    reasons = []
    if flip_share >= threshold:
        reasons.append(f"order flips in {flip_share:.0%} of assumption draws")
    if zoning_flip:
        reasons.append("order flips at an end of the zoning-evidence bound")
    if moe_flip:
        reasons.append("gap is inside the ACS sampling band")
    leader, trailer = (a, b) if gap >= 0 else (b, a)
    return {
        "leader": leader,
        "trailer": trailer,
        "gap": abs(gap),
        "flip_share": flip_share,
        "zoning_flip": zoning_flip,
        "moe_gap": moe_gap,
        "close_call": bool(reasons),
        "reasons": reasons,
    }


def _flip_share_map(locked: dict[str, Any], county_fips: str | None) -> dict[str, float]:
    if county_fips:
        for row in locked["counties"]:
            if row["fips"] == county_fips:
                return {key: float(val[0]) for key, val in row.get("pairs", {}).items()}
    return {key: float(val["flip_share"]) for key, val in locked["statewide"]["pairs"].items()}


def recompute(code: str, overrides: dict[str, float] | None = None, county_key: str | None = None) -> dict[str, Any]:
    """Central + zoning + ACS band for a one-assumption change. Envelope stays locked."""
    code = check_state(code)
    overrides = overrides or {}
    state = load_state(code)
    p = central_params()
    p.update(overrides)
    locked = locked_results(code)
    central = evaluate_state(state, p, variants=package_variants(p))
    zruns = zoning_runs(state, p)
    moe = run_moe(state, p)
    bounds = zoning_bounds(zruns)
    sids = compared_scenarios()
    threshold = float(load_assumptions()["close_call_flip_share"])
    sw_central = {sid: central["statewide"][sid]["delta"] for sid in sids}
    sw_central["baseline"] = central["statewide"]["baseline"]["delivery"]
    z_vals = {
        label: {sid: run["statewide"][sid]["delta"] for sid in sids}
        for label, run in zruns.items()
        if label.startswith("prior")
    }
    flips = _flip_share_map(locked, None)
    ranking = sorted(sids, key=lambda sid: -sw_central[sid])
    benchmarks = sorted(BENCHMARKS, key=lambda sid: -sw_central[sid])
    top = (benchmarks[0], benchmarks[1])
    pair_key = "|".join(sorted(top))
    statewide = {
        "results": {
            sid: _layer_row(
                sid,
                central["statewide"],
                bounds[sid],
                moe["statewide"][sid],
            )
            for sid in ["baseline"] + sids
        },
        "ranking": ranking,
        "benchmark_ranking": benchmarks,
        "top_benchmark_pair": _pair_from_layers(
            top[0], top[1], sw_central, z_vals, moe["gap"](*top), flips.get(pair_key, 0.0), threshold
        ),
        "package_decomposition": package_decomposition(central),
    }
    counties = []
    for index, row in enumerate(central["counties"]):
        cb = zoning_bounds(zruns, index=index)
        counties.append(
            {
                "fips": row["fips"],
                "name": row["name"],
                "results": {
                    sid: _layer_row(sid, row["scenarios"], cb[sid], moe["county"][index][sid])
                    for sid in ["baseline"] + sids
                },
                "coverage": row["coverage"],
                "package_decomposition": package_decomposition(row["scenarios"], key="scenarios"),
            }
        )
    picked = None
    if county_key:
        county = state.county(county_key)
        picked = next(c for c in counties if c["fips"] == county.fips)
    return {
        "state": code,
        "overrides": overrides,
        "envelope_note": (
            f"The p10–p90 envelope is from the locked {locked['draws']:,}-draw run "
            f"(seed {locked['seed']}) and does not move when you change one slider. "
            "Central values, zoning bounds, and the ACS band are live."
        ),
        "coverage": central["coverage"],
        "implied_cost_elasticity": central["implied_cost_elasticity"],
        "statewide": statewide,
        "counties": counties,
        "county": picked,
        "changed": list(overrides),
    }


def _fmt(value: float) -> str:
    from src.plain import homes

    return homes(value, signed=True) if value else "0"


def _band(low: float, high: float) -> str:
    from src.plain import homes

    left = homes(low)
    right = homes(high)
    if left == "0" and right == "0":
        return "0"
    return f"{left}–{right}"


def brief_markdown(code: str, county_key: str | None = None, live: dict[str, Any] | None = None) -> str:
    """One-page policy brief from locked or live results."""
    from src.plain import CORE_URL, LAB_URL, SCENARIO_SHORT, format_assumption, homes, ranking_phrase

    code = check_state(code)
    locked = locked_results(code)
    sw = (live or locked)["statewide"]
    results = sw["results"]
    meta = LAB_STATES[code]
    lines = [
        f"# Small Homes Policy Lab — {meta['name']}",
        "",
        f"Net new homes completed in 2027–2031 versus Baseline. {meta['name']} is the "
        f"{'primary case' if meta['role'] == 'primary' else 'portability test'}.",
        "",
        f"Evidence coverage (stock-weighted): ADU {locked['coverage']['adu']:.1%}, "
        f"2–6 homes {locked['coverage']['mm']:.1%}. Unknown zoning is never treated as zero.",
        "",
        "| Scenario | Central | Likely range | Zoning bound | Census survey error |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for sid in ["baseline"] + list(compared_scenarios()):
        row = results[sid]
        label = SCENARIO_SHORT.get(sid) or next(s["short"] for s in locked["scenarios"] if s["id"] == sid)
        env = locked["statewide"]["results"][sid]
        central = homes(row["central"]) if sid == "baseline" else homes(row["central"], signed=True)
        lines.append(
            f"| {label} | {central} | {_band(env['p10'], env['p90'])} | "
            f"{_band(row['zoning_low'], row['zoning_high'])} | ±{homes(row['acs_moe'])} |"
        )
    top = sw["top_benchmark_pair"]
    leader = SCENARIO_SHORT.get(top["leader"], top["leader"])
    trailer = SCENARIO_SHORT.get(top["trailer"], top["trailer"])
    threshold = locked.get("close_call_flip_share_label", "close-call threshold")
    lines += [
        "",
        f"Handbook ranking: {ranking_phrase(sw['benchmark_ranking'])}.",
        f"Top pair: {leader} leads {trailer} by {homes(top['gap'])} homes.",
        f"The {threshold} is 10 percent of assumption draws.",
    ]
    se_bits = []
    for sid in ["baseline"] + list(compared_scenarios()):
        env = locked["statewide"]["results"][sid]
        if "p50_se" in env:
            label = SCENARIO_SHORT.get(sid) or next(s["short"] for s in locked["scenarios"] if s["id"] == sid)
            se_bits.append(f"{label} ±{homes(env['p50_se'])}")
    if se_bits:
        lines.append(
            f"Envelope sampling error (bootstrap SE of P50, {locked['draws']:,} draws, seed {locked['seed']}): "
            + "; ".join(se_bits) + "."
        )
    if top["close_call"]:
        lines.append("**Ranking is close.** " + "; ".join(top["reasons"]) + ".")
    decomp = sw["package_decomposition"]
    lines += [
        "",
        "## Package is not a sum",
        "",
        f"Legalization resolved (one option per lot): {homes(decomp['legalization_resolved'])}. "
        f"If ADU and missing middle were added: {homes(decomp['legalization_if_summed'])} "
        f"(competition loss {homes(decomp['competition_loss'], signed=True)}). "
        f"Package {homes(decomp['package'])} vs sum of separate {homes(decomp['sum_of_separate'])}.",
        "",
    ]
    wwc = locked["statewide"].get("what_would_change")
    if wwc:
        left = SCENARIO_SHORT.get(wwc["pair"][0], wwc["pair"][0])
        right = SCENARIO_SHORT.get(wwc["pair"][1], wwc["pair"][1])
        lines.append("## What would change the statewide conclusion")
        lines.append("")
        lines.append(f"Central ranking of {left} over {right} flips if:")
        for row in wwc["switches"]:
            lines.append(
                f"- {row['label']} moves to {format_assumption(row['unit'], row['switch_at'])} "
                f"(central {format_assumption(row['unit'], row['central'])})"
            )
        lines.append("")
    if county_key:
        county = load_state(code).county(county_key)
        source = None
        if live and live.get("county") and live["county"]["fips"] == county.fips:
            source = live["county"]
        else:
            source = next(c for c in locked["counties"] if c["fips"] == county.fips)
        lines += [
            f"## {county.name} County",
            "",
            f"ADU coverage {source['coverage']['adu']:.1%}."
            + (" Walkthrough county for Pennsylvania." if county.fips == "42003" else ""),
            "",
        ]
        for sid in BENCHMARKS:
            lines.append(f"- {SCENARIO_SHORT.get(sid, sid)}: {_fmt(source['results'][sid]['central'])}")
        lines.append("")
    if live and live.get("envelope_note"):
        lines += ["## Note", "", live["envelope_note"], ""]
    from src.adu_fee_note import note_text

    lines += [
        "## ADU fee difference",
        "",
        note_text("docs"),
        "",
        "Every number is tagged observed, assumed, or calculated in the Why drawer. "
        "The ADU pro forma shown there is illustrative.",
        "",
        f"Lab: {LAB_URL}. Core engine: {CORE_URL}.",
        "Method: docs/SMALL_HOMES_LAB.md. Apache-2.0.",
    ]
    return "\n".join(lines) + "\n"


def brief_html(markdown: str) -> str:
    """Minimal HTML wrapper so a brief opens in a browser."""
    escaped = (
        markdown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    body = ""
    for line in escaped.splitlines():
        if line.startswith("# "):
            body += f"<h1>{line[2:]}</h1>\n"
        elif line.startswith("## "):
            body += f"<h2>{line[3:]}</h2>\n"
        elif line.startswith("| "):
            body += f"<pre>{line}</pre>\n" if "<table>" not in body else f"<pre>{line}</pre>\n"
        elif line.startswith("- "):
            body += f"<li>{line[2:]}</li>\n"
        elif line.startswith("**"):
            body += f"<p>{line}</p>\n"
        elif line:
            body += f"<p>{line}</p>\n"
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<title>Small Homes Policy Lab brief</title>"
        "<style>body{font-family:Georgia,serif;max-width:720px;margin:32px auto;padding:0 16px;}"
        "pre{font-size:13px}</style></head><body>"
        f"{body}</body></html>"
    )


def county_csv(code: str, live: dict[str, Any] | None = None) -> str:
    locked = locked_results(check_state(code))
    counties = live["counties"] if live and live.get("counties") else locked["counties"]
    locked_map = {row["fips"]: row for row in locked["counties"]}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "fips", "county", "scenario", "central", "envelope_p10", "envelope_p90",
            "zoning_low", "zoning_high", "acs_moe", "eligible", "feasible",
            "close_call_top_benchmark",
        ]
    )
    sids = ["baseline"] + list(compared_scenarios())
    for row in counties:
        locked_row = locked_map[row["fips"]]
        close = False
        if "top_benchmark_pair" in locked_row:
            close = locked_row["top_benchmark_pair"]["close_call"]
        elif "pairs" in locked_row:
            close = any(val[1] for val in locked_row["pairs"].values())
        for sid in sids:
            cell = row["results"][sid]
            env = locked_row["results"][sid]
            writer.writerow(
                [
                    row["fips"], row["name"], sid, f"{cell['central']:.1f}",
                    f"{env['p10']:.1f}", f"{env['p90']:.1f}",
                    f"{cell['zoning_low']:.1f}", f"{cell['zoning_high']:.1f}",
                    f"{cell['acs_moe']:.1f}",
                    f"{cell.get('eligible', 0):.1f}", f"{cell.get('feasible', 0):.1f}",
                    "yes" if close else "no",
                ]
            )
    return buf.getvalue()


def export_brief(
    code: str,
    fmt: str,
    county_key: str | None = None,
    overrides: dict[str, float] | None = None,
) -> tuple[bytes, str, str]:
    if fmt not in {"md", "html", "csv"}:
        raise AssumptionError("format must be md, html, or csv")
    live = recompute(code, overrides, county_key) if overrides else None
    stem = f"lab-{check_state(code).lower()}"
    if fmt == "csv":
        return county_csv(code, live).encode("utf-8"), "text/csv; charset=utf-8", f"{stem}-counties.csv"
    markdown = brief_markdown(code, county_key, live)
    if fmt == "html":
        return brief_html(markdown).encode("utf-8"), "text/html; charset=utf-8", f"{stem}-brief.html"
    return markdown.encode("utf-8"), "text/markdown; charset=utf-8", f"{stem}-brief.md"
