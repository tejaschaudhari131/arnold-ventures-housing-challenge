# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Characterization observations. Defect-flagged values are not accepted answers."""

from __future__ import annotations

import json
from pathlib import Path

from src.bundle import load_bundle
from src.lab.config import central_params
from src.lab.data import load_state
from src.lab.engine import evaluate_state, package_decomposition, package_variants
from src.model.engine import simulate_state

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "characterization.json"


def test_characterized_observations_still_match_and_defects_stay_open():
    recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixtures, assumptions = load_bundle()
    screen = simulate_state(fixtures, assumptions, "PA")
    lab = evaluate_state(load_state("PA"), central_params(), variants=package_variants(central_params()))
    decomp = package_decomposition(lab)
    assert screen["baseline_completions_5yr"] == recorded["screening_pa"]["baseline_completions_5yr"]["value"]
    assert round(screen["scenarios"]["adu"]["incremental_completions"], 1) == recorded["screening_pa"]["adu_incremental_completions"]["value"]
    assert recorded["screening_pa"]["adu_incremental_completions"]["defect"] == 6
    assert round(screen["scenarios"]["combined"]["incremental_completions"], 1) == recorded["screening_pa"]["package_incremental_completions"]["value"]
    assert round(screen["scenarios"]["combined"]["capacity_completions"], 1) == recorded["screening_pa"]["package_capacity_completions"]["value"]
    assert recorded["screening_pa"]["package_capacity_completions"]["defect"] == 9
    assert screen["scenarios"]["baseline"]["capacity_completions_basis"] == "level"
    assert screen["scenarios"]["adu"]["capacity_completions_basis"] == "increment"
    assert round(lab["statewide"]["baseline"]["delivery"], 1) == recorded["lab_pa"]["baseline_central"]["value"]
    assert round(lab["statewide"]["adu"]["delta"], 1) == recorded["lab_pa"]["adu_central"]["value"]
    assert recorded["lab_pa"]["adu_central"]["defect"] == 6
    assert round(decomp["legalization_resolved"], 1) == recorded["lab_pa"]["adu_mm_joint"]["value"]
    assert round(decomp["legalization_if_summed"], 1) == recorded["lab_pa"]["adu_mm_sum"]["value"]
    assert recorded["lab_pa"]["adu_mm_joint"]["defect"] == 4
    assert recorded["lab_pa"]["adu_central"]["value"] != recorded["screening_pa"]["adu_incremental_completions"]["value"]
