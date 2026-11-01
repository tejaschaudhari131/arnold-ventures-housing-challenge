#!/usr/bin/env python3
# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Write the resolved CycloneDX SBOM. See src/sbom.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sbom import document, main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
