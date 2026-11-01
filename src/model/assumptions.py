# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Load config/assumptions.yaml and resolve a state's central case.

Nothing in the equation module reads this file directly. The engine asks for a
flat dictionary of numbers. Overrides from the web app are clamped to the
published Low/High band so a request cannot push the model outside the
sensitivity range the documentation describes.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ASSUMPTIONS_PATH = ROOT / "config" / "assumptions.yaml"

STATE_KEYS = (
    "adu_already_legal_share",
    "mm_already_legal_share",
    "geography_eligible_share",
)


class AssumptionError(ValueError):
    """An override named a parameter that does not exist."""


class Assumptions:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.horizon_years = int(raw["horizon_years"])
        self.parameters: dict[str, dict[str, Any]] = raw["parameters"]
        self.states: dict[str, dict[str, Any]] = raw["states"]
        self.monte_carlo_draws = int(raw.get("monte_carlo_draws", 200))
        self.monte_carlo_seed = int(raw.get("monte_carlo_seed", 20261014))

    def spec(self, name: str, state: str | None = None) -> dict[str, Any]:
        if state and name in STATE_KEYS:
            return self.states[state][name]
        if name not in self.parameters:
            raise AssumptionError(f"Unknown assumption '{name}'")
        return self.parameters[name]

    def band(self, name: str, state: str | None = None) -> tuple[float, float, float]:
        spec = self.spec(name, state)
        return float(spec["low"]), float(spec["central"]), float(spec["high"])

    def ui_parameters(self, state: str) -> list[dict[str, Any]]:
        """Parameters the web app exposes as sliders, including the state's legal shares."""
        rows = []
        for name in STATE_KEYS:
            spec = self.states[state][name]
            rows.append(
                {
                    "name": name,
                    "label": name.replace("_", " "),
                    "group": "Legal baseline",
                    "low": spec["low"],
                    "central": spec["central"],
                    "high": spec["high"],
                    "value": spec["central"],
                    "help": self.states[state].get("legal_note", ""),
                }
            )
        for name, spec in self.parameters.items():
            if not spec.get("ui"):
                continue
            rows.append(
                {
                    "name": name,
                    "label": spec.get("label", name),
                    "group": spec.get("group", "Other"),
                    "unit": spec.get("unit", ""),
                    "low": spec["low"],
                    "central": spec["central"],
                    "high": spec["high"],
                    "value": spec["central"],
                    "help": spec.get("help", ""),
                }
            )
        return rows

    def completion_ratios(self) -> dict[str, dict[str, Any]]:
        """Every completion_ratio_* in config, whether or not it is a slider."""
        return {
            name: {
                "label": spec.get("label", name),
                "group": spec.get("group", "Other"),
                "unit": spec.get("unit", "share"),
                "low": spec["low"],
                "central": spec["central"],
                "high": spec["high"],
                "slider": bool(spec.get("ui")),
                "tag": "assumed",
                "help": spec.get("help", ""),
            }
            for name, spec in self.parameters.items()
            if name.startswith("completion_ratio_")
        }

    def resolve(self, state: str, overrides: dict[str, Any] | None = None) -> dict[str, float]:
        if state not in self.states:
            raise AssumptionError(f"Unknown state '{state}'")
        values: dict[str, float] = {"horizon_years": float(self.horizon_years)}
        for name, spec in self.parameters.items():
            values[name] = float(spec["central"])
        for name in STATE_KEYS:
            values[name] = float(self.states[state][name]["central"])
        for key, raw_value in (overrides or {}).items():
            if key not in values or key == "horizon_years":
                raise AssumptionError("Cannot override that parameter.")
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise AssumptionError("Override must be a finite number.") from exc
            if not math.isfinite(value):
                raise AssumptionError("Override must be a finite number.")
            low, _central, high = self.band(key, state)
            if value < low or value > high:
                value = min(high, max(low, value))
            values[key] = value
        return values

    def sensitive_names(self, state: str) -> list[str]:
        """Sliders, plus parameters marked for the Monte Carlo set (the lags)."""
        names = [row["name"] for row in self.ui_parameters(state)]
        for name, spec in self.parameters.items():
            if spec.get("monte_carlo") and name not in names:
                names.append(name)
        return names


def load_assumptions(path: str | Path | None = None) -> Assumptions:
    target = Path(path) if path else ASSUMPTIONS_PATH
    with target.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise AssumptionError("Assumptions file must be a mapping")
    return Assumptions(raw)
