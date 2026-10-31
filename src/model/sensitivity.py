# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""One-at-a-time tornado charts and a seeded Monte Carlo band.

Both move only the assumptions exposed as sliders, across the Low / Central /
High band in config/assumptions.yaml. The seed is fixed so a second machine
reproduces the same band. Draws are triangular: the mode is the central value,
and the support is the published band.
"""

from __future__ import annotations

import random
from typing import Any

from src.model.engine import simulate_state
from src.model.provenance import stamp_tree


def metric(result: dict[str, Any], scenario: str) -> float:
    if scenario == "baseline":
        return float(result["baseline_completions_5yr"])
    return float(result["scenarios"][scenario]["incremental_completions"])


def tornado(
    fixtures: dict[str, Any],
    assumptions: Any,
    state: str,
    scenario: str = "combined",
    parcel_mode: str = "observed",
    resolution: str = "county",
) -> dict[str, Any]:
    """Swing in the chosen outcome when each slider is set to Low, then High."""
    central_result = simulate_state(
        fixtures, assumptions, state, parcel_mode=parcel_mode, resolution=resolution
    )
    central = metric(central_result, scenario)
    rows = []
    for name in assumptions.sensitive_names(state):
        low, _mode, high = assumptions.band(name, state)
        low_value = metric(
            simulate_state(
                fixtures, assumptions, state, {name: low}, parcel_mode=parcel_mode, resolution=resolution
            ),
            scenario,
        )
        high_value = metric(
            simulate_state(
                fixtures, assumptions, state, {name: high}, parcel_mode=parcel_mode, resolution=resolution
            ),
            scenario,
        )
        spec = assumptions.spec(name, state)
        rows.append(
            {
                "name": name,
                "label": spec.get("label", name.replace("_", " ")),
                "group": spec.get("group", ""),
                "low": low_value,
                "high": high_value,
                "central": central,
                "swing": abs(high_value - low_value),
                "low_input": low,
                "high_input": high,
            }
        )
    rows.sort(key=lambda item: item["swing"], reverse=True)
    return stamp_tree({"state": state, "scenario": scenario, "central": central, "parameters": rows})


def monte_carlo(
    fixtures: dict[str, Any],
    assumptions: Any,
    state: str,
    scenario: str = "combined",
    draws: int | None = None,
    parcel_mode: str = "observed",
    resolution: str = "county",
    sigma_scale: float = 1.0,
    seed: int | None = None,
) -> dict[str, Any]:
    """Seeded triangular Monte Carlo. Returns p10, p50, and p90 of the outcome."""
    count = draws if draws is not None else assumptions.monte_carlo_draws
    rng = random.Random(assumptions.monte_carlo_seed if seed is None else seed)
    names = assumptions.sensitive_names(state)
    samples = []
    for _ in range(count):
        overrides = {}
        for name in names:
            low, mode, high = assumptions.band(name, state)
            if high <= low:
                overrides[name] = mode
            else:
                overrides[name] = rng.triangular(low, high, mode)
        outcome = metric(
            simulate_state(
                fixtures,
                assumptions,
                state,
                overrides,
                parcel_mode=parcel_mode,
                resolution=resolution,
                sigma_scale=sigma_scale,
            ),
            scenario,
        )
        samples.append(outcome)
    samples.sort()
    def percentile(p: float) -> float:
        if not samples:
            return 0.0
        index = min(len(samples) - 1, max(0, int(round(p * (len(samples) - 1)))))
        return samples[index]

    p10 = percentile(0.10)
    p90 = percentile(0.90)
    return stamp_tree(
        {
            "state": state,
            "scenario": scenario,
            "draws": count,
            "seed": assumptions.monte_carlo_seed if seed is None else seed,
            "parcel_mode": parcel_mode,
            "sigma_scale": sigma_scale,
            "p10": p10,
            "p50": percentile(0.50),
            "p90": p90,
            "min": samples[0] if samples else 0.0,
            "max": samples[-1] if samples else 0.0,
            "crosses_zero": bool(p10 < 0 < p90),
        }
    )
