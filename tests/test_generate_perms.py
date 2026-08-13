"""Stage 3: prune decided matchups, then enumerate win/loss outcomes."""

import generate_perms as stage3


def league_with(statuses, matchups):
    return {
        "standings": [
            {"team_name": name, "status": status} for name, status in statuses.items()
        ],
        "next_week_matchups": matchups,
    }


def test_games_between_decided_teams_are_still_enumerated():
    """No matchup is pruned, even when both teams' fates are settled.

    Dropping them left those teams' records frozen while everyone else played
    on, which moved them relative to teams they should have stayed ahead of and
    corrupted the standings the verdict is computed from.
    """
    data = league_with(
        {
            "Locked A": "Clinched Playoff Spot",
            "Locked B": "Eliminated",
            "Live C": "In contention, needs 1 win(s) to clinch",
            "Live D": "In contention, needs 2 win(s) to clinch",
        },
        [
            {"team1": "Locked A", "team2": "Locked B"},
            {"team1": "Locked A", "team2": "Live C"},
            {"team1": "Live C", "team2": "Live D"},
        ],
    )

    perms = stage3.generate_matchup_permutations(data)

    assert len(perms) == 2**3
    assert all(len(p) == 3 for p in perms)


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


def test_no_matchups_leaves_a_single_empty_permutation():
    """Final week already played: one completion, and it is the empty one."""
    data = league_with({"A": "Clinched Playoff Spot", "B": "Eliminated"}, [])

    assert stage3.generate_matchup_permutations(data) == [()]
