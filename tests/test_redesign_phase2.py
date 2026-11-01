# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Phase 2 Lab redesign: live numbers, honesty rule, tokens, tour, geo."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = (ROOT / "src" / "web" / "static" / "lab.html").read_text(encoding="utf-8")
LAB_JS = (ROOT / "src" / "web" / "static" / "lab.js").read_text(encoding="utf-8")
LAB_CSS = (ROOT / "src" / "web" / "static" / "lab.css").read_text(encoding="utf-8")
TOKENS = (ROOT / "src" / "web" / "static" / "tokens.css").read_text(encoding="utf-8")
INDEX = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
DISCLOSURES = (ROOT / "docs" / "DISCLOSURES.md").read_text(encoding="utf-8")
PROVENANCE = (ROOT / "docs" / "DATA_PROVENANCE.md").read_text(encoding="utf-8")
STALE = ("27387", "26,956", "26956", "111,016", "111016", "108,950", "108950")


def _results(code: str) -> dict:
    return json.loads((ROOT / "data" / "sample" / "lab" / f"results_{code}.json").read_text(encoding="utf-8"))


def package_total(results: dict, ids: list[str]) -> tuple[float, bool]:
    sw = results["statewide"]["results"]
    if not ids:
        return 0.0, True
    if len(ids) == 1:
        return float(sw[ids[0]]["central"]), True
    if len(ids) == 4:
        return float(sw["package"]["central"]), True
    return sum(float(sw[k]["central"]) for k in ids), False


def test_tokens_and_try_pennsylvania_entry():
    for color in ("#1d3557", "#0e6e5c", "#f2b632", "#c8553d", "#fbf6ec", "#4f5862"):
        assert color in TOKENS
    assert 'href="/tokens.css"' in INDEX
    assert 'href="/tokens.css"' in LAB
    assert "Try Pennsylvania 2027–31" in INDEX
    assert "Try Pennsylvania 2027–31" in LAB
    assert 'id="try-pa"' in LAB


def test_lab_phase2_landmarks_and_tour():
    assert 'id="start-here"' in LAB and LAB.index('id="start-here"') < LAB.index('id="map-stage"')
    assert LAB.index('id="headline"') < LAB.index('id="map-stage"')
    assert 'id="tour"' in LAB
    assert 'role="dialog"' in LAB
    assert "Skip tour" in LAB
    assert "This is the answer" in LAB_JS
    assert "Flip a reform" in LAB_JS
    assert "Don't add the bills up" in LAB_JS
    assert "Take it with you" in LAB_JS
    assert "sf-lab-tour-v2" in LAB_JS
    assert 'role="tablist"' in LAB
    assert 'id="chips"' in LAB
    assert "Key points for a legislator" in LAB
    assert "Checked against other data" in LAB
    assert "not labeled validated" in LAB
    assert "Copy link to this view" in LAB
    assert "Download PNG" in LAB
    assert "One-page PDF" in LAB
    assert 'id="recon"' in LAB
    assert "reconciliation_note" in LAB_JS


def test_package_honesty_uses_live_results():
    assert "simple sum, not modeled; overlap can move it down or up" in LAB_JS
    assert "Simple sum shown, not modeled" in LAB_JS
    for stale in STALE:
        assert stale not in LAB_JS
        assert stale not in LAB
    pa = _results("PA")
    nh = _results("NH")
    for doc in (pa, nh):
        single, exact = package_total(doc, ["missing_middle"])
        assert exact and single == doc["statewide"]["results"]["missing_middle"]["central"]
        pack, exact_pack = package_total(doc, ["adu", "missing_middle", "parking", "fees"])
        assert exact_pack and pack == doc["statewide"]["results"]["package"]["central"]
        mix, exact_mix = package_total(doc, ["adu", "fees"])
        assert not exact_mix
        assert mix == (
            doc["statewide"]["results"]["adu"]["central"]
            + doc["statewide"]["results"]["fees"]["central"]
        )
        decomp = doc["statewide"]["package_decomposition"]
        assert decomp["package"] != decomp["sum_of_separate"]


