# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""PHASE4_SPEC §6c, with D12: the lot-path mapping is decided."""

from __future__ import annotations

import yaml

from src.lab.config import ROOT
from src.web.server import App

CONFIG = yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text(encoding="utf-8"))["parameters"]
NAMES = sorted(name for name in CONFIG if name.startswith("completion_ratio_"))


def test_all_completion_ratios_exposed():
    assert NAMES == ["completion_ratio_adu", "completion_ratio_mf", "completion_ratio_sf", "completion_ratio_small"]
    app = App()
    for state in ["PA", "NH"]:
        catalog = app.assumption_catalog(state)
        exposed = catalog["completion_ratios"]
        assert sorted(exposed) == NAMES
        for name in NAMES:
            for key in ("low", "central", "high"):
                assert exposed[name][key] == CONFIG[name][key]
            assert exposed[name]["low"] <= exposed[name]["central"] <= exposed[name]["high"]
            assert exposed[name]["tag"] == "assumed"
        assert exposed["completion_ratio_mf"]["central"] == 0.90
        assert "completion_ratio_mf" in [row["name"] for row in catalog["parameters"]]
        lot = catalog["lab_completion_lot"]
        assert lot["status"] == "decided"
        assert lot["tag"] == "assumed"
        assert lot["mapping"]["adu"]["param"] == "completion_ratio_adu"
        assert lot["mapping"]["mm2"]["param"] == "completion_ratio_small"
        assert lot["mapping"]["mm4"]["param"] == "completion_ratio_small"
        assert lot["mapping"]["mm6"]["param"] == "completion_ratio_mf"
        assert lot["mapping"]["adu"]["central"] == CONFIG["completion_ratio_adu"]["central"]
        assert lot["mapping"]["mm6"]["central"] == 0.90
