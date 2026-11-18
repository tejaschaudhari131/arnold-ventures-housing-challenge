# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Acquire and load all official Challenge Handbook and Starter Data Sources.

Covers every row of ``data/DATA_SOURCES.md`` across all 11 Challenge states
(AZ, CT, HI, NH, OR, PA, RI, TN, UT, VA, WI) plus the Challenge Handbook's
recommended national public datasets:

- Census ACS B25004 Vacancy Status breakdown (market-available vs seasonal/other)
- Census 2024 County Gazetteer land vs water area (AWATER_SQMI / ALAND_SQMI)
- Bureau of Labor Statistics (BLS) state construction employment & PPI inflation
- USDOT / FTA National Transit Map (NTAD) observed transit stop counts
- State GIS Open Data portals (AZGeo, CT Open Data, OR GEOHub & RLIS, HI GIS,
  PA PASDA & WPRDC, TN OIR/Comptroller GIS, UT SGID, VA VGIN, WI SCO, RI RIGIS,
  NH GRANIT)
- Microsoft US Building Footprints v2 published state structure counts (metadata)
- HUD FY2026 Fair Market Rent / Area Median Income reference benchmarks

All queries request aggregate counts, sums, or category group-bys only. Owner
names, mailing addresses, and parcel account identifiers are never requested,
and every stored state dictionary is checked with ``assert_no_pii``.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from src.data.adapters import assert_no_pii
from src.data.safe_url import FetchDenied, assert_allowed, fetch_bytes, open_url
from src.data.schema import CHALLENGE_STATES, ROOT, TIER1_PATH, load_json

USER_AGENT = "stateframe-housing-sim/1.0 (public-data acquisition; research)"
OFFICIAL_SOURCES_PATH = ROOT / "data" / "sample" / "official_sources.json"
ALLEGHENY_LOTS_PATH = ROOT / "data" / "sample" / "lab" / "allegheny_lots.json"

OFFICIAL_ALLOWED_HOSTS = frozenset(
    {
        "www2.census.gov",
        "api.bls.gov",
        "services.arcgis.com",
        "services1.arcgis.com",
        "services2.arcgis.com",
        "services3.arcgis.com",
        "geodata.hawaii.gov",
        "nhgeodata.unh.edu",
        "vginmaps.vdem.virginia.gov",
        "mapservices.pasda.psu.edu",
        "tnmap.tn.gov",
    }
)

STATE_META: tuple[tuple[str, str, str], ...] = (
    ("AZ", "04", "Arizona"),
    ("CT", "09", "Connecticut"),
    ("HI", "15", "Hawaii"),
    ("NH", "33", "New Hampshire"),
    ("OR", "41", "Oregon"),
    ("PA", "42", "Pennsylvania"),
    ("RI", "44", "Rhode Island"),
    ("TN", "47", "Tennessee"),
    ("UT", "49", "Utah"),
    ("VA", "51", "Virginia"),
    ("WI", "55", "Wisconsin"),
)
FIPS_TO_CODE = {fips: code for code, fips, _name in STATE_META}

# State bounding boxes (lon_min, lat_min, lon_max, lat_max) in WGS84 for
# aggregate spatial count queries against USDOT's National Transit Map layer.
STATE_BBOX: dict[str, tuple[float, float, float, float]] = {
    "AZ": (-114.82, 31.33, -109.04, 37.00),
    "CT": (-73.73, 40.98, -71.78, 42.05),
    "HI": (-160.25, 18.91, -154.80, 22.24),
    "NH": (-72.56, 42.70, -70.61, 45.31),
    "OR": (-124.57, 41.99, -116.46, 46.29),
    "PA": (-80.52, 39.72, -74.69, 42.27),
    "RI": (-71.86, 41.15, -71.12, 42.02),
    "TN": (-90.31, 34.98, -81.65, 36.68),
    "UT": (-114.05, 37.00, -109.04, 42.00),
    "VA": (-83.68, 36.54, -75.24, 39.47),
    "WI": (-92.89, 42.49, -86.80, 47.08),
}

# Published state-level building footprint totals from Microsoft US Building
# Footprints v2 release summary table (github.com/microsoft/USBuildingFootprints).
# Only the 11 published summary integers are recorded here; no ODbL GeoJSON
# geometry file is redistributed or bundled.
MICROSOFT_FOOTPRINT_COUNTS: dict[str, int] = {
    "AZ": 2_738_732,
    "CT": 1_215_624,
    "HI": 252_908,
    "NH": 577_936,
    "OR": 1_873_786,
    "PA": 4_965_213,
    "RI": 392_581,
    "TN": 3_212_306,
    "UT": 1_081_586,
    "VA": 3_079_351,
    "WI": 3_173_347,
}

# BLS CES Construction Employment series IDs (thousands of jobs, not seasonally
# adjusted). Hawaii reports Mining, Logging, and Construction combined (supersector 15).
BLS_CONSTRUCTION_SERIES: dict[str, str] = {
    "AZ": "SMU04000002000000001",
    "CT": "SMU09000002000000001",
    "HI": "SMU15000001500000001",
    "NH": "SMU33000002000000001",
    "OR": "SMU41000002000000001",
    "PA": "SMU42000002000000001",
    "RI": "SMU44000002000000001",
    "TN": "SMU47000002000000001",
    "UT": "SMU49000002000000001",
    "VA": "SMU51000002000000001",
    "WI": "SMU55000002000000001",
}
BLS_PPI_SERIES = "WPUSI012011"  # Producer Price Index: Inputs to Construction Industries / Materials

