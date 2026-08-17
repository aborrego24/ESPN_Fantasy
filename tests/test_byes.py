"""First-round byes: the same question, asked of fewer seats.

A bye goes to the top seeds, who skip the opening playoff round. So "has this
team clinched a bye" is "does it finish in the top `bye_spots` in every
completion" -- the identical search the playoff verdict already runs, over a
state that names a smaller threshold. Nothing in the search changes.

Two things are deliberate and tested here rather than assumed.

`verdict` stays a three-way playoff answer and the bye is carried separately. A
team with a bye has also clinched a place, so widening `verdict` to a fourth value
would make every existing `== "clinched"` check silently skip them. Only the
readable `status` folds the two together.

And the bye count is derived, because ESPN does not publish the bracket shape.
"""

import random

import pytest

import league_data
import playoff_math
import pretty_print
import refine_current_week as stage2
import to_html
from playoff_math import LeagueState, makes_playoffs, with_seats
from test_playoff_math import brute_force_statuses, random_state
from test_league_data import FakeLeague, FakeTeam


# --- the threshold really is just a parameter ----------------------------------


def test_with_seats_changes_only_the_threshold():
    state = LeagueState(["A", "B", "C"], [2, 1, 0], [0, 1, 2], [10.0, 9.0, 8.0], [(0, 1)], 2)

    narrowed = with_seats(state, 1)

    assert narrowed.playoff_spots == 1
    assert state.playoff_spots == 2, "the original must not be touched"
    for field in ("names", "wins", "losses", "points", "games"):
        assert getattr(narrowed, field) == getattr(state, field)


@pytest.mark.parametrize("seed", range(25))
def test_a_bye_verdict_is_a_top_n_verdict_and_matches_brute_force(seed):
    """Enumerate every completion and ask who is always in the top two."""
    rng = random.Random(seed)
    state = random_state(rng, n=6, weeks=2, spots=4)

    narrowed = with_seats(state, 2)
    expected = brute_force_statuses(narrowed)

    for team in range(state.num_teams):
        got = playoff_math.bye_verdict(state, team, bye_spots=2)
        assert got == expected[state.names[team]], (
            f"{state.names[team]}: bye says {got}, enumeration says "
            f"{expected[state.names[team]]}"
        )


@pytest.mark.parametrize("seed", range(15))
def test_never_more_byes_than_bye_seats(seed):
    rng = random.Random(seed)
    state = random_state(rng, n=6, weeks=2, spots=4)

    clinched = sum(
        playoff_math.bye_verdict(state, t, bye_spots=2) == "clinched"
        for t in range(state.num_teams)
    )
    assert clinched <= 2


# --- the invariants that make it safe to carry alongside `verdict` -------------


def standings_of(names, wins, points):
    return [
        {"team_name": n, "wins": w, "losses": 14 - w, "points_for": p}
        for n, w, p in zip(names, wins, points)
    ]


def decided(wins, points, spots=4, bye_spots=2, remaining=None, envelope=None):
    names = [f"T{i}" for i in range(len(wins))]
    standings = standings_of(names, wins, points)
    return playoff_math.apply_verdicts(
        standings,
        remaining if remaining is not None else [],
        spots,
        swing_envelope=envelope,
        bye_spots=bye_spots,
    )


def test_a_bye_always_comes_with_a_place():
    """Nobody holds a bye without holding a seat -- the containment property."""
    for team in decided([14, 12, 10, 8, 6, 4], [200.0, 190.0, 180.0, 170.0, 160.0, 150.0]):
        if team["bye"] == "clinched":
            assert team["verdict"] == "clinched"


def test_a_team_out_of_the_playoffs_is_out_of_the_byes():
    """The shortcut that produced wrong data: calling these teams bye-'alive'."""
    for team in decided([14, 12, 10, 8, 6, 4], [200.0, 190.0, 180.0, 170.0, 160.0, 150.0]):
        if team["verdict"] == "eliminated":
            assert team["bye"] == "eliminated"


def test_the_playoff_verdict_is_unchanged_by_asking_about_byes():
    """The safety argument for carrying the bye separately, made checkable."""
    wins = [14, 12, 10, 8, 6, 4]
    points = [200.0, 190.0, 180.0, 170.0, 160.0, 150.0]

    without = {t["team_name"]: t["verdict"] for t in decided(wins, points, bye_spots=0)}
    with_byes = {t["team_name"]: t["verdict"] for t in decided(wins, points, bye_spots=2)}

    assert without == with_byes


def test_no_bye_seats_means_no_bye_field_and_no_change_to_status():
    for team in decided([14, 12, 10, 8, 6, 4], [200.0] * 6, bye_spots=0):
        assert team["bye"] is None
        assert team["status"] != playoff_math.STATUS_BYE


