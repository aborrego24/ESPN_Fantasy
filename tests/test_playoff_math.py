"""Verify the clinch/elimination search against exhaustive enumeration.

The search in playoff_math prunes aggressively and early-exits, so the only
convincing test is to compare it against brute force over every completion of
the remaining schedule, on leagues small enough for that to be tractable.

Brute force deliberately reuses the module's own comparator (`beats`). The
comparator is a definition -- ESPN's playoffSeedingRule -- so reimplementing it
here would test nothing. What is under test is the *search*.
"""

import itertools
import random

import pytest

from playoff_math import (
    LeagueState,
    beats,
    classify,
    makes_playoffs,
    status_of,
)


def brute_force_statuses(state):
    """Enumerate every completion. O(2^games) -- small inputs only."""
    n = state.num_teams
    ever_in = [False] * n
    ever_out = [False] * n

    for outcome in itertools.product(*[(i, j) for (i, j) in state.games]):
        wins = list(state.wins)
        losses = list(state.losses)
        for (i, j), winner in zip(state.games, outcome):
            loser = j if winner == i else i
            wins[winner] += 1
            losses[loser] += 1
        for t in range(n):
            if makes_playoffs(t, wins, state.points, n, state.playoff_spots):
                ever_in[t] = True
            else:
                ever_out[t] = True

    statuses = {}
    for t in range(n):
        if not ever_out[t]:
            statuses[state.names[t]] = "clinched"
        elif not ever_in[t]:
            statuses[state.names[t]] = "eliminated"
        else:
            statuses[state.names[t]] = "alive"
    return statuses


def round_robin_weeks(n, weeks, rng):
    """Random pairings: every team plays exactly once per week."""
    schedule = []
    for _ in range(weeks):
        order = list(range(n))
        rng.shuffle(order)
        schedule.extend(
            (order[k], order[k + 1]) for k in range(0, n - 1, 2)
        )
    return schedule


def random_state(rng, n=6, weeks=2, spots=3, played=8):
    wins = []
    for _ in range(n):
        w = rng.randint(0, played)
        wins.append(w)
    losses = [played - w for w in wins]
    points = [round(rng.uniform(1400, 2000), 2) for _ in range(n)]
    games = round_robin_weeks(n, weeks, rng)
    names = [f"T{i}" for i in range(n)]
    return LeagueState(names, wins, losses, points, games, spots)


@pytest.mark.parametrize("seed", range(40))
def test_search_agrees_with_brute_force(seed):
    rng = random.Random(seed)
    state = random_state(rng, n=6, weeks=2, spots=3)

    assert classify(state) == brute_force_statuses(state)


@pytest.mark.parametrize("seed", range(12))
def test_search_agrees_with_brute_force_larger(seed):
    rng = random.Random(1000 + seed)
    state = random_state(rng, n=8, weeks=2, spots=4, played=10)

    assert classify(state) == brute_force_statuses(state)


@pytest.mark.parametrize("seed", range(8))
def test_never_more_clinched_than_seats(seed):
    """The invariant the old magic-number engine violated in 47% of cases."""
    rng = random.Random(500 + seed)
    state = random_state(rng, n=8, weeks=3, spots=4, played=8)

    statuses = classify(state)
    clinched = [k for k, v in statuses.items() if v == "clinched"]
    eliminated = [k for k, v in statuses.items() if v == "eliminated"]

    assert len(clinched) <= state.playoff_spots
    assert len(eliminated) <= state.num_teams - state.playoff_spots


def test_runaway_leader_has_clinched():
    """8-0 with two games left, chasers maxing out at 5 wins."""
    state = LeagueState(
        names=["Runaway", "A", "B", "C"],
        wins=[8, 3, 3, 2],
        losses=[0, 5, 5, 6],
        points=[2000.0, 1500.0, 1400.0, 1300.0],
        games=[(0, 1), (2, 3), (0, 2), (1, 3)],
        playoff_spots=2,
    )

    assert status_of(state, 0) == "clinched"


def test_hopeless_team_is_eliminated():
    """0-8 with two games left cannot reach a two-team bracket."""
    state = LeagueState(
        names=["A", "B", "C", "Hopeless"],
        wins=[7, 6, 6, 0],
        losses=[1, 2, 2, 8],
        points=[1900.0, 1800.0, 1700.0, 1000.0],
        games=[(0, 3), (1, 2), (3, 1), (0, 2)],
        playoff_spots=2,
    )

    assert status_of(state, 3) == "eliminated"


def test_the_tiebreaker_decides_a_seat():
    """Same record, and only total points separates them.

    Both teams end 5-5 whatever happens -- neither has games left -- so the
    seat goes to the higher scorer, and that is decided, not alive.
    """
    state = LeagueState(
        names=["HighScorer", "LowScorer", "Also"],
        wins=[5, 5, 3],
        losses=[5, 5, 7],
        points=[1900.0, 1500.0, 1200.0],
        games=[],
        playoff_spots=1,
    )

    assert status_of(state, 0) == "clinched"
    assert status_of(state, 1) == "eliminated"


def test_everything_still_open_early_on():
    """With a whole season left and level records, nobody is decided."""
    rng = random.Random(7)
    state = LeagueState(
        names=[f"T{i}" for i in range(6)],
        wins=[1] * 6,
        losses=[1] * 6,
        points=[1500.0 + i for i in range(6)],
        games=round_robin_weeks(6, 4, rng),
        playoff_spots=3,
    )

    assert set(classify(state).values()) == {"alive"}


def test_no_games_left_is_decided_by_final_standings():
    state = LeagueState(
        names=["A", "B", "C"],
        wins=[9, 5, 4],
        losses=[5, 9, 10],
        points=[1900.0, 1600.0, 1500.0],
        games=[],
        playoff_spots=2,
    )

    assert classify(state) == {"A": "clinched", "B": "clinched", "C": "eliminated"}
