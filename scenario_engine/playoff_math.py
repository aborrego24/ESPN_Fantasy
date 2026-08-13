"""Exact playoff clinch/elimination math.

A team has CLINCHED iff it finishes in a playoff seat in *every* completion of
the remaining schedule, and is ELIMINATED iff it does so in *none*. Anything
else is still alive.

The engine answers those questions by searching for a counterexample rather
than enumerating every completion:

  clinched  <=>  no completion exists where the team misses
  eliminated <=> no completion exists where the team makes it

Two facts keep that search small.

1. Dominance. To prove a team CAN miss, it is always optimal for that team to
   lose every remaining game -- its own wins only ever help it, and each of its
   losses also hands a win to a rival. So its games are fixed, not branched.
   The mirror holds for proving it can make it.
2. Bounds pruning. At any point in the search, a rival that cannot reach the
   team's win total even by winning out can never finish above it, so whole
   branches collapse.

Seeding follows ESPN's playoffSeedingRule = TOTAL_POINTS_SCORED: order by wins,
then by total points scored. Points are treated as fixed at their current
values (see `points`), which is a modelling choice, not a fact -- callers that
care should consult the margin helpers below.
"""


class SearchBudgetExceeded(Exception):
    """Raised rather than returning a guess when the search grows too large."""


DEFAULT_NODE_BUDGET = 2_000_000


class LeagueState:
    """Snapshot of a league plus the games it has left to play.

    wins/losses/points are parallel lists indexed by team. `games` is a flat
    list of (i, j) pairs -- week boundaries do not affect who finishes where,
    only how conditions get worded, so they are flattened here.
    """

    def __init__(self, names, wins, losses, points, games, playoff_spots):
        self.names = list(names)
        self.wins = list(wins)
        self.losses = list(losses)
        self.points = list(points)
        self.games = list(games)
        self.playoff_spots = playoff_spots

    @property
    def num_teams(self):
        return len(self.names)

    def index_of(self, name):
        return self.names.index(name)

    def games_left_for(self, team):
        return sum(1 for i, j in self.games if team in (i, j))

    def with_results(self, decided):
        """Return a copy with `decided` [(game_index, winner)] already played."""
        wins = list(self.wins)
        losses = list(self.losses)
        played = set()
        for game_index, winner in decided:
            i, j = self.games[game_index]
            loser = j if winner == i else i
            wins[winner] += 1
            losses[loser] += 1
            played.add(game_index)
        games = [g for k, g in enumerate(self.games) if k not in played]
        return LeagueState(
            self.names, wins, losses, self.points, games, self.playoff_spots
        )


def beats(a, b, wins, points):
    """True if team a outranks team b under (wins, then total points)."""
    if wins[a] != wins[b]:
        return wins[a] > wins[b]
    return points[a] > points[b]


def strictly_above(team, wins, points, num_teams):
    return sum(1 for u in range(num_teams) if u != team and beats(u, team, wins, points))


def makes_playoffs(team, wins, points, num_teams, playoff_spots):
    return strictly_above(team, wins, points, num_teams) < playoff_spots


