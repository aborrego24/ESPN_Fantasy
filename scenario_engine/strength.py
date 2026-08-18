"""Strength of schedule and strength of record, from actual results.

Two questions the standings cannot answer on their own:

  STRENGTH OF SCHEDULE (SOS) -- how hard were, and will be, the teams you play?
  A team's opponents are scored two ways, and a weight slides between them:

    - by POINTS: the average points-per-game of the teams you face. This is the
      fantasy-native signal. College football's SOS is built on win-loss only,
      because it bans margin of victory to stop teams running up the score; a
      fantasy league has no such incentive and no such worry, and a team's points
      are the truest measure of how good it is, so points are used directly.
    - by RECORD: the average win percentage of the teams you face. This is the
      classic college-football component. When an opponent's record is measured
      relative to *you*, your mutual games are removed from it (the RPI
      self-exclusion rule), so your own result never inflates your own schedule.

  Only the first hop is used. College football's formula adds a second hop --
  opponents' opponents, weighted a third -- but this league is close to a round
  robin, so by mid-season everyone has played everyone and the second hop
  collapses to "the whole league" for every team: measured signal, none.

  STRENGTH OF RECORD (SOR) -- given the schedule you played, how good is your
  record? A benchmark team is dropped into your exact schedule -- your opponents,
  in the weeks you played them -- and its expected win percentage is computed from
  how often it would have out-scored each. SOR is your real win percentage minus
  the benchmark's: positive means you did better than the benchmark would have
  against your slate, which a hard schedule makes easier to achieve and an easy
  one harder. The benchmark is a pool of weekly scores -- the whole league for an
  "average team", or one strong team's weeks for an "elite" one.

Everything here reads only completed weeks (for records and points) and the
remaining pairings (for the forward half of SOS). Like the season-review tables,
it takes no part in any verdict -- it explains a schedule, it does not decide one.
"""

import league_stats


def _series(weekly_scores):
    """{team: [points]} and {team: [opponent]}, keyed by name.

    Reuses the season-review parser, which refuses a duplicated name rather than
    silently merging two teams' seasons.
    """
    return league_stats._points_and_opponents(weekly_scores)


def _played(score):
    return league_stats._played(score)


def _team_ppg(points):
    """Average points per scored week, per team."""
    ppg = {}
    for name, scores in points.items():
        played = [s for s in scores if _played(s)]
        ppg[name] = sum(played) / len(played) if played else 0.0
    return ppg


def _games(points, opponents):
    """Per team, the list of (opponent, own_score, opp_score) actually played."""
    games = {}
    for name, scores in points.items():
        played = []
        for index, own in enumerate(scores):
            if not _played(own):
                continue
            opponent = opponents[name][index]
            if opponent is None or opponent not in points:
                continue
            against = points[opponent][index]
            if not _played(against):
                continue
            played.append((opponent, own, against))
        games[name] = played
    return games


def _tally(results):
    tally = {"wins": 0, "losses": 0, "ties": 0}
    for own, against in results:
        if own > against:
            tally["wins"] += 1
        elif own < against:
            tally["losses"] += 1
        else:
            tally["ties"] += 1
    return tally


def _win_pct(games_list):
    return league_stats.win_pct(_tally([(o, a) for _, o, a in games_list]))


def _win_pct_excluding(games_list, excluded):
    """A team's win percentage with every game against `excluded` dropped.

    The RPI self-exclusion rule: when this opponent's record is being used to
    measure *your* schedule, the games the two of you played must not count, or
    your own results would be feeding back into your own strength of schedule.
    """
    kept = [(own, against) for opp, own, against in games_list if opp != excluded]
    return league_stats.win_pct(_tally(kept)) if kept else 0.0


def _remaining_opponents(remaining_matchups):
    """{team: [opponent, ...]} from the weeks of upcoming pairings."""
    upcoming = {}
    for week in remaining_matchups or []:
        for game in week:
            a, b = game["team1"], game["team2"]
            upcoming.setdefault(a, []).append(b)
            upcoming.setdefault(b, []).append(a)
    return upcoming


def _mean(values):
    return sum(values) / len(values) if values else None


