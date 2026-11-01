# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Compare committed Lab fingerprints without regenerating the envelope.

Full regeneration (``python -m src.lab.results``) takes about 7 minutes.
This check only hashes inputs and compares them to ``data/sample/lab``.
It is not part of the Lab results fingerprint.
"""

from __future__ import annotations

import argparse
import json

from src.lab.config import LAB_STATES
from src.lab.results import fingerprint, sample_path


def check_codes(codes: list[str]) -> int:
    failed = 0
    for code in codes:
        path = sample_path(code)
        if not path.exists():
            print(f"{code}: MISMATCH no committed file at {path}")
            failed += 1
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        current = fingerprint(code)
        committed = str(doc.get("fingerprint") or "")
        if committed == current:
            print(f"{code}: match {current}")
        else:
            print(f"{code}: MISMATCH committed {committed} current {current}")
            failed += 1
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check committed Lab result fingerprints.")
    parser.add_argument("--states", default=",".join(LAB_STATES))
    args = parser.parse_args(argv)
    codes = [code.strip().upper() for code in args.states.split(",") if code.strip()]
    return check_codes(codes)


if __name__ == "__main__":
    raise SystemExit(main())
