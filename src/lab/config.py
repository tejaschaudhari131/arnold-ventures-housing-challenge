# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Load and validate the Lab's locked configuration files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config" / "lab"
SAMPLE_DIR = ROOT / "data" / "sample" / "lab"
CACHE_DIR = ROOT / "data" / "cache" / "lab"

LAB_STATES: dict[str, dict[str, str]] = {
    "PA": {"fips": "42", "name": "Pennsylvania", "role": "primary"},
    "NH": {"fips": "33", "name": "New Hampshire", "role": "portability"},
}

OPTIONS = ("adu", "mm2", "mm4", "mm6")
CONTEXTS = ("urban", "suburban", "rural")
HOST_TYPES = ("detached", "attached")
STATUSES = ("allowed", "allowed_with_parking", "prohibited", "unknown")


class ConfigError(ValueError):
    """A Lab configuration file is malformed."""


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=None)
def load_scenarios() -> dict[str, Any]:
    doc = _read_yaml(CONFIG_DIR / "scenarios.yaml")
    for sid, scenario in doc["scenarios"].items():
        for option in scenario.get("legalize", []):
            if option not in OPTIONS:
                raise ConfigError(f"{sid}: unknown option {option}")
        if scenario["kind"] not in {"baseline", "benchmark", "extra"}:
            raise ConfigError(f"{sid}: bad kind {scenario['kind']}")
    return doc


@lru_cache(maxsize=None)
def load_assumptions() -> dict[str, Any]:
    doc = _read_yaml(CONFIG_DIR / "assumptions.yaml")
    for name, spec in doc["params"].items():
        for key in ("low", "central", "high", "unit", "group", "label", "rationale"):
            if key not in spec:
                raise ConfigError(f"assumption {name} is missing {key}")
        if not spec["low"] <= spec["central"] <= spec["high"]:
            raise ConfigError(f"assumption {name}: low <= central <= high fails")
        if spec.get("locked") and not spec["low"] == spec["central"] == spec["high"]:
            raise ConfigError(f"assumption {name} is locked but has a band")
    return doc


@lru_cache(maxsize=None)
def load_evidence(code: str) -> dict[str, Any]:
    doc = _read_yaml(CONFIG_DIR / "evidence" / f"{code}.yaml")
    for rule in doc.get("rules", []):
        if rule["option"] in {"adu", "mm"} and rule["status"] not in STATUSES:
            raise ConfigError(f"{code}:{rule['id']} has status {rule['status']}")
        if not rule.get("sources"):
            raise ConfigError(f"{code}:{rule['id']} has no source")
    return doc


def central_params() -> dict[str, float]:
    return {name: float(spec["central"]) for name, spec in load_assumptions()["params"].items()}


def ui_params() -> list[str]:
    return [name for name, spec in load_assumptions()["params"].items() if spec.get("ui")]


def param_spec(name: str) -> dict[str, Any]:
    return load_assumptions()["params"][name]
