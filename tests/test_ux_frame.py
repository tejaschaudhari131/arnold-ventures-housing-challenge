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


def test_derived_figures_and_tier1_shares_bind_at_display_precision():
    from src.lab.explain import assumption_catalog, locked_results

    doc = locked_results("PA")
    base = doc["statewide"]["results"]["baseline"]["central"]
    middle = doc["statewide"]["results"]["missing_middle"]["central"]
    lift = doc["derived"]["lift"]["missing_middle"]
    assert abs(lift - (middle / base)) < 1e-12
    assert f"{lift * 100:.1f}%" == "5.1%"
    ends = doc["statewide"]["one_at_a_time"]["hazard_homeowner_feasible"]
    swing = abs(ends["high"]["missing_middle"] - ends["low"]["missing_middle"])
    shown = doc["derived"]["swing"]["hazard_homeowner_feasible"]["missing_middle"]
    assert abs(shown - swing) < 1e-9
    assert f"{round(shown):,}" == "9,721"

    from src.bundle import load_bundle
    from src.model.crossval import _error
    from src.model.engine import simulate_state

    tier = assumption_catalog()["crossval_tier1"]
    assert set(tier) == {"CT", "WI", "UT", "HI"}
    fixtures, assumptions = load_bundle()
    for code in ("CT", "WI", "UT", "HI"):
        full = simulate_state(fixtures, assumptions, code, parcel_mode="observed", resolution="county")
        imputed = simulate_state(fixtures, assumptions, code, parcel_mode="imputed", resolution="county")
        percent = _error(
            float(full["scenarios"]["adu"]["incremental_completions"]),
            float(imputed["scenarios"]["adu"]["incremental_completions"]),
        )["percent_error"]
        share = tier[code]["percent_error"]
        assert percent is not None and share is not None
        assert abs(share - (percent / 100.0)) < 1e-12
        assert f"{share * 100:+.1f}%" == f"{percent:+.1f}%"
        assert tier[code]["scenario"] == "adu"


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


def test_pc17_completion_literals_are_not_in_python_copy():
    import ast

    # These files are hashed into the locked Lab results fingerprint.
    frozen = {ROOT / "src" / "lab" / name for name in (
        "config.py", "data.py", "engine.py", "options.py", "uncertainty.py", "results.py"
    )}
    banned = ("0.84", "0.90", "0.92", "0.93")
    for path in (ROOT / "src").rglob("*.py"):
        if path.resolve() in {item.resolve() for item in frozen}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for token in banned:
                    assert token not in node.value, (path.name, token)


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