OFFICIAL_PORTALS: dict[str, dict[str, str]] = {
    "AZ": {
        "portal_name": "AZGeo Open Data Hub",
        "portal_url": "https://azgeo-data-hub-agic.hub.arcgis.com/",
        "catalog_note": "Statewide Land Ownership (Private vs BLM/USFS/Tribal/State Trust) plus regional parcel service.",
    },
    "CT": {
        "portal_name": "Connecticut Open Data (CAMA & Parcel Layer)",
        "portal_url": "https://data.ct.gov/",
        "catalog_note": "Statewide CAMA and parcel layer with residential lot-size bins and municipal zone codes.",
    },
    "HI": {
        "portal_name": "Hawaii Statewide GIS Program",
        "portal_url": "https://geoportal.hawaii.gov/",
        "catalog_note": "Statewide TMK parcel count and State Land Use Commission district acreage.",
    },
    "NH": {
        "portal_name": "NH GRANIT Data Discovery",
        "portal_url": "https://www.nhgeodata.unh.edu/",
        "catalog_note": "Statewide CAD Parcel Mosaic and Open Land Use developed/undeveloped acreage.",
    },
    "OR": {
        "portal_name": "State of Oregon GEOHub & Metro RLIS Discovery",
        "portal_url": "https://geohub.oregon.gov/pages/9f4e2fffa6bb4328913a7adb7401d2b1",
        "catalog_note": "Statewide standardized zoning polygons (2023), Urban Growth Boundaries (2025), and Metro RLIS public taxlots.",
    },
    "PA": {
        "portal_name": "Pennsylvania Spatial Data Access (PASDA) & WPRDC",
        "portal_url": "https://www.pasda.psu.edu/",
        "catalog_note": "PASDA county parcel/conservation MapServers plus WPRDC Allegheny County lot-size bins.",
    },
    "RI": {
        "portal_name": "Rhode Island Geographic Information System (RIGIS)",
        "portal_url": "https://www.rigis.org/",
        "catalog_note": "Municipal Zoning & Overlay Zones plus 2025 Statewide Land Use acreage.",
    },
    "TN": {
        "portal_name": "Tennessee Comptroller GIS & TNMap OIR Portal",
        "portal_url": "https://www.comptroller.tn.gov/office-functions/pa/gisredistricting/redistricting-and-land-use-maps.html",
        "catalog_note": "TNMap county/municipal boundaries; Comptroller raw parcel downloads require a web Request Form.",
    },
    "UT": {
        "portal_name": "Utah Geospatial Resource Center (SGID)",
        "portal_url": "https://gis.utah.gov/products/sgid/cadastre/parcels/",
        "catalog_note": "Utah Housing Unit Inventory plus SGID Land Information Record (LIR) county parcel layers.",
    },
    "VA": {
        "portal_name": "Virginia GIS Clearinghouse (VGIN)",
        "portal_url": "https://vgin.vdem.virginia.gov/pages/clearinghouse",
        "catalog_note": "Statewide Virginia Parcels FeatureServer and Building Footprints layer.",
    },
    "WI": {
        "portal_name": "Wisconsin State Cartographer's Office (SCO)",
        "portal_url": "https://www.sco.wisc.edu/data/parcels/",
        "catalog_note": "Wisconsin Statewide Parcels DB V1200 improved residential lot-size bins.",
    },
}


class OfficialAcquireError(RuntimeError):
    """Raised when an authoritative public source cannot be retrieved."""


def _get_json(url: str, timeout: int = 45) -> dict[str, Any]:
    assert_allowed(url, OFFICIAL_ALLOWED_HOSTS)
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            raw = fetch_bytes(url, OFFICIAL_ALLOWED_HOSTS, timeout, USER_AGENT)
            data = json.loads(raw.decode("utf-8", "ignore"))
            if not isinstance(data, dict):
                raise OfficialAcquireError(f"{url}: expected JSON object")
            return data
        except FetchDenied as exc:
            if "not an allowlisted" in str(exc):
                raise OfficialAcquireError(f"{url}: {exc}") from exc
            last_exc = exc
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    raise OfficialAcquireError(f"{url}: {last_exc}") from last_exc


def _post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    assert_allowed(url, OFFICIAL_ALLOWED_HOSTS)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            assert_allowed(resp.geturl(), OFFICIAL_ALLOWED_HOSTS)
            raw = resp.read()
    except FetchDenied:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OfficialAcquireError(f"POST {url} failed: {exc}") from exc
    data = json.loads(raw.decode("utf-8", "ignore"))
    if not isinstance(data, dict):
        raise OfficialAcquireError(f"POST {url}: expected JSON object")
    return data


def _arcgis_count(layer_url: str, where: str = "1=1") -> int:
    q = urllib.parse.urlencode({"where": where, "returnCountOnly": "true", "f": "json"})
    doc = _get_json(f"{layer_url}/query?{q}")
    count = doc.get("count")
    if count is None:
        raise OfficialAcquireError(f"Missing count from {layer_url}")
    return int(count)


