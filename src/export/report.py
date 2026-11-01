# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Turn simulation results into CSV, JSON, and Markdown.

The Markdown table is the same arithmetic the web app shows. It is generated
from the engine, not typed by hand, so the documentation can be checked
against a fresh run.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from src.export.csvsafe import csv_cell
from src.model.engine import SCENARIO_ORDER, simulate_state
from src.model.provenance import LEGEND, TAGS


def simulate_many(
    fixtures: dict[str, Any],
    assumptions: Any,
    states: list[str] | None = None,
    overrides: dict[str, Any] | None = None,
    reform_weights: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    codes = states or list(fixtures["states"].keys())
    # Stable challenge order, not alphabetical.
    order = [code for code in ("PA", "CT", "WI", "UT", "OR", "HI", "AZ", "VA", "TN", "RI", "NH") if code in codes]
    return [
        simulate_state(
            fixtures,
            assumptions,
            code,
            overrides=overrides,
            reform_weights=reform_weights,
        )
        for code in order
    ]


_EXPORT_TAGS = {
    "tier": "classification",
    "completeness": "calculated",
}
COMPLETENESS_SOURCE = "docs/DATA_PROVENANCE.md"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def comparison_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        for scenario_id in SCENARIO_ORDER:
            scenario = result["scenarios"][scenario_id]
            row: dict[str, Any] = {
                "state": result["state"],
                "state_name": result["name"],
                "tier": result["tier"],
                "completeness": result["completeness"],
                "scenario": scenario_id,
                "scenario_label": scenario["label"],
                "permits_5yr": round(scenario["permits_5yr"], 1),
                "completions_5yr": round(scenario["completions_5yr"], 1),
                "incremental_permits": round(scenario["incremental_permits"], 1),
                "incremental_completions": round(scenario["incremental_completions"], 1),
                "annualized_completions": round(scenario["annualized_completions"], 1),
                "annualized_level": round(scenario["annualized_level"], 1),
                "annualized_increment": round(scenario["annualized_increment"], 1),
                "lift_pct": round(scenario["lift_pct"], 2),
                "cap_binding": scenario["cap_binding"],
                "capacity_completions": round(scenario["capacity_completions"], 1),
                "capacity_completions_basis": scenario.get("capacity_completions_basis")
                or ("level" if scenario_id == "baseline" else "increment"),
                "uncapped_potential": (
                    round(scenario["uncapped_potential"], 1) if scenario_id == "combined" else ""
                ),
                "absorption_cap": (
                    round(scenario["absorption_cap"], 1)
                    if scenario_id == "combined" and scenario.get("absorption_cap_binding")
                    else ""
                ),
                "completeness_source": COMPLETENESS_SOURCE,
                "permit_vintage": (result.get("meta") or {}).get("permit_vintage", ""),
            }
            for key, value in list(row.items()):
                if _is_number(value):
                    row[f"{key}_provenance"] = _EXPORT_TAGS.get(key, "calculated")
            # Present on every row so the CSV header matches the package columns.
            row.setdefault("uncapped_potential_provenance", "")
            row.setdefault("absorption_cap_provenance", "")
            rows.append(row)
    return rows


def to_csv(results: list[dict[str, Any]]) -> str:
    rows = comparison_rows(results)
    buffer = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["state"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: csv_cell(row.get(key, "")) for key in fieldnames})
    return buffer.getvalue()


def to_json(results: list[dict[str, Any]], scenario: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {"provenance_legend": LEGEND, "results": results}
    if scenario:
        payload["scenario"] = scenario
    return json.dumps(payload, indent=2)


def to_markdown(results: list[dict[str, Any]], note: str = "") -> str:
    """A policymaker table: baseline completions and net new completions by scenario."""
    lines = [
        "| State | Tier | Baseline completions | ADUs | Missing middle | TOD | Parking | Fees | Package |",
        "| ----- | ---- | -------------------: | ---: | -------------: | --: | ------: | ---: | ------: |",
    ]
    for result in results:
        scenarios = result["scenarios"]
        lines.append(
            "| {state} | {tier} [observed] | {base:,.0f} [calculated] | {adu:,.0f} [calculated] | {mm:,.0f} [calculated] | {tod:,.0f} [calculated] | {park:,.0f} [calculated] | {fee:,.0f} [calculated] | {pkg:,.0f} [calculated] |".format(
                state=result["state"],
                tier=result["tier"],
                base=result["baseline_completions_5yr"],
                adu=scenarios["adu"]["incremental_completions"],
                mm=scenarios["missing_middle"]["incremental_completions"],
                tod=scenarios["tod"]["incremental_completions"],
                park=scenarios["parking"]["incremental_completions"],
                fee=scenarios["fees"]["incremental_completions"],
                pkg=scenarios["combined"]["incremental_completions"],
            )
        )
    lines.append("")
    lines.append("Figures are 5-year net completions added by the reform, except the baseline column, which is total completions under current rules. The package is not the sum of the five reforms.")
    lines.append(
        "The missing-middle cap_binding flag applies to merchant completions only "
        "(teardown and conversion). The CSV keeps capacity_completions for every scenario "
        "and splits the old annualized_completions column into annualized_level "
        "(five-year completions / 5) and annualized_increment (net new / 5). "
        "For the combined package, that figure is the uncapped potential: the "
        "overlap-adjusted total before the absorption cap and the ADU stock ceiling, "
        "including parking and fees. The CSV repeats it as uncapped_potential. "
        "absorption_cap is the merchant ceiling summed over the counties where that "
        "cap binds, and it is blank when the absorption cap does not bind. "
        "Package missing middle can exceed standalone missing middle because the fee "
        "cut and market parking are in the package pro forma. "
        "capacity_completions is the five-year level on the baseline row and the "
        "incremental capacity on reform rows. "
        "Tier is a classification. Completeness is a calculated score; see "
        "docs/DATA_PROVENANCE.md."
    )
    from src.adu_fee_note import note_text

    lines.append(note_text("docs"))
    lines.append("Tags: observed = public measurement; assumed = published assumption or imputation; calculated = equation output; classification = documented grouping. Every completion figure in this table is calculated.")
    lines.append("Allowed tags: " + ", ".join(TAGS) + ".")
    if note:
        lines.append(note)
    return "\n".join(lines) + "\n"


def ranking_sentence(result: dict[str, Any]) -> str:
    """Plain-language rank of the five standalone reforms for one state."""
    order = sorted(
        ("adu", "missing_middle", "tod", "parking", "fees"),
        key=lambda scenario: result["scenarios"][scenario]["incremental_completions"],
        reverse=True,
    )
    labels = {
        "adu": "ADUs",
        "missing_middle": "missing middle",
        "tod": "transit-oriented density",
        "parking": "parking reform",
        "fees": "the fee cut",
    }
    parts = [
        f"{labels[scenario]} ({result['scenarios'][scenario]['incremental_completions']:,.0f})"
        for scenario in order
    ]
    return f"In {result['name']}, the five-year ranking is " + ", then ".join(parts) + "."
