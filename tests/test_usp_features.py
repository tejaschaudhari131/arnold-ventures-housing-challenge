# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the 6 USP / legislative decision-support features."""

from __future__ import annotations

import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from src.adu_fee_note import comparison, engine_gap_html, note_html, note_text
from src.web.server import App, make_handler

ROOT = Path(__file__).resolve().parents[1]


def _server() -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App()))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _get(base: str, path: str):
    with urlopen(base + path, timeout=30) as response:
        return response.status, response.read(), response.headers


def test_deck_route_is_live_bound_csp_safe_and_16_slides():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        for route in ("/deck", "/deck.html"):
            status, body, headers = _get(base, route)
            assert status == 200
            assert "text/html" in headers.get("Content-Type", "")
            assert "script-src 'self'" in headers.get("Content-Security-Policy", "")
            text = body.decode("utf-8")
            for idx in range(1, 17):
                assert f'data-slide="{idx}"' in text
            assert 'data-slide="17"' not in text
            # Zero inline scripts; external script only.
            assert "<script>" not in text
            assert "/deck.js" in text
            assert "/deck.css" in text
            # Live engine numbers bound dynamically.
            assert "+13,285" in text
            assert "+2,742" in text
            assert "+46,219" in text
            assert "+30,213" in text

        css_status, css_body, _ = _get(base, "/deck.css")
        js_status, js_body, _ = _get(base, "/deck.js")
        insp_status, insp_body, _ = _get(base, "/inspector.js")
        assert css_status == 200 and b".slide" in css_body
        assert js_status == 200 and b"deck-print" in js_body
        assert insp_status == 200 and b"StateframeInspector" in insp_body
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_home_and_lab_expose_inspector_presets_pins_bottleneck_and_portability():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        home_status, home_raw, _ = _get(base, "/")
        lab_status, lab_raw, _ = _get(base, "/lab")
        assert home_status == 200 and lab_status == 200
        home = home_raw.decode("utf-8")
        lab = lab_raw.decode("utf-8")

        # Click-any-number lineage inspector on both pages; pitch deck stays decoupled from product nav.
        assert "/inspector.js" in home
        assert "/inspector.js" in lab
        assert 'href="/deck"' not in home
        assert 'href="/deck"' not in lab

        # 3-mode map toggle + bottleneck legend + presets + A/B pin on both pages.
        assert 'id="core-map-metrics"' in home
        assert 'id="core-bottleneck-legend"' in home
        assert 'id="core-pin"' in home
        assert 'id="core-presets"' in home
        assert 'id="open-portability"' in home

        assert 'id="map-metrics"' in lab
        assert 'id="bottleneck-legend"' in lab
        assert 'id="pin-box"' in lab
        assert 'id="preset-box"' in lab
        assert 'id="data-roi"' in lab
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_visual_adu_waterfall_and_package_bridge_preserve_plain_text_exports():
    for code in ("PA", "NH"):
        doc = comparison(code)
        for key in ("lab_adu", "after_fee", "after_yield", "after_lags", "core_adu"):
            assert f'data-bind="display_numbers.{code}.{key}"' in doc["notes"]["core_html"]
            assert f'data-bind="display_numbers.{code}.{key}"' in doc["notes"]["lab_html"]

    core_markup = note_html("core")
    lab_markup = note_html("lab")
    assert 'class="bridge-waterfall"' in core_markup
    assert 'class="bridge-waterfall"' in lab_markup
    assert core_markup.count('class="bridge-row"') == 5
    assert lab_markup.count('class="bridge-row"') == 5

    assert 'class="gap-bars"' in engine_gap_html("core")
    assert 'class="gap-bars"' in engine_gap_html("lab")

    # Plain-text notes for docs and Markdown exports remain strictly free of HTML markup.
    plain = note_text("docs")
    assert "<" not in plain and ">" not in plain


def test_standalone_deck_builder_and_demo_script(tmp_path: Path):
    out_file = tmp_path / "stateframe-deck.html"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_deck.py"), "--out", str(out_file)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert out_file.exists()
    html = out_file.read_text(encoding="utf-8")
    assert "<style>" in html
    assert "deck-print" in html
    assert 'data-slide="16"' in html
    assert '<link rel="stylesheet" href="/deck.css">' not in html

    demo = ROOT / "docs" / "DEMO_SCRIPT.md"
    assert demo.exists()
    demo_text = demo.read_text(encoding="utf-8")
    assert "/deck" in demo_text
    assert "/lab" in demo_text


def test_ui_ux_regression_guards():
    styles_css = (ROOT / "src" / "web" / "static" / "styles.css").read_text(encoding="utf-8")
    lab_css = (ROOT / "src" / "web" / "static" / "lab.css").read_text(encoding="utf-8")
    deck_css = (ROOT / "src" / "web" / "static" / "deck.css").read_text(encoding="utf-8")
    fmt_js = (ROOT / "src" / "web" / "static" / "fmt.js").read_text(encoding="utf-8")
    app_js = (ROOT / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    lab_js = (ROOT / "src" / "web" / "static" / "lab.js").read_text(encoding="utf-8")
    index_html = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    lab_html = (ROOT / "src" / "web" / "static" / "lab.html").read_text(encoding="utf-8")
    brief_html = (ROOT / "src" / "web" / "static" / "brief.html").read_text(encoding="utf-8")

    # 1. Core 11-state county map hit targets must stay transparent (never default SVG black).
    assert "#map-stage svg .map-hit" in styles_css and "fill: transparent" in styles_css
    assert 'class="map-hit"' in app_js and 'fill="transparent"' in app_js

    # 2. Tooltip upgrader must never inject nested <button class="tip"> inside interactive buttons/links.
    assert "BUTTON|A|INPUT|SELECT|TEXTAREA" in fmt_js

    # 3. Reform cards & pill badges must stay compact with expandable drawers and nowrap tags.
    assert "align-content: start;" in lab_css
    assert "button.tip.tag" in lab_css
    assert 'class="card-drawer"' in lab_js
    assert 'class="hero-summary"' in app_js
    assert "#drivers-mount" in lab_css
    assert '.brief-sheet input[type="checkbox"]' in lab_css

    # 4. Unified suite nav across the 3 product routes + standalone pitch deck header + separated cross-model disclosures.
    from src.deck import render_deck_html

    render_deck_html.cache_clear()
    deck_html = render_deck_html()
    for doc in (index_html, lab_html, brief_html):
        assert 'class="suite-nav"' in doc
        assert 'href="/deck"' not in doc
    assert 'class="suite-bar deck-bar no-print"' in deck_html
    assert 'class="bridge-disclosure' in index_html
    assert 'class="bridge-disclosure' in lab_html
    assert 'class="hero-bridge' in lab_html

    # 5. Executive deck wraps wide tables and avoids duplicate <ol> numbering.
    assert ".deck-table-wrap" in deck_css
    assert 'class="deck-table-wrap"' in deck_html
    assert "<li><strong>1. " not in deck_html
    assert "7 counties" in deck_html


