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


def _homes(value: float) -> str:
    return f"{round(value):+,.0f}"


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _pct(value: float) -> str:
    return f"{value:.1%}".replace("%", " percent")


def _waterfall(state: Any, lab_fee: float, core_fee: float, core_cap: float, core_rent: float) -> list[dict[str, Any]]:
    """Move the Lab toward the core, one published assumption at a time."""
    steps: list[dict[str, Any]] = []
    params = dict(central_params())

    def run(label: str) -> float:
        row = evaluate_state(state, params, scenarios=["adu"])["statewide"]["adu"]
        homes = float(row["delta"])
        steps.append({"label": label, "homes": homes})
        return homes

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


@lru_cache(maxsize=4)
def comparison(state: str = "PA") -> dict[str, Any]:
    """Fees, both ADU increments, the waterfall, and the note texts."""
    code = state.strip().upper()
    lab = load_results(code, allow_compute=False)
    lab_adu = float(lab["statewide"]["results"]["adu"]["central"])
    lab_fee = float(central_params()["fee_per_unit"])

    fixtures, assumptions = load_bundle()
    core = simulate_state(fixtures, assumptions, code)
    core_adu = float(core["scenarios"]["adu"]["incremental_completions"])
    catalog = load_assumptions()
    core_fee = float(catalog.spec("adu_fee_per_unit")["central"])
    core_cap = float(catalog.spec("adu_homeowner_cap_rate")["central"])
    core_rent = float(catalog.spec("adu_rent_ratio")["central"])

    steps = _waterfall(load_state(code), lab_fee, core_fee, core_cap, core_rent)
    after_fee = float(steps[1]["homes"])
    after_yield = float(steps[2]["homes"])
    after_lags = float(steps[3]["homes"])
    gap = abs(after_lags - core_adu) / core_adu if core_adu else 0.0

    payload = {
        "state": code,
        "lab_adu": lab_adu,
        "core_adu": core_adu,
        "lab_fee": lab_fee,
        "core_fee": core_fee,
        "core_cap_rate": core_cap,
        "core_rent_ratio": core_rent,
        "waterfall": steps,
        "after_fee": after_fee,
        "after_yield": after_yield,
        "after_lags": after_lags,
        "close_share": gap,
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
    walk = (
        f"Walking the Lab toward the core, one step at a time: use the {core_fee} fee "
        f"({fee_step}); then value the ADU the way a homeowner does — {cap} cap rate, "
        f"no operating share, rent × {rent} ({yield_step}); then drop adoption and "
        f"build lags ({lag_step}), within about {close} of the core."
    )
    if audience == "core":
        lead = (
            f"This page's ADU number ({core} in Pennsylvania) uses the core engine's "
            f"{core_fee} per-home ADU fee. The Small Homes Policy Lab applies the "
            f"Handbook's {lab_fee} fee to ADUs and reports {lab}."
        )
        other = "See the Lab ADU number."
        href, label = "/lab", "Lab ADU number"
    elif audience == "lab":
        lead = (
            f"This page's ADU number ({lab} in Pennsylvania) applies the Handbook's "
            f"{lab_fee} per-home fee to ADUs. The core Stateframe engine uses its own "
            f"{core_fee} ADU fee and reports {core}."
        )
        other = "See the core ADU number."
        href, label = "/", "core ADU number"
    else:
        lead = (
            f"The Lab's Pennsylvania ADU increment ({lab}) applies the Handbook's "
            f"{lab_fee} per-home fee to ADUs. The core Stateframe engine uses its own "
            f"{core_fee} ADU fee and reports {core}."
        )
        other = "See the Lab at /lab and the core engine at /."
        href, label = "/lab", "Lab ADU number"
    why = "That fee gap is why the two numbers differ."
    if html and audience in {"core", "lab"}:
        other = f'See the <a href="{href}">{label}</a>.'
    return f"{lead} {why} {walk} {other}"


def note_text(audience: str = "docs") -> str:
    return comparison()["notes"][audience]


def note_html(audience: str) -> str:
    key = "lab_html" if audience == "lab" else "core_html"
    return comparison()["notes"][key]
