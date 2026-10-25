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

from src.model.engine import SCENARIO_ORDER, simulate_state


def simulate_many(fixtures: dict[str, Any], assumptions: Any, states: list[str] | None = None) -> list[dict[str, Any]]:
    codes = states or list(fixtures["states"].keys())
    # Stable challenge order, not alphabetical.
    order = [code for code in ("PA", "CT", "WI", "UT", "OR", "HI", "AZ", "VA", "TN", "RI", "NH") if code in codes]
    return [simulate_state(fixtures, assumptions, code) for code in order]


def comparison_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for result in results:
        for scenario_id in SCENARIO_ORDER:
            scenario = result["scenarios"][scenario_id]
            rows.append(
                {
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
                    "lift_pct": round(scenario["lift_pct"], 2),
                    "cap_binding": scenario["cap_binding"],
                    "capacity_completions": round(scenario["capacity_completions"], 1),
                }
            )
    return rows


def to_csv(results: list[dict[str, Any]]) -> str:
    rows = comparison_rows(results)
    buffer = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["state"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def to_json(results: list[dict[str, Any]]) -> str:
    return json.dumps({"results": results}, indent=2)


def to_markdown(results: list[dict[str, Any]]) -> str:
    """A policymaker table: baseline completions and net new completions by scenario."""
    lines = [
        "| State | Tier | Baseline completions | ADUs | Missing middle | TOD | Parking | Fees | Package |",
        "| ----- | ---- | -------------------: | ---: | -------------: | --: | ------: | ---: | ------: |",
    ]
    for result in results:
        scenarios = result["scenarios"]
        lines.append(
            "| {state} | {tier} | {base:,.0f} | {adu:,.0f} | {mm:,.0f} | {tod:,.0f} | {park:,.0f} | {fee:,.0f} | {pkg:,.0f} |".format(
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
