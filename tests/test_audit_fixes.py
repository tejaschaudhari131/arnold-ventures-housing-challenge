# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for post-Phase-4 audit fixes across API, CLI, export, and docs."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.bundle import load_bundle
from src.export.report import to_markdown
from src.lab.data import load_state
from src.lab.engine import evaluate_state
from src.lab.explain import locked_results
from src.lab.run import format_table
from src.model.engine import simulate_state
from src.web.server import App, make_handler

ROOT = Path(__file__).resolve().parents[1]


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App()))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _post(base: str, path: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        base + path,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            parsed = raw.decode("utf-8", errors="replace")
        return exc.code, parsed


def test_lab_mix_empty_and_joint_lot_resolution():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        locked = locked_results("PA")
        decomp = locked["statewide"]["package_decomposition"]

        status, empty = _post(base, "/api/lab/mix", {"state": "PA", "reforms": []})
        assert status == 200
        assert empty["empty"] is True
        assert empty["statewide"]["central"] == 0.0

        status, pair = _post(
            base,
            "/api/lab/mix",
            {"state": "PA", "reforms": ["adu", "missing_middle"], "county": "42003"},
        )
        assert status == 200
        assert pair["empty"] is False
        sw = pair["statewide"]
        assert abs(sw["central"] - decomp["legalization_resolved"]) <= 0.1
        assert sw["interaction"] < -2500.0
        assert abs((sw["sum_of_separate"] + sw["interaction"]) - sw["central"]) <= 0.2
        assert sw["zoning_low"] <= sw["central"] <= sw["zoning_high"]
        assert pair["county"] is not None
        assert pair["county"]["fips"] == "42003"
        assert pair["county"]["central"] < pair["county"]["sum_of_separate"]

        status, triple = _post(
            base,
            "/api/lab/mix",
            {"state": "PA", "reforms": ["adu", "missing_middle", "fees"]},
        )
        assert status == 200
        expected_triple = decomp["legalization_resolved"] + decomp["fee_cut_step"]
        assert abs(triple["statewide"]["central"] - expected_triple) <= 0.2

        status, full = _post(
            base,
            "/api/lab/mix",
            {"state": "PA", "reforms": ["adu", "missing_middle", "parking", "fees"]},
        )
        assert status == 200
        pkg_central = locked["statewide"]["results"]["package"]["central"]
        assert abs(full["statewide"]["central"] - pkg_central) <= 0.1
    finally:
        httpd.shutdown()


def test_lab_mix_order_independence_overrides_and_validation():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        s1, mix_ab = _post(base, "/api/lab/mix", {"state": "PA", "reforms": ["fees", "adu"]})
        s2, mix_ba = _post(base, "/api/lab/mix", {"state": "PA", "reforms": ["adu", "fees"]})
        assert s1 == 200 and s2 == 200
        assert mix_ab["statewide"]["central"] == mix_ba["statewide"]["central"]

        s_def, default_mm = _post(
            base,
            "/api/lab/mix",
            {"state": "PA", "reforms": ["adu", "missing_middle"]},
        )
        s_low, low_hazard_mm = _post(
            base,
            "/api/lab/mix",
            {
                "state": "PA",
                "reforms": ["adu", "missing_middle"],
                "overrides": {"hazard_homeowner": 0.0006},
            },
        )
        assert s_def == 200 and s_low == 200
        assert low_hazard_mm["statewide"]["central"] < default_mm["statewide"]["central"]

        for bad_payload, secret in [
            ({"state": "PA", "reforms": ["not_a_reform"]}, "not_a_reform"),
            ({"state": "PA", "reforms": ["tod"]}, "tod"),
            ({"state": "PA", "reforms": ["adu", "adu"]}, None),
            ({"state": "PA", "reforms": ["adu", "fees"], "county": "NotACountyXYZ"}, "NotACountyXYZ"),
        ]:
            code, err = _post(base, "/api/lab/mix", bad_payload)
            assert code == 400
            err_text = json.dumps(err)
            if secret:
                assert secret not in err_text
    finally:
        httpd.shutdown()


def test_lab_cli_rounding_matches_locked_county_results():
    state = load_state("PA")
    ev = evaluate_state(state)
    table = format_table(ev, "42003")
    assert "Allegheny County, PA" in table
    assert "+838" in table
    assert "+1,548" in table


def test_markdown_export_tags_tier_as_classification_and_shows_permit_vintage():
    fixtures, assumptions = load_bundle()
    ct = simulate_state(fixtures, assumptions, "CT")
    pa = simulate_state(fixtures, assumptions, "PA")
    md = to_markdown([ct, pa])
    assert "| CT | 1 [classification] | BPS 2022-2024 [observed] |" in md
    assert "| PA | 2 [classification] | BPS 2023-2025 [observed] |" in md
    assert "1 [observed]" not in md
    assert "2 [observed]" not in md


def test_documentation_post_phase4_consistency():
    policy_doc = (ROOT / "docs" / "POLICY_SCENARIO_COMPARISON.md").read_text(encoding="utf-8")
    assert "5 to 7 percent" not in policy_doc
    assert "10,789" not in policy_doc
    assert "0.8 to 1.7 percent" in policy_doc
    assert "6,360" in policy_doc

    case_doc = (ROOT / "docs" / "CASE_STUDY_PA_ALLEGHENY.md").read_text(encoding="utf-8")
    assert "2023–2025 county files" in case_doc
    assert "BPS 2023-2025" in case_doc
    assert "2022–2024 county files" not in case_doc
