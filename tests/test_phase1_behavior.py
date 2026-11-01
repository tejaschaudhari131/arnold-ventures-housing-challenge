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
from itertools import combinations, permutations

import pytest
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


def _csv_table(body: bytes):
    text = body.decode("utf-8")
    assert text.startswith("fips,"), text.splitlines()[0]
    assert not any(line.startswith("#") for line in text.splitlines())
    return list(csv.DictReader(io.StringIO(text)))


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
        assert "active package" in doc["scenario_label"]
        assert doc["tornado"]["scenario"] == "combined"
        assert doc["tornado"]["central"] == screen["scenarios"]["combined"]["incremental_completions"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_sensitivity_follows_the_open_view():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _, screen, _ = _post(base, "/api/simulate", {"state": "PA"})
        code, adu, _ = _post(
            base,
            "/api/sensitivity",
            {"state": "PA", "scenario": "adu", "draws": 20},
        )
        assert code == 200
        assert adu["tornado"]["scenario"] == "adu"
        assert adu["monte_carlo"]["scenario"] == "adu"
        assert "Showing ADUs" in adu["scenario_label"]
        assert "mode" in adu["scenario_label"]
        assert adu["tornado"]["central"] == screen["scenarios"]["adu"]["incremental_completions"]
        code, package, _ = _post(
            base,
            "/api/sensitivity",
            {"state": "PA", "scenario": "combined", "draws": 20, "reforms": {"adu": 0}},
        )
        assert code == 200
        assert package["tornado"]["scenario"] == "combined"
        assert "active package" in package["scenario_label"]
        assert package["tornado"]["central"] != screen["scenarios"]["combined"]["incremental_completions"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_draws_reject_unicode_digits_and_non_integers():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    bad = ("²", "٢٠", "", " 20", "1e2", True, None)
    try:
        for value in bad:
            for path, message in (
                ("/api/sensitivity", "draws must be an integer from 20 to 400."),
                ("/api/crossval", "draws must be an integer from 20 to 200."),
            ):
                code, body, _ = _post(base, path, {"state": "PA", "scenario": "combined", "draws": value})
                assert code == 400, (path, value, body)
                assert body["error"] == message
                assert "²" not in body["error"]
                assert "٢٠" not in body["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_why_and_csv_for_a_custom_mix_are_not_the_baseline():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, empty, _ = _post(
            base,
            "/api/lab/why",
            {"state": "PA", "county": "Allegheny", "scenario": "selection", "reforms": []},
        )
        assert code == 200
        assert empty["empty"] is True
        assert empty["result"]["delivery"] == 0
        code, adu, _ = _post(
            base, "/api/lab/why", {"state": "PA", "county": "Allegheny", "scenario": "adu"}
        )
        code, fees, _ = _post(
            base, "/api/lab/why", {"state": "PA", "county": "Allegheny", "scenario": "fees"}
        )
        code, mix, _ = _post(
            base,
            "/api/lab/why",
            {"state": "PA", "county": "Allegheny", "scenario": "selection", "reforms": ["adu", "fees"]},
        )
        assert code == 200
        assert mix["scenario"] == "selection"
        assert mix["result"]["eligible"] == adu["result"]["eligible"] + fees["result"]["eligible"]
        assert mix["result"]["feasible"] == adu["result"]["feasible"] + fees["result"]["feasible"]
        assert "not computed" in mix["note"]
        status, csv_body, _ = _post(
            base, "/api/lab/export", {"state": "PA", "format": "csv", "reforms": ["adu", "fees"]}
        )
        assert status == 200
        rows = _csv_table(csv_body)
        allegheny = next(row for row in rows if row["fips"] == "42003")
        assert allegheny["scenario"] == "selection"
        assert "eligible" not in allegheny
        assert allegheny["envelope_p10"] == ""
        assert allegheny["zoning_low"] == ""
        assert "Reference range (defaults)" in allegheny["range_role"]
        assert allegheny["basis"] == "sum of per-reform counts; lots may overlap; not a joint count"
        assert allegheny["central_basis"] == "simple sum of standalone results, not modelled jointly"
        assert allegheny["close_call_top_benchmark"] == "not computed for mix"
        assert float(allegheny["eligible_sum_of_reforms"]) == pytest.approx(
            adu["result"]["eligible"] + fees["result"]["eligible"], abs=0.2
        )
        assert float(allegheny["feasible_sum_of_reforms"]) == pytest.approx(
            adu["result"]["feasible"] + fees["result"]["feasible"], abs=0.2
        )
        status, brief, _ = _post(
            base, "/api/lab/export", {"state": "PA", "format": "md", "reforms": []}
        )
        text = brief.decode("utf-8")
        assert status == 200
        assert "Selected reforms: none" in text
        assert "not computed" in text or "Extra homes from that selection: 0" in text
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_custom_mix_csv_labels_overlap_and_rejects_unknown_reforms():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _, default_body, _ = _get(base, "/api/lab/export?state=PA&format=csv")
        published = _csv_table(default_body)
        assert published[0]["eligible"]
        assert "eligible_sum_of_reforms" not in published[0]

        def published_cell(scenario, field):
            row = next(item for item in published if item["fips"] == "42001" and item["scenario"] == scenario)
            return float(row[field])

        adu_eligible = published_cell("adu", "eligible")
        middle_eligible = published_cell("missing_middle", "eligible")
        package_eligible = published_cell("package", "eligible")
        assert adu_eligible + middle_eligible > package_eligible
        status, mix_body, _ = _post(
            base,
            "/api/lab/export",
            {"state": "PA", "format": "csv", "reforms": ["adu", "missing_middle"]},
        )
        assert status == 200
        rows = _csv_table(mix_body)
        adams = next(row for row in rows if row["fips"] == "42001")
        assert float(adams["eligible_sum_of_reforms"]) == pytest.approx(adu_eligible + middle_eligible, abs=0.2)
        assert float(adams["eligible_sum_of_reforms"]) > package_eligible
        assert float(adams["central"]) == pytest.approx(
            published_cell("adu", "central") + published_cell("missing_middle", "central"), abs=0.2
        )
        assert adams["basis"] == "sum of per-reform counts; lots may overlap; not a joint count"
        assert adams["central_basis"] == "simple sum of standalone results, not modelled jointly"
        assert adams["close_call_top_benchmark"] == "not computed for mix"
        status, empty_body, _ = _post(
            base, "/api/lab/export", {"state": "PA", "format": "csv", "reforms": []}
        )
        assert status == 200
        empty_rows = _csv_table(empty_body)
        empty_adams = next(row for row in empty_rows if row["fips"] == "42001")
        assert empty_adams["scenario"] == "none"
        assert empty_adams["eligible_sum_of_reforms"] == ""
        assert empty_adams["feasible_sum_of_reforms"] == ""
        assert empty_adams["central_basis"] == "no reforms selected"
        assert empty_adams["close_call_top_benchmark"] == "not computed for mix"
        assert empty_adams["central"] == "0.0"
        status, brief, _ = _post(
            base,
            "/api/lab/export",
            {"state": "PA", "format": "md", "reforms": ["adu", "missing_middle"]},
        )
        text = brief.decode("utf-8")
        assert status == 200
        assert "lots may overlap" in text
        assert "not modelled jointly" in text
        for path, payload in (
            ("/api/lab/why", {"state": "PA", "county": "Adams", "scenario": "selection", "reforms": ["adu", "not_a_reform"]}),
            ("/api/lab/why", {"state": "PA", "county": "Adams", "scenario": "selection", "reforms": ["not_a_reform"]}),
            ("/api/lab/export", {"state": "PA", "format": "csv", "reforms": ["not_a_reform"]}),
            ("/api/lab/export", {"state": "PA", "format": "md", "reforms": ["adu", "missing_middle", "nope"]}),
            ("/api/lab/export", {"state": "PA", "format": "html", "reforms": ["ADU"]}),
        ):
            code, body, _ = _post(base, path, payload)
            assert code == 400, (path, payload, body)
            assert body["error"] == "Unknown reform."
            dumped = json.dumps(body)
            assert "not_a_reform" not in dumped
            assert "nope" not in dumped
            assert "ADU" not in dumped
    finally:
        httpd.shutdown()
        httpd.server_close()


_DEFAULT_CSV_COLUMNS = [
    "fips", "county", "scenario", "central", "envelope_p10", "envelope_p90",
    "range_role", "zoning_low", "zoning_high", "acs_moe", "eligible", "feasible",
    "close_call_top_benchmark",
]
_MIX_CSV_COLUMNS = [
    "fips", "county", "scenario", "central", "central_basis",
    "envelope_p10", "envelope_p90", "range_role",
    "zoning_low", "zoning_high", "acs_moe",
    "eligible_sum_of_reforms", "feasible_sum_of_reforms", "basis",
    "close_call_top_benchmark",
]


def test_pandas_reads_lab_csv_and_duplicate_reforms_are_rejected():
    import pandas as pd

    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _, default_body, _ = _get(base, "/api/lab/export?state=PA&format=csv")
        default = pd.read_csv(io.BytesIO(default_body))
        assert list(default.columns) == _DEFAULT_CSV_COLUMNS
        assert len(default) > 1
        adams_adu = default[(default["county"] == "Adams County") & (default["scenario"] == "adu")].iloc[0]
        adams_middle = default[
            (default["county"] == "Adams County") & (default["scenario"] == "missing_middle")
        ].iloc[0]
        status, mix_body, _ = _post(
            base,
            "/api/lab/export",
            {"state": "PA", "format": "csv", "reforms": ["missing_middle", "adu"]},
        )
        assert status == 200
        mix = pd.read_csv(io.BytesIO(mix_body))
        assert list(mix.columns) == _MIX_CSV_COLUMNS
        assert str(mix_body.splitlines()[0], "utf-8").startswith("fips,")
        adams = mix.loc[mix["county"] == "Adams County"].iloc[0]
        assert adams["eligible_sum_of_reforms"] == pytest.approx(
            adams_adu["eligible"] + adams_middle["eligible"], abs=0.2
        )
        assert adams["central"] == pytest.approx(adams_adu["central"] + adams_middle["central"], abs=0.2)
        assert adams["central"] != pytest.approx(adams_adu["central"] * 2, abs=0.05)
        shuffled = ["fees", "parking", "missing_middle", "adu"]
        status, ordered_body, _ = _post(
            base, "/api/lab/export", {"state": "PA", "format": "csv", "reforms": shuffled}
        )
        assert status == 200
        assert ordered_body == default_body
        ordered = pd.read_csv(io.BytesIO(ordered_body))
        assert list(ordered.columns) == _DEFAULT_CSV_COLUMNS
        code, package, _ = _post(
            base, "/api/lab/why", {"state": "PA", "county": "Adams", "scenario": "package"}
        )
        code, same, _ = _post(
            base,
            "/api/lab/why",
            {"state": "PA", "county": "Adams", "scenario": "selection", "reforms": shuffled},
        )
        assert code == 200
        assert same["scenario"] == "package"
        assert same["result"]["eligible"] == package["result"]["eligible"]
        assert same["result"]["delivery"] == package["result"]["delivery"]
        status, brief, _ = _post(
            base, "/api/lab/export", {"state": "PA", "format": "md", "reforms": shuffled}
        )
        assert status == 200
        assert "all four Handbook reforms" in brief.decode("utf-8")
        for path, payload in (
            ("/api/lab/why", {"state": "PA", "county": "Adams", "scenario": "selection", "reforms": ["adu", "adu"]}),
            ("/api/lab/export", {"state": "PA", "format": "csv", "reforms": ["adu", "adu"]}),
            ("/api/lab/export", {"state": "PA", "format": "md", "reforms": ["adu", "adu"]}),
            (
                "/api/lab/export",
                {"state": "PA", "format": "csv", "reforms": ["adu", "missing_middle", "parking", "fees", "adu"]},
            ),
            (
                "/api/lab/why",
                {
                    "state": "PA",
                    "county": "Adams",
                    "scenario": "selection",
                    "reforms": ["fees", "adu", "missing_middle", "parking", "fees"],
                },
            ),
        ):
            code, body, _ = _post(base, path, payload)
            assert code == 400, (path, payload, body)
            assert body["error"] == "Duplicate reform."
            dumped = json.dumps(body)
            assert "adu, adu" not in dumped
            assert "98.2" not in dumped
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_why_options_are_identical_for_every_reform_order():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    reforms = ["adu", "missing_middle", "parking", "fees"]

    def options_for(ids, scenario="selection"):
        code, body, _ = _post(
            base,
            "/api/lab/why",
            {"state": "PA", "county": "Adams", "scenario": scenario, "reforms": ids},
        )
        assert code == 200, (ids, body)
        return body["options"]

    def mm2(rows):
        return next(row for row in rows if row["option"] == "mm2")

    try:
        for size in (2, 3):
            for combo in combinations(reforms, size):
                expected = None
                for perm in permutations(combo):
                    got = options_for(list(perm))
                    if expected is None:
                        expected = got
                    else:
                        assert got == expected, perm
        missing_middle = options_for([], scenario="missing_middle")
        with_fees = options_for(["fees", "missing_middle"])
        with_parking = options_for(["parking", "missing_middle"])
        assert mm2(with_fees)["cost"] < mm2(missing_middle)["cost"]
        assert mm2(with_parking)["spaces"] != mm2(missing_middle)["spaces"]
        assert options_for(["missing_middle", "fees"]) == with_fees
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_out_of_range_draws_are_rejected():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        for bad in (0, -3, 2.5, 5, 401, 100000):
            code, body, _ = _post(
                base,
                "/api/sensitivity",
                {"state": "PA", "scenario": "combined", "draws": bad},
            )
            assert code == 400, bad
            assert body["error"] == "draws must be an integer from 20 to 400."
        code, ok, _ = _post(
            base,
            "/api/sensitivity",
            {"state": "PA", "scenario": "adu", "draws": 20},
        )
        assert code == 200
        assert ok["monte_carlo"]["draws"] == 20
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


def test_recompute_validates_reforms_and_still_returns_every_scenario():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, bad, _ = _post(
            base, "/api/lab/recompute", {"state": "PA", "reforms": ["not_a_reform"]}
        )
        assert code == 400
        assert bad["error"] == "Unknown reform."
        assert "not_a_reform" not in json.dumps(bad)
        code, dup, _ = _post(
            base, "/api/lab/recompute", {"state": "PA", "reforms": ["adu", "adu"]}
        )
        assert code == 400
        assert dup["error"] == "Duplicate reform."
        code, plain, _ = _post(base, "/api/lab/recompute", {"state": "PA"})
        code, kept, _ = _post(
            base,
            "/api/lab/recompute",
            {"state": "PA", "reforms": ["fees", "missing_middle"]},
        )
        assert code == 200 and plain
        assert kept["statewide"]["results"]["missing_middle"]["central"] == (
            plain["statewide"]["results"]["missing_middle"]["central"]
        )
        assert "package" in kept["statewide"]["results"]
        status, brief, _ = _post(
            base,
            "/api/lab/export",
            {"state": "PA", "format": "md", "reforms": ["adu", "missing_middle"]},
        )
        text = brief.decode("utf-8")
        assert status == 200
        assert "Close call: not computed for mix." in text
        assert "Statistical tie" not in text
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_static_aria_describedby_targets_exist():
    from pathlib import Path
    import re

    root = Path(__file__).resolve().parents[1] / "src" / "web" / "static"
    for path in list(root.glob("*.html")) + list(root.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        ids = set(re.findall(r'\bid="([^"]+)"', text))
        for ref in re.findall(r'aria-describedby="([^"]*)"', text):
            if "+" in ref or "\n" in ref or "'" in ref:
                continue
            for token in ref.split():
                assert token in ids, (path.name, token)


def test_client_csv_has_a_constant_column_count():
    proc = subprocess.run(
        ["node", "tests/js/lab_csv.mjs"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "16 subsets" in proc.stdout


def test_lab_url_round_trip_keeps_an_empty_selection(tmp_path):
    proc = subprocess.run(
        ["node", "tests/js/lab_roundtrip.mjs", "?st=PA&on=none&ov=hazard_homeowner_feasible:0.0062"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "on=none" in proc.stdout
