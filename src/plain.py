# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Plain-language labels and number formats for briefs, notes, and docs.

Rounding matches the live Lab brief (Python ``:,.0f`` / ``round``). Nothing
here changes an engine result.
"""

from __future__ import annotations

from typing import Any

LAB_URL = "https://stateframe-housing.vercel.app/lab"
CORE_URL = "https://stateframe-housing.vercel.app/"

SCENARIO_PLAIN = {
    "baseline": "Baseline",
    "adu": "ADUs",
    "missing_middle": "missing middle (2–6 homes)",
    "parking": "parking reform",
    "fees": "a 50% fee cut",
    "package": "the combined package",
    "approval": "by-right approval with a shot clock",
    "tod": "homes near transit",
    "combined": "the combined package",
}

SCENARIO_SHORT = {
    "baseline": "Baseline",
    "adu": "ADUs",
    "missing_middle": "Missing middle",
    "parking": "Parking",
    "fees": "Fees",
    "package": "Package",
    "approval": "Approval",
    "tod": "Homes near transit",
    "combined": "Package",
}


def homes(value: float, signed: bool = False) -> str:
    number = int(round(float(value)))
    return f"{number:+,}" if signed else f"{number:,}"


def money(value: float) -> str:
    return f"${round(float(value)):,}"


def pct(value: float, digits: int = 2) -> str:
    """Format a share (0.003129 → 0.31%)."""
    return f"{float(value) * 100:.{digits}f}%"


def rate(value: float, digits: int = 1) -> str:
    """Format a rate or cap (0.07122 → 7.1%)."""
    return f"{float(value) * 100:.{digits}f}%"


def snap(value: Any) -> Any:
    if isinstance(value, float) and abs(value) < 1e-9:
        return 0.0
    return value


def snap_tree(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: snap_tree(value) for key, value in node.items()}
    if isinstance(node, list):
        return [snap_tree(item) for item in node]
    return snap(node)


def format_assumption(unit: str, value: float) -> str:
    """Human format for a published assumption, never scientific notation."""
    text = (unit or "").lower()
    number = float(value)
    if abs(number) < 1e-9:
        number = 0.0
    if any(token in text for token in ("$", "usd", "per home", "per sq")):
        return money(number)
    if "per year" in text:
        return f"{pct(number)} a year"
    if text in {"share", "ratio", "rate", "probability"} or "share" in text:
        return rate(number)
    if abs(number) >= 1000:
        return f"{round(number):,}"
    if abs(number) >= 1:
        return f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{number:.4f}".rstrip("0").rstrip(".")


MEDIAN_SHORT = {
    "adu": "ADU",
    "missing_middle": "MM",
    "fees": "Fees",
    "parking": "Parking",
}


def is_draw_tie(pair: dict[str, Any] | None) -> bool:
    """True when the trailer wins a majority of envelope draws."""
    if not pair:
        return False
    return bool(pair.get("close_call")) and float(pair.get("flip_share") or 0.0) >= 0.5


def ranking_phrase(ids: list[str], pair: dict[str, Any] | None = None) -> str:
    labels = [SCENARIO_SHORT.get(sid, sid) for sid in ids]
    if is_draw_tie(pair) and len(labels) >= 2:
        tied = f"Statistical tie ({labels[0]} and {labels[1]})"
        rest = labels[2:]
        return " > ".join([tied, *rest]) if rest else tied
    return " > ".join(labels)


def top_pair_tie_clause(pair: dict[str, Any], results: dict[str, Any]) -> str:
    """Tie line from the locked results: medians and flip share, never hard-coded."""
    leader, trailer = pair["leader"], pair["trailer"]
    return (
        f"Central estimate favors {SCENARIO_SHORT.get(leader, leader)}; "
        f"{SCENARIO_SHORT.get(trailer, trailer)} ahead in {float(pair['flip_share']):.0%} of draws "
        f"(draw medians {MEDIAN_SHORT.get(trailer, trailer)} {homes(results[trailer]['p50'])} vs "
        f"{MEDIAN_SHORT.get(leader, leader)} {homes(results[leader]['p50'])})"
    )


def tag_block(value: float | int, tag: str, source: str) -> dict[str, Any]:
    return {"value": value, "tag": tag, "source": source}
