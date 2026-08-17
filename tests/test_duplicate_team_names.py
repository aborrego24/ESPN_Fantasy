"""Two teams with the same name (defect #8).

ESPN does not require team names to be unique, and the pipeline treats the name
as the team's identity everywhere: the standings key on it, the exact engine
builds a name-to-index map from it, a permutation names its winner by it, the
scenario map buckets by it, and both renderers print it.

Before the fix, a colliding pair did all of this at once:

  - both teams recorded a BYE for the week they played each other, because the
    self-matchup guard compared names, so each looked like the other's own
    matchup -- two teams sat at 0-0 having scored a full slate of points;
  - a whole matchup vanished from the remaining schedule, because the pairing
    loop tracks placed teams by name, so the second of the pair was skipped and
    its opponent left unpaired -- verdicts were then decided over an incomplete
    season;
  - the two index lookups disagreed with each other: state_from_standings builds
    a dict, resolving a repeated name to the LAST team, while index_of uses
    list.index and resolves it to the FIRST.

Identity is repaired at stage 1, the one point where data enters, and every
consumer is guarded so nothing can silently merge two teams again.
"""

import pytest

import league_data
import league_stats
import playoff_math
import refine_current_week as stage2
import refine_hypothetical as stage4
import to_html
from test_league_data import FakeLeague, FakeTeam


def colliding_league(abbrevs=("RNGA", "RNGB"), ids=(1, 2)):
    """Four teams, two of them both called 'Ringers'.

    Scores are all distinct, so nothing here is a tie and every comparison has
    one right answer. Week 1: Ringers-A beats Ringers-B, Clear beats Other.
    """
    a = FakeTeam("Ringers", [120.0, 130.0], team_id=ids[0], team_abbrev=abbrevs[0])
    b = FakeTeam("Ringers", [90.0, 80.0], team_id=ids[1], team_abbrev=abbrevs[1])
    c = FakeTeam("Clear", [110.0, 100.0], team_id=3, team_abbrev="CLR")
    d = FakeTeam("Other", [100.0, 95.0], team_id=4, team_abbrev="OTH")
    schedule = {1: [(a, b), (c, d)], 2: [(a, c), (b, d)]}
    return FakeLeague([a, b, c, d], 2, 2, schedule), (a, b, c, d)


def through_stage2(payload, played=1):
    standings = stage2.calculate_stats(payload, 2, 2, 2 - played)
    remaining = stage2.build_remaining_matchups(payload["teams"], 2 - played)
    return standings, remaining


# --- stage 1 makes the name a usable identity ---------------------------------


def test_colliding_names_are_disambiguated():
    league, _ = colliding_league()

    names = league_data.unique_names(league)

    assert sorted(names.values()) == [
        "Clear",
        "Other",
        "Ringers (RNGA)",
        "Ringers (RNGB)",
    ]


def test_names_that_do_not_collide_are_left_exactly_alone():
    """The ordinary case must not grow a suffix on every team."""
    league, _ = colliding_league()
    league.teams[1].team_name = "Sharpes"

    names = league_data.unique_names(league)

    assert sorted(names.values()) == ["Clear", "Other", "Ringers", "Sharpes"]


def test_the_abbreviation_is_preferred_because_it_means_something():
    league, _ = colliding_league(abbrevs=("OVEN", "SCHU"))

    names = league_data.unique_names(league)

    assert names[1] == "Ringers (OVEN)"
    assert names[2] == "Ringers (SCHU)"


def test_a_shared_abbreviation_falls_back_to_the_team_id():
    """Abbreviations collide as easily as names, so they cannot be trusted."""
    league, _ = colliding_league(abbrevs=("SAME", "SAME"), ids=(7, 9))

    names = league_data.unique_names(league)

    assert names[7] == "Ringers (id 7)"
    assert names[9] == "Ringers (id 9)"


def test_a_missing_abbreviation_falls_back_to_the_team_id():
    league, _ = colliding_league(abbrevs=(None, None), ids=(7, 9))

    names = league_data.unique_names(league)

    assert sorted(names.values()) == [
        "Clear",
        "Other",
        "Ringers (7)",
        "Ringers (9)",
    ]


