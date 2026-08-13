import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent
FIXTURE_DIR = REPO_ROOT / "scenario_engine_tests"
ENGINE_DIR = REPO_ROOT / "scenario_engine"

# The pipeline stages are flat modules inside scenario_engine/
sys.path.insert(0, str(ENGINE_DIR))

# Stage 1 is intentionally absent: league_data.py has no __main__ guard, so it
# can only be exercised through a subprocess.
STAGES = [
    "scenario_engine/refine_current_week.py",
    "scenario_engine/generate_perms.py",
    "scenario_engine/refine_hypothetical.py",
    "scenario_engine/pretty_print.py",
]


@pytest.fixture
def load_fixture():
    """Load a JSON fixture from scenario_engine_tests/ by filename."""

    def _load(name):
        with open(FIXTURE_DIR / name) as f:
            return json.load(f)

    return _load


@pytest.fixture
def run_stages():
    """Run pipeline stages in sequence, piping each stdout into the next stdin.

    Runs the stages by hand rather than through a shell pipe so that a failure
    is attributed to the stage that actually failed. A bash pipeline reports
    only the last stage's exit code, which hides upstream errors.

    Returns (returncode, stdout, stderr) of the first failing stage, or of the
    last stage if every stage succeeded.
    """

    def _run(stages, stdin_text=""):
        payload = stdin_text
        result = None
        for stage in stages:
            result = subprocess.run(
                [sys.executable, stage],
                input=payload,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            if result.returncode != 0:
                return result.returncode, result.stdout, result.stderr
            payload = result.stdout
        return result.returncode, result.stdout, result.stderr

    return _run


@pytest.fixture
def all_stages():
    return list(STAGES)


@pytest.fixture
def stage1_json():
    """Run stage 1 in --test mode and return its raw JSON output."""

    def _run(fixture_name):
        result = subprocess.run(
            [
                sys.executable,
                "scenario_engine/league_data.py",
                "--test",
                str(FIXTURE_DIR / fixture_name),
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    return _run
