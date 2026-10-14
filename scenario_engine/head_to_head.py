"""Manager-against-manager records, and the career figures behind a manager page.

Everything here comes out of the history the all-time tables already fetch:
`weekly_scores` carries each week's opponent and `playoff_weeks` carries the
bracket, so a manager page costs no extra ESPN round trip.

Three things decide the shape of all of it:

**The opponent is a team name, so the join has to happen inside a season.** Names
are unique within one season and nowhere else -- "Team T" in 2022 and "Team T" in
2026 need not be the same person -- so a name is resolved to managers per season
and never across the league as a whole.

**Managers are the identity, not teams.** Teams get renamed, sold and
co-managed; the same person can appear under two ESPN accounts. `career_keys` is
the one definition of whose season a team-season is, shared with the all-time
careers so the two cannot disagree. A co-managed team credits **each** of its
managers with the result, which is also what the careers do: both of them played
that game.

**ESPN does not label the bracket.** Every post-season matchup in this league
returns `playoffTierType: NONE`, so a game can be known to be a playoff game but
never known to be a semifinal. Nothing here reports a round.
"""
import statistics

import all_time
import league_stats

# A game decided by less than this is a coin flip, and a record in them says
# something a win-loss record does not: whether the close ones went your way.
CLOSE_GAME = 10.0

# Before a head-to-head record is worth calling anyone's nemesis. Two meetings
# can only ever read 2-0, 1-1 or 0-2, none of which is evidence of anything.
MIN_MEETINGS = 3

REGULAR = "regular"
PLAYOFFS = "playoffs"


def _played(score):
    """One reading of "was this week scored", shared with league_stats: an
    unscored week comes back as 0.0, and a real 0.0 would need a whole lineup to
    score nothing. Counting one would invent a result nobody played."""
    return league_stats._played(score)


def _tally():
    return {"wins": 0, "losses": 0, "ties": 0}


def _add(tally, own, opp):
    if own > opp:
        tally["wins"] += 1
    elif own < opp:
        tally["losses"] += 1
    else:
        tally["ties"] += 1


def _expected_wins(tally, games):
    """The wins an all-play record comes to over `games` real games.

    A tie counts half, as it does everywhere else a win percentage is taken.
    """
    played = tally["wins"] + tally["losses"] + tally["ties"]
    if not played or not games:
        return None
    return round(games * (tally["wins"] + 0.5 * tally["ties"]) / played, 1)


def _season_games(season, kind):
    """Every contested game in one season, once each.

    Yields (week, home, away, home_points, away_points) where "home" and "away"
    are only an order, not a venue. Each game is reached from both teams'
    schedules, so it is emitted the first time and skipped the second.
    """
    key = "playoff_weeks" if kind == PLAYOFFS else "weekly_scores"
    entries = season.get(key) or []
    points = {
        entry["name"]: {week["week"]: week["points"] for week in entry["weeks"]}
        for entry in entries
    }
    seen = set()
    for entry in entries:
        name = entry["name"]
        for week in entry["weeks"]:
            opponent = week["opponent"]
            # A bye has no opponent; ESPN spells a playoff bye as a team against
            # itself, and `postseason` blanks a consolation game the same way.
            if not opponent or opponent == name or opponent not in points:
                continue
            pair = (week["week"], *sorted((name, opponent)))
            if pair in seen:
                continue
            opponent_points = points[opponent].get(week["week"])
            if not _played(week["points"]) or not _played(opponent_points):
                continue
            seen.add(pair)
            yield week["week"], name, opponent, week["points"], opponent_points


def manager_games(history):
    """Every game every manager played, keyed by manager, in time order.

    One entry per manager per game, so a co-managed team puts the same game in
    both managers' lists. Completed seasons only -- the same population the
    all-time tables rank, so a career cannot mean two different things depending
    on which tab it is read from.
    """
    seasons, _ = all_time.ranked_seasons(history)
    by_manager = {}
    for season in seasons:
        year = season["year"]
        teams = {team["name"]: team for team in season["teams"]}
        managers = {name: all_time.career_keys(team) for name, team in teams.items()}
        for kind in (REGULAR, PLAYOFFS):
            for week, home, away, home_points, away_points in _season_games(season, kind):
                for own_name, own_points, foe_name, foe_points in (
                    (home, home_points, away, away_points),
                    (away, away_points, home, home_points),
                ):
                    foe = teams.get(foe_name, {})
                    game = {
                        "year": year,
                        "week": week,
                        "kind": kind,
                        "team": own_name,
                        "points": own_points,
                        "opponent_team": foe_name,
                        "opponent_points": foe_points,
                        # Every manager on the other side, so one game can count
                        # against each of a co-managed pair.
                        "opponents": managers.get(foe_name, []),
                        "opponent_made_playoffs": bool(foe.get("made_playoffs")),
                    }
                    for manager in managers.get(own_name, []):
                        by_manager.setdefault(manager, []).append(game)
    for games in by_manager.values():
        games.sort(key=lambda g: (g["year"], g["kind"] == PLAYOFFS, g["week"]))
    return by_manager