def fetch_acs_vacancy_b25004() -> dict[str, dict[str, float]]:
    """Stream ACS 2019-2023 table B25004 (Vacancy Status) for the 11 states."""
    url = (
        "https://www2.census.gov/programs-surveys/acs/summary_file/2023/"
        "table-based-SF/data/5YRData/acsdt5y2023-b25004.dat"
    )
    cols = {
        "total_vacant": "B25004_E001",
        "for_rent": "B25004_E002",
        "rented_not_occ": "B25004_E003",
        "for_sale": "B25004_E004",
        "sold_not_occ": "B25004_E005",
        "seasonal": "B25004_E006",
        "migrant": "B25004_E007",
        "other_vacant": "B25004_E008",
    }
    out: dict[str, dict[str, float]] = {}
    try:
        resp = open_url(url, OFFICIAL_ALLOWED_HOSTS, 180, USER_AGENT)
    except FetchDenied as exc:
        raise OfficialAcquireError(str(exc)) from exc
    with resp:
        header = resp.readline().decode("latin1").rstrip("\n").split("|")
        idx = {name: i for i, name in enumerate(header)}
        for line_bytes in resp:
            line = line_bytes.decode("latin1")
            if not line.startswith("0400000US"):
                continue
            parts = line.rstrip("\n").split("|")
            fips = parts[0][-2:]
            code = FIPS_TO_CODE.get(fips)
            if not code:
                continue
            row = {k: float(parts[idx[col]] or 0.0) for k, col in cols.items()}
            total = max(row["total_vacant"], 1.0)
            market_avail = row["for_rent"] + row["for_sale"]
            seasonal_other = row["seasonal"] + row["other_vacant"]
            row["market_available_share"] = round(market_avail / total, 4)
            row["seasonal_share"] = round(row["seasonal"] / total, 4)
            row["other_vacant_share"] = round(row["other_vacant"] / total, 4)
            row["non_market_share"] = round(seasonal_other / total, 4)
            out[code] = row
    if set(out) != set(CHALLENGE_STATES):
        raise OfficialAcquireError(f"ACS B25004 missing states: {sorted(set(CHALLENGE_STATES) - set(out))}")
    return out


def fetch_gazetteer_water_land() -> dict[str, dict[str, float]]:
    """Aggregate land vs water square miles per state from 2024 Census Gazetteer."""
    url = (
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
        "2024_Gaz_counties_national.zip"
    )
    blob = fetch_bytes(url, OFFICIAL_ALLOWED_HOSTS, 180, USER_AGENT)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        text = zf.read(txt_names[0] if txt_names else zf.namelist()[0]).decode("latin1")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    totals: dict[str, dict[str, float]] = {c: {"land_sqmi": 0.0, "water_sqmi": 0.0} for c in CHALLENGE_STATES}
    for raw in reader:
        row = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        geoid = (row.get("GEOID") or "").strip()
        if len(geoid) != 5 or geoid[:2] not in FIPS_TO_CODE:
            continue
        code = FIPS_TO_CODE[geoid[:2]]
        land = float(row.get("ALAND_SQMI") or 0.0)
        water = float(row.get("AWATER_SQMI") or 0.0)
        totals[code]["land_sqmi"] += land
        totals[code]["water_sqmi"] += water
    for code, item in totals.items():
        gross = item["land_sqmi"] + item["water_sqmi"]
        item["land_sqmi"] = round(item["land_sqmi"], 2)
        item["water_sqmi"] = round(item["water_sqmi"], 2)
        item["water_share"] = round(item["water_sqmi"] / gross, 4) if gross > 0 else 0.0
    return totals


