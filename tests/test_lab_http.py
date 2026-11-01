# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Lab routes sit beside the existing server. / is unchanged."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.web.server import App, make_handler


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App()))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _get(base, path):
    with urlopen(base + path, timeout=30) as response:
        return response.status, response.read(), response.headers


def _post(base, path, payload):
    body = json.dumps(payload).encode("utf-8")
    request = Request(base + path, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=60) as response:
        return response.status, response.read(), response.headers


def test_lab_page_and_locked_results_leave_home_intact():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        home_status, home, home_headers = _get(base, "/")
        home_text = home.decode("utf-8")
        assert home_status == 200
        assert "Stateframe" in home_text
        assert "Tejas Chaudhari" in home_text
        assert 'href="/lab"' in home_text
        assert home_headers.get("X-Frame-Options") == "DENY"
        assert home_headers.get("Referrer-Policy") == "no-referrer"

        status, page, _ = _get(base, "/lab")
        text = page.decode("utf-8")
        assert status == 200
        assert "Small Homes Policy Lab" in text
        assert "Why this result?" in text
        assert "illustrative" in text.lower()
        assert "Tejas Chaudhari" in text

        results_status, results_body, _ = _get(base, "/api/lab/results?state=PA")
        results = json.loads(results_body.decode("utf-8"))
        assert results_status == 200
        assert results["state"] == "PA"
        assert len(results["counties"]) == 67
        assert results["statewide"]["results"]["adu"]["central"] > 0
        assert "p10" in results["statewide"]["results"]["adu"]

        geo_status, geo_body, _ = _get(base, "/api/lab/geo?state=PA")
        geo = json.loads(geo_body.decode("utf-8"))
        assert geo_status == 200
        assert any(c["fips"] == "42003" for c in geo["counties"])

        why_status, why_body, _ = _get(base, "/api/lab/why?state=PA&county=Allegheny&scenario=adu")
        why = json.loads(why_body.decode("utf-8"))
        assert why_status == 200
        assert why["county"]["fips"] == "42003"
        assert any(row["tag"] == "observed" for row in why["inputs"])
        assert any(row["tag"] == "assumed" for row in why["assumptions"])
        assert why["result"]["tag"] == "calculated"
        assert why["coverage"]["tag"] == "calculated"
        assert why["package_decomposition"]["tag"] == "calculated"
        assert "2023-2025" in why["inputs"][-1]["source"] or any(
            "2023-2025" in row.get("source", "") for row in why["inputs"]
        )
        assert "illustrative" in why["option_note"].lower()
        assert why["lots_note"] and "2012" in why["lots_note"]
        assert results["close_call_flip_share_label"] == "close-call threshold"

        export_status, export_body, headers = _get(base, "/api/lab/export?state=PA&format=md&county=Allegheny")
        brief = export_body.decode("utf-8")
        assert export_status == 200
        assert "Small Homes Policy Lab" in brief
        assert "Allegheny" in brief
        assert "text/markdown" in headers["Content-Type"]

        csv_status, csv_body, _ = _get(base, "/api/lab/export?state=PA&format=csv")
        assert csv_status == 200
        assert csv_body.decode("utf-8").splitlines()[0].startswith("fips,county,scenario")
        assert "42003" in csv_body.decode("utf-8")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_lab_recompute_moves_central_and_rejects_unknown_overrides():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _, locked_body, _ = _get(base, "/api/lab/results?state=PA")
        locked = json.loads(locked_body.decode("utf-8"))
        code, raw, _ = _post(
            base,
            "/api/lab/recompute",
            {"state": "PA", "overrides": {"hazard_homeowner": 0.003}, "county": "42003"},
        )
        live = json.loads(raw.decode("utf-8"))
        assert code == 200
        assert live["statewide"]["results"]["adu"]["central"] < locked["statewide"]["results"]["adu"]["central"]
        assert "envelope_note" in live
        assert live["county"]["fips"] == "42003"
        assert "acs_moe" in live["statewide"]["results"]["adu"]
        assert "zoning_low" in live["statewide"]["results"]["adu"]

        body = json.dumps({"state": "PA", "overrides": {"not_a_real_parameter": 1}}).encode("utf-8")
        request = Request(base + "/api/lab/recompute", data=body, headers={"Content-Type": "application/json"})
        try:
            urlopen(request, timeout=20)
            assert False, "unknown override should fail"
        except HTTPError as exc:
            assert exc.code == 400

        try:
            urlopen(base + "/api/lab/results?state=ZZ", timeout=20)
            assert False, "unknown state should fail"
        except HTTPError as exc:
            assert exc.code == 400

        host, port = httpd.server_address
        connection = HTTPConnection(host, port, timeout=20)
        connection.request(
            "POST",
            "/api/lab/recompute",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "70000"},
        )
        response = connection.getresponse()
        assert response.status == 400
        response.read()
        connection.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
