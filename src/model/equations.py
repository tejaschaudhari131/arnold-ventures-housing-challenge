# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Inspectable structural equations.

Every function is a closed form. There is no fitted machine-learning model.
The normal CDF is the analytic Gaussian integral via ``math.erf``, used only
to turn a pro forma margin and a cross-site dispersion into a share of sites
that clear the hurdle. Callers pass numbers in; this module does not read
files or the network.
"""

from __future__ import annotations

import math


def normal_cdf(z: float) -> float:
    """Standard normal CDF.

    Phi(z) = 0.5 * (1 + erf(z / sqrt(2))).
    """
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def horizon_multiplier(growth: float, years: float) -> float:
    """Units over ``years`` per one unit of current annual flow.

    Sum of a geometric series: ((1+g)^T - 1) / g. The limit as g -> 0 is T,
    so a zero trend reproduces ``annual permits x 5`` exactly.
    """
    if years <= 0:
        return 0.0
    if abs(growth) < 1e-12:
        return years
    return ((1.0 + growth) ** years - 1.0) / growth


def cumulative_hazard(annual_hazard: float, years: float) -> float:
    """Share of a stock that acts within ``years`` at a constant hazard.

    1 - exp(-hazard * years). A hazard of 0.004 for 5 years is 1.98 percent,
    not 2.00 percent. The gap is the compounding of the survivors.
    """
    if annual_hazard <= 0 or years <= 0:
        return 0.0
    return 1.0 - math.exp(-annual_hazard * years)


def feasibility_share(margin: float, threshold: float, sigma: float) -> float:
    """Share of heterogeneous sites whose margin clears the hurdle.

    margin is (value - cost) / cost, or residual land value relative to
    opportunity cost. sigma is the cross-site standard deviation of that
    margin. The share is Phi((margin - threshold) / sigma).
    """
    if sigma <= 1e-9:
        return 1.0 if margin >= threshold else 0.0
    return clamp(normal_cdf((margin - threshold) / sigma), 0.0, 1.0)


def share_at_least(bins: list[dict], min_sqft: float) -> float:
    """Share of lots at least ``min_sqft``, with linear interpolation inside a bin.

    Bins are ``{min_sqft, max_sqft, n}`` and must not overlap. A lot that
    straddles the cutoff counts only for the fraction of the bin above it.
    """
    total = sum(float(item["n"]) for item in bins)
    if total <= 0:
        return 0.0
    eligible = 0.0
    for item in bins:
        low = float(item["min_sqft"])
        high = float(item["max_sqft"])
        count = float(item["n"])
        if high <= min_sqft or count <= 0:
            continue
        if low >= min_sqft:
            eligible += count
            continue
        span = high - low
        if span <= 0:
            continue
        eligible += count * (high - min_sqft) / span
    return clamp(eligible / total, 0.0, 1.0)


def lognormal_tail(mean_sqft: float, sigma_log: float, min_sqft: float) -> float:
    """P(lot >= min) when the mean is known and the log-size is normal.

    If X is lognormal and E[X] = m, then ln X ~ Normal(ln m - sigma^2 / 2, sigma).
    The survival function is 1 - Phi((ln min - mu) / sigma). Used for the Utah
    Housing Unit Inventory, which publishes a mean lot size and not bins.
    """
    if mean_sqft <= 0 or min_sqft <= 0:
        return 0.0
    if sigma_log <= 1e-9:
        return 1.0 if mean_sqft >= min_sqft else 0.0
    mu = math.log(mean_sqft) - 0.5 * sigma_log * sigma_log
    z = (math.log(min_sqft) - mu) / sigma_log
    return clamp(1.0 - normal_cdf(z), 0.0, 1.0)


def adu_hazard(hazard0: float, beta: float, margin: float, hazard_max: float) -> float:
    """Annual adoption hazard = min(hazard_max, hazard0 * exp(beta * margin)).

    A zero margin leaves the base hazard unchanged. A negative pro forma
    (cost above the owner's value) cuts take-up. A positive margin raises it.
    """
    if hazard0 <= 0:
        return 0.0
    raw = hazard0 * math.exp(beta * margin)
    return clamp(raw, 0.0, hazard_max)


def margin_from_value(value: float, cost: float) -> float:
    """(value - cost) / cost. Undefined costs return a large negative margin."""
    if cost <= 0:
        return 0.0 if value >= 0 else -1.0
    return (value - cost) / cost


def rental_value(monthly_rent: float, cap_rate: float, opex_ratio: float = 0.0) -> float:
    """Value = monthly_rent * 12 * (1 - opex) / cap_rate.

    Pass opex_ratio = 0 for the homeowner ADU capitalization, which is a gross
    yield. Pass the merchant operating-expense ratio for a developer pro forma.
    """
    if cap_rate <= 1e-6:
        return 0.0
    annual = max(0.0, monthly_rent) * 12.0 * (1.0 - opex_ratio)
    return annual / cap_rate


def sale_value_per_unit(median_home_value: float, reference_sqft: float, unit_sqft: float, premium: float) -> float:
    """Price per square foot of the median home, scaled to a new unit.

    (median value / reference size) * premium * unit size.
    """
    if reference_sqft <= 0:
        return 0.0
    return (median_home_value / reference_sqft) * premium * unit_sqft


def elasticity_increment(baseline_units: float, savings: float, cost_base: float, elasticity: float) -> float:
    """Extra units from a cost change on an existing pipeline.

    dQ = Q * elasticity * (savings / cost_base).

    savings > 0 means costs fell, so quantity rises. The ratio is the percent
    cost change. Land is not in cost_base: land is a residual, and the
    elasticity here is the supply response of non-land development cost.
    """
    if baseline_units <= 0 or cost_base <= 0 or elasticity == 0 or savings == 0:
        return 0.0
    return baseline_units * elasticity * (savings / cost_base)


def parking_yield_fraction(
    spaces_saved: float,
    sqft_per_space: float,
    unit_sqft: float,
    market_spaces: float,
    constrained_share: float,
) -> float:
    """Extra units on the same footprint when mandated spaces are not built.

    Freed area = spaces_saved * sqft_per_space.
    Remaining area per unit = unit_sqft + market_spaces * sqft_per_space.
    The ratio is the unit gain on constrained sites, times the share of
    projects that are actually footprint-constrained. Unconstrained sites
    get the cost channel only.
    """
    if spaces_saved <= 0 or constrained_share <= 0 or unit_sqft <= 0:
        return 0.0
    freed = spaces_saved * sqft_per_space
    per_unit = unit_sqft + max(market_spaces, 0.0) * sqft_per_space
    if per_unit <= 0:
        return 0.0
    return clamp((freed / per_unit) * constrained_share, 0.0, 1.5)


def walkshed_sqmi(
    rail_stations: float,
    brt_stations: float,
    frequent_bus_miles: float,
    rail_buffer_miles: float,
    bus_buffer_miles: float,
    overlap_factor: float,
) -> float:
    """Area of major-stop walksheds after a uniform overlap discount.

    Rail and BRT: n * pi * r^2.
    Frequent bus: route miles times a corridor of width 2 * bus buffer.
    Overlap (0 to 1) shrinks the union. It is a screening factor, not a
    geometric union of station polygons.
    """
    rail_area = (rail_stations + brt_stations) * math.pi * rail_buffer_miles ** 2
    bus_area = frequent_bus_miles * 2.0 * bus_buffer_miles
    return max(0.0, (rail_area + bus_area) * (1.0 - clamp(overlap_factor, 0.0, 0.95)))


def far_net_multiplier(far_existing: float, far_policy: float) -> float:
    """Net new units per existing unit when a site is rebuilt to a higher FAR.

    (FAR_policy / FAR_existing) - 1. Rebuilding to the same FAR adds nothing
    because the existing homes are replaced. A higher FAR is the whole TOD effect.
    """
    if far_existing <= 0 or far_policy <= far_existing:
        return 0.0
    return (far_policy / far_existing) - 1.0


def largest_remainder(weights: list[float], total: int) -> list[int]:
    """Integer allocation that sums exactly to ``total``.

    Hamilton's method: give each part its floor, then hand the leftover units
    to the largest fractional remainders. County tables use this so a reader
    can add the column and recover the state total with no rounding dust.
    """
    if total <= 0 or not weights:
        return [0 for _ in weights]
    weight_sum = sum(max(0.0, w) for w in weights)
    if weight_sum <= 0:
        shares = [1.0 / len(weights)] * len(weights)
    else:
        shares = [max(0.0, w) / weight_sum for w in weights]
    raw = [share * total for share in shares]
    floors = [math.floor(value) for value in raw]
    leftover = total - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - floors[i], shares[i]), reverse=True)
    for index in order[:leftover]:
        floors[index] += 1
    return floors
