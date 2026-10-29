# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Every pinned dependency uses an approved permissive license."""

from __future__ import annotations

from importlib.metadata import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"

APPROVED = {
    "pyyaml": "MIT",
    "pytest": "MIT",
    "ruff": "MIT",
}
FORBIDDEN_TOKENS = ("GPL", "LGPL", "AGPL", "MPL", "EUPL", "CC0", "SSPL", "Commons Clause")


def _pins() -> list[tuple[str, str]]:
    pins = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        name, version = stripped.split("==")
        pins.append((name, version))
    return pins


def test_requirements_are_pinned_and_allowlisted():
    pins = _pins()
    assert pins, "requirements.txt is empty"
    for name, _version in pins:
        assert name.lower() in APPROVED, name


def test_installed_metadata_matches_the_allowlist():
    for name, _version in _pins():
        info = metadata(name)
        license_text = (info.get("License") or "") + " " + " ".join(
            item for item in info.get_all("Classifier") or [] if "License" in item
        )
        upper = license_text.upper()
        for token in FORBIDDEN_TOKENS:
            assert token not in upper
        expected = APPROVED[name.lower()]
        assert expected.upper() in upper or expected.upper().replace("-", " ") in upper
