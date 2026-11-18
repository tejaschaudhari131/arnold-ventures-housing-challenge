# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Official data-source catalog and clean-room affordability, code, and stance screens.

Integrates two capabilities across all 11 Challenge states (and county selection):

1. Official Hackathon Data Hub (``official_sources_catalog`` & ``official_data_card``):
   Joins ``data/sample/official_sources.json`` (every state portal in
   ``data/DATA_SOURCES.md`` plus ACS B25004 vacancy status, BLS construction
   workforce & materials PPI, USDOT NTAD transit stops, Census Gazetteer water
   shares, and building footprint counts) with Stateframe's county fixtures.

2. Clean-room state/county screens inspired by general policy-explorer patterns
   (written from scratch under Apache-2.0 using Stateframe's pro forma equations
   and published ``config/assumptions.yaml`` parameters; zero source code or
   assets copied from external repositories):
   - HUD AMI monthly rent ceilings (30%–120% AMI) vs. before/after-reform
     cost-based breakeven rents across Backyard ADU, Missing Middle (2–6 units),
     and Transit-Oriented 4–6 Story prototypes.
   - Single-Stair Point-Access Building Code Modernization (up to 6 stories,
     <=4 units/floor) paired with BLS construction workforce absorption.
   - Five Stakeholder Priority Stances separating observed/calculated supply
     metrics from assumed value-judgment weights, with a 3.0-point caution band.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from src.data.official_sources import OFFICIAL_SOURCES_PATH, load_official_sources
from src.data.schema import CHALLENGE_STATES, ROOT, TRANSIT_PATH, load_json
from src.model.assumptions import AssumptionError, Assumptions
from src.model.engine import REFORM_IDS, SCENARIO_LABELS, simulate_state
from src.model.permits import ensure_permit_vintage
from src.model.provenance import LEGEND, stamp_tree

AMI_BANDS: tuple[int, ...] = (30, 50, 60, 80, 100, 120)

# Assumed floorplate / circulation hard-cost efficiency from allowing a single
# pressurized/sprinklered stairway on 3–6 story point-access blocks (<=4 homes
# per floor), reducing non-rentable double-loaded corridor & second-egress core.
SINGLE_STAIR_MM_COST_FACTOR = 0.915   # -8.5% per net rentable sq ft on 3-4 story multiplexes
SINGLE_STAIR_TOD_COST_FACTOR = 0.895  # -10.5% per net rentable sq ft on 4-6 story infill blocks
CAUTION_BAND_POINTS = 3.0

STANCE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "balanced",
        "label": "Balanced Supply",
        "summary": "Weights 5-year net completions first while rewarding lower breakeven rents, compact land use, and near-term feasibility.",
        "weights": {
            "kind": "assumptions",
            "supply": 0.45,
            "affordability": 0.25,
            "compact_transit": 0.15,
            "speed_fiscal": 0.15,
        },
    },
    {
        "id": "affordability",
        "label": "Workforce Affordability (<=80% AMI)",
        "summary": "Prioritizes reforms that cut per-home fee, parking, and structure costs enough to reach moderate-income renter budgets.",
        "weights": {
            "kind": "assumptions",
            "supply": 0.25,
            "affordability": 0.50,
            "compact_transit": 0.10,
            "speed_fiscal": 0.15,
        },
    },
    {
        "id": "transit_climate",
        "label": "Transit & Land Conservation",
        "summary": "Prioritizes walkshed density, infill multiplexes, and parking mandate repeal to conserve open land and reduce VMT.",
        "weights": {
            "kind": "assumptions",
            "supply": 0.15,
            "affordability": 0.10,
            "compact_transit": 0.65,
            "speed_fiscal": 0.10,
        },
    },
    {
        "id": "fiscal_light",
        "label": "Zero Municipal Revenue Loss",
        "summary": "Favors by-right zoning and parking reforms that unlock private investment without requiring municipal fee backfill.",
        "weights": {
            "kind": "assumptions",
            "supply": 0.25,
            "affordability": 0.15,
            "compact_transit": 0.15,
            "speed_fiscal": 0.45,
        },
    },
    {
        "id": "fast_delivery",
        "label": "Fastest 5-Year Delivery",
        "summary": "Prioritizes quick-turnaround gentle density (ADUs, internal conversions, and pipeline cost relief) with short build lags.",
        "weights": {
            "kind": "assumptions",
            "supply": 0.35,
            "affordability": 0.20,
            "compact_transit": 0.05,
            "speed_fiscal": 0.40,
        },
    },
)


