# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Both pages, both briefs, and the write-ups explain the ADU fee gap."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from src.adu_fee_note import comparison, note_html, note_text
from src.lab.config import central_params
from src.lab.explain import brief_markdown
from src.lab.results import load_results
from src.model.assumptions import load_assumptions
from src.web.server import App, make_handler

ROOT = Path(__file__).resolve().parents[1]


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App()))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _get(base, path):
    with urlopen(base + path, timeout=30) as response:
        return response.status, response.read(), response.headers


def test_comparison_reads_both_engines_and_both_fees():
    doc = comparison("PA")
    lab = load_results("PA", allow_compute=False)
    catalog = load_assumptions()
    assert doc["lab_adu"] == int(round(lab["statewide"]["results"]["adu"]["central"]))
    assert doc["lab_fee"] == int(round(central_params()["fee_per_unit"]))
    assert doc["core_fee"] == int(round(catalog.spec("adu_fee_per_unit")["central"]))
    assert doc["core_adu"] > doc["lab_adu"]
    assert doc["after_fee"] > doc["lab_adu"]
    assert doc["after_yield"] > doc["after_fee"]
    assert doc["lab_baseline"] == 111016
    assert doc["core_baseline"] == 108950
    assert "2023-2025" in doc["baseline_note"]
    assert doc["provenance"]["lab_adu"]["tag"] == "calculated"
    assert doc["provenance"]["lab_fee"]["tag"] == "assumed"
    assert "config/lab/assumptions.yaml" in doc["provenance"]["lab_fee"]["source"]
    note = note_text("docs")
    assert f"{doc['lab_fee']:,.0f}" in note
    assert f"{doc['core_fee']:,.0f}" in note
    assert "+6,048" in note
    assert "+46,261" in note
    assert "/lab" in note
    assert "111,016" in note


def test_both_pages_render_adu_fee_note():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        home_status, home, _ = _get(base, "/")
        lab_status, lab, _ = _get(base, "/lab")
        home_text = home.decode("utf-8")
        lab_text = lab.decode("utf-8")
        assert home_status == 200 and lab_status == 200
        assert 'id="adu-fee-note"' in home_text
        assert 'id="adu-fee-note"' in lab_text
        assert note_html("core") in home_text
        assert note_html("lab") in lab_text
        assert 'href="/lab"' in home_text
        assert 'href="/"' in lab_text

        app_status, app_js, _ = _get(base, "/app.js")
        lab_js_status, lab_js, _ = _get(base, "/lab.js")
        assert app_status == 200 and lab_js_status == 200
        assert b"adu-fee-note" in app_js and b"/api/adu-compare" in app_js
        assert b"adu-fee-note" in lab_js and b"/api/adu-compare" in lab_js

        api_status, api_body, _ = _get(base, "/api/adu-compare?state=PA")
        payload = json.loads(api_body.decode("utf-8"))
        assert api_status == 200
        assert payload["notes"]["core"] == note_text("core")
        assert payload["notes"]["lab"] == note_text("lab")
        assert payload["notes"]["docs"] == note_text("docs")

        export_status, export_body, _ = _get(base, "/api/export?state=PA&format=md")
        assert export_status == 200
        assert note_text("docs") in export_body.decode("utf-8")

        brief_status, brief_body, _ = _get(base, "/api/lab/export?state=PA&format=md")
        assert brief_status == 200
        assert note_text("docs") in brief_body.decode("utf-8")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_writeups_and_lab_brief_carry_the_same_note():
    note = note_text("docs")
    policy = (ROOT / "docs" / "POLICY_SCENARIO_COMPARISON.md").read_text(encoding="utf-8")
    method = (ROOT / "docs" / "SMALL_HOMES_LAB.md").read_text(encoding="utf-8")
    case = (ROOT / "docs" / "CASE_STUDY_PA_ALLEGHENY.md").read_text(encoding="utf-8")
    assert note in policy
    assert note in method
    assert note in case
    assert note in brief_markdown("PA")