def test_census_boundary_files_and_keyboard_map():
    pa = json.loads((ROOT / "data" / "sample" / "lab" / "PA_counties.geo.json").read_text(encoding="utf-8"))
    nh = json.loads((ROOT / "data" / "sample" / "lab" / "NH_counties.geo.json").read_text(encoding="utf-8"))
    assert len(pa["counties"]) == 67
    assert len(nh["counties"]) == 10
    assert any(c["fips"] == "42003" and c.get("rings") for c in pa["counties"])
    assert "cb_2024" in PROVENANCE or "cartographic boundary" in PROVENANCE.lower()
    assert "cb_2024_us_county_5m" in LAB
    assert "ArrowRight" in LAB_JS
    assert "neighborFips" in LAB_JS
    assert "Home" in LAB_JS and "End" in LAB_JS
    assert 'role="group"' in LAB_JS


def test_shareable_url_and_exports_and_reduced_motion():
    assert 'q.get("st")' in LAB_JS or 'q.get("on")' in LAB_JS
    assert 'q.get("map")' in LAB_JS
    assert "history.replaceState" in LAB_JS
    assert "exportPng" in LAB_JS
    assert "exportCsv" in LAB_JS
    assert "window.print" in LAB_JS
    assert "prefers-reduced-motion" in LAB_CSS
    assert "prefers-reduced-motion" not in LAB
    assert re.search(r"outline:\s*3px solid var\(--navy\)", (ROOT / "src" / "web" / "static" / "styles.css").read_text())


def test_answer_matches_selection_and_plain_tie_badge():
    assert 'Your package: about " + integer(t.c)' in LAB_JS
    assert "All four reforms together add" not in LAB_JS
    assert "comes out ahead in" in LAB_JS
    assert "typical result " in LAB_JS
    assert "Statistical tie" in LAB_JS
    assert "placeLabel" in LAB_JS
    assert 'id="state-notice"' in LAB
    assert "Unknown state " in LAB_JS
    assert "showing PA." in LAB_JS
    assert "draw medians" not in LAB_JS.split("rankingBadge")[1] if "rankingBadge" in LAB_JS else True
    assert 'extra homes (likely "' in LAB_JS
    assert "<nav" in INDEX and 'role="tablist"' in INDEX
    assert re.search(r"<nav[^>]*role=", INDEX) is None
    assert re.search(r"#methods a\s*\{[^}]*min-height:\s*24px", LAB_CSS)
    assert "In \" + name + \":" in LAB_JS or "In \" + name + \" County" in LAB_JS
    assert "countyPhrase" in LAB_JS
    assert "mapId" in LAB_JS
    assert "onViewTabKey" in LAB_JS
    assert "locked.state !== stateCode" in LAB_JS
    assert "animToken" in LAB_JS
    assert 'id="hero"' in LAB
    assert 'id="mini-total"' in LAB
    assert 'id="state-list"' not in LAB
    assert 'role="listitem" aria-pressed' not in LAB_JS
    assert "<h3>" not in LAB_JS or 'class="card" role="listitem" aria-pressed' not in LAB_JS
    assert 'class="card" role="listitem">' in LAB_JS
    assert 'class="tog" aria-pressed' in LAB_JS
    assert 'id="adu-fee-note"' in LAB and "<div id=\"adu-fee-note\"" in LAB
    assert "querySelector(\"details\")" in LAB_JS


def test_reflow_and_hero_contrast_and_skip_height():
    assert re.search(r"\.where-map[\s\S]*min-width:\s*0", LAB_CSS)
    assert re.search(r"\.panel-head[\s\S]*min-width:\s*0", LAB_CSS)
    assert re.search(r"\.view-tabs[\s\S]*min-width:\s*0", LAB_CSS)
    assert re.search(r"#chips[\s\S]*min-width:\s*0", LAB_CSS)
    assert re.search(r"\.view-tabs\s*\{[^}]*flex-wrap:\s*wrap", LAB_CSS)
    assert "background: transparent" in LAB_CSS
    assert ".hero .headline-answer" in LAB_CSS
    assert "#f4fbf8" in LAB_CSS
    css = (ROOT / "src" / "web" / "static" / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.skip[^{]*\{[^}]*min-height:\s*24px", css)
    assert re.search(r"\.skip-map\s*\{[^}]*min-height:\s*24px", css)


def test_playhouse_license_and_boundary_disclosures():
    assert "license: null" in DISCLOSURES
    assert "No PlayHouse source file" in DISCLOSURES
    assert "cartographic boundary" in DISCLOSURES.lower()
    assert "counties.geo.json" in DISCLOSURES
    assert "StudioTour" in DISCLOSURES
    ui = (ROOT / "config" / "lab" / "ui.yaml").read_text(encoding="utf-8")
    assert "reconciliation_note" in ui
    assert not re.search(r"27,?387|26,?956|111,?016", ui)
