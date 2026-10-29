# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Load the committed benchmark, the transit inventory, and the assumption file."""

from __future__ import annotations

from src.data.schema import TRANSIT_PATH, load_fixtures, load_json
from src.model.assumptions import Assumptions, load_assumptions
from src.model.engine import attach_transit


def load_bundle():
    assumptions: Assumptions = load_assumptions()
    fixtures = attach_transit(load_fixtures(), load_json(TRANSIT_PATH))
    return fixtures, assumptions
