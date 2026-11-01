# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Behavioral checks for the phase-1 defects and the security review.

These hit the HTTP server or call the loader and engines. They do not assert
on source text.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.data.safe_url import FetchDenied, assert_allowed
from src.export.csvsafe import csv_cell
from src.lab.config import central_params
from src.lab.data import load_state
from src.lab.engine import Econ, pipeline_effect, state_unit_values
from src.web.server import App, make_handler


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App()))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _get(base, path):
    with urlopen(base + path, timeout=60) as response:
        return response.status, response.read(), response.headers


def _post(base, path, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    request = Request(base + path, data=body, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read()
            content = response.headers.get("Content-Type", "")
            parsed = json.loads(raw.decode("utf-8")) if "json" in content else raw
            return response.status, parsed, response.headers
    except HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed, exc.headers


def test_custom_export_matches_the_on_screen_scenario():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    reforms = {
        "adu": {"on": False, "weight": 1},
        "missing_middle": {"on": True, "weight": 1},
        "tod": {"on": True, "weight": 1},
        "parking": {"on": True, "weight": 1},
        "fees": {"on": True, "weight": 1},
    }
    try:
        code, screen, _ = _post(base, "/api/simulate", {"state": "PA", "reforms": reforms})
        assert code == 200
        status, exported, headers = _post(
            base, "/api/export", {"state": "PA", "format": "json", "reforms": reforms}
        )
        assert status == 200
        assert "attachment" in headers["Content-Disposition"]
        got = exported["results"][0]["scenarios"]["combined"]["incremental_completions"]
        assert got == screen["scenarios"]["combined"]["incremental_completions"]
        default_status, default_body, _ = _get(base, "/api/export?state=PA&format=json")
        default = json.loads(default_body.decode("utf-8"))
        default_pkg = default["results"][0]["scenarios"]["combined"]["incremental_completions"]
        assert got != default_pkg
        assert "scenario" not in default
        assert exported["scenario"]["state"] == "PA"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_lab_recompute_labels_the_reference_range_and_the_brief():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    payload = {"state": "PA", "overrides": {"hazard_homeowner_feasible": 0.0062}}
    try:
        code, doc, _ = _post(base, "/api/lab/recompute", payload)
        assert code == 200
        row = doc["statewide"]["results"]["missing_middle"]
        assert row["interval_status"] == "reference"
        assert "Reference range (defaults)" in row["interval_label"]
        assert isinstance(row["p10"], (int, float)) and isinstance(row["p90"], (int, float))
        assert row["central"] != row["p10"]
        status, brief, _ = _post(
            base, "/api/lab/export", {"state": "PA", "format": "md", "overrides": payload["overrides"]}
        )
        text = brief.decode("utf-8")
        assert status == 200
        assert "Reference range (defaults)" in text
        assert "At default settings" in text
        assert "With this assumption, the central order is" in text
        csv_status, csv_body, _ = _post(
            base, "/api/lab/export", {"state": "PA", "format": "csv", "overrides": payload["overrides"]}
        )
        rows = list(csv.DictReader(io.StringIO(csv_body.decode("utf-8"))))
        assert csv_status == 200
        assert rows
        assert {row["range_role"] for row in rows} == {"reference_at_default_settings"}
        outside = [
            row for row in rows
            if float(row["central"]) < float(row["envelope_p10"]) or float(row["central"]) > float(row["envelope_p90"])
        ]
        assert outside
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_sensitivity_uses_the_current_reform_mix():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    reforms = {"adu": 0, "missing_middle": 1, "tod": 1, "parking": 1, "fees": 1}
    try:
        sim_code, screen, _ = _post(base, "/api/simulate", {"state": "PA", "reforms": reforms})
        code, doc, _ = _post(
            base,
            "/api/sensitivity",
            {"state": "PA", "scenario": "combined", "draws": 20, "reforms": reforms},
        )
        assert sim_code == 200 and code == 200
        assert doc["reference"] is False
        assert "Current scenario" in doc["scenario_label"]
        assert doc["tornado"]["central"] == screen["scenarios"]["combined"]["incremental_completions"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_bad_requests_are_400_and_do_not_echo_input():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    hostile = "<script>alert(1)</script>" + ("A" * 5000)
    try:
        code, body, headers = _post(base, "/api/simulate", {"state": "PA", "overrides": {"supply_elasticity": float("nan")}})
        assert code == 400
        assert "script" not in json.dumps(body).lower()
        assert len(body["error"]) <= 160
        assert "Content-Security-Policy" in headers
        assert "Permissions-Policy" in headers
        code, body, _ = _post(base, "/api/lab/recompute", {"state": "PA", "overrides": {"hazard_homeowner_feasible": "NaN"}})
        assert code == 400
        code, body, _ = _post(base, "/api/lab/recompute", {"state": "PA", "overrides": {"hazard_homeowner_feasible": "Infinity"}})
        assert code == 400
        code, body, _ = _post(base, "/api/sensitivity", {"state": "PA", "scenario": "combined", "draws": "abc"})
        assert code == 400
        code, body, _ = _post(base, "/api/sensitivity", {"state": "PA", "scenario": "combined", "draws": 1e309})
        assert code == 400
        code, body, _ = _post(base, "/api/lab/why", {"state": "PA", "county": "Not A County", "scenario": "adu"})
        assert code == 400
        assert "Not A County" not in body["error"]
        raw = json.dumps({"state": "PA"}).encode()
        request = Request(
            base + "/api/simulate",
            data=raw,
            headers={"Content-Type": "application/json", "Content-Length": "nope"},
        )
        try:
            urlopen(request, timeout=20)
            raised = False
        except HTTPError as exc:
            raised = exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
            assert "nope" not in payload["error"]
        assert raised
        code, body, _ = _post(base, "/api/simulate", {"state": hostile})
        assert code == 400
        assert hostile not in body["error"]
        assert "<" not in body["error"]
        doc_status, doc_body, doc_headers = _get(base, "/docs/SMALL_HOMES_LAB.md")
        assert doc_status == 200
        assert b"#" in doc_body
        assert "script-src 'self'" in doc_headers["Content-Security-Policy"]
        try:
            _get(base, "/docs/../requirements.txt")
            missing = 200
        except HTTPError as exc:
            missing = exc.code
        assert missing == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_csv_formula_cells_are_quoted_and_numbers_stay_numbers():
    assert csv_cell("=HYPERLINK()") == "'=HYPERLINK()"
    assert csv_cell("-12.5") == "-12.5"
    assert csv_cell(12) == 12


def test_downloads_reject_http_and_off_list_redirects():
    try:
        assert_allowed("http://www2.census.gov/x", frozenset({"www2.census.gov"}))
        raised = False
    except FetchDenied:
        raised = True
    assert raised
    try:
        assert_allowed("https://evil.example/x", frozenset({"www2.census.gov"}))
        raised = False
    except FetchDenied:
        raised = True
    assert raised
    assert_allowed("https://www2.census.gov/x", frozenset({"www2.census.gov"}))


def test_horizon_zero_does_not_crash_the_pipeline():
    state = load_state("PA")
    county = state.county("Allegheny")
    out = pipeline_effect(
        county,
        state_unit_values(state),
        Econ(0.0),
        Econ(0.0),
        central_params(),
        0,
        None,
        None,
    )
    assert out["baseline"] == 0.0
    assert out["delta"] == 0.0
    assert out["timing"] == 0.0


def test_completion_ratio_slider_changes_the_headline():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _, low, _ = _post(base, "/api/simulate", {"state": "PA", "overrides": {"completion_ratio_mf": 0.70}})
        _, high, _ = _post(base, "/api/simulate", {"state": "PA", "overrides": {"completion_ratio_mf": 0.93}})
        assert low["baseline_completions_5yr"] != high["baseline_completions_5yr"]
        assert low["scenarios"]["combined"]["incremental_completions"] != high["scenarios"]["combined"]["incremental_completions"]
        _, sens, _ = _post(
            base,
            "/api/sensitivity",
            {"state": "PA", "scenario": "combined", "draws": 20, "overrides": {"completion_ratio_mf": 0.70}},
        )
        assert sens["tornado"]["scenario"] == "combined"
        assert sens["tornado"]["central"] == low["scenarios"]["combined"]["incremental_completions"]
        _, note_body, _ = _get(base, "/api/adu-compare?state=NH")
        _, pa_body, _ = _get(base, "/api/adu-compare?state=PA")
        note = json.loads(note_body)
        pa_note = json.loads(pa_body)
        assert note["notes"]["lab"] != pa_note["notes"]["lab"]
        _, provenance, _ = _get(base, "/docs/DATA_PROVENANCE.md")
        assert b"Provenance" in provenance or b"provenance" in provenance.lower()
        _, brief, _ = _post(base, "/api/lab/export", {"state": "PA", "format": "md", "reforms": []})
        assert b"Selected reforms: none" in brief
        assert b"0" in brief
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_lab_url_round_trip_keeps_an_empty_selection(tmp_path):
    proc = subprocess.run(
        ["node", "tests/js/lab_roundtrip.mjs", "?st=PA&on=none&ov=hazard_homeowner_feasible:0.0062"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "on=none" in proc.stdout
