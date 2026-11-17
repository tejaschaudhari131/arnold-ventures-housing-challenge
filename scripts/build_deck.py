#!/usr/bin/env python3
# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Write a standalone print-ready executive slide deck to output/stateframe-deck.html."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.deck import render_deck_html  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build standalone Stateframe executive slide deck.")
    parser.add_argument("--out", default=str(ROOT / "output" / "stateframe-deck.html"), help="Output HTML file path")
    args = parser.parse_args(argv)

    static_dir = ROOT / "src" / "web" / "static"
    tokens = (static_dir / "tokens.css").read_text(encoding="utf-8")
    styles = (static_dir / "styles.css").read_text(encoding="utf-8")
    deck_css = (static_dir / "deck.css").read_text(encoding="utf-8")
    deck_js = (static_dir / "deck.js").read_text(encoding="utf-8")

    html = render_deck_html()
    inline_css = f"<style>\n{tokens}\n{styles}\n{deck_css}\n</style>"
    html = (
        html.replace('<link rel="stylesheet" href="/tokens.css">', "")
        .replace('<link rel="stylesheet" href="/styles.css">', "")
        .replace('<link rel="stylesheet" href="/deck.css">', inline_css)
        .replace('<script src="/deck.js"></script>', f"<script>\n{deck_js}\n</script>")
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote standalone 16-slide deck to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
