"""A team's projected scoring, from the best starting lineup its roster allows.

A roster's projected points-per-game is NOT the sum of every rostered player's
projection: only players in a starting slot score, and a team carries more
players than it can start. Two quarterbacks with one QB slot means only the
better one counts; a FLEX slot takes the best eligible player left after the
dedicated slots are filled. So the projection is the sum over the *optimal legal
starting lineup*, which is an assignment problem.

This module is deliberately platform-agnostic -- it never imports espn_api. It
takes plain players (each an object with `eligible_slots` and `projection`) and
a slot requirement list, exactly as the rest of the engine takes plain dicts, so
it can be unit-tested with no network. Stage 1 is the only place that turns ESPN
objects into these plain players.

  A slot is named as ESPN names it: "QB", "RB", "WR", "TE", "D/ST", "K", and the
  composite "RB/WR/TE" for a standard FLEX (or "OP" for a superflex that also
  takes a QB). A player may fill a slot when that slot's name is in the player's
  `eligible_slots` -- ESPN's own eligibility, rather than a guess from the
  player's nominal position.

The greedy below fills the most constrained slot first, each slot taking the
highest-projected eligible player not already used. That is provably optimal
when the slots are *laminar* -- every composite slot is a superset of the
dedicated ones it overlaps (FLEX contains RB, WR, TE; a superflex contains those
plus QB), which is how real fantasy lineups are built. A pathological config
with two partially-overlapping flex slots could defeat it and would need a full
assignment solve; no such league is in scope, and `Player` carries the exact
eligibility so the guard is a matter of the slot list, not the data.
"""


class Player:
    """The minimum a projection needs: what a player may start at, and their number.

    `eligible_slots` is the set of slot names ESPN says the player qualifies for;
    `projection` is whatever projected figure the caller wants summed -- points
    per game for a season estimate, or a single week's projection for one week.
    """

    def __init__(self, name, eligible_slots, projection):
        self.name = name
        self.eligible_slots = set(eligible_slots)
        self.projection = projection

    def __repr__(self):
        return f"Player({self.name!r}, {self.projection})"


def _slot_instances(slot_counts):
    """Expand [("RB", 2), ("QB", 1)] into ["RB", "RB", "QB"]."""
    return [name for name, count in slot_counts for _ in range(count)]


def optimal_lineup(players, slot_counts):
    """The best legal starting lineup, as a list of (slot_name, player).

    `slot_counts` is a list of (slot_name, count) for the *starting* slots only
    -- bench and IR are the caller's to leave out. A slot with no eligible player
    left is simply not filled (an incomplete roster, e.g. a team carrying no
    kicker), rather than raising: the lineup is the best that can be fielded.
    """
    instances = _slot_instances(slot_counts)
    # Fill the most constrained slots first. Counting eligible players once, up
    # front, is enough for a laminar slot family: a dedicated slot can never have
    # more eligible players than a composite that contains it, so the dedicated
    # one sorts earlier and claims its specialists before FLEX takes the leftover.
    eligible_count = {
        slot: sum(1 for p in players if slot in p.eligible_slots)
        for slot in set(instances)
    }
    instances.sort(key=lambda slot: eligible_count[slot])

    used = set()
    chosen = []
    for slot in instances:
        best = None
        for index, player in enumerate(players):
            if index in used or slot not in player.eligible_slots:
                continue
            if best is None or player.projection > players[best].projection:
                best = index
        if best is not None:
            used.add(best)
            chosen.append((slot, players[best]))
    return chosen


def projected_points(players, slot_counts):
    """The summed projection of the optimal starting lineup."""
    return sum(player.projection for _, player in optimal_lineup(players, slot_counts))
