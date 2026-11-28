#!/usr/bin/env bash
# ========= Copyright (c) 2026 TTFISH. Licensed under the MIT License. =========
# See the LICENSE file in the project root for the full license text.
#
# SPDX-License-Identifier: MIT
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${MORPHEUS_ROOT_DIR:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
PYTHON="${ROOT_DIR}/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python"
daily=("$PYTHON" "$ROOT_DIR/src/execute_daily_schedule.py" --recording "${MORPHEUS_RECORDING:-full}" --week "${MORPHEUS_WEEK:-1}")
for arg in "$@"; do
    case "$arg" in --date|--date=*) exec "${daily[@]}" "$@" ;; esac
done
if [[ -n "${MORPHEUS_DATE:-}" ]]; then
    exec "${daily[@]}" --date "$MORPHEUS_DATE" "$@"
fi
run_log=$(mktemp)
trap 'rm -f "$run_log"' EXIT
prior_run=""
for day in Friday Saturday Sunday; do
    day_args=(--date "$day" "$@")
    if [[ -n "$prior_run" ]]; then day_args+=(--previous-run "$prior_run"); fi
    "${daily[@]}" "${day_args[@]}" | tee "$run_log"
    prior_run=$(tail -n 1 "$run_log" | "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["output"])')
done
