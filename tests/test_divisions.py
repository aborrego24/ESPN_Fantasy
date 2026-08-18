"""Divisional seeding: division winners are seeded ahead of everyone else.

ESPN seeds a divisional league by putting every division winner above every team
that did not win one, ordering within each group by record then total points. The
engine used to order purely by record and points, which gets both the seed order
and the bye set wrong: in 2024 an 8-6 division winner was seeded above a 9-5
wildcard.

The consequences reach further than they look, which is why this file is long.

  - A team can finish above another **with fewer wins**, by winning a division.
    That is exactly what the engine's bounds pruning assumed impossible, so the
    bound is widened here by one team per division.
  - Whether one team outranks another is no longer a fact about the pair. It
    depends on who won a division, which is a fact about the whole league, so the
    pairwise comparator cannot answer it.
  - What does survive is monotonicity: with the searched team's record frozen, the
    number of teams above it never falls. Both of the search's early exits rest on
    that, so it is property-tested here rather than argued.

Every claim below is cross-checked against exhaustive enumeration.
"""

import itertools
import random

import pytest

import league_data
import playoff_math
import refine_current_week as stage2
from playoff_math import LeagueState, classify, makes_playoffs, seed_order, status_of
from test_league_data import FakeLeague, FakeTeam
from test_playoff_math import brute_force_statuses, round_robin_weeks


def divisional_state(rng, n=6, weeks=2, spots=3, divisions=2, played=8):
    """A random league split across `divisions`, each division non-empty."""
    assignment = [i % divisions for i in range(n)]
    rng.shuffle(assignment)
    wins = [rng.randrange(0, played + 1) for _ in range(n)]
    return LeagueState(
        [f"T{i}" for i in range(n)],
        wins,
        [played - w for w in wins],
        [round(rng.uniform(1400, 2000), 2) for _ in range(n)],
        round_robin_weeks(n, weeks, rng),
        spots,
        assignment,
    )


# --- the ordering itself ------------------------------------------------------


def test_without_divisions_the_order_is_record_then_points():
    wins, points = [3, 3, 1], [100.0, 200.0, 300.0]

    assert seed_order(wins, points) == [1, 0, 2]
    assert seed_order(wins, points, None) == [1, 0, 2]
    assert seed_order(wins, points, [0, 0, 0]) == [1, 0, 2], "one division changes nothing"


def test_a_division_winner_outranks_a_better_wildcard():
    """The 2024 case in miniature: 8-6 ahead of 9-5 on a division title."""
    #            A(div0)  B(div0)  C(div1)
    wins = [9, 5, 8]
    points = [500.0, 400.0, 300.0]
    divisions = [0, 0, 1]

    # A wins div0, C wins div1 by default. Winners first: A(9) then C(8), then B.
    assert seed_order(wins, points, divisions) == [0, 2, 1]
    # without divisions B (5 wins) would still trail, but C would too
    assert seed_order(wins, points) == [0, 2, 1]

    # now make B the better wildcard: it beats C on record but C won a division
    wins = [9, 8, 5]
    assert seed_order(wins, points, divisions) == [0, 2, 1], "C is seeded on its title"
    assert seed_order(wins, points) == [0, 1, 2], "record alone would put B second"


def test_every_division_winner_precedes_every_non_winner():
    rng = random.Random(7)
    for _ in range(200):
        state = divisional_state(rng, n=8, divisions=3)
        order = seed_order(state.wins, state.points, state.divisions)
        rank = lambda t: (-state.wins[t], -state.points[t])
        winners = {
            min((t for t in range(8) if state.divisions[t] == d), key=rank)
            for d in set(state.divisions)
        }
        positions = {team: i for i, team in enumerate(order)}
        assert max(positions[w] for w in winners) < min(
            positions[t] for t in range(8) if t not in winners
        )


def test_the_order_is_a_permutation_of_every_team():
    rng = random.Random(11)
    for _ in range(200):
        state = divisional_state(rng, n=8, divisions=3)
        order = seed_order(state.wins, state.points, state.divisions)
        assert sorted(order) == list(range(8))


def test_a_one_team_division_always_wins_itself():
    wins, points, divisions = [1, 9, 9], [100.0, 900.0, 800.0], [0, 1, 1]

    assert seed_order(wins, points, divisions)[:2] == [1, 0]