def _normalize(values):
    """Map a {name: number} to {name: 0..1} across the league.

    Min-max, so the hardest schedule reads 1 and the easiest 0. All-equal (a very
    early or a degenerate league) maps everyone to 0.5 rather than dividing by
    zero.
    """
    numbers = [v for v in values.values() if v is not None]
    if not numbers:
        return {name: None for name in values}
    low, high = min(numbers), max(numbers)
    if high == low:
        return {name: (0.5 if v is not None else None) for name, v in values.items()}
    return {
        name: (None if v is None else (v - low) / (high - low))
        for name, v in values.items()
    }


def strength_table(weekly_scores, remaining_matchups=None, blend=0.5, benchmark="average"):
    """Per-team SOS and SOR, sorted hardest schedule first.

    `blend` slides SOS from pure record (0.0) to pure points (1.0). `benchmark`
    is "average" (the whole league's weekly scores) or "elite" (the single
    highest-scoring team's weeks). Returns a list of row dicts; empty if no week
    has been played yet, so a preseason payload degrades to nothing here.
    """
    points, opponents = _series(weekly_scores)
    if not any(_played(s) for scores in points.values() for s in scores):
        return []

    ppg = _team_ppg(points)
    games = _games(points, opponents)
    upcoming = _remaining_opponents(remaining_matchups)

    # Opponent strength, averaged over who each team plays (with multiplicity).
    played_faced = {name: [opp for opp, _, _ in games[name]] for name in points}
    all_faced = {
        name: played_faced[name] + upcoming.get(name, []) for name in points
    }

    def opp_points(faced):
        return _mean([ppg[o] for o in faced if o in ppg])

    def opp_record(name, faced):
        return _mean([_win_pct_excluding(games[o], name) for o in faced if o in games])

    opp_ppg = {name: opp_points(all_faced[name]) for name in points}
    opp_wp = {name: opp_record(name, all_faced[name]) for name in points}
    sos_played = {name: opp_points(played_faced[name]) for name in points}
    sos_remaining = {
        name: opp_points(upcoming.get(name, [])) for name in points
    }

    # The blended index needs the two components on one scale, so each is
    # normalised across the league before mixing.
    pts_norm = _normalize(opp_ppg)
    rec_norm = _normalize(opp_wp)

    def index(name):
        p, r = pts_norm[name], rec_norm[name]
        if p is None or r is None:
            return None
        return blend * p + (1 - blend) * r

    reference = _benchmark_scores(points, ppg, benchmark)

    rows = []
    for name in points:
        actual = _win_pct(games[name])
        expected = _benchmark_win_pct(games[name], reference)
        rows.append(
            {
                "name": name,
                "opp_ppg": opp_ppg[name],
                "opp_win_pct": opp_wp[name],
                "sos_played": sos_played[name],
                "sos_remaining": sos_remaining[name],
                "sos": index(name),
                "actual_win_pct": actual,
                "benchmark_win_pct": expected,
                "sor": None if expected is None else actual - expected,
            }
        )
    rows.sort(key=lambda row: (-(row["sos"] or 0.0), row["name"]))
    return rows


def _benchmark_scores(points, ppg, benchmark):
    """The pool of weekly scores that stands in for the benchmark team."""
    if benchmark == "elite":
        best = max(ppg, key=lambda name: ppg[name])
        return [s for s in points[best] if _played(s)]
    # "average": the whole league's weekly scores
    return [s for scores in points.values() for s in scores if _played(s)]


def _benchmark_win_pct(games_list, reference):
    """The benchmark's win percentage against this team's actual schedule.

    For each game the team played, the benchmark faces the same opponent's score
    from that week; its chance of winning is the share of its own weekly scores
    that beat it, counting a tie as half. Averaged over the schedule.
    """
    if not games_list or not reference:
        return None
    per_game = []
    for _, _, opp_score in games_list:
        wins = sum(1 for s in reference if s > opp_score)
        ties = sum(1 for s in reference if s == opp_score)
        per_game.append((wins + 0.5 * ties) / len(reference))
    return sum(per_game) / len(per_game)
