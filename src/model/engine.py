# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""County pro formas, summed to the state.

The official result for every scenario is the sum of county results. A
state-average pro forma is reported only as a cross-check, because feasibility
is nonlinear: the average of county results is not the result at the average
county. See ``resolution="state"`` for that cruder screen.

Baseline production is the 2022–2024 Building Permits Survey run-rate extended
over the challenge's 5-year horizon. Policy scenarios add units on top of that
baseline. They do not replace it. Net completions subtract homes demolished
by a teardown or a TOD rebuild. Permits count every unit in the new building,
including replacements.
"""

from __future__ import annotations

from typing import Any

from src.model.provenance import LEGEND, stamp_tree
from src.model.equations import (
    adu_hazard,
    cumulative_hazard,
    elasticity_increment,
    far_net_multiplier,
    feasibility_share,
    horizon_multiplier,
    largest_remainder,
    lognormal_tail,
    margin_from_value,
    parking_yield_fraction,
    rental_value,
    sale_value_per_unit,
    share_at_least,
    walkshed_sqmi,
)

REFORM_IDS = ("adu", "missing_middle", "tod", "parking", "fees")

SCENARIO_ORDER = (
    "baseline",
    "adu",
    "missing_middle",
    "tod",
    "parking",
    "fees",
    "combined",
)

SCENARIO_LABELS = {
    "baseline": "Baseline",
    "adu": "1. Accessory dwelling units",
    "missing_middle": "2. Missing middle",
    "tod": "3. Transit-oriented density",
    "parking": "4. Parking reform",
    "fees": "5. Fee reduction",
    "combined": "Combined package",
}

CANNOT = {
    "baseline": [
        "The baseline is a run-rate, not a forecast of the business cycle. It holds the recent permit mix fixed except for the trend slider.",
        "It cannot tell you how many of today's permitted units are already in a pipeline that will be cancelled if prices fall.",
        "It does not allocate production to individual parcels or to specific developers.",
    ],
    "adu": [
        "It cannot tell you which homeowners will borrow, pass a design review, or want a tenant on their lot. The adoption hazard is the stand-in for that behavior, and it dominates the result.",
        "It cannot price an individual lot's setbacks, slope, or septic capacity. Physical feasibility is a lot-size screen, and the benchmark assumes that screen is the only physical constraint.",
        "It cannot tell you the rent an ADU will actually achieve, or how much of the new unit is used by family instead of adding to the rental stock.",
        "Where a state already legalized ADUs, the result is only the residual gap between current law and this benchmark. It is not the effect of the earlier law.",
    ],
    "missing_middle": [
        "It cannot tell you that legalizing 2–6 units will produce 2–6 units. In most counties a teardown of a sound house does not clear a 3-story pro forma. Near-term units come from the conversion tail, not from rebuilding the median house.",
        "It cannot time infrastructure, school capacity, or neighborhood opposition. The pace hazard is a construction-industry speed limit, not a political one.",
        "It assumes, as the benchmark allows, that setbacks and lot coverage do not further limit 2–6 units. If a city keeps those rules, this pathway is smaller.",
        "It does not estimate price effects on existing neighbors. There is no equilibrium price feedback inside the five-year window beyond the absorption cap.",
    ],
    "tod": [
        "It cannot draw a true walkshed. Station counts are a screened public inventory, and homes are placed in that area with an assumed urban density rather than a parcel-to-station join.",
        "It cannot tell you which buildings are historic, which lots are owned by a transit agency, or which corridors have the water and sewer capacity for a mid-rise.",
        "A higher FAR that does not clear the podium cost produces no units. The model will say so, including in expensive states where construction cost is as high as the price.",
        "It does not count intercity Amtrak stops as major transit. New Hampshire's near-zero result is that definition, not a missing file.",
    ],
    "parking": [
        "It cannot observe the parking ratio a developer would choose project by project. The market ratios are assumptions by urban, suburban, and rural context.",
        "It does not model spillover parking on local streets, mode shift, or retail parking. Those are real political constraints and they are outside the housing-unit outcome.",
        "Where the market ratio is already below a weak mandate, or the mandate is already near what buyers demand, the scenario correctly produces little.",
    ],
    "fees": [
        "The $50,000 fee stack is the challenge's comparability assumption. It is not a measurement of what each state charges today. Real fees vary widely, and the scenario will misstate a state whose fees are already far from $50,000.",
        "It applies the cost shock to the baseline pipeline only. It does not redesign zoning. Projects that are illegal under current zoning do not appear here; they appear in the zoning scenarios.",
        "It cannot say who captures the $25,000: a lower price, a higher land bid, or a developer margin. The elasticity splits that dollar into extra units. The rest is incidence, which this model does not solve.",
    ],
    "combined": [
        "The package is not the sum of the five scenarios. Walkshed parcels take the TOD envelope, missing middle is what remains outside it, and ADUs are what remains on homes that were not converted or rebuilt.",
        "Fee and parking savings inside the package are applied in the pro formas. Adding the standalone fee and parking totals on top of that would double-count.",
        "It cannot tell you the political bundle a legislature will actually pass, or the order in which rules take effect inside the five years.",
    ],
}


def _fmt(value: float, digits: int = 0) -> str:
    if abs(value) >= 100:
        return f"{value:,.{digits}f}"
    return f"{value:,.2f}"


def _step(
    title: str,
    equation: str,
    substitution: str,
    result: float,
    unit: str,
    why: str,
    inputs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    row = {
        "title": title,
        "equation": equation,
        "substitution": substitution,
        "result": result,
        "unit": unit,
        "why": why,
    }
    if inputs:
        row["inputs"] = inputs
    return row


def _tagged(label: str, tag: str) -> dict[str, str]:
    return {"label": label, "tag": tag}


def lot_feasibility(state: dict[str, Any], params: dict[str, float], parcel_mode: str) -> tuple[float, str, str]:
    """Physical share of single-family lots that can hold a semi-detached ADU.

    Observed bins win when the state has them and the caller asked for the
    full tier-1 inputs. A mean without bins uses the documented lognormal.
    Otherwise the share is the published imputation.
    """
    tier1 = state.get("tier1") or {}
    cutoff = params["adu_semi_min_lot_sqft"]
    bins = tier1.get("lot_bins_sqft") if parcel_mode == "observed" else None
    if bins:
        return (
            share_at_least(bins, cutoff),
            "Observed lot-size bins from the statewide parcel extract",
            "calculated",
        )
    mean_lot = tier1.get("mean_lot_sqft") if parcel_mode == "observed" else None
    if mean_lot:
        share = lognormal_tail(float(mean_lot), params["lot_size_log_sigma"], cutoff)
        return share, "Lognormal tail from the observed mean lot size (bins were not published)", "calculated"
    return (
        params["imputed_lot_feasible_share"],
        "Imputed from the tier-1 screening share. This state has no lot-size extract in the model.",
        "assumed",
    )


def _context(county: dict[str, Any], params: dict[str, float]) -> str:
    land = county["land_sqmi"]
    density = county["housing_units"] / land if land > 0 else 0.0
    if county["transit_commute_share"] >= params["urban_transit_share"] or density >= params["urban_density_threshold"]:
        return "urban"
    if density >= params["suburban_density_threshold"]:
        return "suburban"
    return "rural"


def _space_cost(context: str, params: dict[str, float], index: float) -> float:
    surface = params["parking_surface_cost"] * index
    if context != "urban":
        return surface
    structured = params["parking_structured_cost"] * index
    share = params["parking_structured_share_urban"]
    return share * structured + (1.0 - share) * surface


def _owner_share(county: dict[str, Any]) -> float:
    occupied = county["owner_occ"] + county["renter_occ"]
    if occupied <= 0:
        return 0.65
    return county["owner_occ"] / occupied


def prepare_geographies(
    state: dict[str, Any],
    resolution: str,
) -> list[dict[str, Any]]:
    """County rows, or one synthetic statewide row for the tier-2 state screen."""
    if resolution == "county":
        return list(state["counties"])
    screen = {
        "fips": state["fips"] + "000",
        "name": f"{state['name']} statewide screen",
        "land_sqmi": state["land_sqmi"],
        "population": state["population"],
        "housing_units": state["housing_units"],
        "vacant": state["vacant"],
        "owner_occ": state["owner_occ"],
        "renter_occ": state["renter_occ"],
        "sf_detached": state["sf_detached"],
        "sf_attached": state["sf_attached"],
        "two_unit": state["two_unit"],
        "three_four": state["three_four"],
        "five_plus": state["five_plus"],
        "mobile": state["mobile"],
        "median_value": state["median_value"],
        "median_rent": state["median_rent"],
        "median_income": state["median_income"],
        "pre1940_share": state["pre1940_share"],
        "transit_commute_share": state["transit_commute_share"],
        "value_imputed": False,
        "bps_sf": state["bps_sf"],
        "bps_two": state["bps_two"],
        "bps_three_four": state["bps_three_four"],
        "bps_five_plus": state["bps_five_plus"],
        "bps_reporting": True,
    }
    return [screen]


def allocate_walkshed(counties: list[dict[str, Any]], shed_sqmi: float, density: float) -> list[float]:
    """Place walkshed homes in counties in proportion to transit commuting.

    The product of transit-commute share and housing units is a stand-in for
    where frequent transit actually is. Each county is then capped at its own
    housing stock so a small county cannot be assigned more homes than it has.
    """
    capacity = max(0.0, shed_sqmi) * max(0.0, density)
    weights = [max(county["transit_commute_share"], 0.0) * county["housing_units"] for county in counties]
    weight_sum = sum(weights)
    if weight_sum <= 0 or capacity <= 0:
        return [0.0 for _ in counties]
    allocated = []
    for county, weight in zip(counties, weights):
        raw = capacity * weight / weight_sum
        allocated.append(min(raw, county["housing_units"]))
    return allocated


def _baseline(county: dict[str, Any], params: dict[str, float]) -> dict[str, float]:
    factor = horizon_multiplier(params["permit_growth_rate"], params["horizon_years"])
    permits = {
        "sf": county["bps_sf"] * factor,
        "small": (county["bps_two"] + county["bps_three_four"]) * factor,
        "mf": county["bps_five_plus"] * factor,
    }
    completions = {
        "sf": permits["sf"] * params["completion_ratio_sf"],
        "small": permits["small"] * params["completion_ratio_small"],
        "mf": permits["mf"] * params["completion_ratio_mf"],
    }
    permits["total"] = permits["sf"] + permits["small"] + permits["mf"]
    completions["total"] = completions["sf"] + completions["small"] + completions["mf"]
    return {"permits": permits, "completions": completions}


def _prices(county: dict[str, Any], params: dict[str, float]) -> tuple[float, float]:
    shock = params["price_shock"]
    return county["median_value"] * shock, county["median_rent"] * shock


def evaluate_county(
    county: dict[str, Any],
    params: dict[str, float],
    indexes: dict[str, float],
    national: dict[str, float],
    lot_share: float,
    walkshed_units: float,
    package: bool,
    explain: bool,
) -> dict[str, Any]:
    """One county, one fee/parking regime.

    ``package=False`` is the standalone pro forma (each zoning reform on its
    own, fees at the segment assumption, missing-middle parking still mandated).
    ``package=True`` cuts segment fees and lets missing-middle parking fall to
    the market ratio. Overlap across reforms is applied by the caller.
    """
    context = _context(county, params)
    value, rent = _prices(county, params)
    sf_index = indexes["sf"]
    mf_index = indexes["mf"]
    small_index = 0.5 * (sf_index + mf_index)
    space = _space_cost(context, params, mf_index if context == "urban" else sf_index)
    p_min = params[f"parking_p_min_{context}"]
    p_mkt = min(params[f"parking_p_mkt_{context}"], p_min)
    fee_factor = (1.0 - params["fee_reduction_fraction"]) if package else 1.0
    mm_spaces = p_mkt if package else p_min
    baseline = _baseline(county, params)
    sigma = params["feasibility_sigma"]
    threshold = params["feasibility_threshold"]
    owner = _owner_share(county)

    # --- ADU -----------------------------------------------------------------
    sf_stock = county["sf_detached"] + params["adu_attached_eligible_share"] * county["sf_attached"]
    sf_stock *= params["geography_eligible_share"]
    tenure = owner * params["adu_owner_weight"] + (1.0 - owner) * params["adu_landlord_weight"]
    legal_gap = 1.0 - params["adu_already_legal_share"]
    eligible = sf_stock * legal_gap * tenure * lot_share
    hard = params["adu_cost_psf"] * sf_index * params["adu_sqft"]
    soft = hard * params["adu_soft_share"]
    fee = params["adu_fee_per_unit"] * fee_factor
    # The benchmark ADU includes the parking waiver, standalone and combined.
    adu_cost = hard + soft + fee
    homeowner_value = rental_value(rent * params["adu_rent_ratio"], params["adu_homeowner_cap_rate"], 0.0)
    market_sale = sale_value_per_unit(
        value, params["reference_sf_sqft"], params["adu_sqft"], params["new_construction_premium"]
    )
    adu_value = max(homeowner_value, market_sale)
    adu_margin = margin_from_value(adu_value, adu_cost)
    hazard = adu_hazard(params["adu_hazard0"], params["adu_hazard_beta"], adu_margin, params["adu_hazard_max"])
    adoption = cumulative_hazard(hazard, params["horizon_years"])
    adu_raw_permits = eligible * adoption
    adu_cap = eligible * params["adu_stock_cap_share"]
    adu_capped = adu_raw_permits > adu_cap + 1e-6 and adu_cap >= 0
    adu_permits = min(adu_raw_permits, adu_cap)
    adu_completions = adu_permits * params["completion_ratio_adu"]
    adu_capacity = adu_raw_permits * params["completion_ratio_adu"]

    # --- Missing middle: teardown, then conversion on what remains ----------
    sf_homes = county["sf_detached"] * params["geography_eligible_share"]
    mm_gap = 1.0 - params["mm_already_legal_share"]
    pace = cumulative_hazard(params["mm_pace_hazard"], params["horizon_years"])
    obsolete = sf_homes * county["pre1940_share"] * params["mm_obsolete_share_of_older_stock"] * mm_gap
    units_per = params["mm_expected_units"]
    hard_t = params["mm_cost_psf"] * small_index * params["mm_unit_sqft"] * units_per
    soft_t = hard_t * params["soft_cost_share"]
    fee_t = params["mm_fee_per_unit"] * fee_factor * units_per
    park_t = mm_spaces * space * units_per
    profit_t = params["profit_ratio"] * (hard_t + soft_t)
    all_in_t = hard_t + soft_t + fee_t + park_t + params["mm_demolition_cost"] + profit_t
    sale_unit = sale_value_per_unit(value, params["reference_sf_sqft"], params["mm_unit_sqft"], params["new_construction_premium"])
    rent_unit = rental_value(rent * 0.95, params["cap_rate"], params["opex_ratio"])
    teardown_revenue = max(sale_unit, rent_unit) * units_per
    opportunity = value * params["mm_land_share_of_value"]
    if opportunity > 1.0:
        teardown_margin = (teardown_revenue - all_in_t - opportunity) / opportunity
    else:
        teardown_margin = margin_from_value(teardown_revenue, all_in_t)
    teardown_feas = feasibility_share(teardown_margin, threshold, sigma)
    teardown_parcels = obsolete * teardown_feas * pace
    teardown_net = teardown_parcels * max(0.0, units_per - 1.0)
    teardown_permits = teardown_parcels * units_per

    convertible = sf_homes * mm_gap * params["mm_conversion_eligible_share"]
    convertible = max(0.0, convertible - teardown_parcels)
    added = params["mm_conversion_added_units"]
    conv_sqft = params["mm_conversion_sqft"]
    hard_c = params["mm_conversion_cost_per_unit"] * small_index * added
    soft_c = hard_c * params["soft_cost_share"]
    fee_c = params["mm_fee_per_unit"] * fee_factor * added
    park_c = mm_spaces * space * added
    profit_c = params["profit_ratio"] * (hard_c + soft_c)
    conv_cost = hard_c + soft_c + fee_c + park_c + profit_c
    conv_unit_value = max(
        sale_value_per_unit(value, params["reference_sf_sqft"], conv_sqft, params["new_construction_premium"]),
        rental_value(rent * 0.9, params["cap_rate"], params["opex_ratio"]),
    )
    conv_margin = margin_from_value(conv_unit_value * added, conv_cost)
    conv_feas = feasibility_share(conv_margin, threshold, sigma)
    conv_homes = convertible * conv_feas * pace
    conv_net = conv_homes * added
    mm_net = teardown_net + conv_net
    mm_permits = teardown_permits + conv_net
    mm_completions = mm_net * params["completion_ratio_small"]
    mm_permits_completed_scale = mm_permits * params["completion_ratio_small"]
    homes_used_mm = teardown_parcels + conv_homes

    # --- TOD -----------------------------------------------------------------
    candidate = walkshed_units * params["tod_redevelop_fraction"]
    hard_d = params["tod_cost_psf"] * mf_index * params["tod_unit_sqft"]
    soft_d = hard_d * params["soft_cost_share"]
    fee_d = params["tod_fee_per_unit"] * fee_factor
    park_d = params["tod_parking_ratio"] * space
    profit_d = params["profit_ratio"] * (hard_d + soft_d)
    tod_cost = hard_d + soft_d + fee_d + park_d + profit_d
    premium = 1.0 + params["tod_transit_premium"]
    tod_unit_value = max(
        sale_value_per_unit(value, params["reference_sf_sqft"], params["tod_unit_sqft"], params["new_construction_premium"]) * premium,
        rental_value(rent * premium, params["cap_rate"], params["opex_ratio"]),
    )
    tod_margin = margin_from_value(tod_unit_value, tod_cost)
    tod_feas = feasibility_share(tod_margin, threshold, sigma)
    net_per = far_net_multiplier(params["tod_far_existing"], params["tod_far_policy"])
    # No envelope increase means the reform does not induce a rebuild.
    # Replacement permits for an unchanged FAR are not an incremental outcome.
    rebuilt = 0.0 if net_per <= 0.0 else candidate * tod_feas * pace
    tod_net = rebuilt * net_per
    tod_permits = rebuilt * (net_per + 1.0)
    tod_completions = tod_net * params["completion_ratio_mf"]

    # --- Parking and fees on the baseline pipeline --------------------------
    def pipeline_increment(segment: str, hard_per_unit: float, unit_sqft: float, constrained: float, segment_fee: float) -> dict[str, float]:
        base_permits = baseline["permits"][segment]
        soft_cost = hard_per_unit * params["soft_cost_share"]
        mandated_parking = p_min * space
        cost_base = hard_per_unit + soft_cost + mandated_parking + segment_fee
        spaces_saved = p_min - p_mkt
        parking_savings = spaces_saved * space
        fee_savings = params["fee_challenge_baseline"] * params["fee_reduction_fraction"]
        # Fee denominator uses the challenge stack, not the lower segment fee,
        # because scenario 5 is defined on the $50,000 comparability case.
        fee_cost_base = hard_per_unit + soft_cost + mandated_parking + params["fee_challenge_baseline"]
        park_units = elasticity_increment(base_permits, parking_savings, cost_base, params["supply_elasticity"])
        park_units += base_permits * parking_yield_fraction(
            spaces_saved, params["parking_sqft_per_space"], unit_sqft, p_mkt, constrained
        )
        fee_units = elasticity_increment(base_permits, fee_savings, fee_cost_base, params["supply_elasticity"])
        return {"parking_permits": max(0.0, park_units), "fee_permits": max(0.0, fee_units)}

    constrained = {
        "urban": params["parking_constrained_urban"],
        "suburban": params["parking_constrained_suburban"],
        "rural": params["parking_constrained_rural"],
    }[context]
    sf_hard = national["sf_permit_value"] * sf_index
    mf_hard = national["mf_permit_value"] * mf_index
    small_hard = params["mm_cost_psf"] * small_index * params["mm_unit_sqft"]
    pipelines = {
        "sf": pipeline_increment("sf", sf_hard, params["reference_sf_sqft"], constrained * 0.25, params["sf_fee_per_unit"]),
        "small": pipeline_increment("small", small_hard, params["mm_unit_sqft"], constrained * 0.6, params["mm_fee_per_unit"]),
        "mf": pipeline_increment("mf", mf_hard, params["tod_unit_sqft"], constrained, params["tod_fee_per_unit"]),
    }
    parking_permits = sum(item["parking_permits"] for item in pipelines.values())
    fee_permits = sum(item["fee_permits"] for item in pipelines.values())
    # Completion ratios follow the segment mix of the increment.
    def _complete(kind: str) -> float:
        total = 0.0
        ratios = {"sf": params["completion_ratio_sf"], "small": params["completion_ratio_small"], "mf": params["completion_ratio_mf"]}
        for segment, ratio in ratios.items():
            total += pipelines[segment][kind] * ratio
        return total

    parking_completions = _complete("parking_permits")
    fee_completions = _complete("fee_permits")

    merchant_cap = max(
        baseline["completions"]["total"] * params["absorption_ratio"],
        county["housing_units"] * 0.002 * params["absorption_ratio"],
    )

    result = {
        "fips": county["fips"],
        "name": county["name"],
        "context": context,
        "baseline": baseline,
        "adu_permits": adu_permits,
        "adu_completions": adu_completions,
        "adu_capacity": adu_capacity,
        "adu_capped": adu_capped,
        "adu_eligible": eligible,
        "adu_margin": adu_margin,
        "mm_permits": mm_permits,
        "mm_completions": mm_completions,
        "mm_net": mm_net,
        "mm_homes_used": homes_used_mm,
        "teardown_net": teardown_net,
        "conversion_net": conv_net,
        "teardown_margin": teardown_margin,
        "conversion_margin": conv_margin,
        "tod_permits": tod_permits,
        "tod_completions": tod_completions,
        "tod_net": tod_net,
        "tod_homes_removed": rebuilt,
        "tod_margin": tod_margin,
        "walkshed_units": walkshed_units,
        "parking_permits": parking_permits,
        "parking_completions": parking_completions,
        "fee_permits": fee_permits,
        "fee_completions": fee_completions,
        "merchant_cap": merchant_cap,
        "sf_stock": sf_stock,
        "housing_units": county["housing_units"],
        "trace_inputs": {
            "eligible_adus": eligible,
            "adu_cost": adu_cost,
            "adu_value": adu_value,
            "adu_margin": adu_margin,
            "hazard": hazard,
            "adoption": adoption,
            "hard": hard,
            "soft": soft,
            "fee": fee,
            "homeowner_value": homeowner_value,
            "market_sale": market_sale,
            "sf_stock": sf_stock,
            "legal_gap": legal_gap,
            "tenure": tenure,
            "lot_share": lot_share,
            "teardown_margin": teardown_margin,
            "teardown_feas": teardown_feas,
            "obsolete": obsolete,
            "teardown_net": teardown_net,
            "conv_margin": conv_margin,
            "conv_feas": conv_feas,
            "convertible": convertible + teardown_parcels,
            "conv_net": conv_net,
            "tod_margin": tod_margin,
            "tod_feas": tod_feas,
            "candidate": candidate,
            "net_per": net_per,
            "tod_net": tod_net,
            "tod_cost": tod_cost,
            "tod_unit_value": tod_unit_value,
            "rebuilt": rebuilt,
            "p_min": p_min,
            "p_mkt": p_mkt,
            "space": space,
            "parking_permits": parking_permits,
            "fee_permits": fee_permits,
            "fee_savings": params["fee_challenge_baseline"] * params["fee_reduction_fraction"],
            "merchant_cap": merchant_cap,
            "value": value,
            "rent": rent,
            "context": context,
        },
    }
    if explain:
        result["steps_ready"] = True
    else:
        result.pop("trace_inputs", None)
    result["_complete_mm_check"] = mm_permits_completed_scale
    return result


def _cap_pair(primary: float, secondary: float, cap: float) -> tuple[float, float, bool]:
    """Scale two merchant pathways so they share one absorption cap."""
    total = primary + secondary
    if total <= cap or total <= 0:
        return primary, secondary, False
    scale = cap / total
    return primary * scale, secondary * scale, True


def _apply_absorption(row: dict[str, Any], which: str) -> dict[str, Any]:
    """Return capped completions for one standalone merchant scenario."""
    cap = row["merchant_cap"]
    if which == "mm":
        net = row["mm_completions"]
        binding = net > cap and cap >= 0
        kept = min(net, cap)
        ratio = kept / net if net > 0 else 1.0
        return {"completions": kept, "permits": row["mm_permits"] * ratio, "binding": binding, "capacity": net}
    if which == "tod":
        net = row["tod_completions"]
        binding = net > cap and cap >= 0
        kept = min(net, cap)
        ratio = kept / net if net > 0 else 1.0
        return {"completions": kept, "permits": row["tod_permits"] * ratio, "binding": binding, "capacity": net}
    raise ValueError(which)


def _reform_weights(weights: dict[str, Any] | None) -> dict[str, float]:
    """Clamp a reform mix to the unit interval. Missing names stay fully on."""
    resolved = {name: 1.0 for name in REFORM_IDS}
    if not weights:
        return resolved
    for name in REFORM_IDS:
        if name not in weights:
            continue
        try:
            value = float(weights[name])
        except (TypeError, ValueError):
            value = 1.0
        resolved[name] = min(1.0, max(0.0, value))
    return resolved


def _mix_note(weights: dict[str, float]) -> str:
    if all(abs(weights[name] - 1.0) < 1e-12 for name in REFORM_IDS):
        return ""
    parts = []
    for name in REFORM_IDS:
        label = SCENARIO_LABELS[name].split(". ", 1)[-1]
        weight = weights[name]
        if weight <= 0:
            parts.append(f"{label} off")
        elif abs(weight - 1.0) < 1e-12:
            parts.append(f"{label} on")
        else:
            parts.append(f"{label} at {weight:.0%}")
    return "The package uses this mix: " + "; ".join(parts) + "."


def _near_hurdle(row: dict[str, Any], threshold: float, sigma: float, name: str) -> tuple[bool, str]:
    """True when a county margin sits near the feasibility hurdle."""
    window = max(0.06, 0.35 * sigma)
    checks = (
        ("Owner margin", row["adu_margin"], 0.0),
        ("Teardown margin", row["teardown_margin"], threshold),
        ("Conversion margin", row["conversion_margin"], threshold),
        ("Podium margin", row["tod_margin"], threshold),
    )
    reasons = []
    for label, margin, hurdle in checks:
        if abs(float(margin) - hurdle) <= window:
            reasons.append(f"{label} in {name} is {float(margin):.2f}, near the hurdle at {hurdle:.2f}.")
    if not reasons:
        return False, ""
    return True, "Close call: " + " ".join(reasons)


def _scenario_close(
    scenario_id: str,
    focus: dict[str, Any],
    params: dict[str, float],
    incremental: float,
    baseline: float,
) -> tuple[bool, str]:
    threshold = params["feasibility_threshold"]
    sigma = params["feasibility_sigma"]
    window = max(0.06, 0.35 * sigma)
    checks = {
        "adu": [("Owner margin", focus["adu_margin"], 0.0)],
        "missing_middle": [
            ("Teardown margin", focus["teardown_margin"], threshold),
            ("Conversion margin", focus["conversion_margin"], threshold),
        ],
        "tod": [("Podium margin", focus["tod_margin"], threshold)],
        "combined": [
            ("Owner margin", focus["adu_margin"], 0.0),
            ("Teardown margin", focus["teardown_margin"], threshold),
            ("Conversion margin", focus["conversion_margin"], threshold),
            ("Podium margin", focus["tod_margin"], threshold),
        ],
    }
    reasons = []
    for label, margin, hurdle in checks.get(scenario_id, []):
        if abs(float(margin) - hurdle) <= window:
            reasons.append(
                f"{label} in {focus['name']} is {float(margin):.2f}, within {window:.2f} of the hurdle at {hurdle:.2f}."
            )
    if scenario_id != "baseline" and baseline > 0 and abs(incremental) < 0.01 * baseline:
        reasons.append("The five-year increment is under 1 percent of baseline completions, near no effect.")
    if not reasons:
        return False, ""
    return True, "Close call: " + " ".join(reasons)


def _explanation(
    state_name: str,
    scenario_id: str,
    incremental: float,
    baseline: float,
    level: float,
    focus_name: str,
    mix_note: str,
) -> str:
    base_n = f"{baseline:,.0f} (calculated)"
    if scenario_id == "baseline":
        return (
            f"Under current rules, {state_name} completes about {base_n} homes over five years. "
            "That extends the recent Building Permits Survey pace. It is not a new policy, "
            "and it is not a forecast of the business cycle."
        )
    label = SCENARIO_LABELS[scenario_id]
    lift = 0.0 if baseline <= 0 else 100.0 * incremental / baseline
    text = (
        f"{label} adds about {incremental:,.0f} (calculated) net completions in {state_name} over five years, "
        f"{lift:.1f} percent (calculated) above the baseline of {base_n}. "
        f"After the reform, five-year completions are about {level:,.0f} (calculated). "
        f"The worked example is {focus_name}."
    )
    if scenario_id == "combined":
        text += " The package removes overlap among the reforms that are switched on. It is not the sum of the five standalone totals."
        if mix_note:
            text += " " + mix_note
    return text


def _combined_row(
    standalone: dict[str, Any],
    packaged: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Remove parcel overlap, then share the absorption cap.

    TOD keeps the walkshed. Missing middle keeps the rest of its county
    pipeline in proportion to homes outside the walkshed. ADUs are reduced
    by the homes the other two reforms consume. Parking yield inside the
    walkshed is dropped because the TOD pro forma already cut parking.
    The fee increment on the baseline pipeline is kept: those are projects
    that are already legal and were not created by the zoning reforms.
    """
    mix = _reform_weights(weights)
    homes = max(packaged["housing_units"], 1.0)
    shed_full = min(1.0, packaged["walkshed_units"] / homes)
    # A partial TOD program claims only that share of the walkshed.
    shed_share = shed_full * mix["tod"]
    mm_factor = (1.0 - shed_share) * mix["missing_middle"]
    tod_factor = mix["tod"]
    mm_completions = packaged["mm_completions"] * mm_factor
    mm_permits = packaged["mm_permits"] * mm_factor
    mm_homes = packaged["mm_homes_used"] * mm_factor
    tod_completions = packaged["tod_completions"] * tod_factor
    tod_permits = packaged["tod_permits"] * tod_factor
    tod_homes = packaged["tod_homes_removed"] * tod_factor
    raw_mm = mm_completions
    raw_tod = tod_completions
    mm_completions, tod_completions, merchant_binding = _cap_pair(
        mm_completions, tod_completions, packaged["merchant_cap"]
    )
    # Permits follow the same scale as completions when the cap binds.
    if merchant_binding:
        mm_permits *= mm_completions / raw_mm if raw_mm > 0 else 0.0
        tod_permits *= tod_completions / raw_tod if raw_tod > 0 else 0.0
        mm_homes *= mm_completions / raw_mm if raw_mm > 0 else 0.0
        tod_homes *= tod_completions / raw_tod if raw_tod > 0 else 0.0
    consumed = mm_homes + tod_homes
    sf_stock = max(packaged["sf_stock"], 1.0)
    adu_scale = max(0.0, 1.0 - consumed / sf_stock)
    adu_completions = packaged["adu_completions"] * adu_scale * mix["adu"]
    adu_permits = packaged["adu_permits"] * adu_scale * mix["adu"]
    parking_completions = standalone["parking_completions"] * (1.0 - shed_share) * mix["parking"]
    parking_permits = standalone["parking_permits"] * (1.0 - shed_share) * mix["parking"]
    # Fees on the baseline pipeline do not rebuild the same parcels as TOD/MM.
    fee_completions = standalone["fee_completions"] * mix["fees"]
    fee_permits = standalone["fee_permits"] * mix["fees"]
    completions = adu_completions + mm_completions + tod_completions + parking_completions + fee_completions
    permits = adu_permits + mm_permits + tod_permits + parking_permits + fee_permits
    adu_binding = mix["adu"] > 0 and packaged["adu_capped"]
    return {
        "completions": completions,
        "permits": permits,
        "adu": adu_completions,
        "mm": mm_completions,
        "tod": tod_completions,
        "parking": parking_completions,
        "fees": fee_completions,
        "binding": merchant_binding or adu_binding,
        "capacity": packaged["adu_completions"] + packaged["mm_completions"] + packaged["tod_completions"],
    }


