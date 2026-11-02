# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Section 9A display binding: range first, funnel, drivers, brief, no hard-coded results."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "web" / "static"


def test_frame_dom_bindings_match_results_json():
    proc = subprocess.run(
        ["node", "tests/js/frame_ux.mjs"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "frame ux ok" in proc.stdout


def test_parking_anchors_come_from_the_catalog():
    from src.web.server import App

    catalog = App().lab_assumptions()
    anchors = catalog["anchors"]
    assert set(anchors) == {"parking_min_urban", "parking_min_suburban", "parking_min_rural"}
    assert "parking_market_urban" in catalog["by_name"]
    assert catalog["by_name"]["parking_market_urban"]["low"] < catalog["by_name"]["parking_market_urban"]["central"]
    assert set(catalog["display_numbers"]) == {"PA", "NH"}
    assert "lab_adu" in catalog["display_numbers"]["PA"]
    assert anchors["parking_min_urban"]["central"] == anchors["parking_min_urban"]["low"]
    ratios = catalog["completion_ratios"]
    assert "completion_ratio_adu" in ratios
    assert "completion_ratio_small" in ratios


def _brief_copy() -> str:
    html = (STATIC / "brief.html").read_text(encoding="utf-8")
    html = re.sub(r"<script[\s\S]*?</script>", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    js = (STATIC / "brief.js").read_text(encoding="utf-8")
    sentences = [
        item for item in re.findall(r'"([^"]*)"', js)
        if " " in item and "<" not in item and "+" not in item and len(item) > 24
    ]
    frame = (STATIC / "frame.js").read_text(encoding="utf-8")
    # Limits and answer sentences the brief renders. Skip paths and code.
    limits = [
        item for item in re.findall(r'"([^"]*)"', frame)
        if item.endswith(".") and " " in item and "data-bind" not in item and "<" not in item
    ]
    return html + "\n" + "\n".join(sentences) + "\n" + "\n".join(limits)


def test_brief_copy_stays_plain():
    text = _brief_copy()
    jargon = re.compile(
        r"\b(hazard|envelope|elasticity|p10|p90|pro forma|sigma|marginal|pipeline|capacity)\b",
        re.I,
    )
    assert jargon.search(text) is None, jargon.findall(text)
    grade = _flesch(text)
    assert grade <= 8, grade


def _flesch(text: str) -> float:
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) < 20:
        return 0.0
    sentences = re.findall(r"[.!?]", text) or ["."]
    syllables = sum(_syllables(word) for word in words)
    return 0.39 * (len(words) / len(sentences)) + 11.8 * (syllables / len(words)) - 15.59


def _syllables(word: str) -> int:
    groups = re.findall(r"[aeiouy]+", word.lower())
    count = len(groups)
    if word.lower().endswith("e") and count > 1:
        count -= 1
    return max(count, 1)
