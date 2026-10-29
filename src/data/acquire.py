# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Acquire authoritative public inputs and fall back to the committed benchmark.

Run ``python -m src.data.acquire``. With a network, the script rebuilds a
fixture file from:

- Census ACS 2019–2023 5-year summary files (housing stock, structure, prices)
- Census Building Permits Survey annual state and county files, 2022–2024
- Census population estimates (growth) and county gazetteer (land area)
- FHFA All-Transactions state house-price index
- Aggregate tier-1 parcel statistics already screened into
  ``data/sample/tier1_benchmarks.json`` (live refresh is optional)

No API key is required. ``CENSUS_API_KEY`` is accepted and ignored by this
path because the summary files are public HTTPS downloads. Owner names and
mailing addresses are never requested.

If a download fails, the command leaves ``data/sample/fixtures.json`` in place
and exits with status 2. ``scripts/get_data.sh`` treats that as a graceful
fallback so a clean checkout still runs.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from src.data.adapters import adapt_state
from src.data.schema import ROOT, SAMPLE_FIXTURES, TIER1_PATH, load_json

USER_AGENT = "stateframe-housing-sim/1.0 (public-data acquisition; research)"
ALLOWED_HOSTS = frozenset(
    {
        "www2.census.gov",
        "www.fhfa.gov",
        "services3.arcgis.com",
        "services1.arcgis.com",
        "geodata.hawaii.gov",
    }
)

# code, fips, name. Tier is applied by the adapter from the challenge list.
STATE_META = (
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
TARGET_FIPS = set(FIPS_TO_CODE)

ACS_BASE = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/2023/"
    "table-based-SF/data/5YRData/"
)
BPS_STATE = "https://www2.census.gov/econ/bps/State/st{yymm}y.txt"
BPS_COUNTY = "https://www2.census.gov/econ/bps/County/co{yymm}y.txt"
PEP_URL = (
    "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/"
    "state/totals/NST-EST2024-ALLDATA.csv"
)
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
    "2024_Gaz_counties_national.zip"
)
FHFA_URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_state.csv"
BPS_YEARS = ("2022", "2023", "2024")

# ACS estimate columns. Margins of error are ignored on purpose: the model
# carries uncertainty in the assumption bands, not in a second sampling layer.
ACS_SPEC = {
    "b01003": {"population": "B01003_E001"},
    "b25001": {"housing_units": "B25001_E001"},
    "b25002": {"vacant": "B25002_E003"},
    "b25003": {"owner_occ": "B25003_E002", "renter_occ": "B25003_E003"},
    "b25024": {
        "sf_detached": "B25024_E002",
        "sf_attached": "B25024_E003",
        "two_unit": "B25024_E004",
        "three_four": "B25024_E005",
        "five_nine": "B25024_E006",
        "ten_nineteen": "B25024_E007",
        "twenty_forty": "B25024_E008",
        "fifty_plus": "B25024_E009",
        "mobile": "B25024_E010",
    },
    "b25034": {"year_total": "B25034_E001", "pre1940": "B25034_E011"},
    "b25064": {"median_rent": "B25064_E001"},
    "b25077": {"median_value": "B25077_E001"},
    "b19013": {"median_income": "B19013_E001"},
    # E010 is "Public transportation (excluding taxicab)" in the 2023 shell.
    # E005 is the 2-person carpool line and must not be used as transit.
    "b08301": {"workers": "B08301_E001", "transit": "B08301_E010"},
}


class AcquireError(RuntimeError):
    """A required public file could not be read."""


def _request(url: str, timeout: int = 180) -> urllib.request.Request:
    host = urllib.request.urlparse(url).hostname
    if host not in ALLOWED_HOSTS:
        raise AcquireError(f"Host is not on the acquisition allowlist: {host}")
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def fetch_bytes(url: str, timeout: int = 180) -> bytes:
    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise AcquireError(f"Failed to fetch {url}: {exc}") from exc


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("latin1")


