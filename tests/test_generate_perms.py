"""Stage 3: prune decided matchups, then enumerate win/loss outcomes."""

import generate_perms as stage3


def league_with(statuses, matchups):
    return {
        "standings": [
            {"team_name": name, "status": status} for name, status in statuses.items()
        ],
        "next_week_matchups": matchups,
    }


def test_matchup_is_dropped_only_when_both_teams_are_decided():
    data = league_with(
        {
            "Locked A": "Clinched Playoff Spot",
            "Locked B": "Eliminated",
            "Live C": "In contention, needs 1 win(s) to clinch",
            "Live D": "In contention, needs 2 win(s) to clinch",
        },
        [
            {"team1": "Locked A", "team2": "Locked B"},  # both decided -> dropped
            {"team1": "Locked A", "team2": "Live C"},  # one live -> kept
            {"team1": "Live C", "team2": "Live D"},  # both live -> kept
        ],
    )

    kept = stage3.refine_matchups(data)["next_week_matchups"]

    assert kept == [
        {"team1": "Locked A", "team2": "Live C"},
        {"team1": "Live C", "team2": "Live D"},
    ]


def test_permutations_are_the_cartesian_product_of_both_outcomes():
    data = league_with(
        {f"T{i}": "In contention, needs 1 win(s) to clinch" for i in range(6)},
        [
            {"team1": "T0", "team2": "T1"},
            {"team1": "T2", "team2": "T3"},
            {"team1": "T4", "team2": "T5"},
        ],
    )

    perms = stage3.generate_matchup_permutations(data)

    assert len(perms) == 2**3
    assert len(set(perms)) == len(perms), "permutations must be distinct"
    for perm in perms:
        assert len(perm) == 3
        for winner, matchup in zip(perm, data["next_week_matchups"]):
            assert winner in (matchup["team1"], matchup["team2"])


def test_dropping_every_matchup_leaves_a_single_empty_permutation():
    data = league_with(
        {"A": "Clinched Playoff Spot", "B": "Eliminated"},
        [{"team1": "A", "team2": "B"}],
    )

    assert stage3.generate_matchup_permutations(data) == [()]
