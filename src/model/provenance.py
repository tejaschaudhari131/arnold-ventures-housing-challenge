# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Tag every published number as observed, assumed, or calculated.

Observed means the figure is a public measurement stored for that place.
Assumed means it is a published assumption or an imputation, not a measurement
for that place. Calculated means the equations produced it from the other two.

``stamp_tree`` writes a ``provenance`` map onto every object that holds
numbers. Tests walk the same objects and reject a number with no tag.
"""

from __future__ import annotations

from typing import Any

TAGS = ("observed", "assumed", "calculated")

LEGEND = {
    "observed": (
        "Measured in a public dataset from the official data list and stored for this place."
    ),
    "assumed": "A published assumption or an imputation. It is not a measurement for this place.",
    "calculated": (
        "Arithmetic in src/model/equations.py, using observed inputs and published assumptions."
    ),
}

# Keys whose presence in a result means "this came from the public file."
OBSERVED_KEYS = frozenset(
    {
        "housing_units",
        "population",
        "vacant",
        "owner_occ",
        "renter_occ",
        "sf_detached",
        "sf_attached",
        "two_unit",
        "three_four",
        "five_plus",
        "mobile",
        "median_rent",
        "median_income",
        "pre1940_share",
        "transit_commute_share",
        "land_sqmi",
        "bps_sf",
        "bps_two",
        "bps_three_four",
        "bps_five_plus",
        "tier",
        "county_count",
        "fhfa_hpi_2020",
        "fhfa_hpi_latest",
        "fhfa_latest_year",
    }
)

# Settings, imputations, and hurdle parameters. Not measurements.
ASSUMED_KEYS = frozenset(
    {
        "completeness",
        "geography_eligible_share",
        "threshold",
        "sigma",
        "seed",
        "draws",
        "sigma_scale",
        "low_input",
        "high_input",
        "feasibility_threshold",
        "feasibility_sigma",
    }
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def tag_for(key: str, node: dict[str, Any]) -> str:
    """Choose the tag for one numeric field on ``node``."""
    kind = node.get("kind")
    if kind == "assumptions":
        return "assumed"
    if kind == "observed":
        if key == "median_value" and node.get("value_imputed"):
            return "assumed"
        return "observed"
    if kind == "calculated":
        return "calculated"
    if key == "value" and node.get("tag") in TAGS:
        return str(node["tag"])
    if key == "median_value":
        return "assumed" if node.get("value_imputed") else "observed"
    if key == "lot_feasible_share":
        declared = node.get("lot_feasible_tag")
        return declared if declared in TAGS else "calculated"
    if key == "lot_full":
        declared = node.get("lot_full_tag")
        return declared if declared in TAGS else "calculated"
    if key == "lot_imputed":
        declared = node.get("lot_imputed_tag")
        return declared if declared in TAGS else "assumed"
    if key in OBSERVED_KEYS:
        return "observed"
    if key in ASSUMED_KEYS:
        return "assumed"
    return "calculated"


def stamp_tree(node: Any) -> Any:
    """Attach provenance maps in place. Returns the same object."""
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "provenance":
                continue
            if isinstance(value, (dict, list)):
                stamp_tree(value)
        numbers = [key for key, value in node.items() if _is_number(value)]
        if numbers:
            node["provenance"] = {key: tag_for(key, node) for key in numbers}
    elif isinstance(node, list):
        for item in node:
            stamp_tree(item)
    return node


def untagged_numbers(node: Any, path: str = "") -> list[str]:
    """Paths of numbers that are missing a valid observed/assumed/calculated tag."""
    missing: list[str] = []
    if isinstance(node, dict):
        provenance = node.get("provenance")
        tags = provenance if isinstance(provenance, dict) else {}
        for key, value in node.items():
            if key == "provenance":
                continue
            here = f"{path}.{key}" if path else key
            if _is_number(value):
                if tags.get(key) not in TAGS:
                    missing.append(here)
            elif isinstance(value, (dict, list)):
                missing.extend(untagged_numbers(value, here))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            here = f"{path}[{index}]"
            if _is_number(item):
                missing.append(here)
            elif isinstance(item, (dict, list)):
                missing.extend(untagged_numbers(item, here))
    return missing