def test_more_divisions_than_seats_leaves_a_winner_out():
    """Winning a division is not a guaranteed place when divisions outnumber seats."""
    wins, points, divisions = [9, 8, 7, 6], [400.0, 300.0, 200.0, 100.0], [0, 1, 2, 3]

    order = seed_order(wins, points, divisions)
    assert order == [0, 1, 2, 3]
    assert not makes_playoffs(3, wins, points, 4, 2, divisions)


# --- the property both early exits rest on ------------------------------------


@pytest.mark.parametrize("seed", range(30))
def test_the_count_of_teams_above_never_falls_while_a_team_is_frozen(seed):
    """The search freezes its team at an extreme and lets every other record grow.

    If the number of teams above it could fall, "enough are already above, stop
    looking" would be wrong, and both of the search's early exits would be unsound
    under divisions. It cannot, because a team that loses a division title is
    replaced above by the teammate that took it.
    """
    rng = random.Random(seed)
    for _ in range(200):
        n, divisions = 8, rng.choice([2, 3, 4])
        state = divisional_state(rng, n=n, divisions=divisions)
        team = rng.randrange(n)

        before = playoff_math.strictly_above(
            team, state.wins, state.points, n, state.divisions
        )
        grown = list(state.wins)
        for other in range(n):
            if other != team:
                grown[other] += rng.randrange(0, 4)
        after = playoff_math.strictly_above(
            team, grown, state.points, n, state.divisions
        )

        assert after >= before, (
            f"above {team} fell from {before} to {after}; "
            f"divisions={state.divisions} wins={state.wins}->{grown}"
        )


# --- cross-checked against exhaustive enumeration -----------------------------


@pytest.mark.parametrize("seed", range(40))
def test_divisional_verdicts_agree_with_brute_force(seed):
    """The check that matters: enumerate every completion, seed it divisionally."""
    rng = random.Random(seed)
    state = divisional_state(rng, n=6, weeks=2, spots=3, divisions=2)

    assert classify(state) == brute_force_statuses(state)


@pytest.mark.parametrize("seed", range(20))
def test_divisional_verdicts_agree_with_brute_force_three_divisions(seed):
    rng = random.Random(1000 + seed)
    state = divisional_state(rng, n=6, weeks=2, spots=4, divisions=3)

    assert classify(state) == brute_force_statuses(state)


@pytest.mark.parametrize("seed", range(20))
def test_divisional_verdicts_agree_with_brute_force_more_games(seed):
    rng = random.Random(2000 + seed)
    state = divisional_state(rng, n=6, weeks=3, spots=3, divisions=2)

    assert classify(state) == brute_force_statuses(state)


@pytest.mark.parametrize("seed", range(20))
def test_the_widened_pruning_bound_never_hides_a_way_to_miss(seed):
    """The bound allows one promotion per division; too tight would over-clinch.

    A wrong bound shows up as a team called clinched that enumeration says is
    alive, so this asserts the clinched set is a subset of the true one.
    """
    rng = random.Random(3000 + seed)
    state = divisional_state(rng, n=6, weeks=2, spots=3, divisions=2)

    got = classify(state)
    truth = brute_force_statuses(state)
    for name, verdict in got.items():
        if verdict == "clinched":
            assert truth[name] == "clinched", f"{name} over-clinched"
        if verdict == "eliminated":
            assert truth[name] == "eliminated", f"{name} over-eliminated"


@pytest.mark.parametrize("seed", range(15))
def test_never_more_clinched_than_seats_with_divisions(seed):
    rng = random.Random(4000 + seed)
    state = divisional_state(rng, n=8, weeks=2, spots=3, divisions=2)

    verdicts = classify(state)
    assert sum(1 for v in verdicts.values() if v == "clinched") <= 3


