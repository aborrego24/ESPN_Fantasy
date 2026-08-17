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
   branches collapse. **With divisions this is only nearly true** -- a division
   winner is seeded above every non-winner whatever its record -- so the bound
   there allows one extra promotion per division.

Seeding follows ESPN's playoffSeedingRule = TOTAL_POINTS_SCORED: order by wins,
then by total points scored. In a league with divisions, **every division winner
is seeded ahead of every team that did not win one**, each group ordered by that
same rule; see `seed_order`. Points are treated as fixed at their current values
(see `points`), which is a modelling choice, not a fact -- callers that care
should consult the margin helpers below.

Both of the search's early exits depend on the number of teams above the searched
team never falling as games are decided. That holds under divisional seeding too,
because the team's own record is frozen and a team losing a division title is
replaced above by whoever took it; `tests/test_divisions.py` property-tests it
rather than trusting the argument.
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

    def __init__(self, names, wins, losses, points, games, playoff_spots, divisions=None):
        self.names = list(names)
        self.wins = list(wins)
        self.losses = list(losses)
        self.points = list(points)
        self.games = list(games)
        self.playoff_spots = playoff_spots
        # One division id per team, or None for a league without divisions. Only
        # two or more distinct ids change anything.
        self.divisions = list(divisions) if divisions else None

    @property
    def is_divisional(self):
        return self.divisions is not None and len(set(self.divisions)) > 1

    @property
    def num_divisions(self):
        return len(set(self.divisions)) if self.divisions else 1

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
            self.names, wins, losses, self.points, games, self.playoff_spots,
            self.divisions,
        )


def beats(a, b, wins, points):
    """True if team a outranks team b under (wins, then total points)."""
    if wins[a] != wins[b]:
        return wins[a] > wins[b]
    return points[a] > points[b]


def seed_order(wins, points, divisions=None):
    """Team indices in seeding order, best seed first.

    Without divisions this is just (wins, then total points). **With divisions,
    every division winner is seeded ahead of every team that did not win one**,
    winners ordered among themselves by the same rule and non-winners likewise.

    That is not a guess. In the two-division 2024 season it reproduces both the
    real set of first-round byes and the real round-one pairing, where a plain
    record ordering does neither: an 8-6 division winner was seeded above a 9-5
    wildcard.
    """
    count = len(wins)
    rank = lambda team: (-wins[team], -points[team])

    if divisions is None or len(set(divisions)) < 2:
        return sorted(range(count), key=rank)

    winners = {
        min((t for t in range(count) if divisions[t] == division), key=rank)
        for division in set(divisions)
    }
    return sorted(winners, key=rank) + sorted(
        (t for t in range(count) if t not in winners), key=rank
    )


def strictly_above(team, wins, points, num_teams, divisions=None):
    """How many teams finish ahead of `team` in the seed order.

    The pairwise comparator is kept for the divisionless case: it is what the
    engine has always used, it is O(n) rather than O(n log n), and every existing
    verification rests on it. Divisions need the whole order, because whether one
    team outranks another depends on who won a division -- which is a fact about
    the league, not about the pair.
    """
    if divisions is None or len(set(divisions)) < 2:
        return sum(
            1 for u in range(num_teams) if u != team and beats(u, team, wins, points)
        )
    return seed_order(wins, points, divisions).index(team)


def makes_playoffs(team, wins, points, num_teams, playoff_spots, divisions=None):
    return strictly_above(team, wins, points, num_teams, divisions) < playoff_spots


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
    divisions = state.divisions

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

        # Both exits below rely on this count never falling as the remaining games
        # are decided, which holds because `team`'s own record is frozen at an
        # extreme and every other record only improves. That is still true with
        # divisions: if the team does not win its division the count is
        # (divisions) + (better non-winners), the first term fixed and the second
        # only growing; and a team losing its own division title can only push it
        # further down. Checked over 20,000 random divisional leagues.
        above_now = strictly_above(team, wins, points, n, divisions)
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
            # could_still_pass only knows about records, and a team can finish
            # above this one by winning its division on a WORSE record -- exactly
            # how an 8-6 team was seeded above a 9-5 team in 2024. At most one
            # team per division is promoted that way, so allowing for one each
            # keeps the bound an over-estimate, which is what makes it safe.
            if divisions is not None:
                reachable += state.num_divisions
            if reachable < spots:
                return False

        if pos == len(open_games):
            return makes_playoffs(team, wins, points, n, spots, divisions) == want_in

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
            team,
            state.wins,
            state.points,
            state.num_teams,
            state.playoff_spots,
            state.divisions,
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


STATUS_BYE = "Clinched a first-round bye"
STATUS_CLINCHED = "Clinched Playoff Spot"
STATUS_ELIMINATED = "Eliminated"
STATUS_ALIVE = "In contention"


