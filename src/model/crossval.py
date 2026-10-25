# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 versus tier-2 cross-validation.

Two screens are run on the data-rich states and compared with the full model:

1. Parcel imputation. Lot-size bins and measured land-use walls are hidden.
   The point estimate uses the same equations. The confidence band is widened
   by ``tier2_sigma_multiplier`` because the missing parcel fields are a real
   source of dispersion, not a reason to invent precision.

2. State screen. Counties are collapsed to the state median price and the
   state permit total. This is what a team can do when it does not join
   county ACS to the model. The error is Jensen's inequality: a curved
   feasibility function at the average price is not the average of the
   county feasibilities.

Tier-2 states can be run through the same comparison. They have no lot bins
to hide, so the parcel screen mainly widens the band. The state-screen error
is still informative, and it is the practical payoff of using county ACS
everywhere instead of waiting for a statewide parcel file.
"""

from __future__ import annotations

from typing import Any

from src.data.schema import TIER1_STATES
from src.model.engine import SCENARIO_ORDER, simulate_state
from src.model.sensitivity import monte_carlo

POLICY_IDS = tuple(scenario for scenario in SCENARIO_ORDER if scenario != "baseline")


def _error(full: float, other: float) -> dict[str, float | None]:
    gap = other - full
    if abs(full) < 50:
        percent = None
    else:
        percent = 100.0 * gap / full
    return {"full": full, "other": other, "gap": gap, "percent_error": percent}


def cross_validate_state(
    fixtures: dict[str, Any],
    assumptions: Any,
    state: str,
    draws: int = 60,
) -> dict[str, Any]:
    full = simulate_state(fixtures, assumptions, state, parcel_mode="observed", resolution="county")
    imputed = simulate_state(fixtures, assumptions, state, parcel_mode="imputed", resolution="county")
    screen = simulate_state(fixtures, assumptions, state, parcel_mode="imputed", resolution="state")
    sigma_scale = assumptions.parameters["tier2_sigma_multiplier"]["central"]
    full_band = monte_carlo(
        fixtures, assumptions, state, "combined", draws=draws, parcel_mode="observed", sigma_scale=1.0, seed=assumptions.monte_carlo_seed
    )
    imputed_band = monte_carlo(
        fixtures,
        assumptions,
        state,
        "combined",
        draws=draws,
        parcel_mode="imputed",
        sigma_scale=float(sigma_scale),
        seed=assumptions.monte_carlo_seed,
    )
    full_width = full_band["p90"] - full_band["p10"]
    imputed_width = imputed_band["p90"] - imputed_band["p10"]
    scenarios = {}
    for scenario in POLICY_IDS:
        full_value = full["scenarios"][scenario]["incremental_completions"]
        scenarios[scenario] = {
            "imputed_parcels": _error(full_value, imputed["scenarios"][scenario]["incremental_completions"]),
            "state_screen": _error(full_value, screen["scenarios"][scenario]["incremental_completions"]),
        }
    return {
        "state": state,
        "tier": full["tier"],
        "lot_full": full["lot_feasible_share"],
        "lot_imputed": imputed["lot_feasible_share"],
        "lot_full_note": full["lot_feasible_note"],
        "lot_imputed_note": imputed["lot_feasible_note"],
        "scenarios": scenarios,
        "combined_band_full": full_band,
        "combined_band_imputed": imputed_band,
        "band_width_full": full_width,
        "band_width_imputed": imputed_width,
        "band_width_ratio": (imputed_width / full_width) if full_width > 1 else None,
    }


def cross_validate_tier1(fixtures: dict[str, Any], assumptions: Any, draws: int = 60) -> dict[str, Any]:
    """The rubric comparison: run the incomplete-data estimator on CT, WI, UT, and HI."""
    return {
        "states": {code: cross_validate_state(fixtures, assumptions, code, draws=draws) for code in TIER1_STATES},
        "note": (
            "Full model uses county prices and any observed lot-size or land-use extract. "
            "Imputed parcels hide those extracts. The state screen also collapses counties."
        ),
    }
