#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${MORPHEUS_ROOT_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
WORKERS="${MORPHEUS_SCALE_WORKERS:-8}"
EMPLOYEES="${MORPHEUS_EMPLOYEE_NUMBER:-100}"
WEEKS="${MORPHEUS_PERIOD_WEEKS:-13}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON="$ROOT_DIR/.venv/bin/python"
else
    PYTHON="python"
fi

exec "$PYTHON" "$ROOT_DIR/src/scale_simulation.py" \
    --employees "$EMPLOYEES" \
    --weeks "$WEEKS" \
    --workers "$WORKERS"
