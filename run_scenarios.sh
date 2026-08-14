#!/bin/bash

# Usage examples:
#   ./run_scenarios.sh --irl 13
#   ./run_scenarios.sh --test scenario_engine_tests/week13.json

# pipefail so a failing stage isn't hidden by the rest of the pipe
set -euo pipefail

# Run from the repo root regardless of where we were invoked
cd "$(dirname "${BASH_SOURCE[0]}")"

# Prefer the venv interpreter if one was built
if [ -x env/bin/python ]; then
  PY=env/bin/python
else
  PY=python3
fi

usage() {
  echo "Usage:"
  echo "  $0 --irl <week_number>  [display flags]"
  echo "  $0 --test <path.json>   [display flags]"
  echo
  echo "Display flags are passed to the report and are all optional:"
  echo "  --no-header      hide the summary line"
  echo "  --no-standings   hide the standings table"
  echo "  --no-matchups    hide next week's matchups"
  exit 1
}

# Need at least the mode and its argument; anything after is a display flag
if [ $# -lt 2 ]; then
  usage
fi

MODE="$1"
ARG="$2"
shift 2
# Expanded below as ${DISPLAY_FLAGS[@]+...} so an empty array is not
# treated as unbound under set -u (bash 3.2 on macOS).
DISPLAY_FLAGS=("$@")

case "$MODE" in
  --irl)
    if ! [[ "$ARG" =~ ^[0-9]+$ ]]; then
      echo "Error: week_number must be an integer" >&2
      exit 1
    fi
    STAGE1=("$PY" scenario_engine/league_data.py "$ARG")
    ;;
  --test)
    if [ ! -f "$ARG" ]; then
      echo "Error: no such file: $ARG" >&2
      exit 1
    fi
    STAGE1=("$PY" scenario_engine/league_data.py --test "$ARG")
    ;;
  *)
    usage
    ;;
esac

# Run pipeline
"${STAGE1[@]}" \
  | "$PY" scenario_engine/refine_current_week.py \
  | "$PY" scenario_engine/generate_perms.py \
  | "$PY" scenario_engine/refine_hypothetical.py \
  | "$PY" scenario_engine/pretty_print.py ${DISPLAY_FLAGS[@]+"${DISPLAY_FLAGS[@]}"}