def test_a_bye_resting_on_a_thin_points_gap_is_withheld():
    """A bye is held to the same standard as a place.

    The gap that matters is cumulative, and getting this wrong is easy. With two
    bye seats, the leader only drops out of the top two when **two** rivals pass
    it, so the binding gap is the larger of the two deficits, not the nearest
    one. Three teams tied on wins at 200/198/196 puts both rivals within 4 points
    of the leader, which is what makes its bye depend on the scoring holding.
    """
    wins = [10, 10, 10, 4, 4, 4]
    points = [200.0, 198.0, 196.0, 90.0, 80.0, 70.0]

    frozen = decided(wins, points, remaining=[], envelope=None)
    guarded = decided(wins, points, remaining=[], envelope=50.0)

    assert [t["bye"] for t in frozen].count("clinched") == 2, "frozen points decide it"
    for name in ("T0", "T1"):
        team = next(t for t in guarded if t["team_name"] == name)
        assert team["bye"] == "alive", f"{name}'s bye rests on a 4-point cushion"


def test_a_wide_points_gap_still_clinches_a_bye():
    """The mirror: the envelope must not withhold a bye nobody can reach.

    Same shape, but the third-placed team is 100 points back, so both rivals
    passing the leader is not something a 50-point swing can produce.
    """
    wins = [10, 10, 10, 4, 4, 4]
    points = [200.0, 198.0, 100.0, 90.0, 80.0, 70.0]

    guarded = decided(wins, points, remaining=[], envelope=50.0)

    leader = next(t for t in guarded if t["team_name"] == "T0")
    assert leader["bye"] == "clinched", "T2 is 100 back; both cannot pass"


# --- how many byes there are, which ESPN does not tell us ----------------------


@pytest.mark.parametrize(
    "spots,expected",
    [(1, 0), (2, 0), (3, 1), (4, 0), (5, 3), (6, 2), (7, 1), (8, 0), (10, 6)],
)
def test_the_bye_count_is_the_gap_to_the_next_power_of_two(spots, expected):
    league = FakeLeague([FakeTeam("A", [1.0])], 1, spots, {})
    league.settings.division_map = {0: "only"}

    assert league_data.bye_spots(league) == expected


def test_a_divisional_league_claims_no_byes():
    """2024 seeded division winners first, so the order is not ours to claim."""
    league = FakeLeague([FakeTeam("A", [1.0])], 1, 6, {})
    league.settings.division_map = {0: "Trump", 1: "Biden"}

    assert league_data.bye_spots(league) == 0


def test_a_league_with_no_division_information_still_answers():
    league = FakeLeague([FakeTeam("A", [1.0])], 1, 6, {})
    league.settings.division_map = None

    assert league_data.bye_spots(league) == 2


# --- how it reads -------------------------------------------------------------


@pytest.mark.parametrize(
    "team,expected",
    [
        ({"verdict": "clinched", "bye": "clinched"}, "bye"),
        ({"verdict": "clinched", "bye": "eliminated"}, "clinched"),
        ({"verdict": "clinched", "bye": "alive"}, "clinched"),
        ({"verdict": "alive", "bye": "alive"}, "alive"),
        ({"verdict": "eliminated", "bye": "eliminated"}, "eliminated"),
        ({"verdict": "clinched", "bye": None}, "clinched"),
        ({"verdict": "alive"}, "alive"),
    ],
)
def test_the_displayed_status_folds_the_two_verdicts(team, expected):
    assert pretty_print.display_status(team) == expected


def test_only_four_statuses_are_ever_displayed():
    shown = {
        pretty_print.display_status(t)
        for t in decided([14, 12, 10, 8, 6, 4], [200.0, 190.0, 180.0, 170.0, 160.0, 150.0])
    }

    assert shown <= {"bye", "clinched", "alive", "eliminated"}


def test_the_html_standings_show_the_bye_status():
    standings = decided(
        [14, 12, 10, 8, 6, 4], [200.0, 190.0, 180.0, 170.0, 160.0, 150.0]
    )
    document = to_html.render(
        {
            "base_league_data": {
                "league_data": {
                    "playoff_spots": 4,
                    "bye_spots": 2,
                    "num_weeks": 14,
                    "remaining_weeks": 0,
                    "current_week": 14,
                },
                "standings": standings,
                "next_week_matchups": [],
                "weekly_scores": [],
            },
            "scenarios": [],
        }
    )

    assert '<span class="pill bye">bye</span>' in document
    assert ".bye { color:" in document


def test_stage_two_passes_the_bye_count_through(load_fixture):
    """A fixture predating bye_spots must still work, claiming no byes."""
    fixture = load_fixture("PC_test.json")
    assert "bye_spots" not in fixture["league_settings"]

    settings = fixture["league_settings"]
    standings = stage2.calculate_stats(fixture, settings["playoff_spots"], 9, 1)
    remaining = stage2.build_remaining_matchups(fixture["teams"], 1)
    decided_standings = playoff_math.apply_verdicts(
        standings, remaining, settings["playoff_spots"], bye_spots=0
    )

    assert all(t["bye"] is None for t in decided_standings)
