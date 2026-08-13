"""End-to-end contracts between pipeline stages, driven by subprocess."""

import json
import re

import pytest

FIXTURES = ["week12.json", "week13.json", "PC_test.json"]

ANSI = re.compile(r"\033\[[0-9;]*m")


@pytest.mark.parametrize("name", FIXTURES)
def test_stage1_test_mode_needs_no_third_party_packages(stage1_json, name):
    """--test must not require espn_api: it makes no network calls."""
    payload = json.loads(stage1_json(name))

    assert set(payload) >= {"league_settings", "teams", "next_week_matchups"}
    assert payload["teams"], "fixture should carry at least one team"


@pytest.mark.parametrize("name", FIXTURES)
def test_stage2_emits_the_documented_wire_format(stage1_json, run_stages, name):
    code, out, err = run_stages(
        ["scenario_engine/refine_current_week.py"], stage1_json(name)
    )
    assert code == 0, err

    payload = json.loads(out)
    assert set(payload) == {
        "league_data",
        "next_week_matchups",
        "remaining_matchups",
        "standings",
    }
    assert set(payload["league_data"]) == {
        "playoff_spots",
        "num_weeks",
        "remaining_weeks",
        "current_week",
    }

    # remaining_matchups is one entry per week left, and its first week must
    # agree with next_week_matchups on who is playing whom.
    remaining = payload["remaining_matchups"]
    assert len(remaining) == payload["league_data"]["remaining_weeks"]
    if remaining:
        as_pairs = {frozenset((m["team1"], m["team2"])) for m in remaining[0]}
        next_pairs = {
            frozenset((m["team1"], m["team2"])) for m in payload["next_week_matchups"]
        }
        assert as_pairs == next_pairs


@pytest.mark.parametrize("name", FIXTURES)
def test_whole_pipeline_runs_clean(stage1_json, run_stages, all_stages, name):
    code, out, err = run_stages(all_stages, stage1_json(name))

    assert code == 0, f"pipeline failed:\n{err}"
    assert "CLINCH SCENARIOS" in out
    assert "ELIMINATION SCENARIOS" in out


@pytest.mark.parametrize("name", FIXTURES)
def test_report_carries_no_debug_output(stage1_json, run_stages, all_stages, name):
    code, out, err = run_stages(all_stages, stage1_json(name))
    assert code == 0, err

    assert "second filtered win" not in out
    assert '"clinch_scenarios"' not in out, "raw scenario JSON leaked into the report"


@pytest.mark.parametrize("name", FIXTURES)
def test_no_team_is_listed_as_its_own_condition(stage1_json, run_stages, all_stages, name):
    """A team's own result is stated as 'a WIN'/'a LOSS', never as a condition.

    The elimination block used to filter the wrong side, so a team could be
    told it is eliminated with "a LOSS and <itself> WIN".
    """
    code, out, err = run_stages(all_stages, stage1_json(name))
    assert code == 0, err
    plain = ANSI.sub("", out)

    current = None
    for line in plain.splitlines():
        header = re.match(r"={6} (.+?) (?:Clinches|Eliminated|Clinched)", line)
        if header:
            current = header.group(1)
            continue
        if current and line.strip().startswith("- "):
            assert f"{current} WIN" not in line, (
                f"{current} is listed as a condition of its own scenario: {line!r}"
            )
