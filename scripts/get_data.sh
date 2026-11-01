#!/usr/bin/env bash
# Fetch Census ACS, BPS, PEP, gazetteer, and FHFA files.
# Any failure in the acquirer — a network error (exit 2) or an unexpected
# crash — leaves the committed benchmark in data/sample/ in place and this
# script exits 0, so a clean checkout works offline and in CI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -n "${STATEFRAME_PYTHON:-}" ]]; then
  PY="$STATEFRAME_PYTHON"
elif [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi
export PYTHONPATH="$ROOT"
set +e
"$PY" -m src.data.acquire "$@"
code=$?
set -e
if [[ "$code" -ne 0 ]]; then
  echo "Live acquisition failed (exit ${code}). Using the committed benchmark in data/sample/."
  exit 0
fi
exit 0
