"""Stage 4: replay each permutation and recompute standings."""

import copy
import json

import pytest

import generate_perms as stage3
import refine_current_week as stage2
import refine_hypothetical as stage4


def base_data_for(fixture):
    """Build the stage-3 payload the way the pipeline does."""
    settings = fixture["league_settings"]
    remaining = settings["weeks_in_season"] - settings["current_week"]
    standings = stage2.calculate_stats(
        fixture, settings["playoff_spots"], settings["weeks_in_season"], remaining
    )
    base = {
        "league_data": {
            "playoff_spots": settings["playoff_spots"],
            "num_weeks": settings["weeks_in_season"],
            "remaining_weeks": remaining,
            "current_week": settings["current_week"],
        },
        "next_week_matchups": fixture["next_week_matchups"],
        "standings": standings,
    }
    perms = stage3.generate_matchup_permutations(base)
    return base, perms


@pytest.mark.parametrize("name", ["week12.json", "week13.json", "PC_test.json"])
def test_each_permutation_adds_one_win_and_one_loss_per_matchup(load_fixture, name):
    base, perms = base_data_for(load_fixture(name))
    played_before = {t["team_name"]: t["wins"] + t["losses"] for t in base["standings"]}
    n_matchups = len(base["next_week_matchups"])

    for perm in perms:
        standings = stage4.apply_permutation(base, perm)

        total_added = sum(
            t["wins"] + t["losses"] - played_before[t["team_name"]] for t in standings
        )
        assert total_added == 2 * n_matchups

        wins_added = sum(
            t["wins"]
            for t in standings
        ) - sum(t["wins"] for t in base["standings"])
        assert wins_added == n_matchups


@pytest.mark.parametrize("name", ["week12.json", "week13.json", "PC_test.json"])
def test_apply_permutation_does_not_mutate_the_base_payload(load_fixture, name):
    base, perms = base_data_for(load_fixture(name))
    before = json.dumps(base, sort_keys=True)

    for perm in perms:
        stage4.apply_permutation(base, perm)

    assert json.dumps(base, sort_keys=True) == before, (
        "apply_permutation is called once per permutation; mutating the base "
        "payload would corrupt every later permutation"
    )


def test_teams_in_a_playoff_spot_do_not_keep_a_stale_elimination_number(load_fixture):
    """Regression for the elim_MIN typo.

    A team moved into the clinch bucket must have its elimination number
    cleared. The typo wrote to a dead key, leaving the previous stage's
    elim_MN in place. It is only latent today because status checks clinch_MN
    first -- correcting the clinch logic would make it observable.
    """
    base, perms = base_data_for(load_fixture("week13.json"))

    for perm in perms:
        for team in stage4.apply_permutation(base, perm):
            if team["clinch_MN"] is not None:
                assert team["elim_MN"] is None, (
                    f"{team['team_name']} has clinch_MN={team['clinch_MN']} "
                    f"but a stale elim_MN={team['elim_MN']}"
                )
            assert "elim_MIN" not in team


def test_no_team_below_the_cutoff_does_not_crash():
    """Same missing first_team_out guard as stage 2, two stages downstream."""
    base = {
        "league_data": {
            "playoff_spots": 2,
            "num_weeks": 14,
            "remaining_weeks": 1,
            "current_week": 13,
        },
        "next_week_matchups": [{"team1": "T0", "team2": "T1"}],
        "standings": [
            {
                "rank": i + 1,
                "team_name": f"T{i}",
                "status": "In contention",
                "wins": 7,
                "losses": 6,
                "clinch_MN": None,
                "elim_MN": None,
                "points_for": 100.0 - i,
            }
            for i in range(4)
        ],
    }

    standings = stage4.apply_permutation(base, ("T0",))
    assert len(standings) == 4


@pytest.mark.parametrize("name", ["week12.json", "week13.json", "PC_test.json"])
def test_never_more_clinched_teams_than_playoff_spots(load_fixture, name):
    """The invariant the magic-number engine violated in 47% of permutations."""
    base, perms = base_data_for(load_fixture(name))
    spots = base["league_data"]["playoff_spots"]
    num_teams = len(base["standings"])

    for perm in perms:
        standings = stage4.apply_permutation(base, perm)
        clinched = [t for t in standings if t["status"] == "Clinched Playoff Spot"]
        eliminated = [t for t in standings if t["status"] == "Eliminated"]

        assert len(clinched) <= spots, (
            f"{len(clinched)} teams clinched for {spots} spots under {perm}"
        )
        assert len(eliminated) <= num_teams - spots, (
            f"{len(eliminated)} eliminated with {num_teams - spots} non-seats under {perm}"
        )


@pytest.mark.parametrize("name", ["week12.json", "week13.json", "PC_test.json"])
def test_a_clinched_team_holds_a_seat_in_every_completion(load_fixture, name):
    """Cross-check the pipeline verdict against the math module directly.

    Guards the wiring, not the math: it catches the pipeline passing the wrong
    slice of remaining weeks, which would silently produce a right-shaped but
    wrong answer.
    """
    import playoff_math

    base, perms = base_data_for(load_fixture(name))
    spots = base["league_data"]["playoff_spots"]

    for perm in perms:
        standings = stage4.apply_permutation(base, perm)
        later = base.get("remaining_matchups", [])[1:]
        state = playoff_math.state_from_standings(standings, later, spots)
        verdicts = playoff_math.classify(state)

        for team in standings:
            expected = verdicts[team["team_name"]]
            if expected == "clinched":
                assert team["status"] == "Clinched Playoff Spot"
            elif expected == "eliminated":
                assert team["status"] == "Eliminated"
