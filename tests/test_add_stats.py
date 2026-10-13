"""add_stats: the optional last stage that attaches season stats for non-to_html renderers."""

import json
import sys

import pytest

sys.path.insert(0, "scenario_engine")
import add_stats  # noqa: E402
import league_stats  # noqa: E402
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
