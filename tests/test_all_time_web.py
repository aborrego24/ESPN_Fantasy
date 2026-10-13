"""all_time.web_payload: the All-Time data for a renderer other than to_html."""

import json
import sys

sys.path.insert(0, "scenario_engine")
import all_time  # noqa: E402


def _season(year, complete, teams):
    return {
        "year": year, "complete": complete, "num_teams": len(teams), "weeks_in_season": 2,
        "playoff_spots": 2, "teams": teams,
        "weekly_scores": [{"name": t["name"], "weeks": [
            {"week": 1, "points": 100 + i * 10, "opponent": None},
            {"week": 2, "points": 110 - i * 5, "opponent": None}]} for i, t in enumerate(teams)],
        "playoff_weeks": [],
    }


def _team(name, owner):
    return {"name": name, "managers": [owner], "points_for": 200, "playoff_points_for": 0, "wins": 1, "losses": 1, "ties": 0,
            "final_standing": 0, "seed": 0, "made_playoffs": False, "playoff_games": 0}


def test_web_payload_matches_the_engine_rows_and_is_json():
    history = {"league_id": 1, "skipped": [], "seasons": [
        _season(2026, False, [_team("A", "Ann"), _team("B", "Bo")]),
        _season(2025, True, [_team("A", "Ann"), _team("B", "Bo")]),
    ]}
    out = json.loads(json.dumps(all_time.web_payload(history)))  # must serialise

    assert set(out["scopes"]) == set(all_time.SCOPES)
    both = out["scopes"]["both"]
    expected = all_time.team_rows(history, "both")
    assert [r["name"] for r in both["teams"]] == [r["name"] for r in expected]
    assert all(r["year"] == 2025 for r in both["teams"])          # in-progress season not ranked
    assert {r["year"] for r in both["current"]} == {2026}          # ...but offered for an overlay
    assert all(r["career_keys"] for r in both["teams"])
    assert {p["key"] for p in out["presets"]} >= {out["default_preset"]}
    assert out["facts"]["excluded"] == [2026]
