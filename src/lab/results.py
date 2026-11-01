# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Precomputed Lab results.

The full analysis (2,000 envelope draws, zoning bounds, ACS band, one-at-a-time
runs, switching values) is precomputed. The web app and the write-up read a
compact copy from ``data/sample/lab/results_{STATE}.json``. Vercel never runs
the envelope (``allow_compute=False``).

Each file carries a fingerprint of every input it depends on: the Lab
configuration, the state's evidence file and extracts, and the Lab source
code. ``tests/test_lab_results.py`` fails if the committed copy is stale, and
rechecks its central values against a fresh run. Regenerate with
``python -m src.lab.results --write-sample``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from src.lab.config import CACHE_DIR, CONFIG_DIR, LAB_STATES, ROOT, SAMPLE_DIR, load_scenarios
from src.lab.data import load_state
from src.lab.uncertainty import analyze, compared_scenarios

SOURCE_FILES = ("config.py", "data.py", "engine.py", "options.py", "uncertainty.py", "results.py")
RESULT_FIELDS = ("eligible", "feasible", "host_delta", "pipeline_delta", "timing_delta")


def fingerprint(code: str) -> str:
    digest = hashlib.sha256()
    paths = [
        CONFIG_DIR / "scenarios.yaml",
        CONFIG_DIR / "assumptions.yaml",
        CONFIG_DIR / "evidence" / f"{code}.yaml",
        SAMPLE_DIR / f"{code}.json",
    ]
    if code == "PA":
        paths.append(SAMPLE_DIR / "allegheny_lots.json")
    paths += [ROOT / "src" / "lab" / name for name in SOURCE_FILES]
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]


def _r(value: float) -> float:
    return round(float(value), 1)


