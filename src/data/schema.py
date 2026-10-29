# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Fixture schema and loader.

Any state is a JSON document with the same keys. Adapters in ``adapters.py``
normalize live Census, permit, parcel, and transit extracts into this shape.
The simulator never reads a vendor-specific column name.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_FIXTURES = ROOT / "data" / "sample" / "fixtures.json"
TRANSIT_PATH = ROOT / "data" / "sample" / "transit_inventory.json"
TIER1_PATH = ROOT / "data" / "sample" / "tier1_benchmarks.json"

REQUIRED_STATE_KEYS = (
    "code",
    "fips",
    "name",
    "tier",
    "population",
    "pop_growth_annual",
    "housing_units",
    "vacant",
    "owner_occ",
    "renter_occ",
    "sf_detached",
    "sf_attached",
    "two_unit",
    "three_four",
    "five_plus",
    "mobile",
    "median_value",
    "median_rent",
    "median_income",
    "pre1940_share",
    "transit_commute_share",
    "land_sqmi",
    "bps_sf",
    "bps_two",
    "bps_three_four",
    "bps_five_plus",
    "cost_index_sf",
    "cost_index_mf",
    "fhfa_hpi_2020",
    "fhfa_hpi_latest",
    "fhfa_latest_year",
    "counties",
)

REQUIRED_COUNTY_KEYS = (
    "fips",
    "name",
    "land_sqmi",
    "population",
    "housing_units",
    "vacant",
    "owner_occ",
    "renter_occ",
    "sf_detached",
    "sf_attached",
    "two_unit",
    "three_four",
    "five_plus",
    "mobile",
    "median_value",
    "median_rent",
    "median_income",
    "pre1940_share",
    "transit_commute_share",
    "value_imputed",
    "bps_sf",
    "bps_two",
    "bps_three_four",
    "bps_five_plus",
    "bps_reporting",
)

CHALLENGE_STATES = ("PA", "CT", "WI", "UT", "OR", "HI", "AZ", "VA", "TN", "RI", "NH")
TIER1_STATES = ("CT", "WI", "UT", "HI")
TIER2_STATES = ("PA", "OR", "VA", "AZ", "TN", "RI", "NH")


def _num(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric, got {type(value).__name__}")
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    return float(value)


def validate_county(county: dict[str, Any], state_code: str) -> None:
    missing = [key for key in REQUIRED_COUNTY_KEYS if key not in county]
    if missing:
        raise ValueError(f"{state_code} county {county.get('fips', '?')} missing {missing}")
    for key in REQUIRED_COUNTY_KEYS:
        if key in ("fips", "name", "value_imputed", "bps_reporting"):
            continue
        _num(county[key], f"{state_code}.{county['fips']}.{key}")
    if not isinstance(county["value_imputed"], bool):
        raise ValueError("value_imputed must be boolean")
    if not isinstance(county["bps_reporting"], bool):
        raise ValueError("bps_reporting must be boolean")
    if county["housing_units"] < 0 or county["land_sqmi"] < 0:
        raise ValueError(f"{state_code} {county['fips']} has a negative stock or area")


def validate_state(state: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_STATE_KEYS if key not in state]
    if missing:
        raise ValueError(f"State {state.get('code', '?')} missing {missing}")
    code = state["code"]
    if code not in CHALLENGE_STATES:
        raise ValueError(f"Unknown challenge state {code}")
    if state["tier"] not in (1, 2):
        raise ValueError(f"{code} tier must be 1 or 2")
    if code in TIER1_STATES and state["tier"] != 1:
        raise ValueError(f"{code} is a tier-1 state in the challenge data list")
    if code in TIER2_STATES and state["tier"] != 2:
        raise ValueError(f"{code} is a tier-2 state in the challenge data list")
    for key in REQUIRED_STATE_KEYS:
        if key in ("code", "fips", "name", "tier", "counties", "fhfa_latest_year"):
            continue
        _num(state[key], f"{code}.{key}")
    if not state["counties"]:
        raise ValueError(f"{code} has no counties")
    seen: set[str] = set()
    for county in state["counties"]:
        validate_county(county, code)
        if county["fips"] in seen:
            raise ValueError(f"Duplicate county {county['fips']}")
        seen.add(county["fips"])
        if not str(county["fips"]).startswith(str(state["fips"])):
            raise ValueError(f"{county['fips']} is not inside state FIPS {state['fips']}")


def validate_fixtures(payload: dict[str, Any]) -> dict[str, Any]:
    if "states" not in payload or not isinstance(payload["states"], dict):
        raise ValueError("Fixture file must contain a states object")
    codes = set(payload["states"])
    if codes != set(CHALLENGE_STATES):
        missing = sorted(set(CHALLENGE_STATES) - codes)
        extra = sorted(codes - set(CHALLENGE_STATES))
        raise ValueError(f"Fixture states mismatch missing={missing} extra={extra}")
    for code in CHALLENGE_STATES:
        validate_state(payload["states"][code])
    return payload


def resolve_fixture_path(explicit: str | None = None) -> Path:
    import os

    if explicit:
        return Path(explicit)
    env = os.environ.get("STATEFRAME_FIXTURES")
    if env:
        return Path(env)
    return SAMPLE_FIXTURES


def load_fixtures(path: str | Path | None = None) -> dict[str, Any]:
    fixture_path = Path(path) if path else resolve_fixture_path()
    with fixture_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    validate_fixtures(payload)
    payload["_path"] = str(fixture_path)
    return payload


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data
