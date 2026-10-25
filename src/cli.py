# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Command line for Stateframe.

    python -m src.cli serve
    python -m src.cli run --out output
    python -m src.cli report --out output
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from src.bundle import load_bundle
from src.export.report import simulate_many, to_csv, to_json, to_markdown


def _write_exports(out_dir: Path, states: list[str] | None) -> None:
    fixtures, assumptions = load_bundle()
    if states:
        unknown = [code for code in states if code not in fixtures["states"]]
        if unknown:
            raise SystemExit(f"Unknown state code: {', '.join(unknown)}")
    results = simulate_many(fixtures, assumptions, states)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.csv").write_text(to_csv(results), encoding="utf-8")
    (out_dir / "comparison.json").write_text(to_json(results), encoding="utf-8")
    (out_dir / "comparison.md").write_text(to_markdown(results), encoding="utf-8")
    print(f"Wrote {out_dir / 'comparison.csv'}")
    print(f"Wrote {out_dir / 'comparison.json'}")
    print(f"Wrote {out_dir / 'comparison.md'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stateframe housing policy simulator")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start the local web simulator")
    serve.add_argument("--host", default=os.environ.get("STATEFRAME_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("STATEFRAME_PORT", "8080")))

    run = sub.add_parser("run", help="Write CSV, JSON, and Markdown comparisons")
    run.add_argument("--state", default="all", help="State code or 'all'")
    run.add_argument("--out", default="output")

    report = sub.add_parser("report", help="Alias for run")
    report.add_argument("--state", default="all")
    report.add_argument("--out", default="output")

    args = parser.parse_args(argv)
    command = args.command or "serve"
    if command == "serve":
        from src.web.server import serve as serve_app

        host = getattr(args, "host", os.environ.get("STATEFRAME_HOST", "127.0.0.1"))
        port = getattr(args, "port", int(os.environ.get("STATEFRAME_PORT", "8080")))
        serve_app(host, port)
        return 0
    state = args.state
    states = None if state == "all" else [code.strip().upper() for code in state.split(",") if code.strip()]
    _write_exports(Path(args.out), states)
    return 0


if __name__ == "__main__":
    sys.exit(main())