def test_a_division_winner_can_clinch_on_a_worse_record():
    """The behaviour that record-only seeding cannot express.

    T is alone in its division with a poor record, so it wins that division in
    every completion; with three seats and two divisions it cannot be squeezed out.
    """
    state = LeagueState(
        ["T", "A", "B", "C"],
        [1, 9, 9, 9],
        [9, 1, 1, 1],
        [100.0, 900.0, 800.0, 700.0],
        [],
        3,
        [0, 1, 1, 1],
    )

    assert status_of(state, 0) == "clinched"
    # and the record-only model would have thrown it out
    without = LeagueState(*[state.names, state.wins, state.losses, state.points, [], 3])
    assert status_of(without, 0) == "eliminated"


# --- byes in a divisional league ----------------------------------------------


def test_a_divisional_league_gets_bye_claims_again():
    league = FakeLeague([FakeTeam("A", [1.0])], 1, 5, {})
    league.settings.division_map = {0: "one", 1: "two"}

    assert league_data.bye_spots(league) == 3, "5 seats -> a bracket of 8 -> 3 byes"


@pytest.mark.parametrize("seed", range(15))
def test_a_divisional_bye_is_a_top_n_finish(seed):
    rng = random.Random(5000 + seed)
    state = divisional_state(rng, n=6, weeks=2, spots=4, divisions=2)

    expected = brute_force_statuses(playoff_math.with_seats(state, 2))
    for team in range(state.num_teams):
        assert (
            playoff_math.bye_verdict(state, team, bye_spots=2)
            == expected[state.names[team]]
        )


def test_with_seats_keeps_the_divisions():
    """Dropping them here would answer the bye question with the wrong seeding."""
    state = divisional_state(random.Random(0), n=6, divisions=2)

    assert playoff_math.with_seats(state, 2).divisions == state.divisions


# --- carrying the map through the pipeline ------------------------------------


def test_the_division_map_is_keyed_by_name_not_position():
    """Stage 2 re-sorts the standings, so an index-aligned list would misalign."""
    league = FakeLeague(
        [FakeTeam("Alpha", [120.0]), FakeTeam("Bravo", [100.0])], 1, 1, {}
    )
    league.teams[0].division_id = 0
    league.teams[1].division_id = 1
    names = league_data.unique_names(league)

    assert league_data.divisions_of(league, names) == {"Alpha": 0, "Bravo": 1}


def test_a_single_division_league_reports_no_map_at_all():
    league = FakeLeague(
        [FakeTeam("Alpha", [120.0]), FakeTeam("Bravo", [100.0])], 1, 1, {}
    )
    for team in league.teams:
        team.division_id = 0
    names = league_data.unique_names(league)

    assert league_data.divisions_of(league, names) is None


def test_flattening_follows_the_standings_order():
    standings = [{"team_name": "B"}, {"team_name": "A"}, {"team_name": "C"}]
    divisions = {"A": 0, "B": 1, "C": 0}

    assert stage2.divisions_in_order(standings, divisions) == [1, 0, 0]


def test_flattening_an_absent_map_is_none():
    assert stage2.divisions_in_order([{"team_name": "A"}], None) is None
    assert stage2.divisions_in_order([{"team_name": "A"}], {}) is None


def test_a_team_missing_from_the_map_is_a_loud_error():
    """Silently defaulting it would put the team in an arbitrary division."""
    with pytest.raises(KeyError):
        stage2.divisions_in_order([{"team_name": "ghost"}], {"A": 0})


# --- the divisionless path must be untouched ----------------------------------


@pytest.mark.parametrize("seed", range(20))
def test_passing_no_divisions_is_identical_to_before(seed):
    """Regression: the fast pairwise comparator still decides a flat league."""
    rng = random.Random(6000 + seed)
    flat = divisional_state(rng, n=6, weeks=2, spots=3, divisions=1)

    assert flat.divisions is None or len(set(flat.divisions)) == 1
    assert classify(flat) == brute_force_statuses(flat)


def test_one_division_takes_the_pairwise_path():
    """len(set(divisions)) < 2 must behave exactly as None does."""
    args = (["A", "B", "C"], [3, 2, 1], [1, 2, 3], [300.0, 200.0, 100.0], [], 2)
    flat = LeagueState(*args)
    single = LeagueState(*args, [0, 0, 0])

    assert classify(flat) == classify(single)
    for team in range(3):
        assert playoff_math.strictly_above(
            team, flat.wins, flat.points, 3
        ) == playoff_math.strictly_above(team, flat.wins, flat.points, 3, [0, 0, 0])