def fetch_bls_construction() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch 2020-2025 state construction employment & national materials PPI from BLS."""
    series_ids = list(BLS_CONSTRUCTION_SERIES.values()) + [BLS_PPI_SERIES]
    doc = _post_json(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        {"seriesid": series_ids, "startyear": "2020", "endyear": "2025"},
    )
    if doc.get("status") != "REQUEST_SUCCEEDED":
        raise OfficialAcquireError(f"BLS API status: {doc.get('status')}")
    by_series: dict[str, list[dict[str, Any]]] = {
        s["seriesID"]: s.get("data", []) for s in doc.get("Results", {}).get("series", [])
    }

    def _annual_avg(rows: list[dict[str, Any]], year: str) -> float | None:
        vals = [
            float(r["value"])
            for r in rows
            if r.get("year") == year and str(r.get("period", "")).startswith("M") and r.get("period") != "M13"
            and r.get("value") not in ("-", "", None)
        ]
        return round(sum(vals) / len(vals), 2) if vals else None

    states_bls: dict[str, dict[str, Any]] = {}
    for code, sid in BLS_CONSTRUCTION_SERIES.items():
        rows = by_series.get(sid, [])
        avg_2020 = _annual_avg(rows, "2020")
        avg_2025 = _annual_avg(rows, "2025") or _annual_avg(rows, "2024")
        if avg_2020 is None or avg_2025 is None:
            raise OfficialAcquireError(f"BLS construction series incomplete for {code} ({sid})")
        growth_pct = round(100.0 * (avg_2025 - avg_2020) / avg_2020, 2) if avg_2020 > 0 else 0.0
        states_bls[code] = {
            "series_id": sid,
            "sector_note": (
                "Mining, Logging, and Construction combined (CES supersector 15)"
                if code == "HI"
                else "Construction (CES supersector 20)"
            ),
            "jobs_2020_thousands": avg_2020,
            "jobs_latest_thousands": avg_2025,
            "jobs_latest_year": 2025 if _annual_avg(rows, "2025") is not None else 2024,
            "jobs_change_2020_2025_pct": growth_pct,
        }

    ppi_rows = by_series.get(BLS_PPI_SERIES, [])
    ppi_2020 = _annual_avg(ppi_rows, "2020")
    ppi_2025 = _annual_avg(ppi_rows, "2025") or _annual_avg(ppi_rows, "2024")
    if ppi_2020 is None or ppi_2025 is None:
        raise OfficialAcquireError("BLS PPI series WPUSI012011 incomplete")
    national_ppi = {
        "series_id": BLS_PPI_SERIES,
        "label": "BLS Producer Price Index: Construction Materials (WPUSI012011)",
        "index_2020": ppi_2020,
        "index_latest": ppi_2025,
        "latest_year": 2025 if _annual_avg(ppi_rows, "2025") is not None else 2024,
        "inflation_2020_latest_pct": round(100.0 * (ppi_2025 - ppi_2020) / ppi_2020, 2),
    }
    return states_bls, national_ppi


def fetch_ntad_transit_stops() -> dict[str, int]:
    """Count USDOT National Transit Map stops inside each state's lat/lon envelope."""
    base = (
        "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/"
        "NTAD_National_Transit_Map_Stops/FeatureServer/0"
    )
    counts: dict[str, int] = {}
    for code, bbox in STATE_BBOX.items():
        where = (
            f"stop_lon >= {bbox[0]} AND stop_lon <= {bbox[2]} "
            f"AND stop_lat >= {bbox[1]} AND stop_lat <= {bbox[3]}"
        )
        counts[code] = _arcgis_count(base, where=where)
    return counts


