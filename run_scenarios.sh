#!/bin/bash


# run with ./run_test.sh <path_to_weekfile.json>
if [ -z "$1" ]; then
  echo "Usage: ./run_test.sh <week_file.json>"
  exit 1
fi

python3 scenario_engine/refine_current_week.py "$1" | \
python3 scenario_engine/generate_perms.py | \
python3 scenario_engine/refine_hypothetical.py | \
python3 scenario_engine/pretty_print.py

