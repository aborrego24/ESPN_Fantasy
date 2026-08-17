"""Two views of a season the standings cannot give you.

The standings answer "who won", which in a league where the schedule is random
is partly a question about luck. These two tables separate the two.

  ALL-PLAY RECORD -- in any week you played one opponent, but you also either
  out-scored or were out-scored by everyone else. Scoring that against the whole
  league every week gives a record that owes nothing to who the schedule handed
  you. A team can be 6-8 and have the second-best all-play record; that team was
  unlucky, not bad.

  SCHEDULE LUCK -- your record if you had played some other team's schedule,
  computed for every other team. The spread between the best and worst of those
  is how much the draw was worth to you. The diagonal is your real record, which
  makes the table read directly: anything above it is a schedule you would have
  preferred.

Both are computed from the weekly history stage 1 now emits, and neither has
anything to do with the clinch math -- they explain a season rather than predict
one, so they take no part in any verdict.

A tie is a real result here. That differs from the scenario engine, which does
not simulate future ties, but these tables report what already happened, and
this league's matchupTieRule is NONE, so equal scores stand.
"""


def _points_and_opponents(weekly_scores):
    """Split the payload into {team: [points]} and {team: [opponent]} lookups.

    Both are keyed by name, so a repeated name would drop a team's whole season
    and silently shrink the league. Stage 1 guarantees names are unique; refuse
    anything that arrives without that guarantee.
    """
    names = [entry["name"] for entry in weekly_scores]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(
            f"team names must be unique to compare seasons; repeated: {duplicates}"
        )

    points = {}
    opponents = {}
    for entry in weekly_scores:
        name = entry["name"]
        points[name] = [week["points"] for week in entry["weeks"]]
        opponents[name] = [week["opponent"] for week in entry["weeks"]]
    return points, opponents


def _weeks_available(points):
    """How many weeks every team has data for."""
    return min((len(scores) for scores in points.values()), default=0)


def _played(score):
    """Was this week actually scored?

    A zero is how an unscored week presents itself -- `played_weeks` in stage 1
    relies on the same reading. A genuine 0.0 in fantasy football would need an
    entire lineup to score nothing, so treating it as "no data" costs nothing and
    keeps an unplayed week from counting as a loss to the whole league.
    """
    return bool(score)


def _tally():
    return {"wins": 0, "losses": 0, "ties": 0}


def _record(mine, theirs, into):
    if mine > theirs:
        into["wins"] += 1
    elif mine < theirs:
        into["losses"] += 1
    else:
        into["ties"] += 1


def _summed(tallies):
    total = _tally()
    for tally in tallies:
        for key in total:
            total[key] += tally[key]
    return total


def all_play_records(weekly_scores):
    """Each team's record against the entire league, week by week.

    Returns a list of {"name", "weeks": [tally], "total": tally}, best total
    first, where a tally is {"wins", "losses", "ties"}. Ordering is by win
    percentage so leagues mid-season compare fairly against each other.
    """
    points, _ = _points_and_opponents(weekly_scores)
    weeks = _weeks_available(points)

    rows = []
    for name, scores in points.items():
        weekly = []
        for index in range(weeks):
            tally = _tally()
            if _played(scores[index]):
                for rival, rival_scores in points.items():
                    if rival == name or not _played(rival_scores[index]):
                        continue
                    _record(scores[index], rival_scores[index], tally)
            weekly.append(tally)
        rows.append({"name": name, "weeks": weekly, "total": _summed(weekly)})

    rows.sort(key=lambda row: (-win_pct(row["total"]), row["name"]))
    return rows


def weekly_finish(tally):
    """Where a week's score placed in the league, 1 being the highest.

    A weekly tally already counts the rivals a team out-scored and the rivals
    that out-scored it, so its place is the number above it plus one. Equal
    scores share a place, as they do in the standings. Returns None for a week
    the team did not score, which has no place to report.
    """
    if not (tally["wins"] + tally["losses"] + tally["ties"]):
        return None
    return tally["losses"] + 1


def win_pct(tally):
    """Ties count as half a win, the usual convention."""
    played = tally["wins"] + tally["losses"] + tally["ties"]
    if not played:
        return 0.0
    return (tally["wins"] + 0.5 * tally["ties"]) / played


def schedule_luck(weekly_scores):
    """Every team's record under every team's schedule.

    `rows[i]["against"][name]` is what team i would have finished with had it
    played `name`'s schedule. `rows[i]["against"][rows[i]["name"]]` is therefore
    its real record, and sits on the diagonal.

    One case needs deciding rather than assuming. In the week the schedule's
    owner played *you*, taking over that schedule means facing the owner itself,
    so your score is compared with theirs. The original implementation had no
    answer here and left a bare `TODO` as the body of an `elif`, which is why
    the file could not even be imported.

    A week the owner had a bye has no opponent to inherit, so it is skipped --
    which is why records in a row can differ in games played.
    """
    points, opponents = _points_and_opponents(weekly_scores)
    weeks = _weeks_available(points)
    names = list(points)

    rows = []
    for name in names:
        against = {}
        for owner in names:
            tally = _tally()
            for index in range(weeks):
                if not _played(points[name][index]):
                    continue
                opponent = opponents[owner][index]
                if opponent is None:
                    continue  # the owner had a bye; no game to inherit
                # Inheriting a schedule that includes a game against yourself
                # means playing its owner instead.
                if opponent == name:
                    opponent = owner
                if opponent not in points or not _played(points[opponent][index]):
                    continue
                _record(points[name][index], points[opponent][index], tally)
            against[owner] = tally
        rows.append({"name": name, "against": against})

    order = {row["name"]: -win_pct(row["against"][row["name"]]) for row in rows}
    rows.sort(key=lambda row: (order[row["name"]], row["name"]))
    return {"teams": [row["name"] for row in rows], "rows": rows}


def luck_spread(row):
    """Best and worst records available to one team across every schedule.

    The gap between them is what the draw was worth. Returned as
    (best_schedule, best_tally, worst_schedule, worst_tally).
    """
    ranked = sorted(
        row["against"].items(), key=lambda pair: (-win_pct(pair[1]), pair[0])
    )
    best_name, best = ranked[0]
    worst_name, worst = ranked[-1]
    return best_name, best, worst_name, worst
