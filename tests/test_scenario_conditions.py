"""End-to-end anti-overclaim test.

For every team and every outcome, the conditions stage 4 reports must be
satisfied by exactly the permutations in which that outcome actually occurs.

Each alternative is {"own": "win"|"loss"|None, "conditions": [...]}. `own` None
means the outcome holds however the team itself does -- a stronger claim than
naming a result that turned out not to matter, and the reason the team's own game
is part of the reduction rather than held out of it.
"""

import pytest

import generate_perms as stage3
import refine_current_week as stage2
import refine_hypothetical as stage4

FIXTURES = ["week12.json", "week13.json", "PC_test.json"]


def pipeline_through_stage4(fixture):
    import margins
    import playoff_math

    settings = fixture["league_settings"]
    remaining = settings["weeks_in_season"] - settings["current_week"]
    standings = stage2.calculate_stats(
        fixture, settings["playoff_spots"], settings["weeks_in_season"], remaining
    )
    remaining_matchups = stage2.build_remaining_matchups(fixture["teams"], remaining)
    envelope = margins.swing_envelope(remaining, margins.load_thresholds())
    standings = playoff_math.apply_verdicts(
        standings, remaining_matchups, settings["playoff_spots"], swing_envelope=envelope
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


def satisfies(permutation, alternatives, team, own):
    """Does this permutation match any stated alternative?"""
    for alternative in alternatives:
        if not all(
            permutation[c["matchup"]] == c["winner"] for c in alternative["conditions"]
        ):
            continue
        if alternative["own"] is not None:
            won = own is not None and permutation[own] == team
            if (alternative["own"] == "win") != won:
                continue
        return True
    return False


def scenarios_for(base, perms, team_results):
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
        yield team, own, scenario, outcomes


@pytest.mark.parametrize("name", FIXTURES)
def test_conditions_match_the_qualifying_permutations_exactly(load_fixture, name):
    base, perms, team_results = pipeline_through_stage4(load_fixture(name))

    for team, own, scenario, outcomes in scenarios_for(base, perms, team_results):
        for key, indices in (
            ("clinch", outcomes["clinched_in"]),
            ("elim", outcomes["eliminated_in"]),
        ):
            if key not in scenario:
                continue
            qualifying = set(indices)

            for i, permutation in enumerate(perms):
                stated = satisfies(permutation, scenario[key], team, own)
                actual = i in qualifying
                assert stated == actual, (
                    f"{name} {team} {key}: permutation {permutation} is "
                    f"{'stated as' if stated else 'not stated as'} qualifying "
                    f"but {'is' if actual else 'is not'}"
                )


@pytest.mark.parametrize("name", FIXTURES)
def test_a_team_is_never_a_condition_of_its_own_scenario(load_fixture, name):
    """The team's own game is carried in `own`, never as a named condition.

    So neither the team nor its opponent can appear in a condition list, and the
    property holds structurally rather than depending on a filter remembering to
    strip them.
    """
    base, perms, team_results = pipeline_through_stage4(load_fixture(name))
    matchups = base["next_week_matchups"]

    for team, own, scenario, _ in scenarios_for(base, perms, team_results):
        opponent = None
        if own is not None:
            pair = matchups[own]
            opponent = pair["team2"] if pair["team1"] == team else pair["team1"]

        for alternatives in scenario.values():
            for alternative in alternatives:
                for condition in alternative["conditions"]:
                    assert condition["matchup"] != own
                    assert condition["winner"] != team
                    assert condition["winner"] != opponent


@pytest.mark.parametrize("name", FIXTURES)
def test_an_alternative_that_ignores_your_own_game_really_does(load_fixture, name):
    """`own: None` claims the outcome holds whichever way the team's game goes.

    That has to be true for both results, otherwise it is the overclaim this
    module exists to prevent, just relocated.
    """
    base, perms, team_results = pipeline_through_stage4(load_fixture(name))

    for team, own, scenario, outcomes in scenarios_for(base, perms, team_results):
        for key, indices in (
            ("clinch", outcomes["clinched_in"]),
            ("elim", outcomes["eliminated_in"]),
        ):
            if key not in scenario:
                continue
            qualifying = set(indices)

            for alternative in scenario[key]:
                if alternative["own"] is not None:
                    continue
                matching = [
                    i
                    for i, permutation in enumerate(perms)
                    if all(
                        permutation[c["matchup"]] == c["winner"]
                        for c in alternative["conditions"]
                    )
                ]
                assert matching, "an alternative must match something"
                # every outcome meeting the conditions qualifies, win or lose
                assert set(matching) <= qualifying, (
                    f"{name} {team} {key}: alternative {alternative} claims to hold "
                    f"win or lose, but some matching outcomes do not qualify"
                )
                won = {i for i in matching if own is not None and perms[i][own] == team}
                assert won and (set(matching) - won), (
                    "the claim only means something if both results are covered"
                )


@pytest.mark.parametrize("name", FIXTURES)
def test_what_a_team_can_control_is_listed_first(load_fixture, name):
    """Actionable alternatives before ones that turn only on other teams.

    "a WIN" is something a team can go and do; "Ben's WIN" is not. The
    actionable path leads however few conditions the other carries. Within each
    group, fewest requirements first.
    """
    base, perms, team_results = pipeline_through_stage4(load_fixture(name))

    for team, _, scenario, _ in scenarios_for(base, perms, team_results):
        for alternatives in scenario.values():
            controllable = [a["own"] is not None for a in alternatives]
            # every True before every False
            assert controllable == sorted(controllable, reverse=True), (
                f"{name} {team}: {alternatives} puts an out-of-control path first"
            )

            for own_involved in (True, False):
                sizes = [
                    len(a["conditions"])
                    for a in alternatives
                    if (a["own"] is not None) is own_involved
                ]
                assert sizes == sorted(sizes), f"{name} {team}: {sizes} not ordered"
