#!/bin/bash

# Usage examples:
#   ./run_scenarios.sh --irl 13
#   ./run_scenarios.sh --test test_week.json

# Check at least 2 arguments
if [ $# -lt 2 ]; then
  echo "Usage:"
  echo "  $0 --irl <week_number>"
  echo "  $0 --test <path_to_file.json>"
  exit 1
fi

MODE="$1"
ARG="$2"

# Validate mode
if [ "$MODE" != "--irl" ] && [ "$MODE" != "--test" ]; then
  echo "Error: First argument must be --irl or --test"
  exit 1
fi

# Run pipeline
if [ "$MODE" == "--irl" ]; then
  python3 scenario_engine/league_data.py "$ARG" | \
  python3 scenario_engine/refine_current_week.py | \
  python3 scenario_engine/generate_perms.py | \
  python3 scenario_engine/refine_hypothetical.py | \
  python3 scenario_engine/pretty_print.py
else
  # --test mode
  python3 scenario_engine/league_data.py --test "$ARG" | \
  python3 scenario_engine/refine_current_week.py | \
  python3 scenario_engine/generate_perms.py | \
  python3 scenario_engine/refine_hypothetical.py | \
  python3 scenario_engine/pretty_print.py
fi
