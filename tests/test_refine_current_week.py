"""Stage 2: sorting the teams into standings order, and pairing up what is left."""

import pytest

import playoff_math
import refine_current_week as stage2


def sort_key(team):
    return (-team["wins"], team["losses"], -team["points_for"])


def standings_for(fixture):
    settings = fixture["league_settings"]
    remaining = settings["weeks_in_season"] - settings["current_week"]
    return stage2.calculate_stats(
        fixture,
        settings["playoff_spots"],
        settings["weeks_in_season"],
        remaining,
    )


@pytest.mark.parametrize("name", ["week12.json", "week13.json", "PC_test.json"])
def test_standings_are_sorted_by_the_seeding_rule(load_fixture, name):
    standings = standings_for(load_fixture(name))

    keys = [sort_key(t) for t in standings]
    assert keys == sorted(keys), "standings must sort by (-wins, losses, -points_for)"


@pytest.mark.parametrize("name", ["week12.json", "week13.json", "PC_test.json"])
def test_only_the_fields_something_reads_are_emitted(load_fixture, name):
    """Stage 2 states the standings; deciding them belongs to playoff_math.

    It used to also attach magic numbers, an elimination number and a status
    string that no renderer ever read, computed twice in two drifted copies.
    """
    for team in standings_for(load_fixture(name)):
        assert set(team) == {"team_name", "wins", "losses", "points_for"}


def test_week13_leader_has_clinched(load_fixture):
    """The claim is unchanged; only what proves it has moved."""
    fixture = load_fixture("week13.json")
    standings = standings_for(fixture)
    leader = standings[0]

    assert leader["team_name"] == "Ben's Underrated Tennis Team"
    assert (leader["wins"], leader["losses"]) == (9, 4)

    remaining = stage2.build_remaining_matchups(fixture["teams"], 1)
    decided = playoff_math.apply_verdicts(
        standings, remaining, fixture["league_settings"]["playoff_spots"]
    )
    assert decided[0]["verdict"] == "clinched"


def test_no_team_below_the_cutoff_does_not_crash(load_fixture):
    """An all-tied league, which used to be its own special case.

    Working out which team was "first out" of the bracket had no answer when
    nobody was behind, and dereferencing it raised TypeError. Sorting alone has
    no such edge, but the shape is worth keeping a test on.
    """
    fixture = {
        "league_settings": {
            "num_teams": 4,
            "playoff_spots": 2,
            "weeks_in_season": 14,
            "current_week": 0,
            "tiebreaker": "points_for",
        },
        "teams": [
            {
                "name": f"T{i}",
                "record": {"wins": 0, "losses": 0, "ties": 0},
                "points_for": 0.0,
                "remaining_schedule": [],
            }
            for i in range(4)
        ],
    }

    standings = standings_for(fixture)
    assert len(standings) == 4


def test_a_bye_slot_is_skipped_rather_than_paired_against_nothing():
    """A None opponent means no game that week, not a matchup with no team 2.

    The slot is kept in remaining_schedule so the weeks stay aligned, so stage 2
    is the place that has to recognise it.
    """
    teams = [
        {"name": "Alpha", "remaining_schedule": ["Bravo", None]},
        {"name": "Bravo", "remaining_schedule": ["Alpha", None]},
        {"name": "Charlie", "remaining_schedule": [None, "Delta"]},
        {"name": "Delta", "remaining_schedule": [None, "Charlie"]},
    ]

    weeks = stage2.build_remaining_matchups(teams, 2)

    assert weeks == [
        [{"team1": "Alpha", "team2": "Bravo"}],
        [{"team1": "Charlie", "team2": "Delta"}],
    ]
    for week in weeks:
        for matchup in week:
            assert matchup["team1"] and matchup["team2"]
