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
from html import escape
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
    run(f"Lab with a {_money(core_fee)} fee instead of the Handbook's {_money(lab_fee)}")
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


def _baseline_note(lab_base: float, core_base: float, host_adj: float = 0.0) -> str:
    """Baseline gap from the two engines. The permit-window piece is the residual."""
    lab = homes(lab_base)
    core = homes(core_base)
    gap = _round_homes(lab_base) - _round_homes(core_base)
    host_n = _round_homes(host_adj)
    permit_piece = gap - host_n
    host = homes(host_adj, signed=True)
    window = homes(permit_piece, signed=True)
    return (
        f"The Lab baseline ({lab}) and the core baseline ({core}) differ by "
        f"{homes(gap, signed=True)}. Pennsylvania's core permits are the same "
        "2023-2025 county files as the Lab. The Lab pipeline uses the same "
        "never-complete shares as the core (0.93/0.90/0.90), including "
        "completion_ratio_mf for 5+ homes, so the pipeline baselines match. "
        f"The residual after the host term is {window}. The Lab also adds a {host} "
        "host adjustment for already-legal homes the permit window cannot contain yet."
    )


@lru_cache(maxsize=4)
def comparison(state: str = "PA") -> dict[str, Any]:
    """Fees, both ADU increments, the waterfall, and the note texts."""
    code = state.strip().upper()
    lab = load_results(code, allow_compute=False)
    lab_adu = float(lab["statewide"]["results"]["adu"]["central"])
    lab_base = float(lab["statewide"]["results"]["baseline"]["central"])
    lab_package = float(lab["statewide"]["results"]["package"]["central"])
    host_adj = float(lab["statewide"]["results"]["baseline"].get("host_adjustment", 0.0))
    lab_fee = float(central_params()["fee_per_unit"])

    fixtures, assumptions = load_bundle()
    core = simulate_state(fixtures, assumptions, code)
    core_adu = float(core["scenarios"]["adu"]["incremental_completions"])
    core_base = float(core["baseline_completions_5yr"])
    core_package = float(core["scenarios"]["combined"]["incremental_completions"])
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
        "state_name": str(lab.get("name") or core.get("name") or code),
        "lab_adu": _round_homes(lab_adu),
        "core_adu": _round_homes(core_adu),
        "lab_package": _round_homes(lab_package),
        "core_package": _round_homes(core_package),
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
        "baseline_note": _baseline_note(lab_base, core_base, host_adj),
        "provenance": {
            "lab_adu": tag_block(
                _round_homes(lab_adu),
                "calculated",
                f"data/sample/lab/results_{code}.json statewide.results.adu.central",
            ),
            "lab_package": tag_block(
                _round_homes(lab_package),
                "calculated",
                f"data/sample/lab/results_{code}.json statewide.results.package.central",
            ),
            "core_adu": tag_block(
                _round_homes(core_adu),
                "calculated",
                "src/model/engine.py scenarios.adu.incremental_completions",
            ),
            "core_package": tag_block(
                _round_homes(core_package),
                "calculated",
                "src/model/engine.py scenarios.combined.incremental_completions",
            ),
            "lab_baseline": tag_block(
                _round_homes(lab_base),
                "calculated",
                f"data/sample/lab/results_{code}.json statewide.results.baseline.central",
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
        "engine_gap_core": engine_gap_text(payload, "core"),
        "engine_gap_lab": engine_gap_text(payload, "lab"),
        "engine_gap_docs": engine_gap_text(payload, "docs"),
        "engine_gap_core_html": engine_gap_text(payload, "core", html=True),
        "engine_gap_lab_html": engine_gap_text(payload, "lab", html=True),
    }
    return payload


def _link(href: str, label: str) -> str:
    return f'<a href="{href}" style="display:inline-block;min-height:24px">{label}</a>'


def engine_gap_text(doc: dict[str, Any], audience: str, html: bool = False) -> str:
    """Why the two pages disagree, from the same engines as the headline numbers."""
    place = doc.get("state_name") or doc["state"]
    lab_fee = _money(doc["lab_fee"])
    core_fee = _money(doc["core_fee"])
    lab_pkg = _homes(doc["lab_package"])
    core_pkg = _homes(doc["core_package"])
    if audience == "core":
        text = (
            f"These headline numbers are the core screening model. It uses a {core_fee} ADU fee. "
            f"The Handbook scenarios are answered on the Small Homes Policy Lab, which uses the "
            f"Handbook's {lab_fee} per-home fees and a county-level model. For {place} the Lab "
            f"package is {lab_pkg}, not the {core_pkg} shown here."
        )
        href, label = "/lab", "Open the Lab"
        plain = f" See the Lab at {LAB_URL}."
    elif audience == "lab":
        text = (
            f"These headline numbers answer the Handbook scenarios. The Lab uses the Handbook's "
            f"{lab_fee} per-home fees and a county-level model. The core Stateframe page uses a "
            f"{core_fee} ADU fee and a statewide screening model. For {place} that core package "
            f"is {core_pkg}, against {lab_pkg} here."
        )
        href, label = "/", "Open the core page"
        plain = f" See the core engine at {CORE_URL}."
    else:
        text = (
            f"The Lab numbers answer the Handbook scenarios (Handbook {lab_fee} per-home fees, "
            f"county-level model). The core numbers are an eleven-state screening model with a "
            f"{core_fee} ADU fee. {place} package: Lab {lab_pkg}, core {core_pkg}."
        )
        href, label = LAB_URL, "Open the Lab"
        plain = f" See the Lab at {LAB_URL} and the core engine at {CORE_URL}."
    if html:
        return f"{escape(text)} {_link(href, label)}."
    return text + plain


def _compose(doc: dict[str, Any], audience: str, html: bool = False) -> str:
    place = doc.get("state_name") or "Pennsylvania"
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
    # after_fee is the Lab engine with the core fee, not the core engine's result.
    fees = (
        f"Lab at the Handbook's {lab_fee} fee: {lab}. "
        f"Lab at a {core_fee} fee: {fee_step}. "
        f"Core at a {core_fee} fee: {core}. "
        f"The same {core_fee} fee does not match because the Lab is a county-level model "
        "and the core uses a different adoption and valuation model."
    )
    walk = (
        f"Walking the Lab toward the core: value the ADU the way a homeowner does — "
        f"{cap} cap rate, no operating share, rent × {rent} ({yield_step}); then drop "
        f"adoption and build lags ({lag_step}), within about {close} of the core."
    )
    if audience == "core":
        lead = (
            f"This page's ADU number ({core} in {place}) uses the core engine's "
            f"{core_fee} per-home ADU fee. The Small Homes Policy Lab applies the "
            f"Handbook's {lab_fee} fee to ADUs and reports {lab}."
        )
        other = f"See the Lab ADU number at {LAB_URL}."
        href, label = "/lab", "Lab ADU number"
    elif audience == "lab":
        lead = (
            f"This page's ADU number ({lab} in {place}) applies the Handbook's "
            f"{lab_fee} per-home fee to ADUs. The core Stateframe engine uses its own "
            f"{core_fee} ADU fee and reports {core}."
        )
        other = f"See the core ADU number at {CORE_URL}."
        href, label = "/", "core ADU number"
    else:
        lead = (
            f"The Lab's {place} ADU increment ({lab}) applies the Handbook's "
            f"{lab_fee} per-home fee to ADUs. The core Stateframe engine uses its own "
            f"{core_fee} ADU fee and reports {core}."
        )
        other = f"See the Lab at {LAB_URL} and the core engine at {CORE_URL}."
        href, label = LAB_URL, "Lab ADU number"
    handbook = "The Lab numbers answer the Handbook scenarios."
    if html and audience in {"core", "lab"}:
        other = f"See the {_link(href, label)}."
        # The bridge stays outside <details> so the two $6,000 figures are explained on screen.
        gap = f"<p class='baseline-gap'>{doc['baseline_note']}</p>"
        return f"{fees} {lead} {handbook} {walk} {other} {gap}"
    if audience == "docs":
        # engine_gap_text already names the Handbook scenarios and links both pages.
        return f"{fees} {lead} {walk} {engine_gap_text(doc, 'docs')} {doc['baseline_note']}"
    return f"{fees} {lead} {handbook} {walk} {other}"


def note_text(audience: str = "docs") -> str:
    return comparison()["notes"][audience]


def note_html(audience: str) -> str:
    key = "lab_html" if audience == "lab" else "core_html"
    return comparison()["notes"][key]


def engine_gap_html(audience: str) -> str:
    key = "engine_gap_lab_html" if audience == "lab" else "engine_gap_core_html"
    return comparison()["notes"][key]
