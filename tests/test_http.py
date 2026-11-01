# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""The local server exposes a fixed route map and the three authors' full names."""

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


def _post(base, path, payload, length=None):
    body = json.dumps(payload).encode("utf-8")
    request = Request(base + path, data=body, headers={"Content-Type": "application/json"})
    if length is not None:
        request.add_header("Content-Length", str(length))
    with urlopen(request, timeout=60) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_pages_name_the_team_and_simulate_pennsylvania():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, page, _headers = _get(base, "/")
        text = page.decode("utf-8")
        assert status == 200
        assert "Stateframe" in text
        assert "Tejas Chaudhari" in text
        assert "Yoon Yik Ng" in text
        assert "Christopher Severns" in text
        assert "YY Ng" not in text
        assert "observed" in text
        assert "assumed" in text
        assert "calculated" in text
        assert "Pennsylvania case study" in text
        assert "One-page brief" in text
        assert 'id="map-stage"' in text
        health, health_body, health_headers = _get(base, "/api/health")
        assert health == 200
        health_doc = json.loads(health_body.decode("utf-8"))
        assert health_doc["ok"] is True
        assert health_doc["sha"] and health_doc["short_sha"]
        assert health_doc["date"]
        assert health_doc["fingerprints"]["PA"] == "18b20e94b790213c"
        assert health_doc["fingerprints"]["NH"] == "f0a85db0ee26fda1"
        assert health_headers["Cache-Control"] == "no-store"
        _status, _css, css_headers = _get(base, "/styles.css")
        assert css_headers["Cache-Control"] == "public, max-age=300, s-maxage=86400"
        _status, _lab, lab_headers = _get(base, "/api/lab/results?state=PA")
        assert lab_headers["Cache-Control"] == "public, max-age=300, s-maxage=86400"
        _status, _geo, geo_headers = _get(base, "/api/lab/geo?state=PA")
        assert geo_headers["Cache-Control"] == "public, max-age=300, s-maxage=86400"
        catalog_status, catalog_body, _ = _get(base, "/api/assumptions?state=PA")
        catalog = json.loads(catalog_body.decode("utf-8"))
        assert catalog_status == 200
        assert any(row["name"] == "fee_reduction_fraction" for row in catalog["parameters"])
        code, result = _post(base, "/api/simulate", {"state": "PA", "overrides": {}})
        assert code == 200
        assert result["state"] == "PA"
        assert result["scenarios"]["baseline"]["completions_5yr"] > 0
        assert result["provenance"]["baseline_completions_5yr"] == "calculated"
        map_status, map_body, _ = _get(base, "/api/map")
        assert map_status == 200
        points = json.loads(map_body.decode("utf-8"))["points"]
        assert any(point["fips"] == "42003" for point in points)
        case_status, case_body, _ = _get(base, "/api/case-study")
        assert case_status == 200
        study = json.loads(case_body.decode("utf-8"))
        assert study["county_name"] == "Allegheny County"
        assert study["counties_sum_to_state"] is True
        script_status, script, _ = _get(base, "/app.js")
        assert script_status == 200
        assert b"api/simulate" in script
        try:
            urlopen(base + "/../requirements.txt", timeout=10)
            raised = False
        except HTTPError as exc:
            raised = exc.code == 404
        assert raised
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_oversized_and_unknown_override_are_rejected():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        body = json.dumps({"state": "PA", "overrides": {"not_a_real_parameter": 1}}).encode("utf-8")
        request = Request(base + "/api/simulate", data=body, headers={"Content-Type": "application/json"})
        try:
            urlopen(request, timeout=20)
            assert False, "unknown override should fail"
        except HTTPError as exc:
            assert exc.code == 400
        host, port = httpd.server_address
        connection = HTTPConnection(host, port, timeout=20)
        connection.request(
            "POST",
            "/api/simulate",
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
