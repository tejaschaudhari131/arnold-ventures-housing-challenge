# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Acquire public inputs for the Small Homes Policy Lab.

Run ``python -m src.lab.acquire`` (or ``make lab-data``). For each Lab state
(Pennsylvania, New Hampshire) it downloads, over HTTPS from an allowlist:

- ACS 2020–2024 5-year table-based summary files: B25001 (housing units),
  B25024 (units in structure), B25031 (median gross rent by bedrooms),
  B25077 (median value), estimates AND margins of error, for counties, tracts,
  and the Census places named in ``config/lab/evidence/*.yaml``
- 2024 Census tract and county gazetteers (land area, names, interior points)
- Census Building Permits Survey annual county files, 2023–2025
- 2024 Census cartographic boundary counties (1:5,000,000)
- HUD FY2026 Fair Market Rents (optional cross-check; skipped on failure)
- WPRDC Allegheny County property assessments (optional, Pennsylvania only):
  aggregate lot-size bins, never parcel rows, owners, or mailing addresses

No API key is needed. Nothing large is committed: output goes to
``data/cache/lab/`` unless ``--write-sample`` refreshes the small committed
extracts in ``data/sample/lab/``. On a network failure the command exits 2
and the committed extracts stay in place.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.parse
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator
from xml.etree import ElementTree as ET

from src.lab import shapefile
from src.lab.config import LAB_STATES, ROOT, load_evidence

USER_AGENT = "stateframe-small-homes-lab/1.0 (public-data acquisition; research)"
ALLOWED_HOSTS = frozenset({"www2.census.gov", "data.wprdc.org", "www.huduser.gov"})

ACS_YEAR = 2024
ACS_URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/{year}/"
    "table-based-SF/data/5YRData/acsdt5y{year}-{table}.dat"
)
BPS_COUNTY_URL = "https://www2.census.gov/econ/bps/County/co{yy}12y.txt"
COUNTY_GAZ_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
    "2024_Gaz_counties_national.zip"
)
TRACT_GAZ_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
    "2024_gaz_tracts_{fips}.txt"
)
BOUNDARY_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_5m.zip"
HUD_FMR_URL = "https://www.huduser.gov/portal/datasets/fmr/fmr2026/FY26_FMRs.xlsx"
WPRDC_SQL_URL = "https://data.wprdc.org/api/3/action/datastore_search_sql?sql="
WPRDC_ASSESSMENTS = "65855e14-549e-4992-b5be-d629afc676fa"

# Fields read from each ACS table. Every estimate keeps its margin of error.
ACS_TABLES: dict[str, dict[str, str]] = {
    "b25001": {"housing_units": "B25001_E001"},
    "b25024": {"units_total": "B25024_E001", "detached": "B25024_E002", "attached": "B25024_E003"},
    "b25031": {"rent_1br": "B25031_E003", "rent_2br": "B25031_E004"},
    "b25077": {"median_value": "B25077_E001"},
}
TRACT_TABLES = ("b25001", "b25024")
PLACE_TABLES = ("b25024",)

# Tract density bins (housing units per square mile of land). Context
# thresholds in config/lab/assumptions.yaml must be bin edges.
DENSITY_EDGES = (0, 50, 100, 200, 500, 1000, 2000, 4000, 8000)

# Lot-area bin edges for the WPRDC aggregate, square feet.
LOT_EDGES = (0, 1500, 2500, 3500, 5000, 7500, 10000, 15000, 21780, 43560)


class AcquireError(RuntimeError):
    """A required public file could not be read."""


def fetch_bytes(url: str, timeout: int = 240) -> bytes:
    from src.data.safe_url import FetchDenied, fetch_bytes as safe_fetch

    try:
        return safe_fetch(url, ALLOWED_HOSTS, timeout, USER_AGENT, require_status=200)
    except FetchDenied as exc:
        raise AcquireError(str(exc)) from exc


# ACS summary-file annotation codes. Estimates with these values are missing
# (never zero). A -555555555 margin means the estimate is controlled and has
# no sampling error, so the margin is 0.
ACS_MISSING = {-999999999.0, -888888888.0, -666666666.0, -333333333.0, -222222222.0}
ACS_CONTROLLED_MOE = -555555555.0


def parse_acs_value(text: str | None, is_moe: bool) -> float | None:
    if text is None:
        return None
    cleaned = text.strip()
    if cleaned in {"", ".", "-", "N", "(X)", "null"}:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if is_moe and value == ACS_CONTROLLED_MOE:
        return 0.0
    if value in ACS_MISSING or value < 0:
        return None
    return value


def parse_acs_lines(
    lines: Iterable[str],
    columns: dict[str, str],
    keep: Any,
) -> dict[str, dict[str, dict[str, float | None]]]:
    """Parse a pipe-delimited ACS summary file.

    ``keep(geo_id)`` returns the key to store the row under, or None to skip.
    Each field is stored as ``{"e": estimate, "m": margin_of_error}``.
    """
    iterator: Iterator[str] = iter(lines)
    header = next(iterator).rstrip("\r\n").split("|")
    index = {name: pos for pos, name in enumerate(header)}
    wanted: list[tuple[str, int, int]] = []
    for field, estimate_col in columns.items():
        moe_col = estimate_col.replace("_E", "_M")
        if estimate_col not in index or moe_col not in index:
            raise AcquireError(f"ACS file is missing {estimate_col} or {moe_col}")
        wanted.append((field, index[estimate_col], index[moe_col]))
    rows: dict[str, dict[str, dict[str, float | None]]] = {}
    for line in iterator:
        geo = line.split("|", 1)[0]
        key = keep(geo)
        if key is None:
            continue
        parts = line.rstrip("\r\n").split("|")
        row = rows.setdefault(key, {})
        for field, e_pos, m_pos in wanted:
            row[field] = {
                "e": parse_acs_value(parts[e_pos] if e_pos < len(parts) else None, False),
                "m": parse_acs_value(parts[m_pos] if m_pos < len(parts) else None, True),
            }
    return rows


def acs_keep(state_fips: set[str], place_ids: set[str]) -> Any:
    def keep(geo: str) -> str | None:
        if geo.startswith("0400000US") and geo[-2:] in state_fips:
            return geo[-2:]
        if geo.startswith("0500000US") and geo[-5:-3] in state_fips:
            return geo[-5:]
        if geo.startswith("1400000US") and geo[9:11] in state_fips:
            return geo[9:]
        if geo.startswith("1600000US") and geo[9:] in place_ids:
            return "place:" + geo[9:]
        return None

    return keep


def stream_acs(table: str, keep: Any) -> dict[str, dict[str, dict[str, float | None]]]:
    url = ACS_URL.format(year=ACS_YEAR, table=table)
    print(f"  ACS {ACS_YEAR} 5-year {table.upper()}", flush=True)
    from src.data.safe_url import FetchDenied, open_url

    try:
        response = open_url(url, ALLOWED_HOSTS, 300, USER_AGENT)
    except FetchDenied as exc:
        raise AcquireError(str(exc)) from exc
    with response:
        lines = (raw.decode("latin1") for raw in response)
        return parse_acs_lines(lines, ACS_TABLES[table], keep)


def parse_gazetteer(text: str) -> dict[str, dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    out: dict[str, dict[str, Any]] = {}
    for row in reader:
        cleaned = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        geoid = cleaned.get("GEOID") or ""
        if not geoid:
            continue
        sqmi = cleaned.get("ALAND_SQMI")
        out[geoid] = {
            "name": cleaned.get("NAME") or geoid,
            "land_sqmi": float(sqmi) if sqmi else float(cleaned.get("ALAND") or 0) / 2_589_988.11,
            "lat": float(cleaned["INTPTLAT"]) if cleaned.get("INTPTLAT") else None,
            "lon": float(cleaned["INTPTLONG"]) if cleaned.get("INTPTLONG") else None,
        }
    return out


def load_county_gazetteer() -> dict[str, dict[str, Any]]:
    print("  county gazetteer", flush=True)
    blob = fetch_bytes(COUNTY_GAZ_URL)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        name = [item for item in archive.namelist() if item.lower().endswith(".txt")][0]
        return parse_gazetteer(archive.read(name).decode("latin1"))


def load_tract_gazetteer(state_fips: str) -> dict[str, dict[str, Any]]:
    print(f"  tract gazetteer {state_fips}", flush=True)
    return parse_gazetteer(fetch_bytes(TRACT_GAZ_URL.format(fips=state_fips)).decode("latin1"))


def parse_bps_county(text: str, state_fips: set[str]) -> dict[str, dict[str, float]]:
    """One annual BPS county file. Columns 7–17 are imputed-plus-reported units and dollars."""
    rows: dict[str, dict[str, float]] = {}
    for parts in csv.reader(io.StringIO(text)):
        if not parts or not parts[0].strip().isdigit() or len(parts) < 18:
            continue
        st = parts[1].strip().zfill(2)
        if st not in state_fips:
            continue

        def num(i: int) -> float:
            try:
                return float(parts[i])
            except ValueError:
                return 0.0

        rows[st + parts[2].strip().zfill(3)] = {
            "u1": num(7), "v1": num(8),
            "u2": num(10), "v2": num(11),
            "u34": num(13), "v34": num(14),
            "u5": num(16), "v5": num(17),
        }
    return rows


def density_bin(units: float, land_sqmi: float) -> int:
    density = units / land_sqmi if land_sqmi > 0 else 0.0
    index = 0
    for i, edge in enumerate(DENSITY_EDGES):
        if density >= edge:
            index = i
    return index


def bin_tracts(
    tract_acs: dict[str, dict[str, dict[str, float | None]]],
    tract_gaz: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, float]]]:
    """Sum detached, attached, and housing units per county into density bins."""
    by_county: dict[str, list[dict[str, float]]] = {}
    for tract, row in tract_acs.items():
        gaz = tract_gaz.get(tract)
        if gaz is None or gaz["land_sqmi"] <= 0:
            continue
        units = (row.get("housing_units") or {}).get("e") or 0.0
        if units <= 0:
            continue
        bins = by_county.setdefault(
            tract[:5], [{"detached": 0.0, "attached": 0.0, "housing_units": 0.0, "tracts": 0} for _ in DENSITY_EDGES]
        )
        cell = bins[density_bin(units, gaz["land_sqmi"])]
        cell["detached"] += (row.get("detached") or {}).get("e") or 0.0
        cell["attached"] += (row.get("attached") or {}).get("e") or 0.0
        cell["housing_units"] += units
        cell["tracts"] += 1
    return by_county


def _xlsx_rows(blob: bytes) -> list[dict[str, str]]:
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = ["".join(n.text or "" for n in si.findall(".//m:t", namespace)) for si in shared.findall("m:si", namespace)]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    table: list[list[str]] = []
    for row in sheet.findall("m:sheetData/m:row", namespace):
        cells: dict[int, str] = {}
        for cell in row.findall("m:c", namespace):
            ref = "".join(ch for ch in (cell.get("r") or "A") if ch.isalpha())
            col = 0
            for ch in ref:
                col = col * 26 + ord(ch.upper()) - 64
            node = cell.find("m:v", namespace)
            if node is None or node.text is None:
                continue
            cells[col - 1] = strings[int(node.text)] if cell.get("t") == "s" else node.text
        if cells:
            table.append([cells.get(i, "") for i in range(max(cells) + 1)])
    header = table[0]
    return [dict(zip(header, row)) for row in table[1:]]


def parse_fmr(blob: bytes, state_fips: set[str]) -> dict[str, dict[str, float]]:
    """County FMRs. New England towns are population-weighted up to the county."""
    sums: dict[str, dict[str, float]] = {}
    for row in _xlsx_rows(blob):
        fips10 = (row.get("fips") or "").strip()
        if len(fips10) < 5 or fips10[:2] not in state_fips:
            continue
        try:
            pop = float(row.get("pop2023") or 0) or 1.0
            fmr1 = float(row["fmr_1"])
            fmr2 = float(row["fmr_2"])
        except (KeyError, ValueError):
            continue
        cell = sums.setdefault(fips10[:5], {"pop": 0.0, "fmr_1br": 0.0, "fmr_2br": 0.0})
        cell["pop"] += pop
        cell["fmr_1br"] += pop * fmr1
        cell["fmr_2br"] += pop * fmr2
    return {
        county: {"fmr_1br": round(c["fmr_1br"] / c["pop"]), "fmr_2br": round(c["fmr_2br"] / c["pop"])}
        for county, c in sums.items()
    }


def wprdc_lot_query() -> str:
    edges = ",".join(str(edge) for edge in LOT_EDGES)
    # Aggregates only. Owner and mailing-address columns are never selected.
    return (
        "SELECT CASE WHEN \"MUNIDESC\" LIKE '%PITTSBURGH%' THEN 'pittsburgh' ELSE 'rest' END AS area, "
        "CASE WHEN \"USEDESC\"='SINGLE FAMILY' THEN 'detached' ELSE 'attached' END AS host, "
        f"width_bucket(\"LOTAREA\", ARRAY[{edges}]) AS bin, COUNT(*) AS n, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY \"FAIRMARKETLAND\"/NULLIF(\"LOTAREA\",0)) AS land_psf_2012 "
        f"FROM \"{WPRDC_ASSESSMENTS}\" WHERE \"CLASS\"='R' "
        "AND \"USEDESC\" IN ('SINGLE FAMILY','TOWNHOUSE','ROWHOUSE') AND \"LOTAREA\">0 "
        "GROUP BY 1,2,3 ORDER BY 1,2,3"
    )


def load_wprdc_lots() -> dict[str, Any]:
    print("  WPRDC Allegheny lot bins (aggregate)", flush=True)
    url = WPRDC_SQL_URL + urllib.parse.quote(wprdc_lot_query())
    payload = json.loads(fetch_bytes(url, timeout=240).decode("utf-8"))
    if not payload.get("success"):
        raise AcquireError("WPRDC query was not successful")
    groups: dict[str, dict[str, Any]] = {}
    for record in payload["result"]["records"]:
        key = f"{record['area']}:{record['host']}"
        group = groups.setdefault(key, {"counts": [0] * len(LOT_EDGES), "land_psf_2012": []})
        index = max(1, min(int(record["bin"]), len(LOT_EDGES))) - 1
        group["counts"][index] += int(record["n"])
        if record.get("land_psf_2012") is not None:
            group["land_psf_2012"].append((int(record["n"]), float(record["land_psf_2012"])))
    out: dict[str, Any] = {}
    for key, group in groups.items():
        weights = group.pop("land_psf_2012")
        total = sum(n for n, _ in weights) or 1
        group["land_psf_2012_weighted_median_of_bins"] = round(sum(n * v for n, v in weights) / total, 2)
        group["parcels"] = sum(group["counts"])
        out[key] = group
    return {
        "source": "Western Pennsylvania Regional Data Center, Allegheny County Property Assessments",
        "resource_id": WPRDC_ASSESSMENTS,
        "license": "CC0 1.0 (public domain dedication)",
        "query": "aggregate counts by lot-area bin; no parcel rows, owner names, or mailing addresses",
        "lot_edges_sqft": list(LOT_EDGES),
        "host_map": {"detached": "USEDESC SINGLE FAMILY", "attached": "USEDESC TOWNHOUSE or ROWHOUSE"},
        "land_value_note": (
            "FAIRMARKETLAND is Allegheny County's 2012 base-year assessed land value. It is shown for "
            "context only and is not used as a current land price."
        ),
        "groups": out,
    }


def load_boundaries(state_fips: set[str], tolerance: float = 0.004) -> dict[str, list[dict[str, Any]]]:
    print("  county boundaries cb_2024 5m", flush=True)
    blob = fetch_bytes(BOUNDARY_URL)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        shp = archive.read([n for n in names if n.endswith(".shp")][0])
        dbf = archive.read([n for n in names if n.endswith(".dbf")][0])
    feats = shapefile.features(shp, dbf, lambda rec: rec.get("STATEFP") in state_fips, tolerance)
    by_state: dict[str, list[dict[str, Any]]] = {}
    for feat in feats:
        props = feat["properties"]
        by_state.setdefault(props["STATEFP"], []).append(
            {"fips": props["GEOID"], "name": props.get("NAME", props["GEOID"]), "rings": feat["rings"]}
        )
    return by_state


def build_state(
    code: str,
    acs: dict[str, dict[str, dict[str, float | None]]],
    tract_bins: dict[str, list[dict[str, float]]],
    county_gaz: dict[str, dict[str, Any]],
    bps_years: dict[int, dict[str, dict[str, float]]],
    fmr: dict[str, dict[str, float]] | None,
    places: list[dict[str, Any]],
    fmr_label: str = "HUD FY2026 Fair Market Rents",
) -> dict[str, Any]:
    meta = LAB_STATES[code]
    fips = meta["fips"]
    counties = []
    for county_fips in sorted(k for k in county_gaz if len(k) == 5 and k.startswith(fips)):
        row = acs.get(county_fips)
        if row is None:
            continue
        gaz = county_gaz[county_fips]
        counties.append(
            {
                "fips": county_fips,
                "name": gaz["name"],
                "land_sqmi": round(gaz["land_sqmi"], 3),
                "lat": gaz["lat"],
                "lon": gaz["lon"],
                "acs": {field: row.get(field, {"e": None, "m": None}) for t in ACS_TABLES.values() for field in t},
                "density_bins": tract_bins.get(county_fips, []),
                "bps": {str(year): frame.get(county_fips, {}) for year, frame in sorted(bps_years.items())},
                "hud_fmr": (fmr or {}).get(county_fips),
            }
        )
    state_row = acs.get(fips, {})
    return {
        "state": code,
        "state_fips": fips,
        "name": meta["name"],
        "vintage": {
            "acs": f"ACS {ACS_YEAR - 4}–{ACS_YEAR} 5-year table-based summary file",
            "bps": "Census Building Permits Survey annual county files (imputed + reported), "
            + ", ".join(str(y) for y in sorted(bps_years)),
            "gazetteer": "2024 Census gazetteer (counties, tracts)",
            "hud_fmr": fmr_label if fmr else "not retrieved",
            "access_date": date.today().isoformat(),
        },
        "density_edges": list(DENSITY_EDGES),
        "state_acs": {field: state_row.get(field, {"e": None, "m": None}) for t in ACS_TABLES.values() for field in t},
        "places": places,
        "counties": counties,
    }


def acquire(
    codes: list[str],
    with_wprdc: bool = True,
    with_hud: bool = True,
    hud_file: Path | None = None,
) -> dict[str, Any]:
    state_fips = {LAB_STATES[c]["fips"] for c in codes}
    place_rules: list[dict[str, Any]] = []
    for code in codes:
        for rule in load_evidence(code).get("rules", []):
            if rule.get("geography", {}).get("place"):
                place_rules.append({"state": code, **rule["geography"], "rule": rule["id"]})
    place_ids = {rule["place"] for rule in place_rules}
    print("Downloading Lab sources...", flush=True)
    keep = acs_keep(state_fips, place_ids)
    acs: dict[str, dict[str, dict[str, float | None]]] = {}
    for table in ACS_TABLES:
        for key, fields in stream_acs(table, keep).items():
            acs.setdefault(key, {}).update(fields)
    county_gaz = load_county_gazetteer()
    tract_bins: dict[str, list[dict[str, float]]] = {}
    for st in sorted(state_fips):
        tract_gaz = load_tract_gazetteer(st)
        tract_rows = {k: v for k, v in acs.items() if len(k) == 11 and k.startswith(st)}
        tract_bins.update(bin_tracts(tract_rows, tract_gaz))
    bps_years: dict[int, dict[str, dict[str, float]]] = {}
    for year in (2023, 2024, 2025):
        print(f"  BPS county {year}", flush=True)
        text = fetch_bytes(BPS_COUNTY_URL.format(yy=str(year)[2:])).decode("latin1")
        bps_years[year] = parse_bps_county(text, state_fips)
    fmr = None
    if with_hud:
        # huduser.gov sometimes answers automated clients with an HTTP 202
        # challenge page. The Lab does not work around it; pass --hud-file
        # with a manually downloaded FY26_FMRs.xlsx instead.
        try:
            print("  HUD FY2026 FMR (optional)", flush=True)
            blob = hud_file.read_bytes() if hud_file else fetch_bytes(HUD_FMR_URL, timeout=90)
            fmr = parse_fmr(blob, state_fips)
        except (AcquireError, OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            print(f"  HUD FMR skipped: {exc}", flush=True)
    boundaries = load_boundaries(state_fips)
    states = {}
    for code in codes:
        places = []
        for rule in place_rules:
            if rule["state"] != code:
                continue
            row = acs.get("place:" + rule["place"], {})
            places.append(
                {
                    "place": rule["place"],
                    "name": rule.get("place_name", rule["place"]),
                    "county": rule["county"],
                    "rule": rule["rule"],
                    "detached": row.get("detached", {"e": None, "m": None}),
                    "attached": row.get("attached", {"e": None, "m": None}),
                }
            )
        label = "HUD FY2026 Fair Market Rents" + (" (manually downloaded workbook)" if hud_file else "")
        states[code] = build_state(code, acs, tract_bins, county_gaz, bps_years, fmr, places, label)
    result: dict[str, Any] = {"states": states, "boundaries": {}}
    for code in codes:
        result["boundaries"][code] = {
            "source": "U.S. Census Bureau cartographic boundary file cb_2024_us_county_5m, Douglas–Peucker simplified",
            "license": "Public domain, U.S. government work",
            "url": BOUNDARY_URL,
            "counties": sorted(boundaries.get(LAB_STATES[code]["fips"], []), key=lambda f: f["fips"]),
        }
    if with_wprdc and "PA" in codes:
        try:
            result["allegheny_lots"] = load_wprdc_lots()
        except (AcquireError, ValueError, KeyError) as exc:
            print(f"  WPRDC skipped: {exc}", flush=True)
    return result


def write_json(payload: Any, path: Path, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=indent, separators=None if indent else (",", ":"))
        handle.write("\n")


def write_outputs(result: dict[str, Any], directory: Path) -> list[Path]:
    written = []
    for code, state in result["states"].items():
        path = directory / f"{code}.json"
        write_json(state, path, indent=1)
        written.append(path)
    for code, boundary in result["boundaries"].items():
        path = directory / f"{code}_counties.geo.json"
        write_json(boundary, path)
        written.append(path)
    if "allegheny_lots" in result:
        path = directory / "allegheny_lots.json"
        write_json(result["allegheny_lots"], path, indent=1)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire public inputs for the Small Homes Policy Lab.")
    parser.add_argument("--states", default=",".join(LAB_STATES), help="Comma-separated state codes (default PA,NH)")
    parser.add_argument("--output", default="", help="Output directory. Default: data/cache/lab")
    parser.add_argument("--write-sample", action="store_true", help="Also refresh data/sample/lab/")
    parser.add_argument("--no-wprdc", action="store_true", help="Skip the optional Allegheny lot enrichment")
    parser.add_argument("--no-hud", action="store_true", help="Skip the optional HUD FMR cross-check")
    parser.add_argument("--hud-file", default="", help="Path to a downloaded HUD FY26_FMRs.xlsx")
    args = parser.parse_args(argv)
    codes = [c.strip().upper() for c in args.states.split(",") if c.strip()]
    unknown = [c for c in codes if c not in LAB_STATES]
    if unknown:
        print(f"Unknown Lab state(s): {unknown}", file=sys.stderr)
        return 1
    try:
        result = acquire(
            codes,
            with_wprdc=not args.no_wprdc,
            with_hud=not args.no_hud,
            hud_file=Path(args.hud_file) if args.hud_file else None,
        )
    except AcquireError as exc:
        print(f"Acquisition failed: {exc}", file=sys.stderr)
        print("Committed extracts in data/sample/lab/ are unchanged.", file=sys.stderr)
        return 2
    output = Path(args.output) if args.output else ROOT / "data" / "cache" / "lab"
    for path in write_outputs(result, output):
        print(f"Wrote {path}")
    if args.write_sample:
        for path in write_outputs(result, ROOT / "data" / "sample" / "lab"):
            print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