@lru_cache(maxsize=2)
def _cached_official_doc(path_str: str) -> dict[str, Any]:
    from pathlib import Path

    return load_official_sources(Path(path_str))


@lru_cache(maxsize=4)
def _cached_lab_fmr(state_code: str) -> dict[str, dict[str, float]]:
    """Return county_fips -> {'fmr_1br': ..., 'fmr_2br': ...} for PA and NH."""
    lab_path = ROOT / "data" / "sample" / "lab" / f"{state_code}.json"
    if not lab_path.is_file():
        return {}
    doc = load_json(lab_path)
    out: dict[str, dict[str, float]] = {}
    weighted_1br = 0.0
    weighted_2br = 0.0
    total_units = 0.0
    for county in doc.get("counties", []):
        fmr = county.get("hud_fmr")
        if not isinstance(fmr, dict):
            continue
        f1 = float(fmr.get("fmr_1br") or 0.0)
        f2 = float(fmr.get("fmr_2br") or 0.0)
        if f1 > 0 and f2 > 0:
            out[str(county["fips"])] = {"fmr_1br": round(f1), "fmr_2br": round(f2)}
            units = float(((county.get("acs") or {}).get("housing_units") or {}).get("e") or 1.0)
            weighted_1br += f1 * units
            weighted_2br += f2 * units
            total_units += units
    if total_units > 0:
        out["STATE"] = {
            "fmr_1br": round(weighted_1br / total_units),
            "fmr_2br": round(weighted_2br / total_units),
        }
    return out


def _benchmark_completeness_pct(state: dict[str, Any]) -> int:
    """Convert fixture completeness (0.0–1.0 fraction or 0–100 integer) to integer percent."""
    raw = state.get("completeness")
    if raw is None:
        return 85 if int(state["tier"]) == 1 else 65
    val = float(raw)
    pct = int(round(val * 100.0)) if val <= 1.5 else int(round(val))
    return max(0, min(100, pct))


def _extended_completeness(state: dict[str, Any], off_state: dict[str, Any]) -> int:
    """Compute extended data-coverage score (0-100) after joining official portals & federal series."""
    base = _benchmark_completeness_pct(state)
    gis = off_state.get("gis") or {}
    bonus = 0
    if int(gis.get("parcel_records_observed") or 0) > 0:
        bonus += 10 if int(state["tier"]) == 2 else 4
    if int(gis.get("zoning_or_landuse_records") or 0) > 0:
        bonus += 6 if int(state["tier"]) == 2 else 3
    if off_state.get("bls_construction"):
        bonus += 3
    if off_state.get("vacancy_b25004"):
        bonus += 3
    if int(off_state.get("ntad_transit_stops") or 0) > 0:
        bonus += 2
    if int(off_state.get("microsoft_building_footprints") or 0) > 0:
        bonus += 2
    cap = 91 if gis.get("gis_status") == "live_admin_plus_gated_parcels" else 99
    return max(base, min(cap, base + bonus))


