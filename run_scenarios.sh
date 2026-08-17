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
  echo "  $0 --irl <week_number>  [league options] [display flags]"
  echo "  $0 --test <path.json>   [display flags]"
  echo
  echo "League options select which league to download (--irl only):"
  echo "  --league-id <id> ESPN league id (default: the author's)"
  echo "  --year <year>    season to read"
  echo
  echo "Display flags are passed to the report and are all optional:"
  echo "  --html <path>    write an HTML report instead of printing to the terminal"
  echo "  --no-header      hide the summary line"
  echo "  --no-standings   hide the standings table"
  echo "  --no-matchups    hide next week's matchups"
  echo "  --no-stats       hide the season-review tables (HTML only)"
  exit 1
}

# Need at least the mode and its argument; anything after is a display flag
if [ $# -lt 2 ]; then
  usage
fi

MODE="$1"
ARG="$2"
shift 2

# Options are sorted by the stage that understands them: --league-id/--year
# belong to the download, --html picks the renderer, and the rest are the
# renderer's own. Passing them all to the last stage, as this script used to,
# meant the documented --league-id invocation died on "unrecognized arguments".
# Expanded below as ${ARRAY[@]+...} so an empty array is not treated as
# unbound under set -u (bash 3.2 on macOS).
DISPLAY_FLAGS=()
LEAGUE_FLAGS=()
HTML_OUT=""

# Each of these takes a value. A missing value, or another flag in its place, is
# an error -- otherwise '--html --no-stats' silently writes a file called
# '--no-stats'.
while [ $# -gt 0 ]; do
  case "$1" in
    --html|--league-id|--year)
      option="$1"
      shift
      if [ $# -eq 0 ]; then
        echo "Error: $option needs a value" >&2
        exit 1
      fi
      case "$1" in
        -*)
          echo "Error: $option needs a value, got '$1'" >&2
          exit 1
          ;;
      esac
      if [ "$option" = "--html" ]; then
        HTML_OUT="$1"
      else
        LEAGUE_FLAGS+=("$option" "$1")
      fi
      shift
      ;;
    *)
      DISPLAY_FLAGS+=("$1")
      shift
      ;;
  esac
done

if [ ${#LEAGUE_FLAGS[@]} -gt 0 ] && [ "$MODE" != "--irl" ]; then
  echo "Error: --league-id and --year only apply to --irl" >&2
  exit 1
fi

if [ -n "$HTML_OUT" ]; then
  REPORT=("$PY" scenario_engine/to_html.py -o "$HTML_OUT")
else
  REPORT=("$PY" scenario_engine/pretty_print.py)
fi

case "$MODE" in
  --irl)
    if ! [[ "$ARG" =~ ^[0-9]+$ ]]; then
      echo "Error: week_number must be an integer" >&2
      exit 1
    fi
    STAGE1=(
      "$PY" scenario_engine/league_data.py "$ARG"
      ${LEAGUE_FLAGS[@]+"${LEAGUE_FLAGS[@]}"}
    )
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
  | "${REPORT[@]}" ${DISPLAY_FLAGS[@]+"${DISPLAY_FLAGS[@]}"}
