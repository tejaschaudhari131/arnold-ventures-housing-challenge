#!/usr/bin/env bash
# Fetch the Small Homes Policy Lab inputs (ACS 2024 5-year, BPS 2023-2025,
# gazetteers, county boundaries, optional HUD FMR and WPRDC Allegheny lots).
# Writes data/cache/lab/. Exit 2 from the acquirer means the network call
# failed: the committed extracts in data/sample/lab/ stay in place and this
# script exits 0 so a clean checkout still runs offline.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi
export PYTHONPATH="$ROOT"
set +e
"$PY" -m src.lab.acquire "$@"
code=$?
set -e
if [[ "$code" -eq 2 ]]; then
  echo "Live acquisition is unavailable. Using the committed Lab extracts in data/sample/lab/."
  exit 0
fi
exit "$code"