def state_from_standings(standings, remaining_matchups, playoff_spots, divisions=None):
    """Build a LeagueState from the pipeline's JSON shapes.

    `remaining_matchups` is a list of weeks, each a list of
    {"team1": ..., "team2": ...}.
    """
    names = [t["team_name"] for t in standings]
    # Identity is the name here, so a repeated one is not recoverable: this dict
    # would resolve it to the LAST team while index_of, which uses list.index,
    # resolves it to the FIRST -- two lookups of one name giving two teams.
    # Stage 1 guarantees uniqueness; anything reaching here without that
    # guarantee is refused rather than quietly answered wrong.
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(
            f"team names must be unique to decide anything; repeated: {duplicates}"
        )
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
        divisions,
    )


def with_seats(state, seats):
    """The same league, asked about a different number of seats.

    Every question the engine answers is "does this team finish in the top
    `playoff_spots`", and the threshold is already a field rather than a
    constant. So "does it finish in the top 2", which is what a first-round bye
    means, is the identical search over a state that says 2 -- the counterexample
    hunt, the dominance argument, the bounds pruning and the tiebreak probes all
    carry over untouched.
    """
    return LeagueState(
        state.names, state.wins, state.losses, state.points, state.games, seats,
        state.divisions,
    )


def points_margins(state, team, contested=None):
    """Points gaps to every rival still in the race you could finish level with.

    Two filters, both needed to keep this useful. A tiebreak only matters against
    a team whose achievable win range overlaps yours -- records matching today is
    the wrong test. And it only matters against a team still contesting a seat:
    listing gaps to teams already clinched or eliminated is noise, since they
    cannot take the seat from you either way.

    The win-range filter is **dropped in a divisional league**, where its premise
    fails: a division winner is seeded above every non-winner whatever its record,
    so a team you can never finish level with on wins can still finish above you.
    Listing a few extra rivals is the safe direction to be wrong in.

    Positive means `team` is ahead. Closest race first.
    """
    my_low = state.wins[team]
    my_high = my_low + state.games_left_for(team)
    comparable_by_record = not state.is_divisional

    margins = []
    for rival in range(state.num_teams):
        if rival == team:
            continue
        if contested is not None and rival not in contested:
            continue
        low = state.wins[rival]
        high = low + state.games_left_for(rival)
        if comparable_by_record and (high < my_low or low > my_high):
            continue  # the ranges cannot meet
        margins.append(
            (state.names[rival], round(state.points[team] - state.points[rival], 2))
        )

    margins.sort(key=lambda pair: abs(pair[1]))
    return margins


def bye_verdict(state, team, bye_spots, swing_envelope=None, budget=DEFAULT_NODE_BUDGET):
    """Has `team` locked up one of the `bye_spots` first-round byes?

    The same question as clinching a playoff seat, asked of a smaller number of
    seats, so it is the same search over `with_seats`. The tiebreak is held to the
    same standard too: a bye resting on a points gap the scoring could still close
    is not a bye, it is a lead.

    Returns 'clinched', 'eliminated' or 'alive'.
    """
    seats = with_seats(state, bye_spots)
    verdict = status_of(seats, team, budget=budget)
    if verdict == "clinched" and swing_envelope is not None:
        dependency = clinch_dependency(seats, team, budget=budget)
        if dependency and dependency[1] <= swing_envelope:
            return "alive"
    return verdict


