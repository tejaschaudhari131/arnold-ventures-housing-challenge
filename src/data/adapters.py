# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""State adapter layer.

Live extracts come in as loose dictionaries from Census summary files, the
Building Permits Survey, FHFA, gazetteer land area, and tier-1 GIS aggregates.
``adapt_state`` is the only constructor the rest of the program uses. Adding
a twelfth state means supplying the same dictionary, not editing the model.
"""

from __future__ import annotations

from typing import Any

from src.data.schema import TIER1_STATES, validate_state

# Fields that must never be copied out of a parcel service, even if a future
# adapter is pointed at a CAMA layer that contains them.
FORBIDDEN_PARCEL_FIELDS = frozenset(
    {
        "Owner",
        "Co_Owner",
        "Mailing_Address",
        "Mailing_City",
        "Mailing_State",
        "Mailing_Zip",
        "PARCEL_ADD",
        "ACCOUNT_NUM",
        "owner",
        "mailing_address",
    }
)


def assert_no_pii(record: dict[str, Any]) -> None:
    """Refuse owner and mailing fields. Aggregate adapters never need them."""
    found = FORBIDDEN_PARCEL_FIELDS.intersection(record)
    if found:
        raise ValueError(f"Parcel record contains forbidden fields: {sorted(found)}")


def housing_density(housing_units: float, land_sqmi: float) -> float:
    if land_sqmi <= 0:
        return 0.0
    return housing_units / land_sqmi


def completeness_score(state: dict[str, Any], tier1: dict[str, Any] | None) -> float:
    """Transparent 0–1 score. Weights are the data classes the model actually uses.

    0.35 ACS stock and prices (always present in this build)
    0.20 state Building Permits Survey
    0.15 county permit coverage
    0.20 a tier-1 parcel or land-use observation
    0.10 lot-size bins, the tightest physical screen
    """
    score = 0.35
    if state["bps_sf"] + state["bps_five_plus"] > 0:
        score += 0.20
    counties = state["counties"]
    if counties:
        reporting = sum(1 for county in counties if county["bps_reporting"])
        score += 0.15 * (reporting / len(counties))
    if tier1:
        score += 0.20
        if tier1.get("lot_bins_sqft"):
            score += 0.10
    return round(score, 3)


def adapt_county(raw: dict[str, Any], state_median_value: float, state_median_rent: float) -> dict[str, Any]:
    """Fill suppressed medians from the state median and flag the imputation."""
    value = raw.get("median_value")
    rent = raw.get("median_rent")
    value_imputed = value is None or value <= 0
    rent_imputed = rent is None or rent <= 0
    county = {
        "fips": str(raw["fips"]),
        "name": str(raw["name"]),
        "land_sqmi": float(raw["land_sqmi"]),
        "population": float(raw.get("population") or 0),
        "housing_units": float(raw.get("housing_units") or 0),
        "vacant": float(raw.get("vacant") or 0),
        "owner_occ": float(raw.get("owner_occ") or 0),
        "renter_occ": float(raw.get("renter_occ") or 0),
        "sf_detached": float(raw.get("sf_detached") or 0),
        "sf_attached": float(raw.get("sf_attached") or 0),
        "two_unit": float(raw.get("two_unit") or 0),
        "three_four": float(raw.get("three_four") or 0),
        "five_plus": float(raw.get("five_plus") or 0),
        "mobile": float(raw.get("mobile") or 0),
        "median_value": float(value) if not value_imputed else float(state_median_value),
        "median_rent": float(rent) if not rent_imputed else float(state_median_rent),
        "median_income": float(raw.get("median_income") or 0),
        "pre1940_share": float(raw.get("pre1940_share") or 0),
        "transit_commute_share": float(raw.get("transit_commute_share") or 0),
        "value_imputed": bool(value_imputed),
        "bps_sf": float(raw.get("bps_sf") or 0),
        "bps_two": float(raw.get("bps_two") or 0),
        "bps_three_four": float(raw.get("bps_three_four") or 0),
        "bps_five_plus": float(raw.get("bps_five_plus") or 0),
        "bps_reporting": bool(raw.get("bps_reporting", False)),
    }
    return county


def adapt_state(raw: dict[str, Any], tier1: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize one state. ``tier1`` is optional and is stored beside the state."""
    if tier1:
        assert_no_pii(tier1)
    counties = [
        adapt_county(county, float(raw["median_value"]), float(raw["median_rent"]))
        for county in raw["counties"]
    ]
    counties.sort(key=lambda item: item["fips"])
    state = {
        "code": raw["code"],
        "fips": str(raw["fips"]),
        "name": raw["name"],
        "tier": 1 if raw["code"] in TIER1_STATES else 2,
        "population": float(raw["population"]),
        "pop_growth_annual": float(raw.get("pop_growth_annual") or 0),
        "housing_units": float(raw["housing_units"]),
        "vacant": float(raw["vacant"]),
        "owner_occ": float(raw["owner_occ"]),
        "renter_occ": float(raw["renter_occ"]),
        "sf_detached": float(raw["sf_detached"]),
        "sf_attached": float(raw["sf_attached"]),
        "two_unit": float(raw["two_unit"]),
        "three_four": float(raw["three_four"]),
        "five_plus": float(raw["five_plus"]),
        "mobile": float(raw["mobile"]),
        "median_value": float(raw["median_value"]),
        "median_rent": float(raw["median_rent"]),
        "median_income": float(raw["median_income"]),
        "pre1940_share": float(raw["pre1940_share"]),
        "transit_commute_share": float(raw["transit_commute_share"]),
        "land_sqmi": float(raw["land_sqmi"]),
        "bps_sf": float(raw["bps_sf"]),
        "bps_two": float(raw["bps_two"]),
        "bps_three_four": float(raw["bps_three_four"]),
        "bps_five_plus": float(raw["bps_five_plus"]),
        "cost_index_sf": float(raw["cost_index_sf"]),
        "cost_index_mf": float(raw["cost_index_mf"]),
        "fhfa_hpi_2020": float(raw["fhfa_hpi_2020"]),
        "fhfa_hpi_latest": float(raw["fhfa_hpi_latest"]),
        "fhfa_latest_year": int(raw["fhfa_latest_year"]),
        "counties": counties,
    }
    state["completeness"] = completeness_score(state, tier1)
    state["tier1"] = tier1
    validate_state(state)
    return state