def _search(state, team, want_in, budget):
    """Look for one completion where `team` does / does not make the playoffs.

    Returns the winning assignment as a list of (game_index, winner), or None if
    no such completion exists. `team`'s own games are fixed by the dominance
    argument in the module docstring: it wins out when we are hunting for a way
    in, and loses out when hunting for a way to miss.
    """
    n = state.num_teams
    wins = list(state.wins)
    losses = list(state.losses)
    points = state.points
    spots = state.playoff_spots

    fixed = []
    open_games = []
    for k, (i, j) in enumerate(state.games):
        if team in (i, j):
            other = j if i == team else i
            winner = team if want_in else other
            loser = other if want_in else team
            wins[winner] += 1
            losses[loser] += 1
            fixed.append((k, winner))
        else:
            open_games.append(k)

    # Remaining games each rival could still win, for bounds pruning.
    upside = [0] * n
    for k in open_games:
        i, j = state.games[k]
        upside[i] += 1
        upside[j] += 1

    nodes = [0]
    chosen = []

    def could_still_pass(u):
        """Could u finish above `team`, given u's best case from here?"""
        best = wins[u] + upside[u]
        if best != wins[team]:
            return best > wins[team]
        return points[u] > points[team]

    def recurse(pos):
        nodes[0] += 1
        if nodes[0] > budget:
            raise SearchBudgetExceeded(
                f"exceeded {budget} nodes deciding {state.names[team]!r}"
            )

        above_now = strictly_above(team, wins, points, n)
        if want_in:
            # Hunting for a way IN: give up this branch once enough rivals are
            # already locked above the team.
            if above_now >= spots:
                return False
        else:
            # Hunting for a way to MISS: success as soon as enough are above.
            if above_now >= spots:
                return True
            reachable = above_now + sum(
                1
                for u in range(n)
                if u != team
                and not beats(u, team, wins, points)
                and could_still_pass(u)
            )
            if reachable < spots:
                return False

        if pos == len(open_games):
            return makes_playoffs(team, wins, points, n, spots) == want_in

        k = open_games[pos]
        i, j = state.games[k]
        for winner, loser in ((i, j), (j, i)):
            wins[winner] += 1
            losses[loser] += 1
            upside[i] -= 1
            upside[j] -= 1
            chosen.append((k, winner))

            found = recurse(pos + 1)

            if not found:
                chosen.pop()
                upside[i] += 1
                upside[j] += 1
                wins[winner] -= 1
                losses[loser] -= 1
            if found:
                return True
        return False

    if recurse(0):
        return fixed + list(chosen)
    return None


def status_of(state, team, budget=DEFAULT_NODE_BUDGET):
    """Return 'clinched', 'eliminated', or 'alive' for one team.

    'clinched' means the team is in a playoff seat in every completion of the
    remaining schedule; 'eliminated' means in none.
    """
    if not state.games:
        made = makes_playoffs(
            team, state.wins, state.points, state.num_teams, state.playoff_spots
        )
        return "clinched" if made else "eliminated"

    if _search(state, team, want_in=False, budget=budget) is None:
        return "clinched"  # no completion where the team misses
    if _search(state, team, want_in=True, budget=budget) is None:
        return "eliminated"  # no completion where the team makes it
    return "alive"


def classify(state, budget=DEFAULT_NODE_BUDGET):
    """Status for every team, keyed by team name."""
    return {
        state.names[t]: status_of(state, t, budget=budget)
        for t in range(state.num_teams)
    }


STATUS_CLINCHED = "Clinched Playoff Spot"
STATUS_ELIMINATED = "Eliminated"


def state_from_standings(standings, remaining_matchups, playoff_spots):
    """Build a LeagueState from the pipeline's JSON shapes.

    `remaining_matchups` is a list of weeks, each a list of
    {"team1": ..., "team2": ...}.
    """
    names = [t["team_name"] for t in standings]
    index = {name: i for i, name in enumerate(names)}
    games = [
        (index[m["team1"]], index[m["team2"]])
        for week in remaining_matchups
        for m in week
    ]
    return LeagueState(
        names,
        [t["wins"] for t in standings],
        [t["losses"] for t in standings],
        [t["points_for"] for t in standings],
        games,
        playoff_spots,
    )


def apply_verdicts(standings, remaining_matchups, playoff_spots, budget=DEFAULT_NODE_BUDGET):
    """Set each team's status from the exact full-season verdict, in place.

    The magic numbers are left untouched as display values. They answer "can
    this one rival pass me", which is a different question from "do I finish in
    a playoff seat" -- only the latter can justify the word "clinched".
    """
    state = state_from_standings(standings, remaining_matchups, playoff_spots)
    verdicts = classify(state, budget=budget)
    for team in standings:
        verdict = verdicts[team["team_name"]]
        team["verdict"] = verdict
        if verdict == "clinched":
            team["status"] = STATUS_CLINCHED
        elif verdict == "eliminated":
            team["status"] = STATUS_ELIMINATED
        # 'alive' keeps whatever in-contention wording the magic number produced
    return standings


def anything_decidable(state, budget=DEFAULT_NODE_BUDGET):
    """Could ANY team be clinched or eliminated yet?

    Cheap whole-request short circuit: early in a season nothing is decidable,
    and answering that costs far less than enumerating completions.
    """
    return any(
        status_of(state, t, budget=budget) != "alive" for t in range(state.num_teams)
    )
