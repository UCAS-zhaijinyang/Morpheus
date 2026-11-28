#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${MORPHEUS_ROOT_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
PYTHON="${ROOT_DIR}/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python"

if [[ -n "${MORPHEUS_SCENARIO_ID:-}" ]]; then
    scenarios="$MORPHEUS_SCENARIO_ID"
else
    scenarios=$("$PYTHON" "$ROOT_DIR/src/scenario_catalog.py")
fi

args=(--week "${MORPHEUS_SCENARIO_WEEK:-1}" --date "${MORPHEUS_SCENARIO_DAY:-Monday}")
if [[ -n "${MORPHEUS_EMPLOYEE_ID:-}" ]]; then args+=(--employee "$MORPHEUS_EMPLOYEE_ID"); fi

for arg in "$@"; do
    case "$arg" in
        --scenario|--scenario=*)
            exec "$PYTHON" "$ROOT_DIR/src/execute_daily_schedule.py" --recording "${MORPHEUS_RECORDING:-full}" "${args[@]}" "$@" ;;
    esac
done
while IFS= read -r scenario; do
    "$PYTHON" "$ROOT_DIR/src/execute_daily_schedule.py" --recording "${MORPHEUS_RECORDING:-full}" \
        --scenario "$scenario" "${args[@]}" "$@"
done <<< "$scenarios"
