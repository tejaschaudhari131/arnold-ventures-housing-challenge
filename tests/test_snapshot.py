# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Lock the headline table that the policy comparison prints.

If an equation or a fixture changes, this test fails until the document and
the expected integers are updated together.
"""

from __future__ import annotations

from pathlib import Path

from src.export.report import simulate_many

ROOT = Path(__file__).resolve().parents[1]

# Five-year completions. Baseline is the level. Every other column is incremental.
HEADLINES = {
    "PA": (113269, 30213, 9613, 612, 1458, 1524, 46219),
    "CT": (26470, 2650, 3452, 1481, 440, 443, 8469),
    "WI": (98922, 10329, 1164, 33, 753, 1273, 14103),
    "UT": (124116, 5656, 6662, 643, 683, 1469, 16386),
    "OR": (79606, 3229, 6720, 1864, 691, 1081, 13822),
    "HI": (18059, 1552, 3511, 70, 117, 135, 5873),
    "AZ": (273771, 20747, 13797, 204, 1880, 3618, 45195),
    "VA": (167814, 30203, 28833, 6360, 1891, 2797, 72580),
    "TN": (208075, 17266, 7545, 111, 1168, 2634, 30817),
    "RI": (6527, 1842, 2073, 111, 55, 82, 4550),
    "NH": (22463, 2278, 1143, 5, 102, 247, 4180),
}


def _rounded(result):
    scenarios = result["scenarios"]
    return (
        round(result["baseline_completions_5yr"]),
        round(scenarios["adu"]["incremental_completions"]),
        round(scenarios["missing_middle"]["incremental_completions"]),
        round(scenarios["tod"]["incremental_completions"]),
        round(scenarios["parking"]["incremental_completions"]),
        round(scenarios["fees"]["incremental_completions"]),
        round(scenarios["combined"]["incremental_completions"]),
    )


def test_engine_matches_the_published_table(bundle):
    fixtures, assumptions = bundle
    results = {item["state"]: item for item in simulate_many(fixtures, assumptions)}
    assert set(results) == set(HEADLINES)
    for code, expected in HEADLINES.items():
        assert _rounded(results[code]) == expected


def test_policy_document_prints_the_same_integers():
    text = (ROOT / "docs" / "POLICY_SCENARIO_COMPARISON.md").read_text(encoding="utf-8")
    for code, row in HEADLINES.items():
        rendered = "| {code} |".format(code=code)
        assert rendered in text
        for value in row:
            assert f"{value:,}" in text