def official_sources_catalog(fixtures: dict[str, Any]) -> dict[str, Any]:
    """Return the complete 11-state + 10-family official dataset catalog with provenance tags."""
    doc = _cached_official_doc(str(OFFICIAL_SOURCES_PATH))
    transit_doc = load_json(TRANSIT_PATH)
    states_list: list[dict[str, Any]] = []
    total_gis_records = 0
    total_ntad = 0
    total_bls_jobs = 0.0

    for code in CHALLENGE_STATES:
        state = fixtures["states"][code]
        off = doc["states"][code]
        gis = off["gis"]
        vac = off["vacancy_b25004"]
        geo = off["geography"]
        bls = off["bls_construction"]
        tr = transit_doc["states"][code]
        parcels_obs = int(gis.get("parcel_records_observed") or 0)
        zoning_obs = int(gis.get("zoning_or_landuse_records") or 0)
        ntad = int(off.get("ntad_transit_stops") or 0)
        footprints = int(
            gis.get("state_gis_building_footprints") or off.get("microsoft_building_footprints") or 0
        )
        total_gis_records += parcels_obs + zoning_obs
        total_ntad += ntad
        total_bls_jobs += float(bls["jobs_latest_thousands"])

        states_list.append(
            {
                "code": code,
                "name": state["name"],
                "portal_name": off["portal"]["portal_name"],
                "portal_url": off["portal"]["portal_url"],
                "catalog_note": off["portal"]["catalog_note"],
                "gis_status": gis["gis_status"],
                "headline_finding": gis["headline_finding"],
                "endpoints": list(gis.get("endpoints") or []),
                "permit_vintage": ensure_permit_vintage(fixtures, code),
                "completeness": {
                    "kind": "calculated",
                    "tier": int(state["tier"]),
                    "benchmark_completeness": _benchmark_completeness_pct(state),
                    "extended_completeness": _extended_completeness(state, off),
                },
                "observed_metrics": {
                    "kind": "observed",
                    "housing_units": int(round(float(state["housing_units"]))),
                    "parcel_records_observed": parcels_obs,
                    "zoning_or_landuse_records": zoning_obs,
                    "ntad_transit_stops": ntad,
                    "major_rail_brt_stations": int(tr["rail_stations"]) + int(tr["brt_stations"]),
                    "building_footprints": footprints,
                    "bls_jobs_2020_thousands": float(bls["jobs_2020_thousands"]),
                    "bls_jobs_latest_thousands": float(bls["jobs_latest_thousands"]),
                    "bls_jobs_change_pct": float(bls["jobs_change_2020_2025_pct"]),
                    "vacant_total": int(round(float(vac["total_vacant"]))),
                    "vacant_market_available_share": float(vac["market_available_share"]),
                    "vacant_seasonal_share": float(vac["seasonal_share"]),
                    "vacant_non_market_share": float(vac["non_market_share"]),
                    "land_sqmi": float(geo["land_sqmi"]),
                    "water_sqmi": float(geo["water_sqmi"]),
                    "water_share": float(geo["water_share"]),
                },
            }
        )

    ppi = doc["national_bls_ppi"]
    payload: dict[str, Any] = {
        "access_date": doc["access_date"],
        "method": doc["method"],
        "provenance_legend": LEGEND,
        "handbook_families": [
            {
                "id": fam["id"],
                "name": fam["name"],
                "vintage": fam["vintage"],
                "status": fam["status"],
                "license": fam["license"],
            }
            for fam in doc["handbook_families"]
        ],
        "national_bls_ppi": {
            "kind": "observed",
            "series_id": ppi["series_id"],
            "label": ppi["label"],
            "index_2020": float(ppi["index_2020"]),
            "index_latest": float(ppi["index_latest"]),
            "latest_year": int(ppi["latest_year"]),
            "inflation_2020_latest_pct": float(ppi["inflation_2020_latest_pct"]),
        },
        "summary": {
            "kind": "calculated",
            "states_covered": len(states_list),
            "handbook_families_integrated": len(doc["handbook_families"]),
            "total_gis_records_observed": total_gis_records,
            "total_ntad_transit_stops": total_ntad,
            "total_bls_construction_jobs_thousands": round(total_bls_jobs, 1),
        },
        "states": states_list,
    }
    return stamp_tree(payload)


def _resolve_place(state: dict[str, Any], county_query: str | None) -> tuple[dict[str, Any], bool]:
    """Return (place_dict, is_county) for state or requested county."""
    if not county_query:
        return state, False
    needle = county_query.strip().lower()
    for county in state["counties"]:
        fips = str(county["fips"]).lower()
        name = str(county["name"]).lower()
        bare = name.removesuffix(" county").removesuffix(" planning region").strip()
        if needle in {fips, name, bare}:
            return county, True
    raise AssumptionError("Unknown county for selected state.")


def _lowest_ami_label(ami_pct_needed: float) -> str:
    for band in AMI_BANDS:
        if ami_pct_needed <= float(band):
            return f"{band}% AMI"
    return ">120% AMI"


