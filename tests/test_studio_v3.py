# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for Stateframe v3: The Legislative Studio & 11-State Census GeoJSON."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from src.bundle import load_bundle
from src.model.engine import REFORM_IDS
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


def test_eleven_state_geo_endpoint_matches_fixtures_county_for_county():
    fixtures, _ = load_bundle()
    expected_by_state = {
        code: {c["fips"] for c in state_doc["counties"]}
        for code, state_doc in fixtures["states"].items()
    }
    assert sum(len(v) for v in expected_by_state.values()) == 476

    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, body, headers = _get(base, "/api/geo")
        assert status == 200
        assert "max-age=" in (headers.get("Cache-Control") or "")
        all_geo = json.loads(body.decode("utf-8"))
        assert all_geo["count"] == 476
        assert set(all_geo["states"]) == set(expected_by_state)
        assert "cb_2024_us_county_5m" in all_geo["source"]

        for code, expected_fips in expected_by_state.items():
            st_status, st_body, _ = _get(base, f"/api/geo?state={code}")
            assert st_status == 200
            st_geo = json.loads(st_body.decode("utf-8"))
            assert st_geo["state"] == code
            assert st_geo["count"] == len(expected_fips)
            got_fips = {c["fips"] for c in st_geo["counties"]}
            assert got_fips == expected_fips, f"FIPS mismatch for {code}"
            for county in st_geo["counties"]:
                assert county.get("rings") and len(county["rings"][0]) >= 4

        # Verify Connecticut 2024 Planning Regions (09110-09190) are present.
        ct_geo = App().geo_11states("CT")
        assert {c["fips"] for c in ct_geo["counties"]} == {
            "09110",
            "09120",
            "09130",
            "09140",
            "09150",
            "09160",
            "09170",
            "09180",
            "09190",
        }

        # Existing /api/map endpoint stays intact alongside /api/geo.
        map_status, map_body, _ = _get(base, "/api/map")
        assert map_status == 200
        assert len(json.loads(map_body.decode("utf-8")).get("points", [])) == 476

        # Unknown state code returns HTTP 400.
        try:
            urlopen(base + "/api/geo?state=ZZ", timeout=15)
            assert False, "expected HTTP 400 for invalid state ZZ"
        except HTTPError as exc:
            assert exc.code == 400
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_legislative_studio_v3_chrome_depth_modes_and_drawers():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _, home_raw, _ = _get(base, "/")
        _, lab_raw, _ = _get(base, "/lab")
        _, deck_raw, _ = _get(base, "/deck")
        home = home_raw.decode("utf-8")
        lab = lab_raw.decode("utf-8")
        deck = deck_raw.decode("utf-8")

        # Shared Legislative Studio branding & 3 Audience Depth pills on / and /lab.
        assert "Legislative Studio" in home
        assert "Legislative Studio" in lab
        assert "Legislative Studio" in deck
        for page in (home, lab):
            assert 'data-depth="briefing"' in page
            assert 'data-depth-btn="briefing"' in page
            assert 'data-depth-btn="markup"' in page
            assert 'data-depth-btn="audit"' in page
            assert 'class="lens-isolation-pill"' in page

        # 11-State Screening Studio controls & slide-over drawers.
        assert 'id="studio-state-select"' in home
        assert 'id="toggle-states-drawer"' in home
        assert 'id="toggle-assumptions-drawer"' in home
        assert 'id="states-drawer"' in home
        assert 'id="assumptions-drawer"' in home
        assert 'id="override-badge"' in home
        assert 'class="studio-split ' in home or 'class="studio-split"' in home

        # County Policy Lab Studio controls, docked audit, and slide-over drawer.
        assert 'id="toggle-lab-adjust"' in lab
        assert 'id="lab-override-badge"' in lab
        assert 'id="lab-markup-ribbon"' in lab
        assert 'class="hero lab-studio-split"' in lab
        assert 'class="lab-docked-audit"' in lab

        # True polygon county choropleth wired into app.js.
        app_js = (ROOT / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        assert '"/api/geo"' in app_js
        assert "county-poly" in app_js
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_upgrades_step_hierarchy_real_legislation_and_impact_note():
    fixtures, _ = load_bundle()
    valid_states = set(fixtures["states"])
    valid_reforms = set(REFORM_IDS)
    valid_lab_reforms = {"adu", "missing_middle", "parking", "fees"}

    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        # 1. Real enacted & proposed legislation endpoint (/api/legislation)
        status, body, headers = _get(base, "/api/legislation")
        assert status == 200
        assert "max-age=" in (headers.get("Cache-Control") or "")
        all_leg = json.loads(body.decode("utf-8"))
        assert all_leg["count"] == 10
        assert len(all_leg["bills"]) == 10
        for bill in all_leg["bills"]:
            assert bill["state"] in valid_states
            assert any(k in bill["status"] for k in ("Enacted", "Proposed"))
            assert bill["bill_number"] and bill["citation"]
            assert set(bill["reforms"]).issubset(valid_reforms)
            assert set(bill["lab_reforms"]).issubset(valid_lab_reforms)
            assert len(bill["clauses"]) >= 2

        pa_status, pa_body, _ = _get(base, "/api/legislation?state=PA")
        assert pa_status == 200
        pa_leg = json.loads(pa_body.decode("utf-8"))
        assert pa_leg["count"] == 2
        assert {b["id"] for b in pa_leg["bills"]} == {"PA_STARTER_PACKAGE", "PA_HB1976_ADU_MM"}

        or_status, or_body, _ = _get(base, "/api/legislation?state=OR")
        assert or_status == 200
        or_leg = json.loads(or_body.decode("utf-8"))
        assert or_leg["count"] == 1
        assert "HB 2001" in or_leg["bills"][0]["bill_number"]

        try:
            urlopen(base + "/api/legislation?state=ZZ", timeout=15)
            assert False, "expected HTTP 400 for invalid state ZZ"
        except HTTPError as exc:
            assert exc.code == 400

        # 2. Explicit Step 1 -> Step 2 -> Step 3 workflow hierarchy & real bill selectors
        _, home_raw, _ = _get(base, "/")
        _, lab_raw, _ = _get(base, "/lab")
        _, brief_raw, _ = _get(base, "/brief")
        home = home_raw.decode("utf-8")
        lab = lab_raw.decode("utf-8")
        brief = brief_raw.decode("utf-8")

        for page in (home, lab):
            assert "1 · Macro Screener" in page
            assert "2 · Lot-by-Lot Lab" in page
            assert "3 · Impact Note" in page
            assert 'href="/deck"' not in page.split("</header>")[0]

        assert 'id="real-bill-select"' in home
        assert 'id="active-bill-banner"' in home
        assert 'id="lab-bill-select"' in lab
        assert 'id="lab-bill-banner"' in lab

        # Bidirectional county handoff wired in app.js and lab.js
        app_js = (ROOT / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        lab_js = (ROOT / "src" / "web" / "static" / "lab.js").read_text(encoding="utf-8")
        assert "county-handoff-cta" in app_js
        assert '"/api/legislation"' in app_js
        assert "county-handoff-back" in lab_js
        assert '"/api/legislation"' in lab_js

        # 3. Official State Housing Impact Note (/brief)
        assert "Housing Impact Note" in brief
        assert 'id="memo-meta"' in brief
        assert 'id="top-counties"' in brief
        assert 'id="top-counties-body"' in brief
        assert 'id="rent-relief"' in brief
        assert 'id="rent-relief-body"' in brief
        assert "1 · Macro View" in brief
        assert "2 · Lot Lab" in brief
        assert "3 · Impact Note" in brief
    finally:
        httpd.shutdown()
        httpd.server_close()

