#!/usr/bin/env bash
# Start the web simulator, or write the comparison exports.
#   bash scripts/run.sh
#   bash scripts/run.sh report --out output
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi
export PYTHONPATH="$ROOT"
command="${1:-serve}"
if [[ "$command" == "report" || "$command" == "run" ]]; then
  shift
  exec "$PY" -m src.cli run "$@"
fi
if [[ "$command" == "serve" ]]; then
  shift
fi
exec "$PY" -m src.cli serve "$@"
