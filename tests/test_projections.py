"""The optimal-lineup projection: a roster's best legal starting lineup.

Every expected total here is worked out by hand. The point of the module is that
a projection is NOT the sum of a roster's projections -- only the best legal
starting lineup scores -- so the tests are built around cases where a naive sum,
or a naive greedy, would get it wrong.

A standard league's starting slots, reused below:
"""

import pytest

from projections import Player, optimal_lineup, projected_points

STARTERS = [
    ("QB", 1),
    ("RB", 2),
    ("WR", 2),
    ("TE", 1),
    ("D/ST", 1),
    ("K", 1),
    ("RB/WR/TE", 1),  # FLEX
]

# ESPN's real eligibility strings per position, including the composite slots a
# player qualifies for. Bench/IR are left off: they are never a starting slot.
ELIGIBLE = {
    "QB": {"QB", "OP"},
    "RB": {"RB", "RB/WR", "RB/WR/TE", "OP"},
    "WR": {"WR", "RB/WR", "WR/TE", "RB/WR/TE", "OP"},
    "TE": {"TE", "WR/TE", "RB/WR/TE", "OP"},
    "D/ST": {"D/ST"},
    "K": {"K"},
}


def player(name, position, projection):
    return Player(name, ELIGIBLE[position], projection)


def test_a_full_roster_starts_its_best_at_each_slot():
    """Worked by hand: the bolded players below start, the rest sit.

    QB 24 (not 18) | RB 20, 15 | WR 18, 14 | TE 11 | DST 8 | K 9
    FLEX = best leftover RB/WR/TE among RB 12, WR 10, TE 6 -> RB 12.
    Total 24+20+15+18+14+11+8+9+12 = 131.
    """
    roster = [
        player("QB1", "QB", 24.0),
        player("QB2", "QB", 18.0),
        player("RB1", "RB", 20.0),
        player("RB2", "RB", 15.0),
        player("RB3", "RB", 12.0),
        player("WR1", "WR", 18.0),
        player("WR2", "WR", 14.0),
        player("WR3", "WR", 10.0),
        player("TE1", "TE", 11.0),
        player("TE2", "TE", 6.0),
        player("DST", "D/ST", 8.0),
        player("K1", "K", 9.0),
    ]

    assert projected_points(roster, STARTERS) == pytest.approx(131.0)


def test_two_quarterbacks_but_one_slot_counts_only_the_better():
    """The headline case: a naive roster sum would double-count the QBs."""
    roster = [
        player("QB1", "QB", 24.0),
        player("QB2", "QB", 18.0),
    ]

    chosen = optimal_lineup(roster, [("QB", 1)])
    assert [p.name for _, p in chosen] == ["QB1"]
    assert projected_points(roster, [("QB", 1)]) == pytest.approx(24.0)


def test_flex_takes_the_best_eligible_player_left_over():
    """RB and WR slots fill first; FLEX gets the best remaining RB/WR/TE."""
    roster = [
        player("RB1", "RB", 20.0),
        player("RB2", "RB", 9.0),  # a spare RB, the best FLEX option
        player("WR1", "WR", 18.0),
        player("WR2", "WR", 7.0),
        player("TE1", "TE", 8.0),
    ]
    slots = [("RB", 1), ("WR", 1), ("RB/WR/TE", 1)]

    chosen = dict((slot, p.name) for slot, p in optimal_lineup(roster, slots))
    assert chosen == {"RB": "RB1", "WR": "WR1", "RB/WR/TE": "RB2"}


def test_a_scarce_slot_is_filled_before_flex_can_steal_its_only_player():
    """The case that distinguishes the real solve from filling FLEX first.

    One TE on the roster, and it is the highest projection. If FLEX grabbed it,
    the TE slot would go empty (no other TE) and the lineup would lose points. So
    TE must take TE1 (30) and FLEX the next best RB (20): total 50, not 30.
    """
    roster = [
        player("TE1", "TE", 30.0),
        player("RB1", "RB", 20.0),
        player("RB2", "RB", 10.0),
    ]
    slots = [("TE", 1), ("RB/WR/TE", 1)]

    chosen = dict((slot, p.name) for slot, p in optimal_lineup(roster, slots))
    assert chosen == {"TE": "TE1", "RB/WR/TE": "RB1"}
    assert projected_points(roster, slots) == pytest.approx(50.0)


def test_a_superflex_slot_can_take_a_second_quarterback():
    """An OP slot accepts QBs, so the backup QB starts when it out-projects the field."""
    roster = [
        player("QB1", "QB", 25.0),
        player("QB2", "QB", 20.0),
        player("RB1", "RB", 18.0),
    ]
    slots = [("QB", 1), ("OP", 1)]

    chosen = dict((slot, p.name) for slot, p in optimal_lineup(roster, slots))
    assert chosen == {"QB": "QB1", "OP": "QB2"}
    assert projected_points(roster, slots) == pytest.approx(45.0)


def test_a_slot_with_no_eligible_player_is_left_unfilled():
    """An incomplete roster fields the best lineup it can, not an error."""
    roster = [player("RB1", "RB", 20.0)]

    chosen = optimal_lineup(roster, [("K", 1)])
    assert chosen == []
    assert projected_points(roster, [("K", 1)]) == pytest.approx(0.0)


def test_an_empty_roster_projects_zero():
    assert projected_points([], STARTERS) == pytest.approx(0.0)
    assert optimal_lineup([], STARTERS) == []


def test_no_player_is_started_in_two_slots_at_once():
    """A structural invariant: the lineup is an assignment, one slot per player."""
    roster = [
        player("RB1", "RB", 20.0),
        player("WR1", "WR", 18.0),
        player("TE1", "TE", 8.0),
        player("RB2", "RB", 6.0),
    ]

    chosen = optimal_lineup(roster, STARTERS)
    started = [p.name for _, p in chosen]
    assert len(started) == len(set(started)), "a player was started twice"


def test_projected_points_is_exactly_the_chosen_lineups_sum():
    roster = [
        player("QB1", "QB", 24.0),
        player("RB1", "RB", 20.0),
        player("WR1", "WR", 18.0),
    ]
    slots = [("QB", 1), ("RB", 1), ("WR", 1), ("RB/WR/TE", 1)]

    chosen = optimal_lineup(roster, slots)
    assert projected_points(roster, slots) == pytest.approx(
        sum(p.projection for _, p in chosen)
    )