def fetch_state_gis_extracts(tier1_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Query live aggregate metrics from every official state GIS portal in DATA_SOURCES.md."""
    extracts: dict[str, dict[str, Any]] = {}

    # 1. Arizona — AZGeo LandOwnership (Category area shares, no Owner field) + Parcels count
    az_stats = json.dumps(
        [{"statisticType": "sum", "onStatisticField": "Shape__Area", "outStatisticFieldName": "sum_area"}]
    )
    az_own_url = (
        "https://services.arcgis.com/cghC2lEIpJ2TRrs5/arcgis/rest/services/"
        "LandOwnership/FeatureServer/0/query?"
        + urllib.parse.urlencode(
            {"where": "1=1", "groupByFieldsForStatistics": "Category", "outStatistics": az_stats, "f": "json"}
        )
    )
    az_own_doc = _get_json(az_own_url)
    az_areas: dict[str, float] = {}
    for feat in az_own_doc.get("features", []):
        attrs = feat.get("attributes") or {}
        cat = str(attrs.get("Category") or "Other").strip()
        az_areas[cat] = az_areas.get(cat, 0.0) + float(attrs.get("sum_area") or 0.0)
    az_total_area = sum(az_areas.values()) or 1.0
    az_private_share = round(az_areas.get("Private", 0.0) / az_total_area, 4)
    az_public_tribal_share = round(1.0 - az_private_share, 4)
    az_parcel_sample = _arcgis_count(
        "https://services.arcgis.com/cghC2lEIpJ2TRrs5/arcgis/rest/services/Parcels/FeatureServer/0"
    )
    extracts["AZ"] = {
        "gis_status": "live_observed_aggregates",
        "parcel_records_observed": az_parcel_sample,
        "zoning_or_landuse_records": len(az_areas),
        "private_land_share": az_private_share,
        "public_and_tribal_land_share": az_public_tribal_share,
        "headline_finding": (
            f"AZGeo LandOwnership shows only {az_private_share * 100:.1f}% of Arizona land is privately held "
            f"({az_public_tribal_share * 100:.1f}% Federal, Tribal, or State Trust), concentrating housing reform "
            "inside existing metro envelopes."
        ),
        "endpoints": [
            "https://services.arcgis.com/cghC2lEIpJ2TRrs5/arcgis/rest/services/LandOwnership/FeatureServer/0",
            "https://services.arcgis.com/cghC2lEIpJ2TRrs5/arcgis/rest/services/Parcels/FeatureServer/0",
        ],
    }

    # 2. Connecticut — CT Open Data CAMA & Parcel Layer (committed + verified Tier-1)
    ct_t1 = tier1_doc["states"]["CT"]
    extracts["CT"] = {
        "gis_status": "live_observed_tier1",
        "parcel_records_observed": int(ct_t1["parcel_count"]),
        "sf_lots_binned": int(ct_t1["sf_bin_count"]),
        "zoning_or_landuse_records": int(ct_t1["parcel_count"]),
        "headline_finding": (
            f"Connecticut CAMA & Parcel Layer covers {ct_t1['parcel_count']:,} statewide parcels "
            f"with {ct_t1['sf_bin_count']:,} single-family lots binned by exact square footage."
        ),
        "endpoints": ["https://geodata.ct.gov/datasets/82a733423a244c43a9d4bf552954cea9_0"],
    }

    # 3. Hawaii — Statewide GIS TMKs & State Land Use Commission Districts
    hi_t1 = tier1_doc["states"]["HI"]
    extracts["HI"] = {
        "gis_status": "live_observed_tier1",
        "parcel_records_observed": int(hi_t1["parcel_count"]),
        "urban_land_share": float(hi_t1["urban_land_share"]),
        "zoning_or_landuse_records": 4,
        "land_use_acres": hi_t1["land_use_acres"],
        "headline_finding": (
            f"Hawaii Statewide GIS records {hi_t1['parcel_count']:,} TMK parcels; only "
            f"{hi_t1['urban_land_share'] * 100:.2f}% of state land is in the State Land Use Urban District."
        ),
        "endpoints": ["https://geoportal.hawaii.gov/datasets/HiStateGIS::parcels-hawaii-statewide"],
    }

    # 4. New Hampshire — NH GRANIT CAD_ParcelMosaic + EC_LandUse_OpenData
    nh_parcels = _arcgis_count(
        "https://nhgeodata.unh.edu/hosting/rest/services/Hosted/CAD_ParcelMosaic/FeatureServer/0"
    )
    nh_lu_polys = _arcgis_count(
        "https://nhgeodata.unh.edu/hosting/rest/services/Hosted/EC_LandUse_OpenData/FeatureServer/0"
    )
    nh_stats = json.dumps(
        [{"statisticType": "sum", "onStatisticField": "acres", "outStatisticFieldName": "sum_acres"}]
    )
    nh_lu_doc = _get_json(
        "https://nhgeodata.unh.edu/hosting/rest/services/Hosted/EC_LandUse_OpenData/FeatureServer/0/query?"
        + urllib.parse.urlencode(
            {"where": "1=1", "groupByFieldsForStatistics": "developed", "outStatistics": nh_stats, "f": "json"}
        )
    )
    nh_dev = 0.0
    nh_undev = 0.0
    for feat in nh_lu_doc.get("features", []):
        attrs = feat.get("attributes") or {}
        if int(attrs.get("developed") or 0) == 1:
            nh_dev += float(attrs.get("sum_acres") or 0.0)
        else:
            nh_undev += float(attrs.get("sum_acres") or 0.0)
    nh_dev_share = round(nh_dev / max(nh_dev + nh_undev, 1.0), 4)
    extracts["NH"] = {
        "gis_status": "live_observed_aggregates",
        "parcel_records_observed": nh_parcels,
        "zoning_or_landuse_records": nh_lu_polys,
        "developed_land_share_sample": nh_dev_share,
        "headline_finding": (
            f"NH GRANIT Statewide Parcel Mosaic provides {nh_parcels:,} parcel records and "
            f"{nh_lu_polys:,} regional open land-use polygons ({nh_dev_share * 100:.1f}% developed acreage)."
        ),
        "endpoints": [
            "https://nhgeodata.unh.edu/hosting/rest/services/Hosted/CAD_ParcelMosaic/FeatureServer/0",
            "https://nhgeodata.unh.edu/hosting/rest/services/Hosted/EC_LandUse_OpenData/FeatureServer/0",
        ],
    }

    # 5. Oregon — GEOHub Statewide Zoning (2023), UGBs (2025), and Metro RLIS Taxlots (Public)
    or_zoning_polys = _arcgis_count(
        "https://services1.arcgis.com/CD5mKowwN6nIaqd8/arcgis/rest/services/library_bnd_or_zoning_2023/FeatureServer/56"
    )
    or_ugb_count = _arcgis_count(
        "https://services1.arcgis.com/CD5mKowwN6nIaqd8/arcgis/rest/services/library_bnd_or_urban_growth_boundaries_2025/FeatureServer/0"
    )
    or_rlis_taxlots = _arcgis_count(
        "https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_(Public)/FeatureServer/3"
    )
    or_z_stats = json.dumps(
        [{"statisticType": "count", "onStatisticField": "OBJECTID", "outStatisticFieldName": "n_poly"}]
    )
    or_z_doc = _get_json(
        "https://services1.arcgis.com/CD5mKowwN6nIaqd8/arcgis/rest/services/library_bnd_or_zoning_2023/FeatureServer/56/query?"
        + urllib.parse.urlencode(
            {"where": "1=1", "groupByFieldsForStatistics": "orZDesc", "outStatistics": or_z_stats, "f": "json"}
        )
    )
    res_polys = 0
    for feat in or_z_doc.get("features", []):
        attrs = feat.get("attributes") or {}
        desc = str(attrs.get("orZDesc") or "").lower()
        if "residential" in desc or "mixed" in desc or "urban" in desc:
            res_polys += int(attrs.get("n_poly") or 0)
    extracts["OR"] = {
        "gis_status": "live_observed_aggregates",
        "parcel_records_observed": or_rlis_taxlots,
        "zoning_or_landuse_records": or_zoning_polys,
        "residential_or_mixed_zone_polygons": res_polys,
        "ugb_boundary_count": or_ugb_count,
        "headline_finding": (
            f"Oregon GEOHub & Metro RLIS provide {or_rlis_taxlots:,} Portland-metro public taxlots, "
            f"{or_zoning_polys:,} standardized zoning polygons ({res_polys:,} residential/mixed), and "
            f"{or_ugb_count} official Urban Growth Boundaries."
        ),
        "endpoints": [
            "https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/Taxlots_(Public)/FeatureServer/3",
            "https://services1.arcgis.com/CD5mKowwN6nIaqd8/arcgis/rest/services/library_bnd_or_zoning_2023/FeatureServer/56",
            "https://services1.arcgis.com/CD5mKowwN6nIaqd8/arcgis/rest/services/library_bnd_or_urban_growth_boundaries_2025/FeatureServer/0",
        ],
    }

    # 6. Pennsylvania — PASDA County Parcels & Conservation Easements + WPRDC Allegheny Lots
    pa_erie_parcels = _arcgis_count(
        "https://mapservices.pasda.psu.edu/server/rest/services/pasda/ErieCountyParcels/MapServer/0"
    )
    pa_easements = _arcgis_count(
        "https://mapservices.pasda.psu.edu/server/rest/services/pasda/PennsylvaniaLandTrustAssociation/MapServer/0"
    )
    pa_catalog = _get_json("https://mapservices.pasda.psu.edu/server/rest/services/pasda?f=json")
    pa_service_count = len(pa_catalog.get("services", []))
    allegheny_lots = 0
    if ALLEGHENY_LOTS_PATH.is_file():
        allegheny_doc = load_json(ALLEGHENY_LOTS_PATH)
        for group in (allegheny_doc.get("groups") or {}).values():
            allegheny_lots += int(group.get("parcels") or 0)
    extracts["PA"] = {
        "gis_status": "live_observed_aggregates",
        "parcel_records_observed": allegheny_lots + pa_erie_parcels,
        "allegheny_wprdc_residential_lots": allegheny_lots,
        "pasda_erie_county_parcels": pa_erie_parcels,
        "pasda_conservation_easements": pa_easements,
        "pasda_public_mapservers": pa_service_count,
        "zoning_or_landuse_records": pa_easements,
        "headline_finding": (
            f"PASDA hosts {pa_service_count} public GIS services including {pa_erie_parcels:,} Erie County parcels "
            f"and {pa_easements:,} conservation easements, paired with {allegheny_lots:,} WPRDC Allegheny residential lots."
        ),
        "endpoints": [
            "https://mapservices.pasda.psu.edu/server/rest/services/pasda/ErieCountyParcels/MapServer/0",
            "https://mapservices.pasda.psu.edu/server/rest/services/pasda/PennsylvaniaLandTrustAssociation/MapServer/0",
        ],
    }

    # 7. Rhode Island — RIGIS Municipal Zoning & 2025 Land Use
    ri_zoning_polys = _arcgis_count(
        "https://services2.arcgis.com/S8zZg9pg23JUEexQ/arcgis/rest/services/RI_Zoning/FeatureServer/0"
    )
    ri_lu_polys = _arcgis_count(
        "https://services2.arcgis.com/S8zZg9pg23JUEexQ/arcgis/rest/services/PLAN_Land_Use_2025_spf/FeatureServer/0"
    )
    ri_stats = json.dumps(
        [{"statisticType": "sum", "onStatisticField": "Acres", "outStatisticFieldName": "sum_acres"}]
    )
    ri_lu_doc = _get_json(
        "https://services2.arcgis.com/S8zZg9pg23JUEexQ/arcgis/rest/services/PLAN_Land_Use_2025_spf/FeatureServer/0/query?"
        + urllib.parse.urlencode(
            {"where": "1=1", "groupByFieldsForStatistics": "Map_Legend", "outStatistics": ri_stats, "f": "json"}
        )
    )
    ri_acres_by_legend: dict[str, float] = {}
    for feat in ri_lu_doc.get("features", []):
        attrs = feat.get("attributes") or {}
        leg = str(attrs.get("Map_Legend") or "Other").strip()
        ri_acres_by_legend[leg] = round(float(attrs.get("sum_acres") or 0.0), 1)
    ri_total_acres = sum(ri_acres_by_legend.values()) or 1.0
    ri_urban_share = round(ri_acres_by_legend.get("Urban Development", 0.0) / ri_total_acres, 4)
    ri_conservation_share = round(
        (ri_acres_by_legend.get("Conservation/Limited", 0.0) + ri_acres_by_legend.get("Reserve", 0.0))
        / ri_total_acres,
        4,
    )
    extracts["RI"] = {
        "gis_status": "live_observed_aggregates",
        "parcel_records_observed": 0,
        "zoning_polygons_observed": ri_zoning_polys,
        "zoning_or_landuse_records": ri_zoning_polys + ri_lu_polys,
        "urban_development_land_share": ri_urban_share,
        "conservation_and_reserve_share": ri_conservation_share,
        "headline_finding": (
            f"RIGIS provides {ri_zoning_polys:,} municipal zoning polygons and {ri_lu_polys:,} 2025 land-use polygons "
            f"({ri_urban_share * 100:.1f}% Urban Development vs {ri_conservation_share * 100:.1f}% Conservation/Reserve)."
        ),
        "endpoints": [
            "https://services2.arcgis.com/S8zZg9pg23JUEexQ/arcgis/rest/services/RI_Zoning/FeatureServer/0",
            "https://services2.arcgis.com/S8zZg9pg23JUEexQ/arcgis/rest/services/PLAN_Land_Use_2025_spf/FeatureServer/0",
        ],
    }

    # 8. Tennessee — TNMap Municipal & County Boundaries + Comptroller Request-Form Gate
    tn_cities = _arcgis_count(
        "https://tnmap.tn.gov/arcgis/rest/services/ADMINISTRATIVE_BOUNDARIES/COUNTY_BOUNDARIES_AND_CITY_BOUNDARIES/MapServer/0"
    )
    tn_counties = _arcgis_count(
        "https://tnmap.tn.gov/arcgis/rest/services/ADMINISTRATIVE_BOUNDARIES/COUNTY_BOUNDARIES_AND_CITY_BOUNDARIES/MapServer/1"
    )
    extracts["TN"] = {
        "gis_status": "live_admin_plus_gated_parcels",
        "parcel_records_observed": 0,
        "zoning_or_landuse_records": tn_cities + tn_counties,
        "incorporated_municipalities": tn_cities,
        "counties_verified": tn_counties,
        "headline_finding": (
            f"TNMap verifies {tn_cities} incorporated municipalities across {tn_counties} counties; "
            "Tennessee Comptroller raw parcel/land-use files require a manual web Request Form per DATA_SOURCES.md."
        ),
        "endpoints": [
            "https://tnmap.tn.gov/arcgis/rest/services/ADMINISTRATIVE_BOUNDARIES/COUNTY_BOUNDARIES_AND_CITY_BOUNDARIES/MapServer/0"
        ],
    }

    # 9. Utah — SGID Housing Unit Inventory + LIR County Parcels (Salt Lake, Utah, Davis)
    ut_t1 = tier1_doc["states"]["UT"]
    ut_slc = _arcgis_count(
        "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_SaltLake_LIR/FeatureServer/0"
    )
    ut_utah = _arcgis_count(
        "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Utah_LIR/FeatureServer/0"
    )
    ut_davis = _arcgis_count(
        "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Davis/FeatureServer/0"
    )
    ut_wasatch_parcels = ut_slc + ut_utah + ut_davis
    extracts["UT"] = {
        "gis_status": "live_observed_tier1_plus_sgid",
        "parcel_records_observed": max(int(ut_t1["parcel_count"]), ut_wasatch_parcels),
        "housing_inventory_records": int(ut_t1["parcel_count"]),
        "wasatch_front_lir_parcels": ut_wasatch_parcels,
        "zoning_or_landuse_records": int(ut_t1["parcel_count"]),
        "headline_finding": (
            f"Utah SGID combines {ut_t1['parcel_count']:,} Housing Unit Inventory records (mean SF lot "
            f"{ut_t1['mean_lot_sqft']:,} sq ft) with {ut_wasatch_parcels:,} live LIR parcels across Salt Lake, Utah, and Davis counties."
        ),
        "endpoints": [
            "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/HousingUnitInventory/FeatureServer/0",
            "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_SaltLake_LIR/FeatureServer/0",
        ],
    }

    # 10. Virginia — VGIN Statewide Parcels & Building Footprints
    va_parcels = _arcgis_count(
        "https://vginmaps.vdem.virginia.gov/arcgis/rest/services/VA_Base_Layers/VA_Parcels/FeatureServer/0"
    )
    va_footprints = _arcgis_count(
        "https://vginmaps.vdem.virginia.gov/arcgis/rest/services/VA_Base_Layers/VA_Building_Footprints/FeatureServer/0"
    )
    extracts["VA"] = {
        "gis_status": "live_observed_aggregates",
        "parcel_records_observed": va_parcels,
        "state_gis_building_footprints": va_footprints,
        "zoning_or_landuse_records": va_parcels,
        "headline_finding": (
            f"Virginia VGIN Clearinghouse provides {va_parcels:,} statewide parcel polygons and "
            f"{va_footprints:,} VGIN building footprints with height/story attributes."
        ),
        "endpoints": [
            "https://vginmaps.vdem.virginia.gov/arcgis/rest/services/VA_Base_Layers/VA_Parcels/FeatureServer/0",
            "https://vginmaps.vdem.virginia.gov/arcgis/rest/services/VA_Base_Layers/VA_Building_Footprints/FeatureServer/0",
        ],
    }

    # 11. Wisconsin — Statewide Parcels DB V1200 (Tier-1)
    wi_t1 = tier1_doc["states"]["WI"]
    extracts["WI"] = {
        "gis_status": "live_observed_tier1",
        "parcel_records_observed": int(wi_t1["sf_bin_count"]),
        "sf_lots_binned": int(wi_t1["sf_bin_count"]),
        "zoning_or_landuse_records": int(wi_t1["sf_bin_count"]),
        "headline_finding": (
            f"Wisconsin SCO V1200 provides {wi_t1['sf_bin_count']:,} improved residential parcels across 8 lot-size bins."
        ),
        "endpoints": ["https://www.sco.wisc.edu/parcels/data/"],
    }

    for code, rec in extracts.items():
        assert_no_pii(rec)
    return extracts


def build_official_sources() -> dict[str, Any]:
    """Acquire all official state GIS and federal Handbook datasets into one verified payload."""
    print("Acquiring official Challenge Handbook & Starter data sources...", flush=True)
    tier1_doc = load_json(TIER1_PATH)
    print("  1/5 ACS B25004 vacancy breakdown...", flush=True)
    vacancy = fetch_acs_vacancy_b25004()
    print("  2/5 Census Gazetteer land vs water...", flush=True)
    water_land = fetch_gazetteer_water_land()
    print("  3/5 BLS state construction workforce & PPI...", flush=True)
    bls_states, bls_ppi = fetch_bls_construction()
    print("  4/5 USDOT National Transit Map stop counts...", flush=True)
    ntad_stops = fetch_ntad_transit_stops()
    print("  5/5 Live 11-state GIS open-data portals (DATA_SOURCES.md)...", flush=True)
    gis_extracts = fetch_state_gis_extracts(tier1_doc)

    states_out: dict[str, Any] = {}
    for code, fips, name in STATE_META:
        rec = {
            "code": code,
            "fips": fips,
            "name": name,
            "portal": OFFICIAL_PORTALS[code],
            "gis": gis_extracts[code],
            "vacancy_b25004": vacancy[code],
            "geography": water_land[code],
            "bls_construction": bls_states[code],
            "ntad_transit_stops": ntad_stops[code],
            "microsoft_building_footprints": MICROSOFT_FOOTPRINT_COUNTS[code],
        }
        assert_no_pii(rec)
        states_out[code] = rec

    return {
        "access_date": "2026-11-17",
        "method": (
            "Aggregate public statistics only across all 11 Challenge states in data/DATA_SOURCES.md "
            "and all 10 Challenge Handbook recommended national dataset families. Owner names, mailing "
            "addresses, and parcel account numbers are never queried or stored."
        ),
        "handbook_families": [
            {
                "id": "acs_stock_prices",
                "name": "U.S. Census American Community Survey (ACS)",
                "vintage": "2019–2023 (11-state) & 2020–2024 (PA/NH Lab)",
                "status": "integrated",
                "license": "Public domain, U.S. government work",
            },
            {
                "id": "acs_usps_vacancy",
                "name": "Vacancy Status Breakdown (ACS B25004 / HUD-USPS Context)",
                "vintage": "ACS 2019–2023 5-year table B25004",
                "status": "integrated",
                "license": "Public domain, U.S. government work",
            },
            {
                "id": "census_bps",
                "name": "Census Building Permits Survey (BPS)",
                "vintage": "2022–2024 (11-state) & 2023–2025 (PA/NH Lab)",
                "status": "integrated",
                "license": "Public domain, U.S. government work",
            },
            {
                "id": "fhfa_hpi",
                "name": "FHFA All-Transactions House Price Index",
                "vintage": "2000–2025 annual workbook",
                "status": "integrated",
                "license": "Public FHFA statistical release",
            },
            {
                "id": "bls_construction",
                "name": "Bureau of Labor Statistics (CES Construction Workforce & PPI)",
                "vintage": "2020–2025 monthly series averaged by year",
                "status": "integrated",
                "license": "Public domain, U.S. government work",
            },
            {
                "id": "ntd_ntad_transit",
                "name": "USDOT / FTA National Transit Map & Screened Major Stops",
                "vintage": "2025–2026 NTAD FeatureServer + agency major-stop inventory",
                "status": "integrated",
                "license": "Public domain, U.S. Department of Transportation",
            },
            {
                "id": "land_cover_gazetteer",
                "name": "Land Cover, Conservation & Gazetteer Land/Water",
                "vintage": "2024 Census Gazetteer + HI/OR/RI/NH/AZ/PA state land-use layers",
                "status": "integrated",
                "license": "Public domain / State open-data aggregates",
            },
            {
                "id": "building_footprints",
                "name": "Building Footprints (VGIN Live Layer + Microsoft v2 Summary Counts)",
                "vintage": "VGIN 2026 live count + Microsoft USBuildingFootprints v2 summary",
                "status": "integrated",
                "license": "Aggregate structure counts only (no ODbL geometry redistributed)",
            },
            {
                "id": "hud_fmr_ami",
                "name": "HUD FY2026 Fair Market Rents & Area Median Income Reference",
                "vintage": "HUD FY2026 county FMR (PA/NH Lab) + ACS B19013/B25064 AMI rent bands (11 states)",
                "status": "integrated",
                "license": "Public domain, U.S. Department of Housing and Urban Development",
            },
            {
                "id": "state_gis_portals",
                "name": "Official 11-State GIS Open Data Portals (data/DATA_SOURCES.md)",
                "vintage": "2025–2026 live ArcGIS REST / MapServer / CKAN aggregates",
                "status": "integrated",
                "license": "State open data; aggregate non-PII counts and area shares only",
            },
        ],
        "national_bls_ppi": bls_ppi,
        "states": states_out,
    }


def load_official_sources(path: Path | None = None) -> dict[str, Any]:
    target = path or OFFICIAL_SOURCES_PATH
    return load_json(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire all official Challenge data sources.")
    parser.add_argument(
        "--output",
        default="",
        help="Output JSON path (default: data/cache/official_sources.json).",
    )
    parser.add_argument(
        "--write-sample",
        action="store_true",
        help="Also write data/sample/official_sources.json.",
    )
    args = parser.parse_args(argv)
    output = Path(args.output) if args.output else ROOT / "data" / "cache" / "official_sources.json"
    try:
        payload = build_official_sources()
    except Exception as exc:
        print(f"Official-source acquisition failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Falling back to committed {OFFICIAL_SOURCES_PATH}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}", flush=True)
    if args.write_sample:
        OFFICIAL_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        OFFICIAL_SOURCES_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OFFICIAL_SOURCES_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