def _affordability_screen(
    state: dict[str, Any],
    place: dict[str, Any],
    is_county: bool,
    params: dict[str, float],
    active_reforms: dict[str, float],
    single_stair: bool,
) -> dict[str, Any]:
    income = max(float(place["median_income"]), 1.0)
    median_rent = float(place["median_rent"])
    median_value = float(place["median_value"])
    cost_sf = float(state["cost_index_sf"]) * float(params["cost_index_shock"])
    cost_mf = float(state["cost_index_mf"]) * float(params["cost_index_shock"])

    fmr_lookup = _cached_lab_fmr(state["code"])
    fmr_entry = fmr_lookup.get(str(place["fips"]) if is_county else "STATE")

    fees_weight = min(1.0, max(0.0, float(active_reforms.get("fees", 1.0))))
    parking_weight = min(1.0, max(0.0, float(active_reforms.get("parking", 1.0))))
    adu_weight = min(1.0, max(0.0, float(active_reforms.get("adu", 1.0))))

    fee_cut_frac = float(params["fee_reduction_fraction"]) * fees_weight
    challenge_fee = float(params["fee_challenge_baseline"])
    surface_space = float(params["parking_surface_cost"]) * cost_sf
    urban_space = (
        float(params["parking_structured_share_urban"]) * float(params["parking_structured_cost"])
        + (1.0 - float(params["parking_structured_share_urban"])) * float(params["parking_surface_cost"])
    ) * cost_mf

    ami_bands = []
    for band in AMI_BANDS:
        max_rent = round((income * (band / 100.0) * 0.30) / 12.0)
        ami_bands.append(
            {
                "kind": "calculated",
                "band_pct": band,
                "label": f"{band}% AMI",
                "annual_income_ceiling": round(income * (band / 100.0)),
                "max_monthly_housing_budget": max_rent,
            }
        )

    # 1. Backyard ADU (homeowner cap-rate screen, 15% tax/insurance/maintenance allowance)
    adu_sqft = float(params["adu_sqft"])
    adu_build = adu_sqft * float(params["adu_cost_psf"]) * cost_sf * (1.0 + float(params["adu_soft_share"]))
    adu_cost_before = adu_build + challenge_fee + surface_space
    adu_fee_after_base = float(params["adu_fee_per_unit"]) if adu_weight > 0 else challenge_fee
    adu_fee_after = adu_fee_after_base * (1.0 - fee_cut_frac)
    adu_parking_after = 0.0 if (adu_weight > 0 or parking_weight > 0) else surface_space
    adu_cost_after = adu_build + adu_fee_after + adu_parking_after
    adu_cap = float(params["adu_homeowner_cap_rate"])
    adu_rent_before = (adu_cost_before * adu_cap) / 0.85 / 12.0
    adu_rent_after = (adu_cost_after * adu_cap) / 0.85 / 12.0

    # 2. Missing Middle Multiplex (2-6 units, Type V-B + optional single-stair 3-4 story efficiency)
    mm_units = max(float(params["mm_expected_units"]), 2.0)
    mm_sqft = float(params["mm_unit_sqft"])
    mm_stair_factor = SINGLE_STAIR_MM_COST_FACTOR if single_stair else 1.0
    mm_land_per_unit = (
        median_value * float(params["mm_land_share_of_value"])
        + float(params["mm_demolition_cost"]) * cost_mf
    ) / mm_units
    mm_hard_soft = (
        mm_sqft
        * float(params["mm_cost_psf"])
        * cost_mf
        * mm_stair_factor
        * (1.0 + float(params["soft_cost_share"]))
        * (1.0 + float(params["profit_ratio"]))
    )
    mm_hard_soft_before = (
        mm_sqft
        * float(params["mm_cost_psf"])
        * cost_mf
        * (1.0 + float(params["soft_cost_share"]))
        * (1.0 + float(params["profit_ratio"]))
    )
    p_sub_min = float(params["parking_p_min_suburban"])
    p_sub_mkt = float(params["parking_p_mkt_suburban"])
    p_sub_after = p_sub_min - parking_weight * max(0.0, p_sub_min - p_sub_mkt)
    mm_cost_before = mm_land_per_unit + mm_hard_soft_before + challenge_fee + p_sub_min * surface_space
    mm_cost_after = (
        mm_land_per_unit
        + mm_hard_soft
        + challenge_fee * (1.0 - fee_cut_frac)
        + p_sub_after * surface_space
    )
    cap = float(params["cap_rate"])
    net_share = max(0.25, 1.0 - float(params["opex_ratio"]))
    mm_rent_before = (mm_cost_before * cap) / net_share / 12.0
    mm_rent_after = (mm_cost_after * cap) / net_share / 12.0

    # 3. Transit-Oriented 4-6 Story Infill (podium/point-access + optional 6-story single-stair)
    tod_sqft = float(params["tod_unit_sqft"])
    tod_stair_factor = SINGLE_STAIR_TOD_COST_FACTOR if single_stair else 1.0
    tod_land_per_unit = median_value * 0.18
    tod_hard_soft_before = (
        tod_sqft
        * float(params["tod_cost_psf"])
        * cost_mf
        * (1.0 + float(params["soft_cost_share"]))
        * (1.0 + float(params["profit_ratio"]))
    )
    tod_hard_soft_after = tod_hard_soft_before * tod_stair_factor
    p_urb_min = float(params["parking_p_min_urban"])
    p_tod_after = (
        float(params["tod_parking_ratio"])
        if float(active_reforms.get("tod", 1.0)) > 0 or parking_weight > 0
        else p_urb_min
    )
    tod_cost_before = tod_land_per_unit + tod_hard_soft_before + challenge_fee + p_urb_min * urban_space
    tod_cost_after = (
        tod_land_per_unit
        + tod_hard_soft_after
        + challenge_fee * (1.0 - fee_cut_frac)
        + p_tod_after * urban_space
    )
    tod_rent_before = (tod_cost_before * cap) / net_share / 12.0
    tod_rent_after = (tod_cost_after * cap) / net_share / 12.0

    def _proto_row(
        proto_id: str,
        label: str,
        sqft: float,
        cost_b: float,
        cost_a: float,
        rent_b: float,
        rent_a: float,
        lever_note: str,
    ) -> dict[str, Any]:
        ami_b = round(100.0 * (rent_b * 12.0 / 0.30) / income, 1)
        ami_a = round(100.0 * (rent_a * 12.0 / 0.30) / income, 1)
        return {
            "id": proto_id,
            "label": label,
            "lever_note": lever_note,
            "lowest_ami_band_before": _lowest_ami_label(ami_b),
            "lowest_ami_band_after": _lowest_ami_label(ami_a),
            "metrics": {
                "kind": "calculated",
                "unit_sqft": round(sqft),
                "total_cost_before": round(cost_b),
                "total_cost_after": round(cost_a),
                "breakeven_rent_before": round(rent_b),
                "breakeven_rent_after": round(rent_a),
                "monthly_rent_savings": round(rent_b - rent_a),
                "ami_pct_needed_before": ami_b,
                "ami_pct_needed_after": ami_a,
            },
        }

    prototypes = [
        _proto_row(
            "adu",
            "Backyard ADU (Homeowner Infill)",
            adu_sqft,
            adu_cost_before,
            adu_cost_after,
            adu_rent_before,
            adu_rent_after,
            "Waives $50k municipal impact-fee poison pill to ADU fee schedule + removes off-street parking mandate.",
        ),
        _proto_row(
            "missing_middle",
            "Missing Middle Multiplex (2–6 Homes)",
            mm_sqft,
            mm_cost_before,
            mm_cost_after,
            mm_rent_before,
            mm_rent_after,
            "Splits land cost across 4 homes, cuts per-unit fees 50%, right-sizes suburban parking"
            + (", plus 8.5% single-stair efficiency." if single_stair else "."),
        ),
        _proto_row(
            "tod",
            "Transit-Oriented 4–6 Story Apartment",
            tod_sqft,
            tod_cost_before,
            tod_cost_after,
            tod_rent_before,
            tod_rent_after,
            "Eliminates structured garage minimums near transit, cuts fees 50%"
            + (", plus 10.5% 6-story single-stair core savings." if single_stair else "."),
        ),
    ]

    observed_context: dict[str, Any] = {
        "kind": "observed",
        "median_income": round(income),
        "median_rent": round(median_rent),
        "median_value": round(median_value),
    }
    if is_county and bool(place.get("value_imputed")):
        observed_context["value_imputed"] = True
    if fmr_entry:
        observed_context["hud_fmr_1br"] = int(fmr_entry["fmr_1br"])
        observed_context["hud_fmr_2br"] = int(fmr_entry["fmr_2br"])

    return {
        "geography_label": f"{place['name']}, {state['code']}" if is_county else state["name"],
        "is_county": is_county,
        "single_stair_active": single_stair,
        "scope_note": (
            "Cost-based breakeven rent screen from published pro forma inputs and observed ACS household "
            "income (30%-of-income rule). This is an underwriting cost screen, not a market-rent projection "
            "or deed-restricted covenant."
        ),
        "observed_context": observed_context,
        "ami_bands": ami_bands,
        "prototypes": prototypes,
    }


