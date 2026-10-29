# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Closed forms match the equations documented in src/model/equations.py."""

from __future__ import annotations

import math

from src.model.equations import (
    adu_hazard,
    cumulative_hazard,
    elasticity_increment,
    far_net_multiplier,
    feasibility_share,
    horizon_multiplier,
    largest_remainder,
    lognormal_tail,
    normal_cdf,
    parking_yield_fraction,
    share_at_least,
    walkshed_sqmi,
)


def test_normal_cdf_at_zero_is_one_half():
    assert normal_cdf(0.0) == 0.5
    assert normal_cdf(1.0) > 0.84
    assert normal_cdf(-1.0) < 0.16


def test_feasibility_rises_with_margin():
    low = feasibility_share(-0.2, 0.0, 0.22)
    mid = feasibility_share(0.0, 0.0, 0.22)
    high = feasibility_share(0.4, 0.0, 0.22)
    assert low < mid < high
    assert mid == 0.5
    assert feasibility_share(0.1, 0.0, 0.0) == 1.0
    assert feasibility_share(-0.1, 0.0, 0.0) == 0.0


def test_share_at_least_interpolates_inside_a_bin():
    bins = [
        {"min_sqft": 0, "max_sqft": 5000, "n": 100},
        {"min_sqft": 5000, "max_sqft": 10000, "n": 100},
    ]
    assert share_at_least(bins, 5000) == 0.5
    assert share_at_least(bins, 7500) == 0.25
    assert share_at_least(bins, 0) == 1.0
    assert share_at_least(bins, 10000) == 0.0


def test_lognormal_tail_matches_the_survival_function():
    sigma = 0.7
    mean = 20000.0
    cutoff = 5000.0
    mu = math.log(mean) - 0.5 * sigma * sigma
    expected = 1.0 - normal_cdf((math.log(cutoff) - mu) / sigma)
    assert lognormal_tail(mean, sigma, cutoff) == expected
    assert lognormal_tail(mean, sigma, 1.0) > lognormal_tail(mean, sigma, 40000.0)


def test_horizon_multiplier_is_exactly_the_horizon_at_zero_growth():
    assert horizon_multiplier(0.0, 5) == 5.0
    assert horizon_multiplier(1e-15, 5) == 5.0
    growing = horizon_multiplier(0.02, 5)
    assert growing == ((1.02 ** 5) - 1) / 0.02
    assert growing > 5


def test_cumulative_hazard_compounds_survivors():
    share = cumulative_hazard(0.004, 5)
    assert share == 1.0 - math.exp(-0.02)
    assert share < 0.02
    assert cumulative_hazard(0.0, 5) == 0.0


def test_adu_hazard_is_bounded_and_rises_with_margin():
    base = adu_hazard(0.004, 1.2, 0.0, 0.06)
    richer = adu_hazard(0.004, 1.2, 0.5, 0.06)
    poorer = adu_hazard(0.004, 1.2, -0.5, 0.06)
    assert base == 0.004
    assert poorer < base < richer
    assert adu_hazard(0.05, 4.0, 1.0, 0.06) == 0.06


def test_elasticity_sign():
    assert elasticity_increment(1000, 25000, 200000, 0.8) == 1000 * 0.8 * (25000 / 200000)
    assert elasticity_increment(1000, -10000, 200000, 0.8) < 0
    assert elasticity_increment(0, 25000, 200000, 0.8) == 0.0


def test_far_net_multiplier():
    assert far_net_multiplier(1.3, 1.3) == 0.0
    assert far_net_multiplier(1.3, 3.5) == (3.5 / 1.3) - 1.0
    assert far_net_multiplier(1.3, 1.0) == 0.0


def test_largest_remainder_sums_exactly():
    weights = [1.2, 2.2, 3.6]
    allocated = largest_remainder(weights, 10)
    assert sum(allocated) == 10
    assert all(isinstance(item, int) for item in allocated)
    assert largest_remainder([0, 0, 0], 3) == [1, 1, 1]
    assert largest_remainder([5, 5], 0) == [0, 0]


def test_walkshed_and_parking_yield_are_non_negative():
    area = walkshed_sqmi(10, 2, 5, 0.5, 0.25, 0.2)
    assert area > 0
    assert walkshed_sqmi(0, 0, 0, 0.5, 0.25, 0.2) == 0.0
    yield_fraction = parking_yield_fraction(0.5, 325, 900, 0.7, 0.45)
    assert 0 < yield_fraction <= 1.5
    assert parking_yield_fraction(0, 325, 900, 0.7, 0.45) == 0.0
