"""Does a draft-day projected PPG predict how a team actually scored?

This is the spike that gates the whole projections feature. Preseason strength of
schedule rests on one assumption: that ESPN's preseason player projections, rolled
up into each team's best legal starting lineup, say something real about how much
a team will score. If they do not, a preseason SOS built on them is worthless and
should not be built.

So this reconstructs each team's DRAFT-DAY roster (from `league.draft`, not the
end-of-season roster, which reflects a season of waivers and trades), projects each
team's points-per-game from the optimal lineup of that roster using ESPN's
preseason projections, and correlates it against what the team actually averaged.

Two facts make this an honest preseason test rather than hindsight:

  - The projections ESPN serves for a completed season are the FROZEN preseason
    numbers, not recomputed. Verified directly: a star who tore up his knee in
    week 4 of 2025 still carries his full healthy-season projection here.
  - The roster is the draft-day one, so it is the information a manager had before
    week 1 -- no in-season moves leak in.

What it cannot test is preseason accuracy on a season that has not drafted yet;
that waits for the next draft. This proves the mechanism and measures the signal
on the seasons we have.

    python3 tools/validate_projections.py 2024 2025

It is a measurement, not a gate: it prints the correlation and a plain-language
read, and always exits 0. On this league it comes back WEAK (mean Pearson r about
0.07) -- a snake draft equalises rosters, so projected team strength is compressed
and barely discriminates, and a season of waivers and lineup decisions sits between
the drafted roster and the realised total. That measured weakness is exactly why
preseason SOS is rendered with a low-confidence label rather than trusted; this
tool is where that label's number comes from. Read the numbers.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenario_engine"
    ),
)

import config
import projections
from espn_api.football import League
from espn_api.football.constant import POSITION_MAP

LEAGUE_ID = config.default_league_id()
if LEAGUE_ID is None:
    sys.exit(
        "no league configured: set ESPN_LEAGUE_ID or copy "
        "scenario_engine/local_config.example.py to local_config.py"
    )
SIGNAL_BAR = 0.2  # mean Pearson r at or above this is "there is a real signal"

# Slots that never score, so never count toward a lineup.
NON_STARTING = {"BE", "IR"}


def starting_slots(league):
    """The scoring slots and their counts, e.g. [("QB", 1), ("RB", 2), ...].

    Read from the raw settings by slot id, then named through the library's
    POSITION_MAP -- the same names ESPN puts in a player's eligibleSlots, so the
    two line up when the lineup is solved. The library's own
    `position_slot_counts` is built by zipping names against counts in id order
    and is fragile; the raw dict keyed by id is authoritative.
    """
    raw = league.espn_request.get_league()
    counts = raw["settings"]["rosterSettings"]["lineupSlotCounts"]
    slots = []
    for slot_id, count in sorted(counts.items(), key=lambda kv: int(kv[0])):
        name = POSITION_MAP.get(int(slot_id))
        if count and name and name not in NON_STARTING:
            slots.append((name, count))
    return slots


def projection_lookup(league):
    """A {playerId: projections.Player} map, filling in drafted-then-dropped players.

    Current rosters carry projections for free, so start there. A player drafted
    and later dropped is on no current roster, so fetch those individually. Both
    give the same preseason projection for the season being queried.
    """
    cache = {}
    for team in league.teams:
        for p in team.roster:
            cache[p.playerId] = projections.Player(
                p.name, p.eligibleSlots, p.projected_avg_points or 0.0
            )
    return cache


def draft_day_rosters(league, cache):
    """Each team's drafted players as projections.Player, keyed by team name."""
    misses = 0
    rosters = {}
    for pick in league.draft:
        team_name = pick.team.team_name
        player = cache.get(pick.playerId)
        if player is None:
            # Drafted then dropped: not on any current roster, so ask directly.
            try:
                info = league.player_info(playerId=pick.playerId)
                player = projections.Player(
                    info.name, info.eligibleSlots, info.projected_avg_points or 0.0
                )
                cache[pick.playerId] = player
            except Exception:
                misses += 1
                continue
        rosters.setdefault(team_name, []).append(player)
    return rosters, misses


def actual_ppg(team, weeks):
    """A team's real regular-season points per game."""
    scores = [s for s in team.scores[:weeks] if s]
    return sum(scores) / len(scores) if scores else 0.0


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


def spearman(xs, ys):
    """Rank correlation: Pearson on the ranks, so it judges the ordering."""
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        rank = [0] * len(values)
        for position, index in enumerate(order):
            rank[index] = position
        return rank

    return pearson(ranks(xs), ranks(ys))


def check_season(year):
    league = League(league_id=LEAGUE_ID, year=year)
    weeks = league.settings.reg_season_count
    slots = starting_slots(league)

    print(f"\n{'=' * 78}")
    print(f"{year}  --  {len(league.teams)} teams, {weeks} weeks")
    print(f"{'=' * 78}")
    print("starting slots:", ", ".join(f"{n}x{c}" for n, c in slots))

    cache = projection_lookup(league)
    rosters, misses = draft_day_rosters(league, cache)
    if misses:
        print(f"note: {misses} drafted player(s) had no retrievable projection, treated as 0")

    rows = []
    for team in league.teams:
        drafted = rosters.get(team.team_name, [])
        proj = projections.projected_points(drafted, slots)
        rows.append((team.team_name, proj, actual_ppg(team, weeks)))
    rows.sort(key=lambda r: r[1], reverse=True)

    print(f"\n{'Team':32} {'ProjPPG':>8} {'ActualPPG':>10}")
    for name, proj, actual in rows:
        print(f"{name[:32]:32} {proj:8.1f} {actual:10.1f}")

    proj_vals = [r[1] for r in rows]
    actual_vals = [r[2] for r in rows]
    r = pearson(proj_vals, actual_vals)
    rho = spearman(proj_vals, actual_vals)
    print(f"\nPearson r  (projected PPG vs actual PPG) = {r:+.3f}")
    print(f"Spearman rho (does it rank teams right)  = {rho:+.3f}")
    return r


def main(years):
    rs = [check_season(year) for year in years]
    mean_r = sum(rs) / len(rs) if rs else 0.0

    print(f"\n{'=' * 78}")
    print(f"mean Pearson r across {len(years)} season(s) = {mean_r:+.3f}  (bar {SIGNAL_BAR})")
    if mean_r >= SIGNAL_BAR:
        print("[SIGNAL]  draft-day projected PPG carries a real signal")
    else:
        print("[WEAK]    draft-day projected PPG barely predicts -- preseason SOS is labeled low-confidence")
    print(f"{'=' * 78}")
    return 0


if __name__ == "__main__":
    sys.exit(main([int(a) for a in sys.argv[1:]] or [2024, 2025]))