# --- end to end through the real pipeline -------------------------------------


def test_the_committed_fixtures_carry_their_divisions(load_fixture):
    """week12/week13 are a two-division season, so they must say so.

    They were captured without it once, which meant the offline report showed a
    different seeding from a live run of the same week -- the same trap as the
    stale points_for they were captured with.
    """
    for name in ("week12.json", "week13.json"):
        fixture = load_fixture(name)
        divisions = fixture["divisions"]
        assert divisions, f"{name} should be divisional"
        assert len(set(divisions.values())) == 2
        assert set(divisions) == {t["name"] for t in fixture["teams"]}
        assert fixture["league_settings"]["bye_spots"] == 3


@pytest.mark.parametrize("name", ["week12.json", "week13.json"])
def test_the_standings_are_in_seed_order_not_record_order(load_fixture, name):
    """The table has to agree with the verdicts printed beside it.

    Sorted by record, an 8-6 division winner holding a bye appeared below a 9-5
    team without one, which reads as a bug in the verdicts.
    """
    fixture = load_fixture(name)
    settings = fixture["league_settings"]
    remaining = settings["weeks_in_season"] - settings["current_week"]
    standings = stage2.calculate_stats(
        fixture, settings["playoff_spots"], settings["weeks_in_season"], remaining
    )

    divisions = stage2.divisions_in_order(standings, fixture["divisions"])
    order = seed_order(
        [t["wins"] for t in standings], [t["points_for"] for t in standings], divisions
    )
    assert order == list(range(len(standings))), "already in seed order"
    # These two weeks happen to be one of the cases where the divisional order and
    # the record order agree; they diverge by week 14, when a division title lifts
    # an 8-6 team above a 9-5 one. That divergence is covered by
    # test_a_division_winner_outranks_a_better_wildcard, so what this asserts is
    # only that stage 2 hands the table over already seeded.


@pytest.mark.parametrize("name", ["week12.json", "week13.json"])
def test_a_bye_never_sits_below_a_non_bye_in_the_table(load_fixture, name):
    """Whatever the ordering, the report must not contradict itself."""
    fixture = load_fixture(name)
    settings = fixture["league_settings"]
    remaining = settings["weeks_in_season"] - settings["current_week"]
    standings = stage2.calculate_stats(
        fixture, settings["playoff_spots"], settings["weeks_in_season"], remaining
    )
    standings = playoff_math.apply_verdicts(
        standings,
        stage2.build_remaining_matchups(fixture["teams"], remaining),
        settings["playoff_spots"],
        bye_spots=settings["bye_spots"],
        divisions=stage2.divisions_in_order(standings, fixture["divisions"]),
    )

    byes = [i for i, t in enumerate(standings) if t["bye"] == "clinched"]
    others = [i for i, t in enumerate(standings) if t["bye"] != "clinched"]
    if byes and others:
        assert max(byes) < min(others), "a bye must never appear below a non-bye"


def test_hypotheticals_keep_the_divisional_seeding(load_fixture):
    """apply_permutation re-sorts, and dropping divisions there would silently
    decide next week's scenarios with the wrong seeding."""
    import generate_perms
    import refine_hypothetical as stage4

    fixture = load_fixture("week13.json")
    settings = fixture["league_settings"]
    remaining = settings["weeks_in_season"] - settings["current_week"]
    standings = stage2.calculate_stats(
        fixture, settings["playoff_spots"], settings["weeks_in_season"], remaining
    )
    base = {
        "league_data": {
            "playoff_spots": settings["playoff_spots"],
            "bye_spots": settings["bye_spots"],
            "num_weeks": settings["weeks_in_season"],
            "remaining_weeks": remaining,
            "current_week": settings["current_week"],
        },
        "next_week_matchups": fixture["next_week_matchups"],
        "remaining_matchups": stage2.build_remaining_matchups(
            fixture["teams"], remaining
        ),
        "standings": standings,
        "divisions": fixture["divisions"],
    }

    for permutation in generate_perms.generate_matchup_permutations(base):
        result = stage4.apply_permutation(base, permutation)
        divisions = stage2.divisions_in_order(result, fixture["divisions"])
        order = seed_order(
            [t["wins"] for t in result], [t["points_for"] for t in result], divisions
        )
        assert order == list(range(len(result))), (
            f"permutation {permutation} left the standings out of seed order"
        )


