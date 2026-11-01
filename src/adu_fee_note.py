# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Explain why the Lab and core Pennsylvania ADU increments differ.

Both published numbers are kept. The Lab applies the Handbook's locked
per-home fee to ADUs. The core engine uses its own ADU fee. This module
reads those fees and both increments from the engines, then walks the Lab
toward the core one assumption at a time so the note can say why they differ.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from src.bundle import load_bundle
from src.lab.config import central_params
from src.lab.data import load_state
from src.lab.engine import evaluate_state
from src.lab.results import load_results
from src.model.assumptions import load_assumptions
from src.model.engine import simulate_state
from src.plain import CORE_URL, LAB_URL, homes, money, snap, tag_block


def _homes(value: float) -> str:
    return homes(value, signed=True)


def _money(value: float) -> str:
    return money(value)


def _pct(value: float) -> str:
    return f"{value:.1%}".replace("%", " percent")


def _round_homes(value: float) -> int:
    return int(round(float(value)))


def _waterfall(state: Any, lab_fee: float, core_fee: float, core_cap: float, core_rent: float) -> list[dict[str, Any]]:
    """Move the Lab toward the core, one published assumption at a time."""
    steps: list[dict[str, Any]] = []
    params = dict(central_params())

    def run(label: str) -> float:
        row = evaluate_state(state, params, scenarios=["adu"])["statewide"]["adu"]
        raw = float(row["delta"])
        steps.append(
            {
                "label": label,
                "homes": _round_homes(raw),
                "tag": "calculated",
                "source": "src/lab/engine.py evaluate_state adu.delta",
            }
        )
        return raw

    run(f"Lab central (Handbook {_money(lab_fee)} fee per home)")
    params["fee_per_unit"] = core_fee
    run(f"Core ADU fee of {_money(core_fee)} instead of {_money(lab_fee)}")
    params["cap_rate"] = core_cap
    params["opex_share"] = 0.0
    params["new_unit_rent_premium"] = core_rent
    run(
        "Homeowner yield: cap rate "
        f"{_pct(core_cap)}, no operating share, rent × {core_rent:g}"
    )
    params["adoption_lag_years"] = 0.0
    params["build_lag_adu_years"] = 0.0
    run("No adoption lag and no ADU build lag")
    return steps


def _baseline_note(lab_base: float, core_base: float) -> str:
    lab = homes(lab_base)
    core = homes(core_base)
    return (
        f"The Lab baseline ({lab}) and the core baseline ({core}) use the same "
        "completion shares (0.93/0.90/0.84) and the same 5-year window. The Lab "
        "uses the 2023-2025 permit average and the core uses 2022-2024. That "
        "moves Pennsylvania by +1,988, mostly from 5+ unit permits (+2,170). "
        "The Lab also adds a +78 host adjustment for already-legal homes."
    )


@lru_cache(maxsize=4)
def comparison(state: str = "PA") -> dict[str, Any]:
    """Fees, both ADU increments, the waterfall, and the note texts."""
    code = state.strip().upper()
    lab = load_results(code, allow_compute=False)
    lab_adu = float(lab["statewide"]["results"]["adu"]["central"])
    lab_base = float(lab["statewide"]["results"]["baseline"]["central"])
    lab_fee = float(central_params()["fee_per_unit"])

    fixtures, assumptions = load_bundle()
    core = simulate_state(fixtures, assumptions, code)
    core_adu = float(core["scenarios"]["adu"]["incremental_completions"])
    core_base = float(core["baseline_completions_5yr"])
    catalog = load_assumptions()
    core_fee = float(catalog.spec("adu_fee_per_unit")["central"])
    core_cap = float(catalog.spec("adu_homeowner_cap_rate")["central"])
    core_rent = float(catalog.spec("adu_rent_ratio")["central"])

    steps = _waterfall(load_state(code), lab_fee, core_fee, core_cap, core_rent)
    after_fee = float(steps[1]["homes"])
    after_yield = float(steps[2]["homes"])
    after_lags = float(steps[3]["homes"])
    gap = abs(after_lags - _round_homes(core_adu)) / core_adu if core_adu else 0.0

    payload = {
        "state": code,
        "lab_adu": _round_homes(lab_adu),
        "core_adu": _round_homes(core_adu),
        "lab_baseline": _round_homes(lab_base),
        "core_baseline": _round_homes(core_base),
        "lab_fee": _round_homes(lab_fee),
        "core_fee": _round_homes(core_fee),
        "core_cap_rate": snap(core_cap),
        "core_rent_ratio": snap(core_rent),
        "waterfall": steps,
        "after_fee": _round_homes(after_fee),
        "after_yield": _round_homes(after_yield),
        "after_lags": _round_homes(after_lags),
        "close_share": round(gap, 2),
        "baseline_note": _baseline_note(lab_base, core_base),
        "provenance": {
            "lab_adu": tag_block(
                _round_homes(lab_adu),
                "calculated",
                "data/sample/lab/results_PA.json statewide.results.adu.central",
            ),
            "core_adu": tag_block(
                _round_homes(core_adu),
                "calculated",
                "src/model/engine.py scenarios.adu.incremental_completions",
            ),
            "lab_baseline": tag_block(
                _round_homes(lab_base),
                "calculated",
                "data/sample/lab/results_PA.json statewide.results.baseline.central",
            ),
            "core_baseline": tag_block(
                _round_homes(core_base),
                "calculated",
                "src/model/engine.py baseline_completions_5yr",
            ),
            "lab_fee": tag_block(
                _round_homes(lab_fee),
                "assumed",
                "config/lab/assumptions.yaml params.fee_per_unit",
            ),
            "core_fee": tag_block(
                _round_homes(core_fee),
                "assumed",
                "config/assumptions.yaml parameters.adu_fee_per_unit",
            ),
            "core_cap_rate": tag_block(
                core_cap,
                "assumed",
                "config/assumptions.yaml parameters.adu_homeowner_cap_rate",
            ),
            "core_rent_ratio": tag_block(
                core_rent,
                "assumed",
                "config/assumptions.yaml parameters.adu_rent_ratio",
            ),
            "after_fee": tag_block(
                _round_homes(after_fee),
                "calculated",
                "src/lab/engine.py evaluate_state fee_per_unit override",
            ),
            "after_yield": tag_block(
                _round_homes(after_yield),
                "calculated",
                "src/lab/engine.py evaluate_state homeowner yield overrides",
            ),
            "after_lags": tag_block(
                _round_homes(after_lags),
                "calculated",
                "src/lab/engine.py evaluate_state lag overrides",
            ),
            "close_share": tag_block(
                round(gap, 2),
                "calculated",
                "src/adu_fee_note.py after_lags vs core_adu",
            ),
        },
    }
    payload["notes"] = {
        "core": _compose(payload, "core"),
        "lab": _compose(payload, "lab"),
        "docs": _compose(payload, "docs"),
        "core_html": _compose(payload, "core", html=True),
        "lab_html": _compose(payload, "lab", html=True),
    }
    return payload


