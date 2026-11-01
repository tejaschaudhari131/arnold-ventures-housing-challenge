# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Small-home options and their pro formas.

Every option is something one single-family lot can do:

  adu  add one detached or semi-detached ADU (Handbook benchmark 1)
  mm2  keep the house and add one home: conversion or addition (2 homes)
  mm4  replace the house with 4 homes, up to 3 stories (+3 net)
  mm6  replace the house with 6 homes, up to 3 stories (+5 net)

For each option the module computes, in plain closed forms:

  value V    capitalized rent of the added homes
  cost C     hard + soft + development fees + parking (+ lot + demolition for rebuilds)
  margin m   V / C - 1
  excess x   m - hurdle (owner for adu/mm2, developer for rebuilds)
  area A     lot area the option needs: footprints and surface parking
  net d      homes added
"""

from __future__ import annotations

from dataclasses import dataclass

OWNER_OPTIONS = ("adu", "mm2")
REBUILD_UNITS = {"mm4": 4, "mm6": 6}
NET_HOMES = {"adu": 1, "mm2": 1, "mm4": 3, "mm6": 5}
MM_STORIES = 3


@dataclass(frozen=True)
class Econ:
    """Economic levers a scenario sets.

    fee          development fees per new home
    parking      "minimum" (current mandates) or "market" (no mandates)
    adu_no_parking  the Handbook ADU benchmark: no space may be required for an ADU
    approval     by-right approval with a shot clock (pipeline only)
    """

    fee: float
    parking: str = "minimum"
    adu_no_parking: bool = False
    approval: bool = False


@dataclass(frozen=True)
class OptionResult:
    option: str
    value: float
    cost: float
    margin: float
    hurdle: float
    excess: float
    area: float
    net: int
    hazard: float
    build_lag: float
    spaces: float
    ref_excess: float | None = None  # ADU excess at fee 0 and no parking


LOT_COMPLETION = {
    "adu": "completion_ratio_adu",
    "mm2": "completion_ratio_small",
    "mm4": "completion_ratio_small",
    "mm6": "completion_ratio_mf",
}


def lot_completion(option: str, p: dict[str, float]) -> float:
    """D12. Screening never-complete share for this lot option. Default 1 if unset."""
    name = LOT_COMPLETION.get(option)
    if not name:
        return 1.0
    return float(p.get(name, 1.0))


def feasible_lot_hazard(p: dict[str, float]) -> float:
    """mm2 hazard. An explicit override wins; otherwise hazard_homeowner / F_CA."""
    if p.get("_use_hhf_override"):
        return float(p["hazard_homeowner_feasible"])
    share = float(p.get("adu_feasible_share_ca") or 0.5)
    return float(p["hazard_homeowner"]) / share


def adu_hazard_rate(p: dict[str, float]) -> float:
    """All-lots CA rate re-based onto feasible lots: λ_all / F_CA."""
    share = float(p.get("adu_feasible_share_ca") or 0.5)
    return float(p["hazard_homeowner"]) / share


def unit_value(rent: float, p: dict[str, float]) -> float:
    """Capitalized value of one new rental home from a monthly ACS median rent."""
    return rent * p["new_unit_rent_premium"] * 12.0 * (1.0 - p["opex_share"]) / p["cap_rate"]


def provided_parking(ctx: str, econ: Econ, p: dict[str, float], cap: float | None) -> float:
    """Spaces per home a builder provides.

    With a mandate the builder provides max(minimum, market ratio), because
    nothing stops a builder from providing more than the code requires.
    Without one, the market ratio. ``cap`` is a statewide ceiling on minimums.
    """
    minimum = p[f"parking_min_{ctx}"]
    if cap is not None:
        minimum = min(minimum, cap)
    market = p[f"parking_market_{ctx}"]
    if econ.parking == "market":
        return market
    return max(minimum, market)


def rebuild_space_cost(ctx: str, p: dict[str, float]) -> tuple[float, float]:
    """(cost per space, share of spaces on surface) for a 4–6 home rebuild."""
    if ctx == "urban":
        tucked = p["structured_share_urban"]
        return tucked * p["stall_cost_structured"] + (1.0 - tucked) * p["stall_cost_surface"], 1.0 - tucked
    return p["stall_cost_surface"], 1.0


def evaluate_option(
    option: str,
    host_type: str,
    ctx: str,
    rent_1br: float,
    rent_2br: float,
    median_value: float,
    econ: Econ,
    adu_spaces: float,
    p: dict[str, float],
    cap: float | None,
) -> OptionResult:
    soft = 1.0 + p["soft_cost_share"]
    footprint = p[f"footprint_{host_type}"]
    stall_area = p["stall_area_sqft"]
    if option == "adu":
        spaces = 0.0 if (econ.adu_no_parking or econ.parking == "market") else adu_spaces
        value = unit_value(rent_1br, p)
        cost = p["adu_sqft"] * p["adu_cost_psf"] * soft + econ.fee + spaces * p["stall_cost_surface"]
        area = footprint + p["adu_sqft"] / p["adu_stories"] + p["adu_open_space_sqft"] + spaces * stall_area
        hurdle, hazard, lag = p["hurdle_owner"], adu_hazard_rate(p), p["build_lag_adu_years"]
        # CA calibration: Gov. Code 66311.5(c)(1) (formerly 65852.2(f)(3))
        # exempts ADUs of 750 sq ft or less of interior livable space from
        # impact fees, and the Handbook ADU needs no space. Confirmed at
        # https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=GOV&sectionNum=66311.5.
        # The Lab prototype is 600 sq ft.
        ref_cost = p["adu_sqft"] * p["adu_cost_psf"] * soft
        ref_excess = (value / ref_cost - 1.0) - hurdle if ref_cost > 0 else None
    elif option == "mm2":
        spaces = provided_parking(ctx, econ, p, cap)
        value = unit_value(rent_2br, p)
        cost = p["conversion_cost_per_unit"] * soft + econ.fee + spaces * p["stall_cost_surface"]
        area = footprint + p["mm_unit_sqft"] / 2.0 + spaces * stall_area
        hurdle, hazard, lag = p["hurdle_owner"], feasible_lot_hazard(p), p["build_lag_conversion_years"]
        ref_excess = None
    else:
        units = REBUILD_UNITS[option]
        per_home = provided_parking(ctx, econ, p, cap)
        spaces = units * per_home
        space_cost, surface_share = rebuild_space_cost(ctx, p)
        value = units * unit_value(rent_2br, p)
        cost = (
            units * (p["mm_unit_sqft"] * p["newbuild_cost_psf"] * soft + econ.fee)
            + spaces * space_cost
            + median_value * p["teardown_value_factor"]
            + p["demolition_cost"]
        )
        area = units * p["mm_unit_sqft"] / MM_STORIES + spaces * surface_share * stall_area
        hurdle, hazard, lag = p["hurdle_developer"], p["hazard_developer"], p["build_lag_newbuild_years"]
        ref_excess = None
    margin = value / cost - 1.0
    return OptionResult(
        option=option,
        value=value,
        cost=cost,
        margin=margin,
        hurdle=hurdle,
        excess=margin - hurdle,
        area=area,
        net=NET_HOMES[option],
        hazard=hazard,
        build_lag=lag,
        spaces=spaces,
        ref_excess=ref_excess,
    )