def _streak(games, won):
    """The longest run of wins (or of losses) across a whole career.

    Deliberately not reset between seasons: carrying a streak into next year is
    the version anyone actually argues about. A tie breaks a streak without
    starting one of the other kind.
    """
    best = run = 0
    for game in games:
        own, opp = game["points"], game["opponent_points"]
        hit = own > opp if won else own < opp
        run = run + 1 if hit else 0
        best = max(best, run)
    return best


def _expected_and_ranks(seasons):
    """Per (year, team): the all-play record, the points-for rank, and the weeks
    the team was the league's top scorer.

    All-play is what the record would be if every team played the whole league
    every week, so the gap between it and the real record is what the schedule
    was worth. Computed per season by the same code the season report uses.
    """
    expected, ranks, top_weeks = {}, {}, {}
    for season in seasons:
        year = season["year"]
        weekly = season.get("weekly_scores") or []
        for row in league_stats.all_play_records(weekly):
            expected[(year, row["name"])] = row["total"]
        # Points-for rank within the season, so "scored 2nd, finished 6th" can be
        # said at all.
        ordered = sorted(season["teams"], key=lambda t: -t["points_for"])
        for position, team in enumerate(ordered, 1):
            ranks[(year, team["name"])] = position
        # The week's high score, counted per team. Only teams with a game that
        # week are eligible: a bye carries a real score, and crowning it would
        # make a week nobody contested somebody's best.
        scores = {}
        for entry in weekly:
            for week in entry["weeks"]:
                if _played(week["points"]) and week["opponent"]:
                    scores.setdefault(week["week"], []).append((week["points"], entry["name"]))
        for week, pairs in scores.items():
            best = max(points for points, _ in pairs)
            for points, name in pairs:
                if points == best:
                    top_weeks[(year, name)] = top_weeks.get((year, name), 0) + 1
    return expected, ranks, top_weeks


def _profile(manager, games, team_seasons, expected, ranks, top_weeks):
    """One manager's career, as the page reads it top to bottom."""
    regular = [g for g in games if g["kind"] == REGULAR]
    playoffs = [g for g in games if g["kind"] == PLAYOFFS]

    def side(subset):
        tally = _tally()
        for game in subset:
            _add(tally, game["points"], game["opponent_points"])
        points = [g["points"] for g in subset]
        against = [g["opponent_points"] for g in subset]
        return {
            **tally,
            "games": len(subset),
            "points_for": round(sum(points), 2),
            "points_against": round(sum(against), 2),
            "ppg": round(statistics.fmean(points), 2) if points else None,
            "papg": round(statistics.fmean(against), 2) if against else None,
        }

    close, versus_playoff_teams = _tally(), _tally()
    for game in regular:
        margin = game["points"] - game["opponent_points"]
        if abs(margin) < CLOSE_GAME:
            _add(close, game["points"], game["opponent_points"])
        if game["opponent_made_playoffs"]:
            _add(versus_playoff_teams, game["points"], game["opponent_points"])

    wins = [g["points"] - g["opponent_points"] for g in regular if g["points"] > g["opponent_points"]]
    losses = [g["opponent_points"] - g["points"] for g in regular if g["points"] < g["opponent_points"]]

    # The career all-play record: what the seasons would have produced against
    # the whole league every week.
    expect = _tally()
    rows, co_managers = [], {}
    # By year only: a team dict is not orderable, and a manager has one team a season.
    for year, team in sorted(team_seasons, key=lambda pair: pair[0]):
        entry = expected.get((year, team["name"]))
        if entry:
            for part in expect:
                expect[part] += entry[part]
        for other in team.get("managers") or []:
            if other != manager:
                co_managers.setdefault(other, []).append(year)
        played = team["wins"] + team["losses"] + team["ties"]
        rows.append({
            "year": year,
            "team": team["name"],
            "wins": team["wins"],
            "losses": team["losses"],
            "ties": team["ties"],
            "points_for": team["points_for"],
            "ppg": round(team["points_for"] / played, 2) if played else None,
            "scoring_rank": ranks.get((year, team["name"])),
            # rankCalculatedFinal: 1 is the champion, 0 an unsettled season.
            "finish": team["final_standing"],
            "seed": team["seed"],
            "made_playoffs": bool(team["made_playoffs"]),
            "division_winner": bool(team["division_winner"]),
            "playoff_wins": team["playoff_wins"],
        })

    points = [g["points"] for g in regular]

    def moment(game):
        """A single score worth naming, with when it happened. `games` is in time
        order, so a tied best or worst reports the first time they managed it."""
        if game is None:
            return None
        return {"points": game["points"], "year": game["year"], "week": game["week"]}

    return {
        "manager": manager,
        "seasons": len(rows),
        "years": [row["year"] for row in rows],
        "regular": side(regular),
        "playoffs": side(playoffs),
        "accolades": {
            "championships": sum(1 for r in rows if r["finish"] == 1),
            "berths": sum(1 for r in rows if r["made_playoffs"]),
            "division_titles": sum(1 for r in rows if r["division_winner"]),
            "top_seeds": sum(1 for r in rows if r["seed"] == 1),
            "playoff_wins": sum(r["playoff_wins"] for r in rows),
        },
        # All-play, as the tally and as the wins it comes to over the games
        # actually played. The second is the number a reader wants -- "you are
        # 8-6, you earned 5.9" -- and deriving it here keeps one definition of
        # what the schedule was worth.
        "expected": expect,
        "expected_wins": _expected_wins(expect, len(regular)),
        "close": close,
        "vs_playoff_teams": versus_playoff_teams,
        "scoring": {
            "ppg": round(statistics.fmean(points), 2) if points else None,
            # Population deviation: these are all the games played, not a sample
            # of them. Two managers on the same PPG can be wildly different.
            "stdev": round(statistics.pstdev(points), 2) if len(points) > 1 else None,
            "high": moment(max(regular, key=lambda g: g["points"], default=None)),
            "low": moment(min(regular, key=lambda g: g["points"], default=None)),
        },
        "margins": {
            "avg_win": round(statistics.fmean(wins), 2) if wins else None,
            "avg_loss": round(statistics.fmean(losses), 2) if losses else None,
        },
        "streaks": {"win": _streak(games, True), "loss": _streak(games, False)},
        "top_scorer_weeks": sum(top_weeks.get((year, t["name"]), 0) for year, t in team_seasons),
        "co_managers": [
            {"manager": name, "years": years} for name, years in sorted(co_managers.items())
        ],
        "season_rows": rows,
    }


