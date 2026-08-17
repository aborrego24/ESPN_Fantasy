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
        # the real pipeline carries this, and seeding depends on it
        "divisions": fixture.get("divisions"),
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


def test_no_team_below_the_cutoff_does_not_crash():
    """An all-tied league, two stages downstream."""
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
                "team_name": f"T{i}",
                "wins": 7,
                "losses": 6,
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
def test_the_tiebreaker_guard_only_ever_downgrades(load_fixture, name):
    """Anything the pipeline calls decided must be decided on frozen points too.

    The guard exists to withhold a verdict when it rests on a points gap that
    could plausibly close, so it may only ever turn clinched/eliminated into
    alive -- never the reverse. Anything else would mean the pipeline is
    claiming more than the exact search supports.
    """
    import playoff_math
    import refine_current_week

    fixture = load_fixture(name)
    base, perms = base_data_for(fixture)
    spots = base["league_data"]["playoff_spots"]

    # a clinched team reads as the strongest claim that is true of it
    clinched_labels = {
        playoff_math.STATUS_CLINCHED,
        playoff_math.STATUS_BYE,
        playoff_math.STATUS_TOP_SEED,
    }

    for perm in perms:
        standings = stage4.apply_permutation(base, perm)
        later = base.get("remaining_matchups", [])[1:]
        unguarded = playoff_math.classify(
            playoff_math.state_from_standings(
                standings,
                later,
                spots,
                refine_current_week.divisions_in_order(
                    standings, fixture.get("divisions")
                ),
            )
        )

        for team in standings:
            if team["verdict"] == "clinched":
                assert unguarded[team["team_name"]] == "clinched"
                assert team["status"] in clinched_labels
            elif team["verdict"] == "eliminated":
                assert unguarded[team["team_name"]] == "eliminated"
                assert team["status"] == playoff_math.STATUS_ELIMINATED
            else:
                assert team["status"] == playoff_math.STATUS_ALIVE
