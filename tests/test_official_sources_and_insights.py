# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Tests for all 11 official state GIS / Handbook data sources and clean-room insights."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from src.bundle import load_bundle
from src.data import official_sources
from src.data.adapters import assert_no_pii
from src.data.safe_url import FetchDenied, fetch_bytes
from src.data.schema import CHALLENGE_STATES
from src.model.assumptions import AssumptionError
from src.model.playhouse_insights import build_state_insights, official_sources_catalog
from src.model.provenance import untagged_numbers
from src.web.server import App, make_handler

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_SAMPLE = ROOT / "data" / "sample" / "official_sources.json"


def _server() -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App()))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _get_json(base: str, path: str) -> tuple[int, dict]:
    with urlopen(base + path, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _post_json(base: str, path: str, body: dict) -> tuple[int, dict]:
    req = Request(
        base + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_official_sources_sample_covers_all_11_states_and_10_handbook_families():
    assert OFFICIAL_SAMPLE.exists()
    doc = json.loads(OFFICIAL_SAMPLE.read_text(encoding="utf-8"))
    assert_no_pii(doc)

    families = {fam["id"] for fam in doc["handbook_families"]}
    assert families == {
        "acs_stock_prices",
        "acs_usps_vacancy",
        "census_bps",
        "fhfa_hpi",
        "bls_construction",
        "ntd_ntad_transit",
        "land_cover_gazetteer",
        "building_footprints",
        "hud_fmr_ami",
        "state_gis_portals",
    }

    ppi = doc["national_bls_ppi"]
    assert ppi["series_id"] == "WPUSI012011"
    assert float(ppi["inflation_2020_latest_pct"]) > 20.0

    states = doc["states"]
    assert set(states.keys()) == set(CHALLENGE_STATES)
    for code in CHALLENGE_STATES:
        item = states[code]
        assert item["portal"]["portal_url"].startswith("https://")
        assert int(item["ntad_transit_stops"]) > 0
        assert float(item["bls_construction"]["jobs_latest_thousands"]) > 0.0
        assert float(item["vacancy_b25004"]["total_vacant"]) > 0.0
        assert float(item["geography"]["land_sqmi"]) > 0.0
        footprints = int(
            item["gis"].get("state_gis_building_footprints")
            or item.get("microsoft_building_footprints")
            or 0
        )
        assert footprints > 100_000
        assert (
            int(item["gis"].get("parcel_records_observed") or 0)
            + int(item["gis"].get("zoning_or_landuse_records") or 0)
        ) > 0
        assert item["gis"]["gis_status"]
        assert item["gis"]["headline_finding"]

    assert states["PA"]["gis"]["parcel_records_observed"] >= 500_000
    assert states["VA"]["gis"]["parcel_records_observed"] >= 4_000_000
    assert states["VA"]["gis"]["state_gis_building_footprints"] >= 4_500_000
    assert states["UT"]["gis"]["parcel_records_observed"] >= 800_000
    assert states["TN"]["gis"]["incorporated_municipalities"] == 345
    assert states["TN"]["gis"]["counties_verified"] == 95


def test_official_sources_allowlist_and_graceful_fallback(monkeypatch, capsys):
    with pytest.raises(FetchDenied):
        fetch_bytes(
            "http://api.bls.gov/publicAPI/v2/timeseries/data/",
            official_sources.OFFICIAL_ALLOWED_HOSTS,
            timeout=5,
            user_agent="test",
        )
    with pytest.raises(FetchDenied):
        fetch_bytes(
            "https://evil.example.com/parcels.json",
            official_sources.OFFICIAL_ALLOWED_HOSTS,
            timeout=5,
            user_agent="test",
        )

    def boom():
        raise RuntimeError("simulated upstream outage")

    monkeypatch.setattr(official_sources, "build_official_sources", boom)
    assert official_sources.main([]) == 2
    err = capsys.readouterr().err
    assert "simulated upstream outage" in err
    assert "Falling back" in err


def test_playhouse_insights_provenance_affordability_single_stair_and_stances():
    fixtures, assumptions = load_bundle()
    catalog = official_sources_catalog(fixtures)
    assert_no_pii(catalog)
    assert untagged_numbers(catalog) == []
    assert catalog["summary"]["states_covered"] == 11
    assert catalog["summary"]["handbook_families_integrated"] == 10
    assert catalog["summary"]["total_gis_records_observed"] > 15_000_000
    assert catalog["summary"]["total_ntad_transit_stops"] > 150_000

    saw_close_stance = False
    for code in CHALLENGE_STATES:
        ins = build_state_insights(fixtures, assumptions, code, single_stair=True)
        assert_no_pii(ins)
        assert untagged_numbers(ins) == [], f"Untagged numbers in {code}: {untagged_numbers(ins)}"

        comp = ins["official_data_card"]["completeness"]
        assert 50 <= comp["benchmark_completeness"] <= 100
        assert comp["extended_completeness"] >= comp["benchmark_completeness"]

        for proto in ins["affordability_screen"]["prototypes"]:
            m = proto["metrics"]
            assert m["breakeven_rent_after"] < m["breakeven_rent_before"]
            assert m["monthly_rent_savings"] > 0

        stair = ins["building_code_and_capacity"]["single_stair_impact"]
        assert stair["incremental_homes_from_single_stair"] >= 0

        stances = ins["priority_stances"]["stances"]
        assert [s["id"] for s in stances] == [
            "balanced",
            "affordability",
            "transit_climate",
            "fiscal_light",
            "fast_delivery",
        ]
        for st in stances:
            assert len(st["rankings"]) == 5
            gap = st["margin"]["top_two_point_gap"]
            assert st["too_close_to_call"] is (gap <= 3.0)
            if st["too_close_to_call"]:
                saw_close_stance = True

    assert saw_close_stance, "Expected at least one state/stance pair within the 3.0-point caution band"

    pa_stair = build_state_insights(fixtures, assumptions, "PA", single_stair=True)
    assert (
        pa_stair["building_code_and_capacity"]["single_stair_impact"]["incremental_homes_from_single_stair"]
        > 3000
    )

    allegheny = build_state_insights(fixtures, assumptions, "PA", county="42003", single_stair=True)
    assert allegheny["selected_county_fips"] == "42003"
    assert "Allegheny" in allegheny["selected_geography"]
    assert allegheny["affordability_screen"]["observed_context"]["hud_fmr_2br"] > 0
    adu_proto = next(p for p in allegheny["affordability_screen"]["prototypes"] if p["id"] == "adu")
    assert adu_proto["metrics"]["ami_pct_needed_after"] < adu_proto["metrics"]["ami_pct_needed_before"]
    assert adu_proto["lowest_ami_band_after"] != adu_proto["lowest_ami_band_before"]

    with pytest.raises(AssumptionError):
        build_state_insights(fixtures, assumptions, "PA", county="99999")


def test_http_data_sources_and_insights_endpoints():
    httpd = _server()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        st, cat = _get_json(base, "/api/data-sources")
        assert st == 200
        assert cat["summary"]["states_covered"] == 11
        assert cat["summary"]["handbook_families_integrated"] == 10

        st2, ins = _get_json(base, "/api/insights?state=PA&county=42003&single_stair=1")
        assert st2 == 200
        assert ins["state"] == "PA"
        assert ins["selected_county_fips"] == "42003"
        assert ins["building_code_and_capacity"]["single_stair_active"] is True

        st3, ins_post = _post_json(
            base,
            "/api/insights",
            {
                "state": "NH",
                "single_stair": False,
                "reform_weights": {"adu": 1.0, "missing_middle": 1.0, "tod": 0.0, "parking": 1.0, "fees": 0.0},
            },
        )
        assert st3 == 200
        assert ins_post["state"] == "NH"
        assert ins_post["building_code_and_capacity"]["single_stair_active"] is False

        for bad_url in (
            "/api/insights?state=ZZ",
            "/api/insights?state=PA&county=99999",
            "/api/insights?state=PA&single_stair=maybe",
        ):
            with pytest.raises(HTTPError) as exc:
                _get_json(base, bad_url)
            assert exc.value.code == 400
            exc.value.close()

        with pytest.raises(HTTPError) as exc_post:
            _post_json(base, "/api/insights", {"state": "PA", "overrides": {"not_a_param": 1.0}})
        assert exc_post.value.code == 400
        exc_post.value.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
