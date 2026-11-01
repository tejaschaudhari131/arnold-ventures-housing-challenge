# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Permit vintage actually loaded for each state.

Pennsylvania and New Hampshire have county Building Permits Survey files for
2023–2025 in the Lab extracts. The other nine states stay on the screening
fixture, whose vintage string names 2022–2024. The label is parsed from the
file that was loaded. It is not a hardcoded state list.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LAB_DIR = ROOT / "data" / "sample" / "lab"
_YEAR = re.compile(r"20\d{2}")


def vintage_label(years: list[int]) -> str:
    if not years:
        return "BPS"
    ordered = sorted(set(years))
    if len(ordered) == 1:
        return f"BPS {ordered[0]}"
    return f"BPS {ordered[0]}-{ordered[-1]}"


@lru_cache(maxsize=None)
def _lab_document(code: str) -> dict[str, Any] | None:
    path = LAB_DIR / f"{code}.json"
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not doc.get("counties"):
        return None
    return doc


def _years_in(doc: dict[str, Any]) -> list[int]:
    for county in doc.get("counties") or []:
        bps = county.get("bps")
        if isinstance(bps, dict) and bps:
            return sorted(int(year) for year in bps)
    text = str((doc.get("vintage") or {}).get("bps", ""))
    return sorted({int(year) for year in _YEAR.findall(text)})


def _fixture_years(fixtures: dict[str, Any]) -> list[int]:
    text = str((fixtures.get("vintage") or {}).get("bps", ""))
    return sorted({int(year) for year in _YEAR.findall(text)})


def ensure_permit_vintage(fixtures: dict[str, Any], state_code: str) -> str:
    """Point one state's permit cells at the county file on disk and label it.

    Idempotent. County annual rates become the mean of the years stored in the
    loaded file. State totals are the sum of those county rates.
    """
    state = fixtures["states"][state_code]
    cached = state.get("_permit_vintage")
    if isinstance(cached, str) and cached:
        return cached
    doc = _lab_document(state_code)
    if doc is not None:
        years = _years_in(doc)
        by_fips = {str(county["fips"]): county.get("bps") or {} for county in doc["counties"]}
        keys = [str(year) for year in years]
        for county in state["counties"]:
            series = by_fips.get(str(county["fips"]))
            if not isinstance(series, dict) or not keys:
                continue
            if any(year not in series for year in keys):
                continue
            n = float(len(keys))
            county["bps_sf"] = sum(float(series[year].get("u1", 0.0)) for year in keys) / n
            county["bps_two"] = sum(float(series[year].get("u2", 0.0)) for year in keys) / n
            county["bps_three_four"] = sum(float(series[year].get("u34", 0.0)) for year in keys) / n
            county["bps_five_plus"] = sum(float(series[year].get("u5", 0.0)) for year in keys) / n
        if keys:
            state["bps_sf"] = sum(float(county["bps_sf"]) for county in state["counties"])
            state["bps_two"] = sum(float(county["bps_two"]) for county in state["counties"])
            state["bps_three_four"] = sum(float(county["bps_three_four"]) for county in state["counties"])
            state["bps_five_plus"] = sum(float(county["bps_five_plus"]) for county in state["counties"])
        label = vintage_label(years)
        source = f"data/sample/lab/{state_code}.json"
    else:
        years = _fixture_years(fixtures)
        label = vintage_label(years)
        source = str(fixtures.get("_path") or "data/sample/fixtures.json")
    state["_permit_vintage"] = label
    state["_permit_source"] = source
    state["_permit_years"] = years
    return label