def _to_float(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = text.strip()
    if cleaned in {"", ".", "-", "null", "None"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _blank_geo() -> dict[str, Any]:
    return {}


def stream_acs_table(table: str, columns: dict[str, str]) -> dict[str, dict[str, float | None]]:
    """Stream one ACS table and keep state and county rows for the 11 states."""
    url = ACS_BASE + f"acsdt5y2023-{table}.dat"
    print(f"  ACS {table}", flush=True)
    request = _request(url)
    try:
        response = urllib.request.urlopen(request, timeout=240)
    except urllib.error.URLError as exc:
        raise AcquireError(f"Failed to fetch {url}: {exc}") from exc
    kept: dict[str, dict[str, float | None]] = {}
    with response:
        header_line = response.readline().decode("latin1").rstrip("\n")
        header = header_line.split("|")
        index = {name: pos for pos, name in enumerate(header)}
        missing = [col for col in columns.values() if col not in index]
        if missing:
            raise AcquireError(f"{table} missing columns {missing}")
        wanted = {index[col]: key for key, col in columns.items()}
        for raw_line in response:
            line = raw_line.decode("latin1")
            geo = line.split("|", 1)[0]
            if geo.startswith("0400000US"):
                fips = geo[-2:]
                if fips not in TARGET_FIPS:
                    continue
                key = fips
            elif geo.startswith("0500000US"):
                fips5 = geo[-5:]
                if fips5[:2] not in TARGET_FIPS:
                    continue
                key = fips5
            else:
                continue
            parts = line.rstrip("\n").split("|")
            row = kept.setdefault(key, {})
            for pos, field in wanted.items():
                row[field] = _to_float(parts[pos] if pos < len(parts) else None)
    return kept


def load_acs() -> dict[str, dict[str, float | None]]:
    merged: dict[str, dict[str, float | None]] = defaultdict(_blank_geo)
    for table, columns in ACS_SPEC.items():
        rows = stream_acs_table(table, columns)
        for key, values in rows.items():
            merged[key].update(values)
    return merged


def _bps_units(parts: list[str], unit_index: int, value_index: int, scale: float) -> tuple[float, float]:
    units = _to_float(parts[unit_index]) or 0.0
    value = (_to_float(parts[value_index]) or 0.0) * scale
    return units, value


def parse_bps_file(text: str, kind: str) -> dict[str, dict[str, float]]:
    """Parse one annual BPS file. State values are published in thousands of dollars."""
    scale = 1000.0 if kind == "state" else 1.0
    rows: dict[str, dict[str, float]] = {}
    reader = csv.reader(io.StringIO(text))
    for parts in reader:
        if not parts or not parts[0].isdigit() or len(parts[0]) != 6:
            continue
        if kind == "state":
            fips = parts[1].zfill(2)
            if fips == "00":
                continue
            key = fips
            sf_u, sf_v = _bps_units(parts, 6, 7, scale)
            two_u, two_v = _bps_units(parts, 9, 10, scale)
            tf_u, tf_v = _bps_units(parts, 12, 13, scale)
            mf_u, mf_v = _bps_units(parts, 15, 16, scale)
        else:
            state_fips = parts[1].zfill(2)
            if state_fips not in TARGET_FIPS:
                continue
            key = state_fips + parts[2].zfill(3)
            sf_u, sf_v = _bps_units(parts, 7, 8, scale)
            two_u, two_v = _bps_units(parts, 10, 11, scale)
            tf_u, tf_v = _bps_units(parts, 13, 14, scale)
            mf_u, mf_v = _bps_units(parts, 16, 17, scale)
        rows[key] = {
            "sf_u": sf_u,
            "sf_v": sf_v,
            "two_u": two_u,
            "two_v": two_v,
            "tf_u": tf_u,
            "tf_v": tf_v,
            "mf_u": mf_u,
            "mf_v": mf_v,
        }
    return rows


def average_bps(frames: list[dict[str, dict[str, float]]]) -> dict[str, dict[str, float]]:
    keys: set[str] = set()
    for frame in frames:
        keys.update(frame)
    averaged: dict[str, dict[str, float]] = {}
    fields = ("sf_u", "sf_v", "two_u", "two_v", "tf_u", "tf_v", "mf_u", "mf_v")
    for key in keys:
        present = [frame[key] for frame in frames if key in frame]
        if not present:
            continue
        averaged[key] = {
            field: sum(item[field] for item in present) / len(frames) for field in fields
        }
    return averaged


def load_bps() -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    state_frames = []
    county_frames = []
    for year in BPS_YEARS:
        yymm = year[2:] + "12"
        print(f"  BPS {year}", flush=True)
        state_frames.append(parse_bps_file(fetch_text(BPS_STATE.format(yymm=yymm)), "state"))
        county_frames.append(parse_bps_file(fetch_text(BPS_COUNTY.format(yymm=yymm)), "county"))
    return average_bps(state_frames), average_bps(county_frames)


def national_unit_value(state_bps: dict[str, dict[str, float]], units_key: str, value_key: str) -> float:
    units = sum(row[units_key] for row in state_bps.values())
    value = sum(row[value_key] for row in state_bps.values())
    if units <= 0:
        raise AcquireError(f"National permit value for {units_key} is empty")
    return value / units


def shrink_index(raw_index: float, units: float) -> float:
    """Thin permit cells are pulled toward 1 so a handful of projects cannot set the index."""
    weight = max(0.0, min(1.0, units / 800.0))
    index = weight * raw_index + (1.0 - weight)
    return max(0.55, min(index, 2.40))


def load_growth() -> dict[str, float]:
    print("  population estimates", flush=True)
    text = fetch_text(PEP_URL)
    reader = csv.DictReader(io.StringIO(text))
    growth: dict[str, float] = {}
    for row in reader:
        fips = (row.get("STATE") or "").zfill(2)
        if fips not in TARGET_FIPS:
            continue
        pop_2020 = _to_float(row.get("POPESTIMATE2020"))
        pop_2024 = _to_float(row.get("POPESTIMATE2024"))
        if not pop_2020 or not pop_2024 or pop_2020 <= 0:
            continue
        growth[fips] = (pop_2024 / pop_2020) ** 0.25 - 1.0
    if len(growth) != len(TARGET_FIPS):
        raise AcquireError(f"Population growth missing for {sorted(TARGET_FIPS - set(growth))}")
    return growth


def load_land() -> dict[str, float]:
    print("  gazetteer", flush=True)
    blob = fetch_bytes(GAZETTEER_URL)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        name = archive.namelist()[0]
        text = archive.read(name).decode("latin1")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    land: dict[str, float] = {}
    for row in reader:
        geoid = (row.get("GEOID") or "").strip()
        if len(geoid) != 5 or geoid[:2] not in TARGET_FIPS:
            continue
        sqmi = _to_float(row.get("ALAND_SQMI"))
        if sqmi is None:
            aland = _to_float(row.get("ALAND")) or 0.0
            sqmi = aland / 2_589_988.11
        land[geoid] = sqmi
    return land


def _column_index(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - 64)
    return index - 1


def load_fhfa() -> dict[str, dict[str, float]]:
    """Parse the FHFA workbook. The published URL ends in .csv but the body is xlsx."""
    print("  FHFA HPI", flush=True)
    blob = fetch_bytes(FHFA_URL)
    if not blob.startswith(b"PK"):
        raise AcquireError("FHFA file was not an xlsx workbook")
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = []
        for item in shared_root.findall("m:si", namespace):
            strings.append("".join(node.text or "" for node in item.findall(".//m:t", namespace)))
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    by_state: dict[str, dict[int, float]] = defaultdict(dict)
    for row in sheet.findall("m:sheetData/m:row", namespace):
        values: dict[int, str] = {}
        for cell in row.findall("m:c", namespace):
            ref = cell.get("r") or "A1"
            node = cell.find("m:v", namespace)
            if node is None or node.text is None:
                continue
            text = strings[int(node.text)] if cell.get("t") == "s" else node.text
            values[_column_index(ref)] = text
        abbrev = values.get(1, "")
        if abbrev not in {code for code, _fips, _name in STATE_META}:
            continue
        year = _to_float(values.get(3))
        index = _to_float(values.get(7))
        if year is None or index is None:
            continue
        by_state[abbrev][int(year)] = index
    parsed: dict[str, dict[str, float]] = {}
    for code, _fips, _name in STATE_META:
        series = by_state.get(code) or {}
        if 2020 not in series or not series:
            raise AcquireError(f"FHFA series missing for {code}")
        latest_year = max(series)
        parsed[code] = {
            "hpi_2020": series[2020],
            "hpi_latest": series[latest_year],
            "latest_year": float(latest_year),
        }
    return parsed


def _share(part: float | None, whole: float | None) -> float:
    if not part or not whole or whole <= 0:
        return 0.0
    return max(0.0, part / whole)


def reconcile_segment(
    counties: list[dict[str, Any]],
    field: str,
    state_total: float,
    weight_field: str,
) -> None:
    """Make county permits add up to the state Building Permits Survey total.

    Counties that reported keep their counts when the state total is larger.
    The gap is spread across non-reporting counties in proportion to housing
    units. If reporting counties already exceed the state total, they are
    scaled down together.
    """
    reporting = [county for county in counties if county["bps_reporting"]]
    silent = [county for county in counties if not county["bps_reporting"]]
    reported = sum(county[field] for county in reporting)
    if state_total <= 0:
        for county in counties:
            county[field] = 0.0
        return
    if reported <= 0:
        weight = sum(max(county[weight_field], 0.0) for county in counties) or 1.0
        for county in counties:
            county[field] = state_total * max(county[weight_field], 0.0) / weight
        return
    if reported > state_total:
        scale = state_total / reported
        for county in reporting:
            county[field] *= scale
        for county in silent:
            county[field] = 0.0
        return
    residual = state_total - reported
    weight = sum(max(county[weight_field], 0.0) for county in silent)
    if weight <= 0 or not silent:
        scale = state_total / reported
        for county in reporting:
            county[field] *= scale
        return
    for county in silent:
        county[field] = residual * max(county[weight_field], 0.0) / weight


def build_states() -> tuple[dict[str, Any], dict[str, float]]:
    print("Downloading public sources...", flush=True)
    acs = load_acs()
    state_bps, county_bps = load_bps()
    growth = load_growth()
    land = load_land()
    fhfa = load_fhfa()
    tier1_doc = load_json(TIER1_PATH)
    national_sf = national_unit_value(state_bps, "sf_u", "sf_v")
    national_mf = national_unit_value(state_bps, "mf_u", "mf_v")
    print(f"  national SF permit value ${national_sf:,.0f}; MF ${national_mf:,.0f}", flush=True)

    states: dict[str, Any] = {}
    for code, fips, name in STATE_META:
        state_row = acs.get(fips) or {}
        if not state_row.get("housing_units"):
            raise AcquireError(f"ACS state row missing for {code}")
        county_ids = sorted(key for key in land if key.startswith(fips) and len(key) == 5)
        if not county_ids:
            raise AcquireError(f"No gazetteer counties for {code}")
        counties = []
        for county_fips in county_ids:
            row = acs.get(county_fips) or {}
            if not row.get("housing_units"):
                # County equivalents with no ACS housing row are skipped.
                continue
            five_plus = sum(row.get(key) or 0.0 for key in ("five_nine", "ten_nineteen", "twenty_forty", "fifty_plus"))
            permits = county_bps.get(county_fips)
            pre1940 = _share(row.get("pre1940"), row.get("year_total"))
            transit = _share(row.get("transit"), row.get("workers"))
            counties.append(
                {
                    "fips": county_fips,
                    "name": _county_name(county_fips, land),
                    "land_sqmi": land[county_fips],
                    "population": row.get("population") or 0.0,
                    "housing_units": row.get("housing_units") or 0.0,
                    "vacant": row.get("vacant") or 0.0,
                    "owner_occ": row.get("owner_occ") or 0.0,
                    "renter_occ": row.get("renter_occ") or 0.0,
                    "sf_detached": row.get("sf_detached") or 0.0,
                    "sf_attached": row.get("sf_attached") or 0.0,
                    "two_unit": row.get("two_unit") or 0.0,
                    "three_four": row.get("three_four") or 0.0,
                    "five_plus": five_plus,
                    "mobile": row.get("mobile") or 0.0,
                    "median_value": row.get("median_value"),
                    "median_rent": row.get("median_rent"),
                    "median_income": row.get("median_income"),
                    "pre1940_share": pre1940,
                    "transit_commute_share": transit,
                    "bps_sf": (permits or {}).get("sf_u", 0.0),
                    "bps_two": (permits or {}).get("two_u", 0.0),
                    "bps_three_four": (permits or {}).get("tf_u", 0.0),
                    "bps_five_plus": (permits or {}).get("mf_u", 0.0),
                    "bps_reporting": permits is not None,
                }
            )
        bps = state_bps.get(fips)
        if not bps:
            raise AcquireError(f"State BPS missing for {code}")
        for field, total, weight in (
            ("bps_sf", bps["sf_u"], "sf_detached"),
            ("bps_two", bps["two_u"], "two_unit"),
            ("bps_three_four", bps["tf_u"], "three_four"),
            ("bps_five_plus", bps["mf_u"], "five_plus"),
        ):
            reconcile_segment(counties, field, total, weight)
        five_plus_state = sum(state_row.get(key) or 0.0 for key in ("five_nine", "ten_nineteen", "twenty_forty", "fifty_plus"))
        sf_units = bps["sf_u"]
        mf_units = bps["mf_u"]
        sf_index = shrink_index((bps["sf_v"] / sf_units) / national_sf if sf_units else 1.0, sf_units)
        mf_index = shrink_index((bps["mf_v"] / mf_units) / national_mf if mf_units else sf_index, mf_units or sf_units)
        raw = {
            "code": code,
            "fips": fips,
            "name": name,
            "population": state_row.get("population") or 0.0,
            "pop_growth_annual": growth[fips],
            "housing_units": state_row.get("housing_units") or 0.0,
            "vacant": state_row.get("vacant") or 0.0,
            "owner_occ": state_row.get("owner_occ") or 0.0,
            "renter_occ": state_row.get("renter_occ") or 0.0,
            "sf_detached": state_row.get("sf_detached") or 0.0,
            "sf_attached": state_row.get("sf_attached") or 0.0,
            "two_unit": state_row.get("two_unit") or 0.0,
            "three_four": state_row.get("three_four") or 0.0,
            "five_plus": five_plus_state,
            "mobile": state_row.get("mobile") or 0.0,
            "median_value": state_row.get("median_value") or 0.0,
            "median_rent": state_row.get("median_rent") or 0.0,
            "median_income": state_row.get("median_income") or 0.0,
            "pre1940_share": _share(state_row.get("pre1940"), state_row.get("year_total")),
            "transit_commute_share": _share(state_row.get("transit"), state_row.get("workers")),
            "land_sqmi": sum(county["land_sqmi"] for county in counties),
            "bps_sf": bps["sf_u"],
            "bps_two": bps["two_u"],
            "bps_three_four": bps["tf_u"],
            "bps_five_plus": bps["mf_u"],
            "cost_index_sf": sf_index,
            "cost_index_mf": mf_index,
            "fhfa_hpi_2020": fhfa[code]["hpi_2020"],
            "fhfa_hpi_latest": fhfa[code]["hpi_latest"],
            "fhfa_latest_year": int(fhfa[code]["latest_year"]),
            "counties": counties,
        }
        # Transit commute share sanity: Pennsylvania should be a few percent, not half.
        if code == "PA":
            share = raw["transit_commute_share"]
            if not 0.025 <= share <= 0.055:
                raise AcquireError(
                    f"Pennsylvania transit-commute share {share:.3f} is outside the expected "
                    "ACS range. B08301_E010 may not be the public-transit column in this vintage."
                )
        tier1 = tier1_doc["states"].get(code)
        states[code] = adapt_state(raw, tier1)
        print(
            f"  {code}: units {raw['housing_units']:,.0f}, "
            f"BPS SF {raw['bps_sf']:,.0f}, counties {len(counties)}, "
            f"completeness {states[code]['completeness']}",
            flush=True,
        )
    return states, {"sf_permit_value": national_sf, "mf_permit_value": national_mf}


def _county_name(fips: str, land: dict[str, float]) -> str:
    # Gazetteer names are joined later if present on the land map via a side channel.
    names = getattr(load_land, "_names", {})
    return names.get(fips, f"County {fips}")


def load_land_with_names() -> dict[str, float]:
    """Wrapper that also stashes names for ``_county_name`` without a second download."""
    print("  gazetteer", flush=True)
    blob = fetch_bytes(GAZETTEER_URL)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        name = [item for item in archive.namelist() if item.lower().endswith(".txt")][0]
        text = archive.read(name).decode("latin1")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    land: dict[str, float] = {}
    names: dict[str, str] = {}
    for row in reader:
        geoid = (row.get("GEOID") or "").strip()
        if len(geoid) != 5 or geoid[:2] not in TARGET_FIPS:
            continue
        sqmi = _to_float(row.get("ALAND_SQMI"))
        if sqmi is None:
            aland = _to_float(row.get("ALAND")) or 0.0
            sqmi = aland / 2_589_988.11
        land[geoid] = sqmi
        names[geoid] = (row.get("NAME") or f"County {geoid}").strip()
    load_land_with_names._names = names  # type: ignore[attr-defined]
    return land


# The builder calls load_land. Point it at the name-aware implementation and
# keep county naming on the same function object.
def _bind_names() -> None:
    global load_land

    def _county_name_bound(fips: str, _land: dict[str, float]) -> str:
        names = getattr(load_land, "_names", {})
        return names.get(fips, f"County {fips}")

    globals()["_county_name"] = _county_name_bound
    load_land = load_land_with_names


_bind_names()


def build_payload(states: dict[str, Any], national: dict[str, float]) -> dict[str, Any]:
    return {
        "vintage": {
            "acs": "ACS 2019-2023 5-year table-based summary file",
            "bps": "Census Building Permits Survey annual state and county files, average of 2022, 2023, and 2024",
            "fhfa": "FHFA All-Transactions state index, 2000=100, through the latest year in the March 2026 workbook vintage",
            "pep": "Census population estimates, July 1 2020 to July 1 2024",
            "gazetteer": "2024 Census county gazetteer, land area",
            "access_date": "2026-10-25",
            "tier1": "Aggregate GIS statistics in data/sample/tier1_benchmarks.json",
            "transit": "Screened inventory in data/sample/transit_inventory.json",
        },
        "national": {
            "sf_permit_value": national["sf_permit_value"],
            "mf_permit_value": national["mf_permit_value"],
            "note": "Unit-weighted national Building Permits Survey valuation per unit, 2022-2024 average. State cost indexes are state unit value divided by these anchors, shrunk toward 1 when the cell is thin.",
        },
        "states": states,
    }


def write_fixtures(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire public housing data for Stateframe.")
    parser.add_argument(
        "--output",
        default="",
        help="Where to write the refreshed fixture. Default: data/cache/fixtures.json",
    )
    parser.add_argument(
        "--write-sample",
        action="store_true",
        help="Also overwrite data/sample/fixtures.json. Used when refreshing the committed benchmark.",
    )
    args = parser.parse_args(argv)
    output = Path(args.output) if args.output else ROOT / "data" / "cache" / "fixtures.json"
    try:
        states, national = build_states()
        payload = build_payload(states, national)
    except AcquireError as exc:
        print(f"Acquisition failed: {exc}", file=sys.stderr)
        print(f"Falling back to committed benchmark at {SAMPLE_FIXTURES}", file=sys.stderr)
        return 2
    write_fixtures(payload, output)
    print(f"Wrote {output}")
    if args.write_sample:
        write_fixtures(payload, SAMPLE_FIXTURES)
        print(f"Wrote {SAMPLE_FIXTURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
