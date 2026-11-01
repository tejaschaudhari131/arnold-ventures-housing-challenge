# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""A capped scenario cannot report more completions than its capacity."""

from __future__ import annotations

import pytest

from src.data.schema import CHALLENGE_STATES
from src.model.engine import simulate_state


@pytest.mark.parametrize("code", CHALLENGE_STATES)
def test_binding_cap_is_at_least_the_increment(bundle, code):
    fixtures, assumptions = bundle
    result = simulate_state(fixtures, assumptions, code)
    for scenario_id, row in result["scenarios"].items():
        if not row["cap_binding"]:
            continue
        assert row["incremental_completions"] <= row["capacity_completions"] + 1e-6, scenario_id


def test_pennsylvania_package_capacity_covers_parking_and_fees(bundle):
    """The old package capacity omitted parking and fees, so 74,114 was labeled
    capped against a capacity of 68,782. The incremental total is unchanged.
    """
    fixtures, assumptions = bundle
    result = simulate_state(fixtures, assumptions, "PA")
    combined = result["scenarios"]["combined"]
    parts = result["components"]
    assert round(combined["incremental_completions"]) == 74114
    assert combined["cap_binding"] is True
    assert combined["incremental_completions"] <= combined["capacity_completions"]
    # Parking and fees are inside the package and were missing from the old capacity.
    assert combined["capacity_completions"] > parts["combined_adu"] + parts["combined_mm"] + parts["combined_tod"]
    # Package missing middle can exceed the standalone total because the package
    # pro forma includes the fee cut and market parking. It is still capped
    # per county; the state flag stays consistent with the capacity field.
    assert parts["combined_mm"] > result["scenarios"]["missing_middle"]["capacity_completions"]
