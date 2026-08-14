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
    assert '"matchup"' not in out, "raw scenario JSON leaked into the report"
    assert '"winner"' not in out, "raw scenario JSON leaked into the report"


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


# --- display sections ---------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURES)
def test_report_shows_header_standings_and_matchups_by_default(
    stage1_json, run_stages, all_stages, name
):
    code, out, err = run_stages(all_stages, stage1_json(name))
    assert code == 0, err
    plain = ANSI.sub("", out)

    assert "Playoff spots" in plain
    assert "Up for grabs" in plain
    assert "STANDINGS" in plain
    assert "MATCHUPS" in plain or "No games left" in plain
    assert "playoff cut line" in plain


@pytest.mark.parametrize(
    "flag,absent",
    [
        ("--no-header", "Playoff spots"),
        ("--no-standings", "STANDINGS"),
        ("--no-matchups", "MATCHUPS"),
    ],
)
def test_each_display_section_can_be_switched_off(stage1_json, run_stages, flag, absent):
    import subprocess
    import sys as _sys
    from pathlib import Path

    root = Path(__file__).parent.parent
    payload = stage1_json("week13.json")
    for stage in [
        "scenario_engine/refine_current_week.py",
        "scenario_engine/generate_perms.py",
        "scenario_engine/refine_hypothetical.py",
    ]:
        result = subprocess.run(
            [_sys.executable, stage], input=payload, capture_output=True,
            text=True, cwd=root,
        )
        assert result.returncode == 0, result.stderr
        payload = result.stdout

    result = subprocess.run(
        [_sys.executable, "scenario_engine/pretty_print.py", flag],
        input=payload, capture_output=True, text=True, cwd=root,
    )
    assert result.returncode == 0, result.stderr
    plain = ANSI.sub("", result.stdout)

    assert absent not in plain
    # the scenarios themselves are never suppressed
    assert "CLINCH SCENARIOS" in plain
    assert "ELIMINATION SCENARIOS" in plain


@pytest.mark.parametrize("name", FIXTURES)
def test_the_cut_line_sits_below_the_last_playoff_seat(
    stage1_json, run_stages, all_stages, name
):
    code, out, err = run_stages(all_stages, stage1_json(name))
    assert code == 0, err
    plain = ANSI.sub("", out)

    rows = []
    for line in plain.splitlines():
        stripped = line.strip()
        if "playoff cut line" in stripped:
            rows.append("CUT")
        elif stripped[:2].strip().isdigit() and "  " in stripped:
            rows.append("team")
        if "CLINCH SCENARIOS" in stripped:
            break

    assert "CUT" in rows
    # every seat above the line, every non-seat below it
    spots = json.loads(stage1_json(name))["league_settings"]["playoff_spots"]
    assert rows.index("CUT") == spots
