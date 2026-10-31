# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Lab acquisition parsers and the committed sample extracts."""

import copy
import json
import struct

import pytest

from src.lab import acquire, shapefile
from src.lab.config import SAMPLE_DIR
from src.lab.data import build_state, load_boundaries, load_state


def test_acs_sentinels_are_missing_not_zero():
    assert acquire.parse_acs_value("-666666666", False) is None
    assert acquire.parse_acs_value("-222222222", True) is None
    assert acquire.parse_acs_value("-555555555", True) == 0.0
    assert acquire.parse_acs_value("", False) is None
    assert acquire.parse_acs_value("965", False) == 965.0


def test_parse_acs_lines_keeps_estimate_and_moe():
    lines = [
        "GEO_ID|B25031_E003|B25031_M003|B25031_E004|B25031_M004",
        "0500000US42003|965|16|1201|15",
        "0500000US42023|-666666666|-222222222|700|80",
        "0500000US36001|1|1|1|1",
    ]
    keep = acquire.acs_keep({"42"}, set())
    rows = acquire.parse_acs_lines(lines, acquire.ACS_TABLES["b25031"], keep)
    assert set(rows) == {"42003", "42023"}
    assert rows["42003"]["rent_1br"] == {"e": 965.0, "m": 16.0}
    assert rows["42023"]["rent_1br"] == {"e": None, "m": None}


def test_parse_bps_county_uses_imputed_plus_reported_columns():
    line = "202512,42,003,1,2,Allegheny County,1200,1265,438208959,2,4,546740,4,13,1976508,40,2015,169634193," + ",".join(["0"] * 12)
    rows = acquire.parse_bps_county("header\n" + line + "\n", {"42"})
    assert rows["42003"]["u1"] == 1265 and rows["42003"]["u5"] == 2015
    assert rows["42003"]["v1"] == 438208959


def test_density_bins():
    assert acquire.density_bin(0, 1) == 0
    assert acquire.density_bin(250, 1) == acquire.DENSITY_EDGES.index(200)
    assert acquire.density_bin(10_000, 1) == len(acquire.DENSITY_EDGES) - 1


def test_allowlist_rejects_other_hosts():
    with pytest.raises(acquire.AcquireError):
        acquire._request("https://example.com/data.csv")


def test_wprdc_query_is_aggregate_and_never_selects_owner_fields():
    sql = acquire.wprdc_lot_query().upper()
    assert "COUNT(*)" in sql and "GROUP BY" in sql
    for forbidden in ("OWNER", "CHANGENOTICE", "PROPERTYHOUSENUM", "PARID"):
        assert forbidden not in sql


def _tiny_shapefile():
    ring = [(0.0, 0.0), (0.0, 1.0), (0.5, 1.0000001), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]
    content = struct.pack("<i", 5) + struct.pack("<4d", 0, 0, 1, 1) + struct.pack("<ii", 1, len(ring))
    content += struct.pack("<i", 0) + b"".join(struct.pack("<2d", x, y) for x, y in ring)
    record = struct.pack(">ii", 1, len(content) // 2) + content
    shp = b"\x00" * 100 + record
    fields = [("GEOID", 5), ("STATEFP", 2)]
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + sum(length for _, length in fields)
    dbf = bytearray(32)
    dbf[0] = 3
    dbf[4:8] = struct.pack("<I", 1)
    dbf[8:12] = struct.pack("<HH", header_len, record_len)
    for name, length in fields:
        desc = bytearray(32)
        desc[0 : len(name)] = name.encode()
        desc[11] = ord("C")
        desc[16] = length
        dbf += desc
    dbf += b"\x0d" + b" " + b"42003" + b"42"
    return shp, bytes(dbf)


def test_shapefile_reader_and_simplifier():
    shp, dbf = _tiny_shapefile()
    assert shapefile.read_dbf(dbf) == [{"GEOID": "42003", "STATEFP": "42"}]
    shapes = shapefile.read_polygons(shp)
    assert len(shapes) == 1 and len(shapes[0][0]) == 6
    feats = shapefile.features(shp, dbf, lambda rec: rec["STATEFP"] == "42", tolerance=0.001)
    assert len(feats[0]["rings"][0]) == 5  # the near-collinear midpoint is dropped


def test_sample_extracts_cover_all_counties():
    pa = load_state("PA")
    nh = load_state("NH")
    assert len(pa.counties) == 67
    assert len(nh.counties) == 10
    for state in (pa, nh):
        for county in state.counties:
            assert county.rent_1br.value > 0 and county.rent_2br.value > 0
            assert county.median_value.value > 0
            assert county.bps_avg["u1"] >= 0
            hosts = sum(cell.hosts.value for cell in county.cells)
            assert hosts == pytest.approx(county.detached.value + county.attached.value, rel=1e-9)
            for cell in county.cells:
                assert sum(seg.share for seg in cell.segments) == pytest.approx(1.0)
            assert sum(county.context_units.values()) == pytest.approx(1.0)


def test_allegheny_has_pittsburgh_segment_and_observed_lots():
    county = load_state("PA").county("Allegheny")
    urban = [cell for cell in county.cells if cell.context == "urban" and cell.host_type == "detached"][0]
    pgh = [seg for seg in urban.segments if "pittsburgh_adu_2026" in seg.rules]
    assert pgh and pgh[0].adu == "allowed" and pgh[0].adu_parking == 0
    allocated = sum(seg.share * cell.hosts.value for cell in county.cells for seg in cell.segments if seg.rules)
    assert allocated == pytest.approx(70572 + 22776, rel=0.01)
    assert urban.lot_bins is not None and sum(b[2] for b in urban.lot_bins) == pytest.approx(1.0)


def test_philadelphia_adu_is_observed_prohibited():
    county = load_state("PA").county("42101")
    for cell in county.cells:
        assert [seg.adu for seg in cell.segments] == ["prohibited"]


def test_suppressed_acs_is_imputed_and_flagged_never_zero():
    raw = json.loads((SAMPLE_DIR / "NH.json").read_text())
    broken = copy.deepcopy(raw)
    broken["counties"][0]["acs"]["rent_1br"] = {"e": None, "m": None}
    broken["counties"][0]["acs"]["median_value"] = {"e": None, "m": None}
    state = build_state(broken, None, "test")
    county = state.counties[0]
    assert county.rent_1br.tag == "assumed" and county.rent_1br.value > 0
    assert county.rent_1br.moe > 0
    assert county.median_value.tag == "assumed" and county.median_value.value > 0
    assert set(county.imputed) == {"rent_1br", "median_value"}


def test_boundaries_and_sample_size_budget():
    for code, count in (("PA", 67), ("NH", 10)):
        geo = load_boundaries(code)
        assert len(geo["counties"]) == count
        assert all(feature["rings"] for feature in geo["counties"])
    total = sum(path.stat().st_size for path in SAMPLE_DIR.iterdir())
    assert total < 512 * 1024, "keep committed Lab extracts small"