def _sum(rows: list[dict[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows)


def _trace_inputs(title: str, lot_tag: str) -> list[dict[str, str]]:
    if title == "Eligible homes":
        return [
            _tagged("Single-family stock", "observed"),
            _tagged("Legal and tenure shares", "assumed"),
            _tagged("Lot screen", lot_tag),
        ]
    if title.startswith("Five-year"):
        return [
            _tagged("Building Permits Survey annual units", "observed"),
            _tagged("Permit growth rate", "assumed"),
        ]
    if title.startswith("Completions") or title.startswith("Net") or title.startswith("Adoption"):
        return [
            _tagged("Permits or net units from the prior step", "calculated"),
            _tagged("Completion ratio", "assumed"),
        ]
    if "margin" in title.lower() or "Margin" in title or "cost" in title.lower() or title.startswith("Value") or title.startswith("Podium") or title.startswith("Challenge") or title.startswith("Spaces"):
        return [
            _tagged("Local prices or rents", "observed"),
            _tagged("Cost, fee, and ratio assumptions", "assumed"),
        ]
    if title.startswith("Official") or title.startswith("Where") or title.startswith("Overlap") or title.startswith("Homes inside"):
        return [
            _tagged("County measurements", "observed"),
            _tagged("Published assumptions", "assumed"),
            _tagged("Sum of county results", "calculated"),
        ]
    return [
        _tagged("Observed inputs", "observed"),
        _tagged("Published assumptions", "assumed"),
    ]


def build_trace(
    kind: str,
    focus: dict[str, Any],
    params: dict[str, float],
    lot_note: str,
    state_total: float,
    lot_tag: str = "assumed",
) -> list[dict[str, Any]]:
    """Worked example for the largest county, then the state sum."""
    info = focus.get("trace_inputs") or {}
    name = focus["name"]
    steps: list[dict[str, Any]] = [
        _step(
            "Where this arithmetic is from",
            "State total = sum over counties of the same equation",
            name,
            state_total,
            "units",
            "The lines below substitute this county's prices, stock, and permits. "
            "The last line is the official state total. Because feasibility is curved, "
            "plugging the state median into the same equation would not reproduce that total.",
        )
    ]
    if kind == "baseline":
        base = focus["baseline"]
        steps.append(
            _step(
                "Five-year permits",
                "annual_BPS x ((1+g)^5 - 1) / g",
                f"SF {_fmt(base['permits']['sf'])}, 2–4 {_fmt(base['permits']['small'])}, 5+ {_fmt(base['permits']['mf'])}",
                base["permits"]["total"],
                "permits",
                "At a zero trend the multiplier is exactly 5, so this is five times the recent annual run-rate.",
            )
        )
        steps.append(
            _step(
                "Completions inside the window",
                "permits x completion ratio",
                f"SF ratio {params['completion_ratio_sf']:.2f}, small {params['completion_ratio_small']:.2f}, multifamily {params['completion_ratio_mf']:.2f}",
                base["completions"]["total"],
                "completions",
                "A steady pipeline means homes permitted just before the window offset homes permitted at the end of it. What remains is cancellation and the longer multifamily schedule.",
            )
        )
    elif kind == "adu":
        steps.extend(
            [
                _step(
                    "Eligible homes",
                    "(detached + attached_weight x attached) x geography x (1 - already_legal) x tenure x lot_feasible",
                    f"stock {_fmt(info.get('sf_stock', 0))} x legal gap {info.get('legal_gap', 0):.2f} x tenure {info.get('tenure', 0):.2f} x lot {info.get('lot_share', 0):.2f}",
                    info.get("eligible_adus", 0),
                    "homes",
                    lot_note,
                ),
                _step(
                    "Owner's cost, with the parking waiver",
                    "cost_per_sf x cost_index x size + soft + fee. Parking = $0.",
                    f"hard {_fmt(info.get('hard', 0))} + soft {_fmt(info.get('soft', 0))} + fee {_fmt(info.get('fee', 0))}",
                    info.get("adu_cost", 0),
                    "dollars",
                    "The benchmark says no additional parking is required. A required surface space would be added on top of this cost; it is not, in this scenario.",
                ),
                _step(
                    "Value the owner underwrites",
                    "max(rent x size_factor x 12 / homeowner_cap, sale price of the square feet)",
                    f"rent value {_fmt(info.get('homeowner_value', 0))}, sale value {_fmt(info.get('market_sale', 0))}",
                    info.get("adu_value", 0),
                    "dollars",
                    "This is a homeowner yield, not a merchant residual-land-value test. No developer profit is subtracted.",
                ),
                _step(
                    "Adoption over five years",
                    "hazard = min(max, hazard0 x exp(beta x margin)); share = 1 - exp(-hazard x 5)",
                    f"margin {info.get('adu_margin', 0):.2f}, hazard {info.get('hazard', 0):.4f}, share {info.get('adoption', 0):.3f}",
                    focus["adu_completions"],
                    "completions",
                    "Permits are eligible homes times the cumulative share, then capped, then multiplied by the ADU completion ratio.",
                ),
            ]
        )
    elif kind == "missing_middle":
        steps.extend(
            [
                _step(
                    "Teardown margin",
                    "(revenue - all-in cost - land opportunity) / land opportunity",
                    f"obsolete homes {_fmt(info.get('obsolete', 0))}, feasibility {info.get('teardown_feas', 0):.3f}",
                    info.get("teardown_margin", 0),
                    "margin",
                    "Opportunity cost is land share times the county median, and only for an obsolete slice of the pre-1940 stock. Paying the full median for a sound house almost never clears a 4-unit cap.",
                ),
                _step(
                    "Conversion margin",
                    "(value of added units - conversion cost - fees - parking - profit) / cost",
                    f"feasibility {info.get('conv_feas', 0):.3f}",
                    info.get("conv_margin", 0),
                    "margin",
                    "The existing house stays. Setbacks are assumed not to bind, which is the benchmark's instruction. The handbook does not assume the pro forma binds.",
                ),
                _step(
                    "Net completions before the county absorption cap",
                    "teardown net + conversion net, times the small-building completion ratio",
                    f"teardown {_fmt(info.get('teardown_net', 0))}, conversion {_fmt(info.get('conv_net', 0))}",
                    focus["mm_completions"],
                    "completions",
                    "Net units from a teardown are gross units minus the home that was demolished. Conversion units are all net new.",
                ),
            ]
        )
    elif kind == "tod":
        steps.extend(
            [
                _step(
                    "Homes inside the walkshed",
                    "station and bus area x (1 - overlap) x assumed urban density, allocated by transit commuting",
                    f"candidate share {params['tod_redevelop_fraction']:.2f} of walkshed homes {_fmt(focus['walkshed_units'])}",
                    info.get("candidate", 0),
                    "homes on candidate sites",
                    "Major stops are rail, BRT, and bus corridors at a 15-minute headway or better. Buffers are the slider. This is not a GTFS polygon.",
                ),
                _step(
                    "Podium margin",
                    "(transit-premium price - hard - soft - fee - reduced parking - profit) / cost",
                    f"cost {_fmt(info.get('tod_cost', 0))} per unit, value {_fmt(info.get('tod_unit_value', 0))}, feasibility {info.get('tod_feas', 0):.3f}",
                    info.get("tod_margin", 0),
                    "margin",
                    "If this margin is deeply negative, a higher FAR does not create a feasible project. Zoning capacity and feasible capacity are different numbers.",
                ),
                _step(
                    "Net units from the FAR gap",
                    "rebuilt homes x (FAR_policy / FAR_existing - 1) x multifamily completion ratio",
                    f"FAR {params['tod_far_existing']:.2f} to {params['tod_far_policy']:.2f}, net per home {info.get('net_per', 0):.2f}",
                    focus["tod_completions"],
                    "net completions",
                    "Rebuilding to the same FAR is not induced. Gross permits count replacement units only when the envelope actually rises.",
                ),
            ]
        )
    elif kind == "parking":
        steps.append(
            _step(
                "Spaces no longer required",
                "market ratio is min(p_market, p_minimum); savings = (p_min - p_mkt) x cost per space",
                f"{info.get('context', '')}: minimum {info.get('p_min', 0):.2f}, market {info.get('p_mkt', 0):.2f}, space cost {_fmt(info.get('space', 0))}",
                focus["parking_completions"],
                "completions",
                "Two channels are added: some baseline projects become feasible because cost fell, and footprint-constrained projects fit more units. The market ratio does not go to zero.",
            )
        )
    elif kind == "fees":
        steps.append(
            _step(
                "Challenge fee shock",
                "dQ = Q x elasticity x ((0.5 x $50,000) / (hard + soft + mandated parking + $50,000))",
                f"savings {_fmt(info.get('fee_savings', 0))} per unit, elasticity {params['supply_elasticity']:.2f}",
                focus["fee_completions"],
                "completions",
                "The $50,000 stack is applied even where the zoning pro formas use a lower segment fee. That is the cross-submission comparison the challenge asked for. It is not a claim that every state charges $50,000 today.",
            )
        )
    elif kind == "combined":
        steps.append(
            _step(
                "Overlap rule",
                "TOD takes the walkshed; missing middle takes the share of the county outside it; ADUs take homes that were not converted or rebuilt; parking yield inside the walkshed is not added again",
                name,
                state_total,
                "net completions",
                "Fees still move the baseline pipeline, because those projects are legal without the zoning reforms. They are not the same units as a new ADU or a mid-rise.",
            )
        )
    steps.append(
        _step(
            "Official state total",
            "sum of county net completions over 5 years",
            f"worked example is {name}; official total sums every county",
            state_total,
            "completions",
            "Use this number. The county lines above are the proof, not a second estimate.",
        )
    )
    for step in steps:
        step["inputs"] = _trace_inputs(step["title"], lot_tag)
    return steps


def _scenario_shell(
    scenario_id: str,
    baseline_completions: float,
    baseline_permits: float,
    incremental_completions: float,
    incremental_permits: float,
    binding: bool,
    capacity: float,
    trace: list[dict[str, Any]],
    extra_drivers: list[str],
    explanation: str,
    close_call: bool,
    close_call_reason: str,
) -> dict[str, Any]:
    level_c = baseline_completions + incremental_completions
    level_p = baseline_permits + incremental_permits
    lift = 0.0 if baseline_completions <= 0 else 100.0 * incremental_completions / baseline_completions
    annualized_completions = level_c / 5.0 if scenario_id == "baseline" else incremental_completions / 5.0
    annualized_permits = level_p / 5.0 if scenario_id == "baseline" else incremental_permits / 5.0
    drivers = list(extra_drivers)
    if binding:
        drivers.append("A cap is binding: feasible capacity is larger than what the five-year market or the adoption ceiling will absorb.")
    if not drivers:
        drivers.append("The county price-to-cost gap and the size of the eligible stock.")
    return {
        "id": scenario_id,
        "label": SCENARIO_LABELS[scenario_id],
        "permits_5yr": level_p,
        "completions_5yr": level_c,
        "incremental_permits": incremental_permits,
        "incremental_completions": incremental_completions,
        "annualized_completions": annualized_completions,
        "annualized_level": level_c / 5.0,
        "annualized_increment": 0.0 if scenario_id == "baseline" else incremental_completions / 5.0,
        "annualized_permits": annualized_permits,
        "lift_pct": lift,
        "cap_binding": binding,
        "capacity_completions": capacity,
        "trace": trace,
        "drivers": drivers,
        "cannot": CANNOT[scenario_id],
        "explanation": explanation,
        "close_call": close_call,
        "close_call_reason": close_call_reason,
    }


def simulate_state(
    fixtures: dict[str, Any],
    assumptions: Any,
    state_code: str,
    overrides: dict[str, Any] | None = None,
    parcel_mode: str = "observed",
    resolution: str = "county",
    neutral: bool = False,
    sigma_scale: float = 1.0,
    reform_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run baseline and all five reforms plus the package for one state.

    ``parcel_mode="imputed"`` hides lot-size extracts and, where a tier-1 land
    use wall was measured, pretends that wall was never observed.
    ``resolution="state"`` collapses counties to one screen at the state median.
    ``neutral=True`` is the identity check: no incremental reform.
    """
    state = fixtures["states"][state_code]
    params = assumptions.resolve(state_code, overrides)
    if neutral:
        params = dict(params)
        params["adu_already_legal_share"] = 1.0
        params["mm_already_legal_share"] = 1.0
        params["tod_far_policy"] = params["tod_far_existing"]
        for context in ("urban", "suburban", "rural"):
            params[f"parking_p_mkt_{context}"] = params[f"parking_p_min_{context}"]
        params["fee_reduction_fraction"] = 0.0
        params["tod_parking_ratio"] = params["parking_p_min_urban"]
    if sigma_scale != 1.0:
        params = dict(params)
        params["feasibility_sigma"] *= sigma_scale
    geography_note = ""
    tier1 = state.get("tier1") or {}
    if parcel_mode == "imputed" and tier1.get("urban_land_share"):
        params = dict(params)
        params["geography_eligible_share"] = 1.0
        geography_note = (
            "The tier-2 screen does not see Hawaii's State Land Use districts, "
            "so it treats the entire single-family stock as geographically eligible."
        )
    lot_share, lot_note, lot_tag = lot_feasibility(state, params, parcel_mode)
    if geography_note:
        lot_note = lot_note + " " + geography_note
    indexes = {
        "sf": state["cost_index_sf"] * params["cost_index_shock"],
        "mf": state["cost_index_mf"] * params["cost_index_shock"],
    }
    national = fixtures.get("national") or {"sf_permit_value": 297175.0, "mf_permit_value": 150337.0}
    counties = prepare_geographies(state, resolution)
    transit = {}
    # Transit lives beside the fixture when present, and also inside the state
    # only if an adapter copied it. The loader attaches it in simulate().
    transit = fixtures.get("_transit", {}).get("states", {}).get(state_code, {})
    if not transit:
        transit = {"rail_stations": 0, "brt_stations": 0, "frequent_bus_route_miles": 0, "overlap_factor": 0.3}
    shed = walkshed_sqmi(
        transit["rail_stations"] * params["tod_station_scale"],
        transit["brt_stations"] * params["tod_station_scale"],
        transit["frequent_bus_route_miles"] * params["tod_station_scale"],
        params["tod_buffer_miles"],
        params["tod_bus_buffer_miles"],
        float(transit.get("overlap_factor", 0.3)),
    )
    walks = allocate_walkshed(counties, shed, params["tod_shed_density"])
    standalone_rows = [
        evaluate_county(county, params, indexes, national, lot_share, walk, False, False)
        for county, walk in zip(counties, walks)
    ]
    packaged_rows = [
        evaluate_county(county, params, indexes, national, lot_share, walk, True, False)
        for county, walk in zip(counties, walks)
    ]
    focus_index = max(range(len(counties)), key=lambda i: counties[i]["housing_units"])
    focus = evaluate_county(
        counties[focus_index], params, indexes, national, lot_share, walks[focus_index], False, True
    )

    def capped_metric(rows: list[dict[str, Any]], which: str) -> tuple[float, float, bool, float]:
        completions = permits = capacity = 0.0
        binding = False
        for row in rows:
            if which == "adu":
                completions += row["adu_completions"]
                permits += row["adu_permits"]
                capacity += row["adu_capacity"]
                binding = binding or row["adu_capped"]
            elif which in {"mm", "tod"}:
                piece = _apply_absorption(row, which)
                completions += piece["completions"]
                permits += piece["permits"]
                capacity += piece["capacity"]
                binding = binding or piece["binding"]
            elif which == "parking":
                completions += row["parking_completions"]
                permits += row["parking_permits"]
                capacity += row["parking_completions"]
            elif which == "fees":
                completions += row["fee_completions"]
                permits += row["fee_permits"]
                capacity += row["fee_completions"]
        return completions, permits, binding, capacity

    baseline_completions = _sum_baseline(standalone_rows, "completions")
    baseline_permits = _sum_baseline(standalone_rows, "permits")
    weights = _reform_weights(reform_weights)
    mix_note = _mix_note(weights)
    combined_bits = [_combined_row(left, right, weights) for left, right in zip(standalone_rows, packaged_rows)]
    combined_c = sum(bit["completions"] for bit in combined_bits)
    combined_p = sum(bit["permits"] for bit in combined_bits)
    combined_binding = any(bit["binding"] for bit in combined_bits)
    combined_capacity = sum(bit["capacity"] for bit in combined_bits)

    metrics = {
        "adu": capped_metric(standalone_rows, "adu"),
        "missing_middle": capped_metric(standalone_rows, "mm"),
        "tod": capped_metric(standalone_rows, "tod"),
        "parking": capped_metric(standalone_rows, "parking"),
        "fees": capped_metric(standalone_rows, "fees"),
        "combined": (combined_c, combined_p, combined_binding, combined_capacity),
    }

    def top_counties(values: list[float]) -> list[str]:
        ranked = sorted(zip(counties, values), key=lambda item: item[1], reverse=True)[:3]
        total = sum(values) or 1.0
        lines = []
        for county, amount in ranked:
            if amount <= 0:
                continue
            lines.append(f"{county['name']} contributes {amount:,.0f} net completions ({100.0 * amount / total:.0f}%).")
        return lines

    per_county = {
        "adu": [row["adu_completions"] for row in standalone_rows],
        "missing_middle": [_apply_absorption(row, "mm")["completions"] for row in standalone_rows],
        "tod": [_apply_absorption(row, "tod")["completions"] for row in standalone_rows],
        "parking": [row["parking_completions"] for row in standalone_rows],
        "fees": [row["fee_completions"] for row in standalone_rows],
        "combined": [bit["completions"] for bit in combined_bits],
    }

    def _shell(scenario_id: str, incremental_c: float, incremental_p: float, binding: bool, capacity: float, drivers: list[str]) -> dict[str, Any]:
        level_c = baseline_completions + incremental_c
        close, reason = _scenario_close(scenario_id, focus, params, incremental_c, baseline_completions)
        return _scenario_shell(
            scenario_id,
            baseline_completions,
            baseline_permits,
            incremental_c,
            incremental_p,
            binding,
            capacity,
            build_trace(scenario_id, focus, params, lot_note, incremental_c if scenario_id != "baseline" else baseline_completions, lot_tag),
            drivers,
            _explanation(state["name"], scenario_id, incremental_c, baseline_completions, level_c, focus["name"], mix_note),
            close,
            reason,
        )

    scenarios = {
        "baseline": _shell(
            "baseline",
            0.0,
            0.0,
            False,
            baseline_completions,
            ["Recent Building Permits Survey mix, extended five years at the trend slider."],
        )
    }
    # Baseline shell adds incremental to baseline. Incremental is zero, so levels equal the baseline.
    for scenario_id in ("adu", "missing_middle", "tod", "parking", "fees", "combined"):
        completions, permits, binding, capacity = metrics[scenario_id]
        scenarios[scenario_id] = _shell(
            scenario_id,
            completions,
            permits,
            binding,
            capacity,
            top_counties(per_county[scenario_id]),
        )

    county_table = []
    integer_weights = {
        scenario_id: largest_remainder(per_county[scenario_id], int(round(metrics[scenario_id][0])))
        for scenario_id in ("adu", "missing_middle", "tod", "parking", "fees", "combined")
    }
    base_ints = largest_remainder(
        [row["baseline"]["completions"]["total"] for row in standalone_rows],
        int(round(baseline_completions)),
    )
    for index, county in enumerate(counties):
        row = standalone_rows[index]
        close, reason = _near_hurdle(
            row, params["feasibility_threshold"], params["feasibility_sigma"], county["name"]
        )
        county_table.append(
            {
                "fips": county["fips"],
                "name": county["name"],
                "context": standalone_rows[index]["context"],
                "housing_units": county["housing_units"],
                "median_value": county["median_value"],
                "baseline_completions": base_ints[index],
                "adu": integer_weights["adu"][index],
                "missing_middle": integer_weights["missing_middle"][index],
                "tod": integer_weights["tod"][index],
                "parking": integer_weights["parking"][index],
                "fees": integer_weights["fees"][index],
                "combined": integer_weights["combined"][index],
                "adu_margin": row["adu_margin"],
                "teardown_margin": row["teardown_margin"],
                "conversion_margin": row["conversion_margin"],
                "tod_margin": row["tod_margin"],
                "value_imputed": county["value_imputed"],
                "bps_reporting": county["bps_reporting"],
                "close_call": close,
                "close_call_reason": reason,
            }
        )

    hpi_2020 = state["fhfa_hpi_2020"]
    hpi_change = 0.0 if hpi_2020 == 0 else state["fhfa_hpi_latest"] / hpi_2020 - 1.0
    payload = {
        "state": state_code,
        "name": state["name"],
        "tier": state["tier"],
        "completeness": state.get("completeness", 0),
        "parcel_mode": parcel_mode,
        "resolution": resolution,
        "neutral": neutral,
        "lot_feasible_share": lot_share,
        "lot_feasible_note": lot_note,
        "lot_feasible_tag": lot_tag,
        "provenance_legend": LEGEND,
        "geography_eligible_share": params["geography_eligible_share"],
        "walkshed_sqmi": shed,
        "focus_county": focus["name"],
        "focus_margins": {
            "adu": focus["adu_margin"],
            "teardown": focus["teardown_margin"],
            "conversion": focus["conversion_margin"],
            "tod": focus["tod_margin"],
            "threshold": params["feasibility_threshold"],
            "sigma": params["feasibility_sigma"],
        },
        "housing_units": state["housing_units"],
        "median_value": state["median_value"],
        "median_rent": state["median_rent"],
        "pop_growth_annual": state["pop_growth_annual"],
        "fhfa_change_since_2020": hpi_change,
        "cost_index_sf": indexes["sf"],
        "cost_index_mf": indexes["mf"],
        "transit_note": transit.get("note", ""),
        "legal_note": assumptions.states[state_code].get("legal_note", ""),
        "baseline_permits_5yr": baseline_permits,
        "baseline_completions_5yr": baseline_completions,
        "scenarios": scenarios,
        "counties": county_table,
        "components": {
            "combined_adu": sum(bit["adu"] for bit in combined_bits),
            "combined_mm": sum(bit["mm"] for bit in combined_bits),
            "combined_tod": sum(bit["tod"] for bit in combined_bits),
            "combined_parking": sum(bit["parking"] for bit in combined_bits),
            "combined_fees": sum(bit["fees"] for bit in combined_bits),
            "standalone_adu": metrics["adu"][0],
            "standalone_mm": metrics["missing_middle"][0],
            "standalone_tod": metrics["tod"][0],
            "standalone_parking": metrics["parking"][0],
            "standalone_fees": metrics["fees"][0],
        },
    }
    return stamp_tree(payload)


def _sum_baseline(rows: list[dict[str, Any]], kind: str) -> float:
    return sum(row["baseline"][kind]["total"] for row in rows)


def attach_transit(fixtures: dict[str, Any], transit: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of the fixture bundle with the transit inventory attached."""
    attached = dict(fixtures)
    attached["_transit"] = transit
    return attached