def test_a_name_that_cannot_be_made_unique_is_refused():
    """Pathological, but refusing beats merging two teams.

    Reaching the last resort takes a shared abbreviation, which forces the id
    fallback, plus a team already named exactly what that fallback produces.
    """
    league, teams = colliding_league(abbrevs=("SAME", "SAME"), ids=(1, 2))
    teams[2].team_name = "Ringers (id 1)"

    with pytest.raises(league_data.DuplicateTeamNames, match="unique"):
        league_data.unique_names(league)


def test_a_team_named_like_a_tag_is_worked_around_where_it_can_be():
    """The last resort is genuinely last: this case resolves without raising.

    Both members of the collision are re-tagged, including the team whose name
    was legitimate all along -- it is the one being collided *with*. Slightly
    unfair to that team, but the result is unambiguous, deterministic, and this
    needs a team literally named after another team's generated tag to happen.
    """
    league, teams = colliding_league(abbrevs=(None, None), ids=(1, 2))
    teams[2].team_name = "Ringers (1)"  # collides with what team 1 would be tagged

    names = league_data.unique_names(league)

    assert len(set(names.values())) == 4
    assert names[1] == "Ringers (id 1)"
    assert names[3] == "Ringers (1) (id 3)"


@pytest.mark.parametrize("week", [0, 1, 2])
def test_every_view_of_the_schedule_uses_the_same_names(week):
    """Four independent references to a team, which have to agree.

    A name appearing in remaining_schedule or next_week_matchups that is not in
    the standings is the shape of the original bug: stage 2 looks teams up by
    these strings.
    """
    league, _ = colliding_league()

    payload = league_data.build_payload(league, current_week=week)
    known = {team["name"] for team in payload["teams"]}

    assert len(known) == 4, "every team must be individually addressable"
    assert {entry["name"] for entry in payload["weekly_scores"]} == known
    for team in payload["teams"]:
        for opponent in team["remaining_schedule"]:
            assert opponent is None or opponent in known
    for matchup in payload["next_week_matchups"]:
        assert matchup["team1"] in known and matchup["team2"] in known
    for entry in payload["weekly_scores"]:
        for game in entry["weeks"]:
            assert game["opponent"] is None or game["opponent"] in known


# --- the game they played against each other ----------------------------------


def test_playing_a_team_with_your_own_name_is_a_real_game_not_a_bye():
    """The regression: the self-matchup guard used to compare names.

    Ringers-A beat Ringers-B 120-90 in week 1. Both used to come back 0-0 with
    the points still counted, because each looked like the other's own matchup.
    """
    league, _ = colliding_league()

    payload = league_data.build_payload(league, current_week=1)
    records = {t["name"]: t["record"] for t in payload["teams"]}

    assert records["Ringers (RNGA)"] == {"wins": 1, "losses": 0, "ties": 0}
    assert records["Ringers (RNGB)"] == {"wins": 0, "losses": 1, "ties": 0}


def test_they_are_each_others_recorded_opponent():
    league, _ = colliding_league()

    payload = league_data.build_payload(league, current_week=1)
    history = {e["name"]: e["weeks"] for e in payload["weekly_scores"]}

    assert history["Ringers (RNGA)"][0]["opponent"] == "Ringers (RNGB)"
    assert history["Ringers (RNGB)"][0]["opponent"] == "Ringers (RNGA)"


def test_a_genuine_self_matchup_is_still_read_as_a_bye():
    """Identity, not name: a team really scheduled against itself has no game."""
    league, teams = colliding_league()
    a = teams[0]
    a.schedule[0] = a

    assert league_data.opponent_in_week(a, 0) is None


# --- nothing vanishes ---------------------------------------------------------


def test_no_matchup_disappears_from_the_remaining_schedule():
    """Week 2 is Ringers-A v Clear and Ringers-B v Other. Both must survive."""
    league, _ = colliding_league()

    payload = league_data.build_payload(league, current_week=1)
    _, remaining = through_stage2(payload)

    assert len(remaining) == 1, "one week left"
    pairs = {frozenset((m["team1"], m["team2"])) for m in remaining[0]}
    assert pairs == {
        frozenset(("Ringers (RNGA)", "Clear")),
        frozenset(("Ringers (RNGB)", "Other")),
    }


def test_every_team_appears_exactly_once_in_the_standings():
    league, _ = colliding_league()

    payload = league_data.build_payload(league, current_week=1)
    standings, _ = through_stage2(payload)

    assert len(standings) == 4
    assert len({t["team_name"] for t in standings}) == 4


