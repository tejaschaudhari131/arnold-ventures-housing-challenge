# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""The Lab's scenario definitions must match the Participant Handbook."""

from datetime import date

from src.lab.config import (
    LAB_STATES,
    OPTIONS,
    STATUSES,
    load_assumptions,
    load_evidence,
    load_scenarios,
    ui_params,
)

OFFICIAL = {"adu", "missing_middle", "tod", "parking", "fees"}
CODING_PERIOD = (date(2026, 10, 14), date(2026, 12, 16))


def scenarios():
    return load_scenarios()["scenarios"]


def test_baseline_plus_at_least_three_official_benchmarks():
    doc = load_scenarios()
    assert scenarios()["baseline"]["kind"] == "baseline"
    modeled = set(doc["benchmarks_modeled"])
    assert modeled <= OFFICIAL
    assert len(modeled) >= 3
    for sid in modeled:
        assert scenarios()[sid]["kind"] == "benchmark"


def test_only_official_benchmarks_are_called_benchmarks():
    for sid, scenario in scenarios().items():
        if scenario["kind"] == "benchmark":
            assert sid in OFFICIAL
        if scenario["kind"] == "extra":
            assert "extra" in scenario["label"].lower()
            assert "state-specific" in scenario["label"].lower()


def test_horizon_is_five_years():
    assert load_scenarios()["horizon_years"] == 5
    assert load_assumptions()["horizon_years"] == 5


def test_adu_benchmark_matches_handbook():
    adu = scenarios()["adu"]
    assert adu["legalize"] == ["adu"]
    assert adu["levers"]["adu_max_per_host"] == 1
    assert adu["levers"]["adu_min_sqft"] == 600
    assert set(adu["levers"]["adu_forms"]) == {"detached", "semi_detached"}
    assert adu["levers"]["adu_parking_spaces"] == 0
    assert "600 square feet" in adu["handbook"]
    assert load_assumptions()["params"]["adu_sqft"]["low"] >= 600


def test_missing_middle_is_two_to_six_homes_up_to_three_stories():
    mm = scenarios()["missing_middle"]
    levers = mm["levers"]
    assert (levers["mm_min_units"], levers["mm_max_units"]) == (2, 6)
    assert levers["mm_max_stories"] == 3
    assert levers["setbacks_bind"] is False
    assert levers["lot_coverage_binds"] is False
    assert set(mm["legalize"]) == {"mm2", "mm4", "mm6"}
    assert "2–6 dwelling units" in mm["handbook"]


def test_parking_states_developer_parking_and_is_not_bundled_with_approval():
    parking = scenarios()["parking"]
    assert parking["levers"]["parking_minimums"] == "eliminated"
    assert parking["levers"]["developer_parking"] == "market_ratio"
    assert parking["levers"]["approval_reform"] is False
    assert parking["legalize"] == []
    params = load_assumptions()["params"]
    for ctx in ("urban", "suburban", "rural"):
        assert f"parking_market_{ctx}" in params
        assert params[f"parking_market_{ctx}"]["central"] <= params[f"parking_min_{ctx}"]["central"]
    assert "parking_sf_gap_share" in params
    assert scenarios()["approval"]["kind"] == "extra"
    assert "approval" not in scenarios()["package"]["combines"]


def test_fee_benchmark_is_fifty_percent_of_fifty_thousand():
    fees = scenarios()["fees"]
    assert fees["levers"]["fee_per_unit_baseline"] == 50000
    assert fees["levers"]["fee_cut_share"] == 0.5
    params = load_assumptions()["params"]
    assert params["fee_per_unit"]["locked"] and params["fee_per_unit"]["central"] == 50000
    assert params["fee_cut_share"]["locked"] and params["fee_cut_share"]["central"] == 0.5
    assert "fee_per_unit" not in ui_params()


def test_package_is_resolved_per_host_not_summed():
    package = scenarios()["package"]
    assert package["kind"] == "extra"
    assert package["resolution"] == "one_best_option_per_host"
    assert set(package["combines"]) == {"adu", "missing_middle", "parking", "fees"}


def test_every_scenario_quotes_the_handbook_and_uses_known_options():
    for sid, scenario in scenarios().items():
        assert len(scenario["handbook"]) > 40, sid
        assert set(scenario["legalize"]) <= set(OPTIONS)


def test_tod_is_documented_as_not_modeled_in_lab():
    assert "tod" in load_scenarios()["not_modeled_in_lab"]


def test_config_lock_dates_fall_inside_coding_period():
    for doc in (load_scenarios(), load_assumptions()):
        locked = date.fromisoformat(doc["locked"])
        assert CODING_PERIOD[0] <= locked <= CODING_PERIOD[1]


def test_every_assumption_has_a_band_unit_and_rationale():
    for name, spec in load_assumptions()["params"].items():
        assert spec["low"] <= spec["central"] <= spec["high"], name
        assert spec["rationale"].strip(), name
        if spec.get("ui"):
            assert spec["low"] < spec["high"], f"{name} is drawn but has no band"


def test_evidence_files_cite_https_sources_and_valid_statuses():
    for code in LAB_STATES:
        doc = load_evidence(code)
        assert doc["state"] == code
        for url in doc["statewide"].get("sources", []):
            assert url.startswith("https://")
        for rule in doc["rules"]:
            assert rule["sources"], rule["id"]
            assert all(url.startswith("https://") for url in rule["sources"])
            if rule["option"] in {"adu", "mm"}:
                assert rule["status"] in STATUSES


def test_pittsburgh_and_philadelphia_records():
    rules = {rule["id"]: rule for rule in load_evidence("PA")["rules"]}
    pgh = rules["pittsburgh_adu_2026"]
    assert pgh["status"] == "allowed" and pgh["effective"] == "2026-10-29"
    assert pgh["geography"] == {"county": "42003", "place": "4261000", "place_name": "Pittsburgh city"}
    assert pgh["parking_spaces"] == 0
    assert rules["philadelphia_adu"]["status"] == "prohibited"
    assert load_evidence("PA")["statewide"]["adu"] == "unknown"


def test_new_hampshire_statutes():
    doc = load_evidence("NH")
    assert doc["statewide"]["parking_cap_per_unit"] == 1.0
    rules = {rule["id"]: rule for rule in doc["rules"]}
    assert rules["nh_adu_detached_hosts"]["status"] == "allowed_with_parking"
    assert rules["nh_adu_attached_hosts"]["status"] == "unknown"
