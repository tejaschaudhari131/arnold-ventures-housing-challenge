# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Command line: ``python -m src.lab.run --state PA [--county Allegheny] [--json out.json]``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.lab.config import LAB_STATES, load_scenarios
from src.lab.data import load_state
from src.lab.engine import evaluate_state


def format_table(result: dict, county: str | None = None) -> str:
    scenarios = load_scenarios()["scenarios"]
    if county:
        rows = [c for c in result["counties"] if c["fips"] == county or c["name"].lower().startswith(county.lower())]
        if not rows:
            raise SystemExit(f"No county matches {county}")
        source = rows[0]["scenarios"]
        title = f"{rows[0]['name']}, {result['state']}"
    else:
        source = result["statewide"]
        title = f"{result['state']} statewide"
    lines = [title, f"{'Scenario':44s} {'Delivered 5y':>13s} {'vs Baseline':>12s} {'Eligible':>12s} {'Feasible':>10s}"]
    for sid, row in source.items():
        lines.append(
            f"{scenarios[sid]['label']:44s} {row['delivery']:>13,.0f} {row['delta']:>+12,.0f} "
            f"{row.get('eligible', 0):>12,.0f} {row.get('feasible', 0):>10,.0f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Small Homes Policy Lab.")
    parser.add_argument("--state", default="PA", choices=sorted(LAB_STATES))
    parser.add_argument("--county", default="", help="County name or FIPS")
    parser.add_argument("--json", default="", help="Write the full result to this path")
    parser.add_argument("--cache", action="store_true", help="Use data/cache/lab instead of the committed sample")
    args = parser.parse_args(argv)
    state = load_state(args.state, prefer_cache=args.cache)
    result = evaluate_state(state)
    print(format_table(result, args.county or None))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1, default=float) + "\n", encoding="utf-8")
        print(f"Wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
