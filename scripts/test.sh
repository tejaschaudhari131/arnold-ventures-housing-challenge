#!/usr/bin/env bash
# Run the compiler check and the pytest suite. Exits non-zero on failure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi
export PYTHONPATH="$ROOT"
"$PY" -m compileall -q src tests
"$PY" -m pytest
if [[ -x .venv/bin/ruff ]]; then
  .venv/bin/ruff check src tests
fi
