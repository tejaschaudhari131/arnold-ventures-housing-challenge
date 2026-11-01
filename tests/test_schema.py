# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Schema, privacy, and acquisition allowlist."""

from __future__ import annotations

import copy

import pytest

from src.data.acquire import ALLOWED_HOSTS
from src.data.safe_url import FetchDenied, assert_allowed
from src.data.adapters import assert_no_pii
from src.data.schema import CHALLENGE_STATES, TIER1_STATES, TIER2_STATES, load_fixtures, validate_state


def test_committed_benchmark_covers_all_eleven_states():
    fixtures = load_fixtures()
    assert set(fixtures["states"]) == set(CHALLENGE_STATES)
    for code in TIER1_STATES:
        assert fixtures["states"][code]["tier"] == 1
    for code in TIER2_STATES:
        assert fixtures["states"][code]["tier"] == 2
        assert fixtures["states"][code].get("tier1") in (None, {})
    pennsylvania = fixtures["states"]["PA"]
    assert 0.025 <= pennsylvania["transit_commute_share"] <= 0.055


def test_county_stocks_and_permits_reconcile_to_the_state():
    fixtures = load_fixtures()
    for code, state in fixtures["states"].items():
        for key in ("housing_units", "bps_sf", "bps_two", "bps_three_four", "bps_five_plus"):
            county_sum = sum(county[key] for county in state["counties"])
            assert county_sum == pytest.approx(state[key], rel=1e-6, abs=1.0), code


def test_bad_tier_and_duplicate_county_are_rejected():
    fixtures = load_fixtures()
    broken = copy.deepcopy(fixtures["states"]["CT"])
    broken["tier"] = 2
    with pytest.raises(ValueError, match="tier-1"):
        validate_state(broken)
    duplicated = copy.deepcopy(fixtures["states"]["NH"])
    duplicated["counties"].append(dict(duplicated["counties"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_state(duplicated)


def test_owner_and_mailing_fields_are_refused():
    with pytest.raises(ValueError, match="forbidden"):
        assert_no_pii({"Owner": "Example Person", "lot_sqft": 8000})
    assert_no_pii({"use_code": "101", "lot_sqft": 8000}) is None


def test_acquisition_rejects_hosts_outside_the_allowlist():
    with pytest.raises(FetchDenied):
        assert_allowed("https://example.invalid/housing.csv", ALLOWED_HOSTS)
    with pytest.raises(FetchDenied):
        assert_allowed("http://www2.census.gov/housing.csv", ALLOWED_HOSTS)