# --- division-winner verdict (the title race) ---------------------------------


def brute_force_division_winner(state):
    """Enumerate every completion and mark, per team, whether it ever / never
    finishes best in its own division (by wins, then points). O(2^games)."""
    n = state.num_teams
    ever_win = [False] * n
    ever_not = [False] * n
    for outcome in itertools.product(*[(i, j) for (i, j) in state.games]):
        wins = list(state.wins)
        for (i, j), winner in zip(state.games, outcome):
            wins[winner] += 1
        for division in set(state.divisions):
            members = [t for t in range(n) if state.divisions[t] == division]
            best = max(members, key=lambda t: (wins[t], state.points[t]))
            for t in members:
                (ever_win if t == best else ever_not)[t] = True
    statuses = {}
    for t in range(n):
        if not ever_not[t]:
            statuses[state.names[t]] = "clinched"
        elif not ever_win[t]:
            statuses[state.names[t]] = "eliminated"
        else:
            statuses[state.names[t]] = "alive"
    return statuses


def division_verdicts(state):
    return {
        state.names[t]: playoff_math.division_verdict(state, t)
        for t in range(state.num_teams)
    }


@pytest.mark.parametrize("seed", range(40))
def test_division_winner_agrees_with_brute_force(seed):
    rng = random.Random(7000 + seed)
    state = divisional_state(rng, n=6, weeks=2, spots=3, divisions=2, played=8)

    assert division_verdicts(state) == brute_force_division_winner(state)


@pytest.mark.parametrize("seed", range(12))
def test_division_winner_agrees_with_brute_force_three_divisions(seed):
    rng = random.Random(9000 + seed)
    state = divisional_state(rng, n=9, weeks=2, spots=4, divisions=3, played=8)

    assert division_verdicts(state) == brute_force_division_winner(state)


def test_a_runaway_division_leader_has_clinched_its_title():
    """One team so far ahead that losing out still tops the division."""
    state = LeagueState(
        ["Runaway", "Chaser", "Other"],
        wins=[9, 5, 0], losses=[3, 7, 12], points=[1800.0, 1700.0, 1500.0],
        games=[(0, 1), (1, 2)],  # one week left
        playoff_spots=1, divisions=[0, 0, 1],
    )
    assert playoff_math.division_verdict(state, 0) == "clinched"
    # the chaser cannot catch a two-game lead with one game left
    assert playoff_math.division_verdict(state, 1) == "eliminated"


def test_a_tight_division_is_still_a_live_race():
    state = LeagueState(
        ["A", "B", "Other"],
        wins=[6, 6, 0], losses=[6, 6, 12], points=[1700.0, 1690.0, 1500.0],
        games=[(0, 1)],  # they play head to head, winner takes the division
        playoff_spots=1, divisions=[0, 0, 1],
    )
    assert playoff_math.division_verdict(state, 0) == "alive"
    assert playoff_math.division_verdict(state, 1) == "alive"


def test_division_verdict_is_none_without_divisions():
    state = LeagueState(
        ["A", "B"], [1, 0], [0, 1], [100.0, 90.0], [(0, 1)], playoff_spots=1
    )
    assert playoff_math.division_verdict(state, 0) is None


def test_an_outside_game_still_counts_toward_the_division_race():
    """A member's game against the other division must feed its own record.

    Leader and Rival are tied on wins; each has one game left, but against
    OUTSIDE teams. Whoever wins theirs takes the division, so both are alive --
    which only holds if the phantom (outside) game is modelled at all.
    """
    state = LeagueState(
        ["Leader", "Rival", "OutX", "OutY"],
        wins=[6, 6, 3, 3], losses=[6, 6, 9, 9],
        points=[1700.0, 1680.0, 1500.0, 1490.0],
        games=[(0, 2), (1, 3)],  # Leader vs OutX, Rival vs OutY -- cross-division
        playoff_spots=1, divisions=[0, 0, 1, 1],
    )
    assert playoff_math.division_verdict(state, 0) == "alive"
    assert playoff_math.division_verdict(state, 1) == "alive"
