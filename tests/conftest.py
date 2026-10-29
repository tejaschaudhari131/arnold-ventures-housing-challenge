# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Shared bundle for the equation and identity tests."""

from __future__ import annotations

import pytest

from src.bundle import load_bundle


@pytest.fixture(scope="session")
def bundle():
    return load_bundle()