def apply_verdicts(
    standings,
    remaining_matchups,
    playoff_spots,
    swing_envelope=None,
    budget=DEFAULT_NODE_BUDGET,
    bye_spots=0,
    divisions=None,
):
    """Set each team's status from the exact full-season verdict, in place.

    Also records, per decided team, whether the verdict rests on the total-points
    tiebreaker, and **downgrades it to 'alive' when it does and the gap could
    plausibly close**.

    That downgrade is the difference between a verdict that is right and one that
    merely sounds right. Verdicts freeze total points at today's values, but
    points keep accruing, so a "clinch" that depends on holding a 30-point lead
    is not a clinch -- it is a lead. Backtesting against real results caught
    exactly this: a team was declared clinched with a 30-point cushion and lost
    the seat on the final week's scoring.

    `swing_envelope` is the largest points swing considered plausible over the
    weeks remaining, normally the largest ever observed in this league. Pass
    None to trust frozen points, which is only safe when nothing is left to
    play.

    This is the only place a verdict is decided. The magic numbers that used to
    run alongside it answered "can this one rival pass me", which is a different
    question from "do I finish in a playoff seat", and no renderer ever read
    them; they have been removed rather than kept as a second opinion.

    `divisions` is one division id per team, in standings order. Given two or more,
    seeding puts every division winner ahead of every team that did not win one,
    which is what ESPN does and what a plain record ordering gets wrong.

    `bye_spots` asks the same question of a smaller number of seats, for leagues
    where the top seeds skip the first playoff round. It is reported separately in
    `bye` and folded into the readable `status`; `verdict` deliberately stays a
    three-way playoff answer, because a team with a bye has also clinched a
    playoff spot, and widening `verdict` would make every existing
    `== "clinched"` test silently miss them.
    """
    state = state_from_standings(
        standings, remaining_matchups, playoff_spots, divisions
    )
    verdicts = classify(state, budget=budget)

    settled = {}
    for index, team in enumerate(standings):
        verdict = verdicts[team["team_name"]]
        team["tiebreak"] = None

        dependency = None
        if verdict == "clinched":
            dependency = clinch_dependency(state, index, budget=budget)
        elif verdict == "eliminated":
            dependency = elimination_dependency(state, index, budget=budget)

        if dependency:
            rival, gap = dependency
            team["tiebreak"] = {"rival": rival, "gap": gap}
            if swing_envelope is not None and gap <= swing_envelope:
                # Decided only if the scoring holds, and it plausibly might not.
                verdict = "alive"

        settled[index] = verdict
        team["verdict"] = verdict

        # Asked of every team, not just the ones already through. Skipping the
        # rest and calling them 'alive' was a shortcut that produced wrong data:
        # a team eliminated from the playoffs is certainly out of bye contention,
        # and one still alive for a place can already be out of bye contention.
        team["bye"] = (
            bye_verdict(
                state, index, bye_spots, swing_envelope=swing_envelope, budget=budget
            )
            if bye_spots
            else None
        )

        # Derived from the verdict, every time, so the readable form cannot
        # disagree with the decision. A second writer of this field once left a
        # downgraded team saying "Clinched Playoff Spot", and two places believed
        # the text over the verdict.
        team["status"] = (
            STATUS_BYE
            if team["bye"] == "clinched"
            else {
                "clinched": STATUS_CLINCHED,
                "eliminated": STATUS_ELIMINATED,
                "alive": STATUS_ALIVE,
            }[verdict]
        )

    # Margins need the FINAL verdicts, including any downgrades, so they are
    # filled in only once every team is settled.
    contested = {i for i, v in settled.items() if v == "alive"}
    for index, team in enumerate(standings):
        team["margins"] = (
            points_margins(state, index, contested=contested)
            if settled[index] == "alive"
            else []
        )
    return standings


POINTS_EPSILON = 0.01  # fantasy scores carry at most two decimals


def _with_points_override(state, team, value):
    points = list(state.points)
    points[team] = value
    return LeagueState(
        state.names, state.wins, state.losses, points, state.games,
        state.playoff_spots, state.divisions,
    )


def clinch_dependency(state, team, budget=DEFAULT_NODE_BUDGET):
    """Which rival overtaking on total points would cost `team` its clinch.

    Verdicts freeze total points at today's values, so a clinch that rests on
    the tiebreaker is really "clinched *if* the scoring holds". This finds the
    nearest rival that would break it, and by how much it must catch up.

    Probes cumulatively: at a candidate gap, every rival within that gap is
    lifted past the team, not just one. It can take more than one rival
    overtaking to actually cost a seat -- with two seats and three teams tied on
    wins, the leader only drops out when *both* of the others pass it -- and
    probing one rival at a time would find no dependency and report a bare
    "clinched", which is exactly the overclaim being avoided.

    The gap returned is the largest a rival must close among those that had to
    move, i.e. the binding constraint: some rival has to make up at least this
    much. Returns (rival_name, points_gap), or None if the clinch does not
    depend on the tiebreaker at all.
    """
    behind = sorted(
        (state.points[team] - state.points[u], u)
        for u in range(state.num_teams)
        if u != team and state.points[u] < state.points[team]
    )

    for gap, binding in behind:
        points = list(state.points)
        for other_gap, u in behind:
            if other_gap <= gap:
                points[u] = state.points[team] + POINTS_EPSILON
        probe = LeagueState(
            state.names,
            state.wins,
            state.losses,
            points,
            state.games,
            state.playoff_spots,
            state.divisions,
        )
        if status_of(probe, team, budget=budget) != "clinched":
            return state.names[binding], round(gap, 2)
    return None


def elimination_dependency(state, team, budget=DEFAULT_NODE_BUDGET):
    """Which rival `team` would have to overtake on points to still have a shot.

    The mirror of clinch_dependency: an elimination that rests on the
    tiebreaker is "eliminated unless the scoring changes".
    """
    rivals = [
        u
        for u in range(state.num_teams)
        if u != team and state.points[u] > state.points[team]
    ]
    rivals.sort(key=lambda u: state.points[u] - state.points[team])

    for u in rivals:
        gap = state.points[u] - state.points[team]
        probe = _with_points_override(state, team, state.points[u] + POINTS_EPSILON)
        if status_of(probe, team, budget=budget) != "eliminated":
            return state.names[u], round(gap, 2)
    return None