def _building_code_and_capacity(
    fixtures: dict[str, Any],
    assumptions: Assumptions,
    state_code: str,
    overrides: dict[str, Any] | None,
    reform_weights: dict[str, float] | None,
    base_sim: dict[str, Any],
    off_state: dict[str, Any],
    single_stair: bool,
) -> dict[str, Any]:
    """Compute Single-Stair 6-story code reform lift and BLS workforce absorption."""
    params = assumptions.resolve(state_code, overrides)
    stair_overrides = dict(overrides or {})
    stair_overrides["mm_cost_psf"] = float(params["mm_cost_psf"]) * SINGLE_STAIR_MM_COST_FACTOR
    stair_overrides["mm_conversion_cost_per_unit"] = (
        float(params["mm_conversion_cost_per_unit"]) * 0.92
    )
    stair_overrides["tod_cost_psf"] = float(params["tod_cost_psf"]) * SINGLE_STAIR_TOD_COST_FACTOR
    stair_sim = simulate_state(
        fixtures,
        assumptions,
        state_code,
        overrides=stair_overrides,
        reform_weights=reform_weights,
        with_decomposition=False,
    )

    base_pkg = float(base_sim["scenarios"]["combined"]["incremental_completions"])
    stair_pkg = float(stair_sim["scenarios"]["combined"]["incremental_completions"])
    stair_extra_pkg = max(0.0, stair_pkg - base_pkg)
    mm_extra = max(
        0.0,
        float(stair_sim["scenarios"]["missing_middle"]["incremental_completions"])
        - float(base_sim["scenarios"]["missing_middle"]["incremental_completions"]),
    )
    tod_extra = max(
        0.0,
        float(stair_sim["scenarios"]["tod"]["incremental_completions"])
        - float(base_sim["scenarios"]["tod"]["incremental_completions"]),
    )

    active_pkg = stair_pkg if single_stair else base_pkg
    baseline_5yr = max(1.0, float(base_sim["baseline_completions_5yr"]))
    annual_baseline = baseline_5yr / 5.0
    annual_extra = active_pkg / 5.0

    bls = off_state["bls_construction"]
    workers_thousands = max(0.1, float(bls["jobs_latest_thousands"]))
    baseline_per_1k = round(annual_baseline / workers_thousands, 2)
    extra_per_1k = round(annual_extra / workers_thousands, 2)
    annual_lift_pct = round(100.0 * annual_extra / annual_baseline, 1)

    if annual_lift_pct < 18.0 and extra_per_1k < 18.0:
        strain_tier = "Low workforce strain (within normal residential trade capacity)"
    elif annual_lift_pct <= 36.0 and extra_per_1k <= 32.0:
        strain_tier = "Moderate workforce ramp (absorbable with steady trade hiring)"
    else:
        strain_tier = "High workforce utilization (pair zoning with modular/off-site & trade apprenticeship capacity)"

    return {
        "single_stair_active": single_stair,
        "code_reform_title": "Single-Stair Point-Access Building Code Reform (IBC up to 6 Stories)",
        "code_reform_mechanism": (
            "Modernizes state building code so sprinklered 3–6 story residential blocks (<=4 units per floor) "
            "require one pressurized stairway instead of two stairwells and a long hotel-style corridor, "
            "improving net-to-gross floorplate efficiency on small urban and transit lots."
        ),
        "assumptions_used": {
            "kind": "assumptions",
            "mm_hard_cost_multiplier": SINGLE_STAIR_MM_COST_FACTOR,
            "tod_hard_cost_multiplier": SINGLE_STAIR_TOD_COST_FACTOR,
            "max_stories_modeled": 6,
            "max_units_per_floor": 4,
        },
        "single_stair_impact": {
            "kind": "calculated",
            "package_homes_without_single_stair": round(base_pkg),
            "package_homes_with_single_stair": round(stair_pkg),
            "incremental_homes_from_single_stair": round(stair_extra_pkg),
            "missing_middle_standalone_lift": round(mm_extra),
            "tod_standalone_lift": round(tod_extra),
        },
        "workforce_capacity": {
            "sector_note": bls["sector_note"],
            "labor_strain_tier": strain_tier,
            "observed_bls": {
                "kind": "observed",
                "bls_jobs_2020_thousands": float(bls["jobs_2020_thousands"]),
                "bls_jobs_latest_thousands": float(bls["jobs_latest_thousands"]),
                "bls_jobs_change_2020_2025_pct": float(bls["jobs_change_2020_2025_pct"]),
            },
            "absorption_metrics": {
                "kind": "calculated",
                "annual_baseline_completions": round(annual_baseline),
                "annual_reform_incremental_completions": round(annual_extra),
                "baseline_homes_per_1k_workers": baseline_per_1k,
                "incremental_homes_per_1k_workers": extra_per_1k,
                "annual_supply_lift_pct": annual_lift_pct,
            },
        },
    }