def test_the_engine_gives_the_two_teams_separate_indices():
    league, _ = colliding_league()
    payload = league_data.build_payload(league, current_week=1)
    standings, remaining = through_stage2(payload)

    state = playoff_math.state_from_standings(standings, remaining, 2)

    assert len(set(state.games[0]) | set(state.games[1])) == 4, "four distinct teams"
    # the two lookups of one name used to disagree; now each name is one team
    for position, name in enumerate(state.names):
        assert state.index_of(name) == position


def test_a_win_is_credited_to_one_team_only():
    """apply_permutation matched on the name, so it credited both."""
    league, _ = colliding_league()
    payload = league_data.build_payload(league, current_week=1)
    standings, remaining = through_stage2(payload)
    base = {
        "league_data": {
            "playoff_spots": 2,
            "num_weeks": 2,
            "remaining_weeks": 1,
            "current_week": 1,
        },
        "next_week_matchups": payload["next_week_matchups"],
        "remaining_matchups": remaining,
        "standings": standings,
    }

    # Ringers-A beats Clear; Ringers-B beats Other
    result = stage4.apply_permutation(base, ("Ringers (RNGA)", "Ringers (RNGB)"))
    records = {t["team_name"]: (t["wins"], t["losses"]) for t in result}

    assert records["Ringers (RNGA)"] == (2, 0)
    assert records["Ringers (RNGB)"] == (1, 1)
    assert records["Clear"] == (1, 1)
    assert records["Other"] == (0, 2)
    for name, (wins, losses) in records.items():
        assert wins + losses == 2, f"{name} played {wins + losses} of 2 games"


def test_both_teams_keep_their_own_season_in_the_review_tables():
    league, _ = colliding_league()
    payload = league_data.build_payload(league, current_week=2)

    rows = league_stats.all_play_records(payload["weekly_scores"])
    luck = league_stats.schedule_luck(payload["weekly_scores"])

    assert len(rows) == 4, "a merged team would leave three"
    assert len(luck["rows"]) == 4
    totals = {row["name"]: row["total"] for row in rows}
    # Ringers-A outscored everyone both weeks; Ringers-B nobody
    assert totals["Ringers (RNGA)"] == {"wins": 6, "losses": 0, "ties": 0}
    assert totals["Ringers (RNGB)"] == {"wins": 0, "losses": 6, "ties": 0}


# --- guards: nothing may merge two teams silently again ------------------------


def duplicated_standings():
    return [
        {"team_name": "Ringers", "wins": 1, "losses": 0, "points_for": 120.0},
        {"team_name": "Ringers", "wins": 0, "losses": 1, "points_for": 90.0},
    ]


def test_the_engine_refuses_standings_with_a_repeated_name():
    with pytest.raises(ValueError, match="unique"):
        playoff_math.state_from_standings(duplicated_standings(), [], 1)


def test_the_review_tables_refuse_a_repeated_name():
    weekly = [
        {"name": "Ringers", "weeks": [{"week": 1, "points": 120.0, "opponent": None}]},
        {"name": "Ringers", "weeks": [{"week": 1, "points": 90.0, "opponent": None}]},
    ]

    with pytest.raises(ValueError, match="unique"):
        league_stats.all_play_records(weekly)
    with pytest.raises(ValueError, match="unique"):
        league_stats.schedule_luck(weekly)


# --- and it reads correctly ---------------------------------------------------


def test_the_report_names_the_two_teams_distinguishably():
    """Internally correct is not enough if the page prints one name twice."""
    league, _ = colliding_league()
    payload = league_data.build_payload(league, current_week=1)
    standings, remaining = through_stage2(payload)
    standings = playoff_math.apply_verdicts(standings, remaining, 2)

    document = to_html.render(
        {
            "base_league_data": {
                "league_data": {
                    "playoff_spots": 2,
                    "num_weeks": 2,
                    "remaining_weeks": 1,
                    "current_week": 1,
                },
                "standings": standings,
                "next_week_matchups": payload["next_week_matchups"],
                "weekly_scores": payload["weekly_scores"],
            },
            "scenarios": [],
        }
    )

    assert "Ringers (RNGA)" in document
    assert "Ringers (RNGB)" in document
