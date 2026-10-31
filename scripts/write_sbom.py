#!/usr/bin/env python3
# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Write a CycloneDX 1.5 SBOM for the pins in requirements.txt."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
OUTPUT = ROOT / "docs" / "sbom.cdx.json"

LICENSES = {"PyYAML": "MIT", "pytest": "MIT", "ruff": "MIT"}
SCOPES = {"PyYAML": "required", "pytest": "optional", "ruff": "optional"}
PURLs = {"PyYAML": "pyyaml"}


def pins() -> list[tuple[str, str]]:
    out = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        name, version = stripped.split("==")
        out.append((name, version))
    return out


def document(now: str | None = None) -> dict:
    stamp = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    components = []
    for name, version in pins():
        purl_name = PURLs.get(name, name.lower())
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "licenses": [{"license": {"id": LICENSES[name]}}],
                "purl": f"pkg:pypi/{purl_name}@{version}",
                "scope": SCOPES[name],
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": stamp,
            "tools": [
                {
                    "vendor": "Stateframe",
                    "name": "hand-maintained CycloneDX for the direct pins in requirements.txt",
                    "version": "1.0.0",
                }
            ],
            "component": {
                "type": "application",
                "name": "stateframe",
                "version": "1.0.0",
                "licenses": [{"license": {"id": "Apache-2.0"}}],
                "authors": [
                    {"name": "Tejas Chaudhari", "email": "tchaudha@andrew.cmu.edu"},
                    {"name": "Yoon Yik Ng", "email": "yoonyikn@andrew.cmu.edu"},
                    {"name": "Christopher Severns", "email": "cseverns@andrew.cmu.edu"},
                ],
            },
        },
        "components": components,
    }


def main() -> int:
    existing = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    stamp = existing.get("metadata", {}).get("timestamp")
    OUTPUT.write_text(json.dumps(document(stamp), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
