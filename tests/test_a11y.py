# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Structural accessibility and on-screen provenance checks. No npm."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
LAB = (ROOT / "src" / "web" / "static" / "lab.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
LAB_JS = (ROOT / "src" / "web" / "static" / "lab.js").read_text(encoding="utf-8")
CSS = (ROOT / "src" / "web" / "static" / "styles.css").read_text(encoding="utf-8")
LAB_CSS = (ROOT / "src" / "web" / "static" / "lab.css").read_text(encoding="utf-8")
TOKENS = (ROOT / "src" / "web" / "static" / "tokens.css").read_text(encoding="utf-8")


def test_start_here_and_headline_sit_above_the_map():
    for page in (INDEX, LAB):
        assert page.index('id="start-here"') < page.index('id="map-stage"')
        assert page.index('id="headline"') < page.index('id="map-stage"')
        assert 'href="#county-table"' in page
        assert 'id="county-select"' in page
        assert 'role="region"' in page
        assert 'prefers-reduced-motion' not in page


def test_lab_why_drawer_and_table_headers_are_labeled():
    assert 'aria-expanded="false"' in LAB
    assert 'aria-controls="why"' in LAB
    assert 'id="why"' in LAB
    assert LAB_JS.count("aria-valuetext") >= 1
    assert 'for="' in LAB_JS
    assert 'role="group"' in LAB_JS
    assert "Escape" in LAB_JS
    assert "whyEl.focus" in LAB_JS
    assert "close-call threshold" in LAB_JS
    assert 'tag("calculated")' in LAB_JS
    for header in ("Delivery", "Eligible", "Feasible", "Envelope", "Zoning", "ACS MOE"):
        assert header in LAB
    assert LAB.index("Delivery") < LAB.index("county-body")


def test_core_tabs_and_card_buttons():
    assert 'role="tablist"' in INDEX
    assert 'role="tab"' in INDEX
    assert 'id="more-tabs"' in INDEX
    assert "For analysts" in INDEX
    assert "createElement(\"h3\")" in APP_JS
    assert "titleBtn" in APP_JS
    assert "aria-valuetext" in APP_JS
    assert 'role="group"' in APP_JS
    assert "badge-uncertain" in APP_JS
    assert "Outcome uncertain" in APP_JS
    assert "Ranking is close" in LAB_JS
    assert "completeness" in APP_JS and 'badge("calculated")' in APP_JS


def test_reduced_motion_and_print_and_slider_size():
    assert "prefers-reduced-motion" in CSS
    assert "prefers-reduced-motion" in LAB_CSS
    assert "size: letter" in CSS
    assert "24px" in CSS
    assert ":focus-visible" in CSS
    assert re.search(r"min-height:\s*360px", CSS)
    assert "--sun: #f2b632" in TOKENS
    assert "role=\"dialog\"" in LAB
    assert "aria-live=\"polite\"" in LAB
    assert 'id="state-list"' not in LAB
    assert "onViewTabKey" in LAB_JS
    assert 'class="tog" aria-pressed' in LAB_JS
    assert 'role="listitem" aria-pressed' not in LAB_JS


def test_lab_js_tags_envelope_as_calculated():
    assert "Envelope" in LAB_JS
    assert LAB_JS.count('tag("calculated")') >= 4
    assert 'tag("assumed")' in LAB_JS
    assert "rationale" in LAB_JS
    assert "Package is not a sum" in LAB_JS
    assert "Also modeled, not a Handbook benchmark" in LAB
