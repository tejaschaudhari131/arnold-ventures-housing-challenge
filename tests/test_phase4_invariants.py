# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Package invariants for the Phase 4 resolver (PHASE4_SPEC §7)."""

from __future__ import annotations

import itertools
import math

import pytest

from src.bundle import load_bundle
from src.model.engine import REFORM_IDS, simulate_state

FX, ASSUMPTIONS = load_bundle()
STATES = ["PA", "NH", "VA", "CT"]


def _value(result: dict, scenario: str = "combined") -> float:
    return float(result["scenarios"][scenario]["incremental_completions"])


def _run(state: str, bits: tuple[int, ...]) -> dict:
    weights = dict(zip(REFORM_IDS, bits))
    return simulate_state(FX, ASSUMPTIONS, state, reform_weights=weights)


@pytest.mark.parametrize("state", STATES)
def test_empty_is_zero(state):
    assert abs(_value(_run(state, (0, 0, 0, 0, 0)))) < 1e-6


@pytest.mark.parametrize("state", STATES)
def test_package_le_capacity(state):
    for bits in itertools.product([0, 1], repeat=5):
        scenarios = _run(state, bits)["scenarios"]["combined"]
        assert scenarios["incremental_completions"] <= scenarios["capacity_completions"] + 1e-6


@pytest.mark.parametrize("state", STATES)
def test_singleton_equals_standalone(state):
    names = {"adu": "adu", "missing_middle": "missing_middle", "tod": "tod", "parking": "parking", "fees": "fees"}
    for index, name in enumerate(REFORM_IDS):
        bits = tuple(1 if j == index else 0 for j in range(5))
        scenarios = _run(state, bits)["scenarios"]
        assert _value_of(scenarios["combined"]) == pytest.approx(_value_of(scenarios[names[name]]), rel=1e-6, abs=1.0)


def _value_of(row: dict) -> float:
    return float(row["incremental_completions"])


@pytest.mark.parametrize("state", STATES)
def test_decompositions_sum_exactly(state):
    results = {bits: _value(_run(state, bits)) for bits in itertools.product([0, 1], repeat=5)}
    full = results[(1, 1, 1, 1, 1)]
    assert sum(_shapley(results).values()) == pytest.approx(full, abs=0.5)
    for order in itertools.permutations(range(5)):
        bits = [0] * 5
        previous = results[tuple(bits)]
        total = 0.0
        for index in order:
            bits[index] = 1
            current = results[tuple(bits)]
            total += current - previous
            previous = current
        assert total == pytest.approx(full, abs=1e-6)


def _shapley(results: dict) -> dict[str, float]:
    n = 5
    out = {}
    for index, name in enumerate(REFORM_IDS):
        share = 0.0
        for bits in results:
            if bits[index] != 0:
                continue
            k = sum(bits)
            flipped = list(bits)
            flipped[index] = 1
            weight = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
            share += weight * (results[tuple(flipped)] - results[bits])
        out[name] = share
    return out


@pytest.mark.parametrize("state", STATES)
def test_monotone_zoning(state):
    results = {bits: _value(_run(state, bits)) for bits in itertools.product([0, 1], repeat=5)}
    for bits in results:
        for index in range(3):
            if bits[index] == 0:
                flipped = list(bits)
                flipped[index] = 1
                assert results[tuple(flipped)] >= results[bits] - 1.0


def test_deterministic():
    assert _value(_run("PA", (1, 1, 1, 1, 1))) == _value(_run("PA", (1, 1, 1, 1, 1)))


GOLDEN = {"PA": 46219, "NH": 4180}


@pytest.mark.parametrize("state", list(GOLDEN))
def test_golden(state):
    assert round(_value(_run(state, (1, 1, 1, 1, 1)))) == GOLDEN[state]
