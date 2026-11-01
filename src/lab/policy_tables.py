# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Markdown tables for the policy write-up, from the same locked results
the live Lab brief uses. Not part of the Lab fingerprint.
"""

from __future__ import annotations

from src.lab.results import load_results
from src.lab.uncertainty import compared_scenarios
from src.plain import homes


LABELS = {
    "baseline": "Baseline (level)",
    "adu": "ADUs",
    "missing_middle": "Missing middle (2–6)",
    "parking": "Parking",
    "fees": "Fees",
    "package": "Package (extra)",
    "approval": "Approval (extra)",
}
ORDER = ["baseline", *compared_scenarios()]


def _range_row(label: str, cell: dict, level: bool = False) -> str:
    central = homes(cell["central"]) if level else homes(cell["central"], signed=True)
    return (
        f"| {label} | {central} | {homes(cell['p10'])}–{homes(cell['p90'])} | "
        f"{homes(cell['zoning_low'])}–{homes(cell['zoning_high'])} | "
        f"±{homes(cell['acs_moe'])} |"
    )


def pa_statewide_table(doc: dict | None = None) -> str:
    sw = (doc or load_results("PA", allow_compute=False))["statewide"]["results"]
    lines = [
        "| Scenario | Central | Likely range | Zoning bound | Census survey error |",
        "| -------- | ------: | -----------: | -----------: | ------------------: |",
    ]
    for sid in ORDER:
        lines.append(_range_row(LABELS[sid], sw[sid], level=sid == "baseline"))
    return "\n".join(lines)


def allegheny_table(doc: dict | None = None) -> str:
    county = next(
        row
        for row in (doc or load_results("PA", allow_compute=False))["counties"]
        if row["fips"] == "42003"
    )
    short = {
        "baseline": "Baseline (level)",
        "adu": "ADUs",
        "missing_middle": "Missing middle",
        "parking": "Parking",
        "fees": "Fees",
        "package": "Package",
        "approval": "Approval",
    }
    lines = [
        "| Scenario | Allegheny increment | Likely range | Zoning | Census survey error |",
        "| -------- | ------------------: | -----------: | -----: | ------------------: |",
    ]
    for sid in ORDER:
        lines.append(_range_row(short[sid], county["results"][sid], level=sid == "baseline"))
    return "\n".join(lines)


def sampling_error_sentence(code: str = "PA", doc: dict | None = None) -> str:
    locked = doc or load_results(code, allow_compute=False)
    sw = locked["statewide"]["results"]
    bits = []
    for sid in ORDER:
        se = sw[sid].get("p50_se", 0.0)
        bits.append(f"{LABELS[sid]} ±{homes(se)}")
    return (
        f"Envelope sampling error (bootstrap SE of the statewide P50, "
        f"{locked['draws']:,} draws, seed {locked['seed']}): " + "; ".join(bits) + "."
    )


def nh_table(doc: dict | None = None) -> str:
    sw = (doc or load_results("NH", allow_compute=False))["statewide"]["results"]
    short = {
        "baseline": "Baseline (level)",
        "adu": "ADUs",
        "missing_middle": "Missing middle",
        "parking": "Parking",
        "fees": "Fees",
        "package": "Package",
        "approval": "Approval",
    }
    lines = [
        "| Scenario | NH increment | Likely range | Zoning | Census survey error |",
        "| -------- | -----------: | -----------: | -----: | ------------------: |",
    ]
    for sid in ORDER:
        lines.append(_range_row(short[sid], sw[sid], level=sid == "baseline"))
    return "\n".join(lines)