def _results_block(layer: dict[str, Any], central_rows: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for sid, row in layer["scenarios"].items():
        entry = {
            "central": _r(row["central"]),
            "p10": _r(row["envelope"]["p10"]),
            "p50": _r(row["envelope"]["p50"]),
            "p90": _r(row["envelope"]["p90"]),
            "p10_se": _r(row["envelope"].get("p10_se", 0.0)),
            "p50_se": _r(row["envelope"].get("p50_se", 0.0)),
            "p90_se": _r(row["envelope"].get("p90_se", 0.0)),
            "zoning_low": _r(row["zoning"]["low"]),
            "zoning_high": _r(row["zoning"]["high"]),
            "logical_low": _r(row["zoning"]["logical_low"]),
            "logical_high": _r(row["zoning"]["logical_high"]),
            "acs_moe": _r(row["acs_moe"]),
        }
        source = central_rows[sid]
        if sid == "baseline":
            entry["pipeline_baseline"] = _r(source["pipeline_baseline"])
            entry["pipeline_adjustment"] = _r(source["pipeline_adjustment"])
            host = source["host_adjustment"]
            entry["host_adjustment"] = _r(host["delivered"] if isinstance(host, dict) else host)
        else:
            for f in RESULT_FIELDS:
                entry[f] = _r(source.get(f, 0.0))
            entry["by_option"] = {k: _r(v) for k, v in source.get("by_option", {}).items() if abs(v) >= 0.05}
        out[sid] = entry
    return out


def _pair(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "leader": row["leader"],
        "trailer": row["trailer"],
        "gap": _r(row["gap"]),
        "flip_share": round(row["flip_share"], 3),
        "zoning_flip": row["zoning_flip"],
        "moe_gap": _r(row["moe_gap"]),
        "close_call": row["close_call"],
        "reasons": row["reasons"],
    }


def compact(analysis: dict[str, Any], code: str) -> dict[str, Any]:
    scenarios = load_scenarios()["scenarios"]
    central = analysis["central"]
    sw = analysis["statewide"]
    out: dict[str, Any] = {
        "state": code,
        "name": LAB_STATES[code]["name"],
        "role": LAB_STATES[code]["role"],
        "fingerprint": fingerprint(code),
        "generated": date.today().isoformat(),
        "draws": analysis["draws"],
        "seed": analysis["seed"],
        "envelope_params": analysis["envelope_params"],
        "close_call_flip_share": analysis["close_call_flip_share"],
        "coverage": {k: round(v, 4) for k, v in analysis["coverage"].items()},
        "implied_cost_elasticity": round(analysis["implied_cost_elasticity"], 3),
        "scenarios": [
            {"id": sid, "label": scenarios[sid]["label"], "short": scenarios[sid]["short"], "kind": scenarios[sid]["kind"]}
            for sid in scenarios
        ],
        "statewide": {
            "results": _results_block(sw, central["statewide"]),
            "ranking": sw["ranking"],
            "benchmark_ranking": sw["benchmark_ranking"],
            "pairs": {key: _pair(row) for key, row in sw["pairs"].items()},
            "top_pair": _pair(sw["top_pair"]),
            "top_benchmark_pair": _pair(sw["top_benchmark_pair"]),
            "package_decomposition": {k: _r(v) for k, v in sw["package_decomposition"].items()},
        },
        "counties": [],
    }
    if "one_at_a_time" in analysis:
        out["statewide"]["one_at_a_time"] = {
            name: {end: {sid: _r(v) for sid, v in vals.items()} for end, vals in ends.items()}
            for name, ends in analysis["one_at_a_time"].items()
        }
        wwc = analysis["what_would_change"]
        out["statewide"]["what_would_change"] = {
            "pair": wwc["pair"],
            "switches": [
                {
                    **{k: v for k, v in row.items() if k != "zero_pipeline"},
                    "central": round(row["central"], 6),
                    "switch_at": round(row["switch_at"], 6),
                    **(
                        {"zero_pipeline": {sid: _r(val) for sid, val in row["zero_pipeline"].items()}}
                        if "zero_pipeline" in row
                        else {}
                    ),
                }
                for row in wwc["switches"]
            ],
        }
    if "elasticity_zero" in analysis:
        ez = analysis["elasticity_zero"]
        out["statewide"]["elasticity_zero"] = {
            "pipeline_sigma": ez["pipeline_sigma"],
            "implied_cost_elasticity": round(ez["implied_cost_elasticity"], 4),
            "statewide": {sid: _r(val) for sid, val in ez["statewide"].items()},
        }
    for index, row in enumerate(analysis["counties"]):
        crow = central["counties"][index]
        out["counties"].append(
            {
                "fips": row["fips"],
                "name": row["name"],
                "hosts": _r(crow["hosts"]),
                "coverage": {k: round(v, 4) for k, v in row["coverage"].items()},
                "results": _results_block(row, crow["scenarios"]),
                "ranking": row["ranking"],
                "benchmark_ranking": row["benchmark_ranking"],
                "top_pair": _pair(row["top_pair"]),
                "top_benchmark_pair": _pair(row["top_benchmark_pair"]),
                "pairs": {key: [round(p["flip_share"], 3), p["close_call"]] for key, p in row["pairs"].items()},
                "package_decomposition": {k: _r(v) for k, v in row["package_decomposition"].items()},
            }
        )
    return out


def compute(code: str, draws: int | None = None) -> dict[str, Any]:
    return compact(analyze(load_state(code), draws=draws), code)


def sample_path(code: str) -> Path:
    return SAMPLE_DIR / f"results_{code}.json"


def load_results(code: str, allow_compute: bool = True) -> dict[str, Any]:
    """Committed results if current, else a cached run, else compute and cache."""
    code = code.upper()
    current = fingerprint(code)
    for path in (sample_path(code), CACHE_DIR / f"results_{code}.json"):
        if path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("fingerprint") == current:
                return doc
    if not allow_compute:
        raise FileNotFoundError(f"No current Lab results for {code}; run python -m src.lab.results --write-sample")
    doc = compute(code)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"results_{code}.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute Lab results with all uncertainty layers.")
    parser.add_argument("--states", default=",".join(LAB_STATES))
    parser.add_argument("--draws", type=int, default=None)
    parser.add_argument("--write-sample", action="store_true", help="Refresh data/sample/lab/results_*.json")
    args = parser.parse_args(argv)
    for code in [c.strip().upper() for c in args.states.split(",") if c.strip()]:
        started = time.time()
        doc = compute(code, args.draws)
        target = sample_path(code) if args.write_sample else CACHE_DIR / f"results_{code}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
        sw = doc["statewide"]["results"]
        print(f"{code}: {time.time() - started:.0f}s -> {target}")
        for sid in ["baseline"] + compared_scenarios():
            row = sw[sid]
            print(f"  {sid:16s} {row['central']:>10,.0f}  envelope [{row['p10']:,.0f}, {row['p90']:,.0f}]  "
                  f"zoning [{row['zoning_low']:,.0f}, {row['zoning_high']:,.0f}]  ACS ±{row['acs_moe']:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
