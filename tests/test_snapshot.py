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
    "PA": (108950, 46261, 14111, 1038, 3373, 6490, 74114),
    "CT": (25455, 3077, 4813, 2514, 1127, 1606, 11033),
    "WI": (96473, 15846, 1798, 56, 1870, 5258, 25445),
    "UT": (121388, 8576, 10300, 1091, 1630, 6434, 27809),
    "OR": (77580, 4942, 10381, 3164, 1695, 4478, 24839),
    "HI": (17616, 2378, 5425, 118, 287, 603, 8958),
    "AZ": (267943, 31715, 21318, 346, 4484, 15920, 79357),
    "VA": (163509, 39352, 41077, 10789, 4724, 11409, 105804),
    "TN": (204644, 25857, 11676, 189, 2719, 12073, 55061),
    "RI": (6421, 2821, 2587, 189, 133, 370, 6298),
    "NH": (21478, 3489, 1766, 8, 238, 1077, 7170),
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
