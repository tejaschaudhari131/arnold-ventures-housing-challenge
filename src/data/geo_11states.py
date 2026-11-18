# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Build simplified county boundaries for all 11 Challenge states.

Uses the public-domain U.S. Census Bureau cartographic boundary archive
``cb_2024_us_county_5m.zip`` and the pure-stdlib Douglas–Peucker reader in
``src.lab.shapefile`` so the screening studio renders authentic county
choropleth polygons across every Challenge state with zero third-party GIS
dependencies or external map tiles.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from src.data.adapters import assert_no_pii
from src.data.safe_url import fetch_bytes
from src.data.schema import CHALLENGE_STATES, ROOT
from src.lab import shapefile

BOUNDARY_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_5m.zip"
ALLOWED_HOSTS = frozenset({"www2.census.gov"})
USER_AGENT = "stateframe-housing-sim/1.0 (public-data acquisition; research)"
GEO_11STATES_PATH = ROOT / "data" / "sample" / "counties_11states.geo.json"

STATE_FIPS_TO_CODE: dict[str, str] = {
    "04": "AZ",
    "09": "CT",
    "15": "HI",
    "33": "NH",
    "41": "OR",
    "42": "PA",
    "44": "RI",
    "47": "TN",
    "49": "UT",
    "51": "VA",
    "55": "WI",
}
CODE_TO_STATE_FIPS: dict[str, str] = {code: fips for fips, code in STATE_FIPS_TO_CODE.items()}


def parse_cb_archive(
    blob: bytes,
    tolerance: float = 0.005,
    digits: int = 3,
) -> dict[str, Any]:
    """Extract and simplify county polygons for all 11 Challenge states."""
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        shp_name = [n for n in names if n.lower().endswith(".shp")][0]
        dbf_name = [n for n in names if n.lower().endswith(".dbf")][0]
        shp_bytes = archive.read(shp_name)
        dbf_bytes = archive.read(dbf_name)

    records = shapefile.read_dbf(dbf_bytes)
    shapes = shapefile.read_polygons(shp_bytes)
    if len(records) != len(shapes):
        raise ValueError(f"{len(records)} dbf records vs {len(shapes)} shapes")

    states_out: dict[str, list[dict[str, Any]]] = {code: [] for code in CHALLENGE_STATES}
    for rec, rings in zip(records, shapes):
        st_fips = rec.get("STATEFP", "").strip()
        code = STATE_FIPS_TO_CODE.get(st_fips)
        if not code:
            continue
        geoid = rec.get("GEOID", "").strip()
        name = rec.get("NAMELSAD") or rec.get("NAME") or geoid
        simplified = shapefile.simplify_shape(rings, tolerance=tolerance, digits=digits)
        states_out[code].append(
            {
                "fips": geoid,
                "name": name,
                "short_name": rec.get("NAME") or name,
                "rings": simplified,
            }
        )

    for code in states_out:
        states_out[code].sort(key=lambda item: item["fips"])

    doc: dict[str, Any] = {
        "source": "U.S. Census Bureau cartographic boundary file cb_2024_us_county_5m, Douglas–Peucker simplified",
        "license": "Public domain, U.S. government work (17 U.S.C. 105)",
        "url": BOUNDARY_URL,
        "states": states_out,
    }
    assert_no_pii(doc)
    return doc


def load_geo_11states(state_code: str | None = None, path: Path = GEO_11STATES_PATH) -> dict[str, Any]:
    """Load the committed 11-state GeoJSON document (optionally filtered to 1 state)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not state_code or state_code.upper() == "ALL":
        return doc
    code = state_code.strip().upper()
    states = doc.get("states") or {}
    if code not in states:
        raise KeyError(f"Unknown state: {code}")
    return {
        "source": doc["source"],
        "license": doc["license"],
        "url": doc["url"],
        "state": code,
        "counties": states[code],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build 11-state simplified county boundary JSON.")
    parser.add_argument("--output", type=Path, default=GEO_11STATES_PATH)
    parser.add_argument("--tolerance", type=float, default=0.005)
    parser.add_argument("--digits", type=int, default=3)
    args = parser.parse_args(argv)

    print(f"Downloading {BOUNDARY_URL} ...", flush=True)
    blob = fetch_bytes(BOUNDARY_URL, ALLOWED_HOSTS, 180, USER_AGENT)
    doc = parse_cb_archive(blob, tolerance=args.tolerance, digits=args.digits)
    text = json.dumps(doc, separators=(",", ":"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
    total_counties = sum(len(rows) for rows in doc["states"].values())
    print(
        f"Wrote {args.output} ({len(text) / 1024:.1f} KB, {total_counties} counties across {len(doc['states'])} states).",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
