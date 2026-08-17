"""Stage 2: standings, magic numbers, and status strings."""

import pytest

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
def test_standings_are_ranked_and_sorted_by_the_tiebreaker(load_fixture, name):
    standings = standings_for(load_fixture(name))

    assert [t["rank"] for t in standings] == list(range(1, len(standings) + 1))

    keys = [sort_key(t) for t in standings]
    assert keys == sorted(keys), "standings must sort by (-wins, losses, -points_for)"


@pytest.mark.parametrize("name", ["week12.json", "week13.json", "PC_test.json"])
def test_every_team_gets_exactly_one_magic_number_and_a_real_status(load_fixture, name):
    for team in standings_for(load_fixture(name)):
        has_clinch = team["clinch_MN"] is not None
        has_elim = team["elim_MN"] is not None
        assert has_clinch != has_elim, (
            f"{team['team_name']} should have exactly one of clinch_MN/elim_MN, "
            f"got clinch_MN={team['clinch_MN']} elim_MN={team['elim_MN']}"
        )
        assert team["status"] != "Status Unknown"


def test_week13_leader_has_clinched(load_fixture):
    standings = standings_for(load_fixture("week13.json"))
    leader = standings[0]

    assert leader["team_name"] == "Ben's Underrated Tennis Team"
    assert (leader["wins"], leader["losses"]) == (9, 4)
    assert leader["clinch_MN"] == -1
    assert leader["status"] == "Clinched Playoff Spot"


def test_no_team_below_the_cutoff_does_not_crash(load_fixture):
    """Regression: first_team_out is None when nobody is behind the cutoff.

    calculate_magic_numbers looks for the first team with fewer wins than the
    cutoff team. In an all-tied league there is no such team, and dereferencing
    it used to raise TypeError.
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