def _priority_stances(
    base_sim: dict[str, Any],
    affordability: dict[str, Any],
) -> dict[str, Any]:
    """Rank the 5 benchmark reforms across 5 explicit value-judgment stances with a 3-point caution band."""
    scenarios = base_sim["scenarios"]
    net_by_id = {
        rid: max(0.0, float(scenarios[rid]["incremental_completions"]))
        for rid in REFORM_IDS
    }
    max_net = max(max(net_by_id.values()), 1.0)

    proto_by_id = {p["id"]: p["metrics"] for p in affordability["prototypes"]}
    adu_ami = float(proto_by_id["adu"]["ami_pct_needed_after"])
    mm_ami = float(proto_by_id["missing_middle"]["ami_pct_needed_after"])
    tod_ami = float(proto_by_id["tod"]["ami_pct_needed_after"])

    def _afford_from_ami(ami_val: float) -> float:
        return round(min(96.0, max(25.0, 130.0 - 0.72 * ami_val)), 1)

    # Policy-design sub-scores: supply is calculated from county pro formas;
    # compact_transit and speed_fiscal reflect documented mechanism attributes.
    criteria_by_reform: dict[str, dict[str, float]] = {
        "adu": {
            "supply": round(100.0 * net_by_id["adu"] / max_net, 1),
            "affordability": _afford_from_ami(adu_ami),
            "compact_transit": 52.0,
            "speed_fiscal": 94.0,
        },
        "missing_middle": {
            "supply": round(100.0 * net_by_id["missing_middle"] / max_net, 1),
            "affordability": _afford_from_ami(mm_ami),
            "compact_transit": 84.0,
            "speed_fiscal": 80.0,
        },
        "tod": {
            "supply": round(100.0 * net_by_id["tod"] / max_net, 1),
            "affordability": _afford_from_ami(tod_ami),
            "compact_transit": 98.0,
            "speed_fiscal": 56.0,
        },
        "parking": {
            "supply": round(100.0 * net_by_id["parking"] / max_net, 1),
            "affordability": 84.0,
            "compact_transit": 90.0,
            "speed_fiscal": 92.0,
        },
        "fees": {
            "supply": round(100.0 * net_by_id["fees"] / max_net, 1),
            "affordability": 94.0,
            "compact_transit": 50.0,
            "speed_fiscal": 48.0,
        },
    }

    stances_out: list[dict[str, Any]] = []
    for stance in STANCE_DEFINITIONS:
        w = stance["weights"]
        rankings = []
        for rid in REFORM_IDS:
            c = criteria_by_reform[rid]
            composite = round(
                float(w["supply"]) * c["supply"]
                + float(w["affordability"]) * c["affordability"]
                + float(w["compact_transit"]) * c["compact_transit"]
                + float(w["speed_fiscal"]) * c["speed_fiscal"],
                1,
            )
            rankings.append(
                {
                    "id": rid,
                    "label": SCENARIO_LABELS[rid],
                    "scores": {
                        "kind": "calculated",
                        "composite_score": composite,
                        "net_completions_5yr": round(net_by_id[rid]),
                        "supply_score": c["supply"],
                        "affordability_score": c["affordability"],
                        "compact_transit_score": c["compact_transit"],
                        "speed_fiscal_score": c["speed_fiscal"],
                    },
                }
            )
        rankings.sort(key=lambda item: (-item["scores"]["composite_score"], item["id"]))
        top_gap = round(
            rankings[0]["scores"]["composite_score"] - rankings[1]["scores"]["composite_score"],
            1,
        )
        close = top_gap <= CAUTION_BAND_POINTS
        caution_note = (
            f"Too close to call: #{1} {rankings[0]['label']} and #{2} {rankings[1]['label']} "
            f"sit within {top_gap:.1f} points (<= {CAUTION_BAND_POINTS:.0f}-point caution band). "
            "Treat them as co-priorities rather than a strict winner."
            if close
            else f"{rankings[0]['label']} leads {rankings[1]['label']} by {top_gap:.1f} points under this stance."
        )
        stances_out.append(
            {
                "id": stance["id"],
                "label": stance["label"],
                "summary": stance["summary"],
                "too_close_to_call": close,
                "caution_note": caution_note,
                "weights": dict(stance["weights"]),
                "margin": {
                    "kind": "calculated",
                    "top_two_point_gap": top_gap,
                    "caution_threshold_points": CAUTION_BAND_POINTS,
                },
                "rankings": rankings,
            }
        )

    return {
        "methodology_note": (
            "Separates Calculated Supply/Cost Outputs from Assumed Value Judgments: changing the priority "
            "stance re-weights criteria without altering a single underlying housing completion number."
        ),
        "stances": stances_out,
    }


