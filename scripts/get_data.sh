#!/usr/bin/env bash
# Fetch Census ACS, BPS, PEP, gazetteer, and FHFA files.
# Exit 2 from the acquirer means the network call failed. The committed
# benchmark in data/sample/ stays in place and this script still exits 0,
# so a clean checkout works offline and in CI.
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
"$PY" -m src.data.acquire "$@"
code=$?
set -e
if [[ "$code" -eq 2 ]]; then
  echo "Live acquisition is unavailable. Using the committed benchmark in data/sample/."
  exit 0
fi
exit "$code"