def pairings(by_manager):
    """Every pair of managers who have met, once each.

    Stored from `a`'s side only; the other direction is the same numbers
    inverted, and shipping both would invite the two halves to disagree.
    """
    pairs = {}
    for manager, games in by_manager.items():
        for game in games:
            for foe in game["opponents"]:
                if foe == manager:
                    continue  # nobody plays themselves; a co-managed pair never faces itself
                key = tuple(sorted((manager, foe)))
                entry = pairs.setdefault(key, {
                    "a": key[0], "b": key[1],
                    REGULAR: {**_tally(), "points_for": 0.0, "points_against": 0.0},
                    PLAYOFFS: {**_tally(), "points_for": 0.0, "points_against": 0.0},
                    "meetings": [],
                })
                # Record once per game, from a's side.
                if manager != key[0]:
                    continue
                side = entry[game["kind"]]
                _add(side, game["points"], game["opponent_points"])
                side["points_for"] += game["points"]
                side["points_against"] += game["opponent_points"]
                entry["meetings"].append({
                    "year": game["year"], "week": game["week"], "kind": game["kind"],
                    "points": game["points"], "opponent_points": game["opponent_points"],
                    "team": game["team"], "opponent_team": game["opponent_team"],
                })
    for entry in pairs.values():
        for kind in (REGULAR, PLAYOFFS):
            entry[kind]["points_for"] = round(entry[kind]["points_for"], 2)
            entry[kind]["points_against"] = round(entry[kind]["points_against"], 2)
        entry["meetings"].sort(key=lambda m: (m["year"], m["kind"] == PLAYOFFS, m["week"]))
    return [pairs[key] for key in sorted(pairs)]


def web_payload(history):
    """Everything a manager page needs, as plain JSON.

    Aggregated here rather than shipping the raw weekly scores for a renderer to
    re-derive: the figures are a few KB where the scores are tens of them, and
    the all-time careers already set the precedent that this math has one home.
    """
    seasons, _ = all_time.ranked_seasons(history)
    expected, ranks, top_weeks = _expected_and_ranks(seasons)

    # Which team-seasons belong to each manager, by the same rule as the careers.
    seasons_for = {}
    for season in seasons:
        for team in season["teams"]:
            for manager in all_time.career_keys(team):
                seasons_for.setdefault(manager, []).append((season["year"], team))

    by_manager = manager_games(history)
    managers = [
        _profile(manager, by_manager.get(manager, []), rows, expected, ranks, top_weeks)
        for manager, rows in sorted(seasons_for.items())
    ]
    return {
        "managers": managers,
        "pairings": pairings(by_manager),
        "close_game": CLOSE_GAME,
        "min_meetings": MIN_MEETINGS,
    }