def _compose(doc: dict[str, Any], audience: str, html: bool = False) -> str:
    lab = _homes(doc["lab_adu"])
    core = _homes(doc["core_adu"])
    lab_fee = _money(doc["lab_fee"])
    core_fee = _money(doc["core_fee"])
    fee_step = _homes(doc["after_fee"])
    yield_step = _homes(doc["after_yield"])
    lag_step = _homes(doc["after_lags"])
    cap = _pct(doc["core_cap_rate"])
    rent = f"{doc['core_rent_ratio']:g}"
    close = f"{doc['close_share'] * 100:.0f} percent"
    policy = (
        f"ADU results depend heavily on local ADU fees. At the Handbook's {lab_fee} fee: "
        f"{lab}. At a {core_fee} fee: {fee_step}. Our headline uses the Handbook fee."
    )
    walk = (
        f"Walking the Lab toward the core: value the ADU the way a homeowner does — "
        f"{cap} cap rate, no operating share, rent × {rent} ({yield_step}); then drop "
        f"adoption and build lags ({lag_step}), within about {close} of the core."
    )
    if audience == "core":
        lead = (
            f"This page's ADU number ({core} in Pennsylvania) uses the core engine's "
            f"{core_fee} per-home ADU fee. The Small Homes Policy Lab applies the "
            f"Handbook's {lab_fee} fee to ADUs and reports {lab}."
        )
        other = f"See the Lab ADU number at {LAB_URL}."
        href, label = "/lab", "Lab ADU number"
    elif audience == "lab":
        lead = (
            f"This page's ADU number ({lab} in Pennsylvania) applies the Handbook's "
            f"{lab_fee} per-home fee to ADUs. The core Stateframe engine uses its own "
            f"{core_fee} ADU fee and reports {core}."
        )
        other = f"See the core ADU number at {CORE_URL}."
        href, label = "/", "core ADU number"
    else:
        lead = (
            f"The Lab's Pennsylvania ADU increment ({lab}) applies the Handbook's "
            f"{lab_fee} per-home fee to ADUs. The core Stateframe engine uses its own "
            f"{core_fee} ADU fee and reports {core}."
        )
        other = f"See the Lab at {LAB_URL} and the core engine at {CORE_URL}."
        href, label = LAB_URL, "Lab ADU number"
    why = "That fee gap is why the two numbers differ."
    if html and audience in {"core", "lab"}:
        other = f'See the <a href="{href}">{label}</a>.'
        details = f"<details><summary>How the two ADU numbers connect</summary><p>{walk}</p></details>"
        gap = f"<p class='baseline-gap'>{doc['baseline_note']}</p>"
        return f"{policy} {lead} {why} {other} {details}{gap}"
    if audience == "docs":
        return f"{policy} {lead} {why} {walk} {other} {doc['baseline_note']}"
    return f"{policy} {lead} {why} {walk} {other}"


def note_text(audience: str = "docs") -> str:
    return comparison()["notes"][audience]


def note_html(audience: str) -> str:
    key = "lab_html" if audience == "lab" else "core_html"
    return comparison()["notes"][key]
