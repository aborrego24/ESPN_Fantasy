"""add_stats: the optional last stage that attaches season stats for non-to_html renderers."""

import json
import sys

import pytest

sys.path.insert(0, "scenario_engine")
import add_stats  # noqa: E402
import league_stats  # noqa: E402
import margins  # noqa: E402
import strength  # noqa: E402

PIPELINE = [
    "scenario_engine/refine_current_week.py",
    "scenario_engine/generate_perms.py",
    "scenario_engine/refine_hypothetical.py",
    "scenario_engine/add_stats.py",
]


@pytest.mark.parametrize("name", ["week12.json", "week13.json"])
def test_stats_match_what_to_html_computes(stage1_json, run_stages, name):
    """The stage adds exactly the figures to_html's stats sections use, and leaves
    the rest of the payload alone."""
    code, out, err = run_stages(PIPELINE, stage1_json(name))
    assert code == 0, err
    payload = json.loads(out)
    base = payload["base_league_data"]
    ws, rm = base["weekly_scores"], base.get("remaining_matchups")

    assert set(payload) == {"base_league_data", "scenarios"}
    # Round-trip through JSON so tuples/ints compare the way they were serialized.
    expected = json.loads(json.dumps({
        "strength": strength.strength_table(ws, rm),
        "all_play": league_stats.all_play_records(ws),
        "schedule_luck": league_stats.schedule_luck(ws),
    }))
    assert base["stats"] == expected


@pytest.mark.parametrize("name", ["week12.json", "week13.json"])
def test_scenario_notes_say_what_to_html_says(stage1_json, run_stages, name):
    """Every note matches the sentence to_html writes under the same team, so the
    two renderers cannot drift into wording a verdict differently."""
    code, out, err = run_stages(PIPELINE, stage1_json(name))
    assert code == 0, err
    base = json.loads(out)["base_league_data"]
    thresholds = margins.load_thresholds()
    weeks = base["league_data"]["remaining_weeks"]

    for team in base["standings"]:
        entry = base["scenario_notes"].get(team["team_name"])
        expected = margins.describe(
            team.get("tiebreak"), weeks, thresholds, margins=team.get("margins")
        )
        assert (entry or {}).get("note") == expected
        if entry:
            assert entry["on_current_scoring"] == margins.qualifies_headline(
                team.get("tiebreak"), weeks, thresholds
            )


def test_a_team_with_no_tiebreak_dependency_gets_no_entry():
    """The common case: nothing to qualify, so nothing in the payload."""
    base = {
        "league_data": {"remaining_weeks": 2},
        "standings": [{"team_name": "A"}, {"team_name": "B", "tiebreak": None}],
    }
    assert add_stats.scenario_notes(base) == {}


def test_an_unremarkable_gap_is_flagged_for_the_headline():
    """A gap the league closes all the time is a live race, so the bare verdict
    overstates it and the headline has to say "on current scoring"."""
    base = {
        "league_data": {"remaining_weeks": 1},
        "standings": [{"team_name": "A", "tiebreak": {"rival": "B", "gap": 10.0}}],
    }
    entry = add_stats.scenario_notes(base)["A"]
    assert entry["on_current_scoring"] is True
    assert "live points race with B" in entry["note"]


def test_a_gap_the_league_has_never_closed_is_only_a_footnote():
    """The other end: the verdict stands, with the swing named for scale."""
    thresholds = {"by_weeks_remaining": {"1": {"max_observed": 120.0, "p99": 87.0}}}
    base = {
        "league_data": {"remaining_weeks": 1},
        "standings": [{"team_name": "A", "tiebreak": {"rival": "B", "gap": 400.0}}],
    }
    entry = add_stats.scenario_notes(base, thresholds)["A"]
    assert entry["on_current_scoring"] is False
    assert entry["note"] == (
        "barring a 400-point swing against B in the final week "
        "— the largest on record in this league is 120"
    )


def test_a_settled_season_has_nothing_left_to_qualify():
    """With no weeks left no gap can close, so the tiebreak is already decided."""
    base = {
        "league_data": {"remaining_weeks": 0},
        "standings": [{"team_name": "A", "tiebreak": {"rival": "B", "gap": 10.0}}],
    }
    assert add_stats.scenario_notes(base) == {}


def test_preseason_gets_only_the_preseason_view():
    base = {
        "weekly_scores": [{"name": "A", "weeks": []}, {"name": "B", "weeks": []}],
        "projected_ppg": {"A": 110.0, "B": 100.0},
        "remaining_matchups": [[{"team1": "A", "team2": "B"}]],
    }
    stats = add_stats.season_stats(base)
    assert set(stats) == {"preseason_strength"}


def test_no_history_and_no_projections_means_no_stats():
    assert add_stats.season_stats({"weekly_scores": [{"name": "A", "weeks": []}]}) == {}
