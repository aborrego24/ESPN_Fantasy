"""End-to-end anti-overclaim test.

For every team and every side, the conditions stage 4 reports must be satisfied
by exactly the permutations in which that outcome actually occurs. This is the
regression for the bug where an intersection with nothing in common rendered as
"unconditional" -- on week13, Weezer Africa was reported as both clinching with
a win and eliminated with a win.
"""

import pytest

import generate_perms as stage3
import refine_current_week as stage2
import refine_hypothetical as stage4

FIXTURES = ["week12.json", "week13.json", "PC_test.json"]


def pipeline_through_stage4(fixture):
    settings = fixture["league_settings"]
    remaining = settings["weeks_in_season"] - settings["current_week"]
    standings = stage2.calculate_stats(
        fixture, settings["playoff_spots"], settings["weeks_in_season"], remaining
    )
    remaining_matchups = stage2.build_remaining_matchups(
        fixture["teams"], remaining
    )
    import playoff_math

    standings = playoff_math.apply_verdicts(
        standings, remaining_matchups, settings["playoff_spots"]
    )
    base = {
        "league_data": {
            "playoff_spots": settings["playoff_spots"],
            "num_weeks": settings["weeks_in_season"],
            "remaining_weeks": remaining,
            "current_week": settings["current_week"],
        },
        "next_week_matchups": fixture["next_week_matchups"],
        "remaining_matchups": remaining_matchups,
        "standings": standings,
    }
    perms = stage3.generate_matchup_permutations(base)
    team_results = stage4.build_team_scenarios(base, perms)
    return base, perms, team_results


def satisfies(permutation, alternatives):
    """Does this permutation match any stated alternative?"""
    for conditions in alternatives:
        if all(permutation[c["matchup"]] == c["winner"] for c in conditions):
            return True
    return False


@pytest.mark.parametrize("name", FIXTURES)
def test_conditions_match_the_qualifying_permutations_exactly(load_fixture, name):
    base, perms, team_results = pipeline_through_stage4(load_fixture(name))
    matchups = base["next_week_matchups"]

    for team, outcomes in team_results.items():
        scenario = stage4.output_scenarios(
            team,
            outcomes["clinched_in"],
            outcomes["eliminated_in"],
            perms,
            matchups,
        )
        own = stage4.own_matchup_index(matchups, team)

        for key, indices in (
            ("clinch", outcomes["clinched_in"]),
            ("elim", outcomes["eliminated_in"]),
        ):
            if key not in scenario:
                continue
            qualifying = set(indices)

            for team_won, alternatives in (
                (True, scenario[key]["win"]),
                (False, scenario[key]["loss"]),
            ):
                for i, permutation in enumerate(perms):
                    won = own is not None and permutation[own] == team
                    if won != team_won:
                        continue
                    stated = satisfies(permutation, alternatives)
                    actual = i in qualifying
                    assert stated == actual, (
                        f"{name} {team} {key} "
                        f"({'win' if team_won else 'loss'} side): "
                        f"permutation {permutation} is "
                        f"{'stated as' if stated else 'not stated as'} qualifying "
                        f"but {'is' if actual else 'is not'}"
                    )


@pytest.mark.parametrize("name", FIXTURES)
def test_a_team_is_never_a_condition_of_its_own_scenario(load_fixture, name):
    """The team's own game is stated as 'a WIN'/'a LOSS', never as a condition.

    Holding the team's own matchup out of the condition set makes this
    structural rather than something a filter has to remember to do -- and the
    opponent cannot appear either, for the same reason.
    """
    base, perms, team_results = pipeline_through_stage4(load_fixture(name))
    matchups = base["next_week_matchups"]

    for team, outcomes in team_results.items():
        scenario = stage4.output_scenarios(
            team,
            outcomes["clinched_in"],
            outcomes["eliminated_in"],
            perms,
            matchups,
        )
        own = stage4.own_matchup_index(matchups, team)
        opponent = None
        if own is not None:
            pair = matchups[own]
            opponent = pair["team2"] if pair["team1"] == team else pair["team1"]

        for paths in scenario.values():
            for alternatives in paths.values():
                for conditions in alternatives:
                    for condition in conditions:
                        assert condition["matchup"] != own
                        assert condition["winner"] != team
                        assert condition["winner"] != opponent


@pytest.mark.parametrize("name", FIXTURES)
def test_unconditional_claims_really_are_unconditional(load_fixture, name):
    """'a WIN' with no conditions must hold for every outcome on that side."""
    base, perms, team_results = pipeline_through_stage4(load_fixture(name))
    matchups = base["next_week_matchups"]
    side_total = 2 ** (len(matchups) - 1) if matchups else 1

    for team, outcomes in team_results.items():
        scenario = stage4.output_scenarios(
            team,
            outcomes["clinched_in"],
            outcomes["eliminated_in"],
            perms,
            matchups,
        )
        own = stage4.own_matchup_index(matchups, team)

        for key, indices in (
            ("clinch", outcomes["clinched_in"]),
            ("elim", outcomes["eliminated_in"]),
        ):
            if key not in scenario:
                continue
            for team_won, alternatives in (
                (True, scenario[key]["win"]),
                (False, scenario[key]["loss"]),
            ):
                if alternatives != [[]]:
                    continue
                on_this_side = sum(
                    1
                    for i in indices
                    if (own is not None and perms[i][own] == team) == team_won
                )
                assert on_this_side == side_total, (
                    f"{name} {team} {key} claims to need nothing else, but only "
                    f"{on_this_side} of {side_total} outcomes on that side qualify"
                )