def build_state_insights(
    fixtures: dict[str, Any],
    assumptions: Assumptions,
    state_code: str,
    county: str | None = None,
    overrides: dict[str, Any] | None = None,
    reform_weights: dict[str, float] | None = None,
    single_stair: bool = False,
) -> dict[str, Any]:
    """Build combined official-dataset, AMI breakeven, single-stair, and stance insights."""
    code = state_code.strip().upper()
    if code not in fixtures["states"]:
        raise AssumptionError("Unknown state.")
    state = fixtures["states"][code]
    place, is_county = _resolve_place(state, county)
    params = assumptions.resolve(code, overrides)

    active_reforms = {rid: 1.0 for rid in REFORM_IDS}
    if reform_weights is not None:
        for rid in REFORM_IDS:
            if rid in reform_weights:
                active_reforms[rid] = float(reform_weights[rid])

    base_sim = simulate_state(
        fixtures,
        assumptions,
        code,
        overrides=overrides,
        reform_weights=reform_weights,
        with_decomposition=False,
    )

    off_doc = _cached_official_doc(str(OFFICIAL_SOURCES_PATH))
    off_state = off_doc["states"][code]
    transit_state = load_json(TRANSIT_PATH)["states"][code]
    gis = off_state["gis"]
    vac = off_state["vacancy_b25004"]
    geo = off_state["geography"]
    bls = off_state["bls_construction"]
    ppi = off_doc["national_bls_ppi"]

    footprints = int(
        gis.get("state_gis_building_footprints") or off_state.get("microsoft_building_footprints") or 0
    )
    hu = max(1.0, float(state["housing_units"]))

    official_data_card = {
        "portal_name": off_state["portal"]["portal_name"],
        "portal_url": off_state["portal"]["portal_url"],
        "catalog_note": off_state["portal"]["catalog_note"],
        "gis_status": gis["gis_status"],
        "headline_finding": gis["headline_finding"],
        "endpoints": list(gis.get("endpoints") or []),
        "permit_vintage": ensure_permit_vintage(fixtures, code),
        "completeness": {
            "kind": "calculated",
            "tier": int(state["tier"]),
            "benchmark_completeness": _benchmark_completeness_pct(state),
            "extended_completeness": _extended_completeness(state, off_state),
            "footprints_per_housing_unit": round(footprints / hu, 2),
        },
        "observed": {
            "kind": "observed",
            "parcel_records_observed": int(gis.get("parcel_records_observed") or 0),
            "zoning_or_landuse_records": int(gis.get("zoning_or_landuse_records") or 0),
            "ntad_transit_stops": int(off_state.get("ntad_transit_stops") or 0),
            "rail_stations": int(transit_state["rail_stations"]),
            "brt_stations": int(transit_state["brt_stations"]),
            "frequent_bus_route_miles": int(transit_state["frequent_bus_route_miles"]),
            "building_footprints": footprints,
            "vacant_total": int(round(float(vac["total_vacant"]))),
            "vacant_for_rent": int(round(float(vac["for_rent"]))),
            "vacant_for_sale": int(round(float(vac["for_sale"]))),
            "vacant_seasonal": int(round(float(vac["seasonal"]))),
            "vacant_other": int(round(float(vac["other_vacant"]))),
            "vacant_market_available_share": float(vac["market_available_share"]),
            "vacant_seasonal_share": float(vac["seasonal_share"]),
            "vacant_non_market_share": float(vac["non_market_share"]),
            "land_sqmi": float(geo["land_sqmi"]),
            "water_sqmi": float(geo["water_sqmi"]),
            "water_share": float(geo["water_share"]),
            "bls_jobs_latest_thousands": float(bls["jobs_latest_thousands"]),
            "bls_jobs_change_2020_2025_pct": float(bls["jobs_change_2020_2025_pct"]),
            "national_ppi_inflation_2020_latest_pct": float(ppi["inflation_2020_latest_pct"]),
        },
    }

    affordability = _affordability_screen(
        state, place, is_county, params, active_reforms, single_stair=single_stair
    )
    code_capacity = _building_code_and_capacity(
        fixtures,
        assumptions,
        code,
        overrides,
        reform_weights,
        base_sim,
        off_state,
        single_stair=single_stair,
    )
    stances = _priority_stances(base_sim, affordability)

    result: dict[str, Any] = {
        "state": code,
        "state_name": state["name"],
        "selected_county_fips": str(place["fips"]) if is_county else None,
        "selected_geography": affordability["geography_label"],
        "provenance_legend": LEGEND,
        "official_data_card": official_data_card,
        "affordability_screen": affordability,
        "building_code_and_capacity": code_capacity,
        "priority_stances": stances,
    }
    return stamp_tree(result)
