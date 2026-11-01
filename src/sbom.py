# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Resolved CycloneDX SBOM for the app pin and the dev pins.

Direct pins come from requirements.txt. Transitive packages are the ones
actually installed for those pins, split into runtime and dev scopes.
"""

from __future__ import annotations

import json
import re
from importlib.metadata import metadata, requires, version
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
OUTPUT = ROOT / "docs" / "sbom.cdx.json"

RUNTIME = {"pyyaml"}
APPROVED = {
    "MIT": "MIT",
    "Apache-2.0": "Apache-2.0",
    "BSD-2-Clause": "BSD-2-Clause",
    "BSD-3-Clause": "BSD-3-Clause",
}
FORBIDDEN = ("GPL", "LGPL", "AGPL", "MPL", "EUPL", "CC0", "SSPL", "Commons Clause")
_CLASSIFIER = {
    "MIT License": "MIT",
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
}


def direct_pins() -> list[tuple[str, str, str]]:
    """Return (distribution name, version, scope) for requirements.txt."""
    pins = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or "==" not in stripped:
            continue
        name, pinned = stripped.split("==", 1)
        scope = "required" if name.lower() in RUNTIME else "optional"
        pins.append((name, pinned, scope))
    return pins


def _marker_ok(req: Requirement) -> bool:
    if req.marker is None:
        return True
    # Extras such as pytest[dev] are not part of the installed test runner.
    if "extra" in str(req.marker):
        return False
    return bool(req.marker.evaluate())


def _dist_name(name: str) -> str:
    return name.lower().replace("_", "-")


def resolved_graph() -> dict[str, dict]:
    """Installed packages reachable from the direct pins, keyed by normalized name."""
    pins = direct_pins()
    pin_names = {_dist_name(name): name for name, _version, _scope in pins}
    scope_of = {_dist_name(name): scope for name, _version, scope in pins}
    queue = [name for name, _version, _scope in pins]
    seen: dict[str, dict] = {}
    while queue:
        name = queue.pop(0)
        key = _dist_name(name)
        if key in seen:
            continue
        installed = version(name)
        parents = requires(name) or []
        depends: list[str] = []
        for raw in parents:
            req = Requirement(raw)
            if not _marker_ok(req):
                continue
            depends.append(req.name)
            queue.append(req.name)
        seen[key] = {
            "name": pin_names.get(key, name),
            "version": installed,
            "scope": scope_of.get(key, "optional"),
            "depends": depends,
            "licenses": license_ids(name),
        }
    # Dependencies of the runtime pin inherit required.
    changed = True
    while changed:
        changed = False
        for item in seen.values():
            if item["scope"] != "required":
                continue
            for dep in item["depends"]:
                child = seen.get(_dist_name(dep))
                if child and child["scope"] != "required":
                    child["scope"] = "required"
                    changed = True
    return seen


def license_ids(dist_name: str) -> list[str]:
    info = metadata(dist_name)
    found: list[str] = []
    expression = info.get("License-Expression") or ""
    license_field = info.get("License") or ""
    blob = f"{expression} {license_field}"
    for classifier in info.get_all("Classifier") or []:
        if "License" not in classifier:
            continue
        blob += " " + classifier
        tail = classifier.split("::")[-1].strip()
        mapped = _CLASSIFIER.get(tail)
        if mapped and mapped not in found:
            found.append(mapped)
    upper = blob.upper()
    for token in FORBIDDEN:
        if token in upper:
            raise ValueError(f"{dist_name} license text contains {token}")
    for raw_id, canonical in APPROVED.items():
        if re.search(rf"\b{re.escape(raw_id)}\b", blob) and canonical not in found:
            found.append(canonical)
    if not found:
        raise ValueError(f"{dist_name} has no approved license identifier")
    return found


def document(now: str = "2026-11-01T08:00:00Z") -> dict:
    graph = resolved_graph()
    components = []
    dependencies = []
    for key in sorted(graph):
        item = graph[key]
        purl = f"pkg:pypi/{key}@{item['version']}"
        licenses = [{"license": {"id": license_id}} for license_id in item["licenses"]]
        components.append(
            {
                "type": "library",
                "name": item["name"],
                "version": item["version"],
                "licenses": licenses,
                "purl": purl,
                "scope": item["scope"],
            }
        )
        dependencies.append(
            {
                "ref": purl,
                "dependsOn": [
                    f"pkg:pypi/{_dist_name(dep)}@{graph[_dist_name(dep)]['version']}"
                    for dep in item["depends"]
                    if _dist_name(dep) in graph
                ],
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": now,
            "tools": [
                {
                    "vendor": "Stateframe",
                    "name": "resolved from the installed requirements.txt tree",
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
        "dependencies": dependencies,
    }


def main() -> int:
    OUTPUT.write_text(json.dumps(document(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
