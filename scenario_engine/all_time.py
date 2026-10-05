"""Ranking every team-season a league has ever played.

The unit is a **team-season**, not a team: "the best team of all time" is a claim
about one year's roster, and in this league the names do not even survive a year.
Franchise careers are ranked separately, keyed by owner (see `owner_rows`).

WHY NOT JUST POINTS OR JUST RECORD

Neither travels across seasons. One real league played 15 weeks with 9 teams in
2023 and 14 weeks with 10 in 2024, so season point totals are measuring different
things, and scoring inflation means even PPG is only meaningful against the teams
that faced the same rules. So every rate here is normalised **within its own
season** before any two seasons are compared.

THE THREE RATES

  STRENGTH -- all-play win%: the team's record against the entire league every
  week. Already a fraction, so it compares across seasons of any size or length
  without further work.

  RECORD -- actual win%. Kept alongside strength even though the two overlap,
  because the standings are what the league lived through: a team that went 12-2
  *was* 12-2, and ranking it as though it went 8-6 describes a season nobody
  remembers. The gap between record and strength is schedule luck, so carrying
  both credits a lucky team for its wins without crediting it as though it earned
  them all.

  SCORING -- PPG as a z-score against that season's league, where 0.5 is exactly
  average. Answers "how far above its own era did this team score", which the
  other two flatten: a team can out-score the league by 30 a week and still lose
  in the weeks it matters. Named for what it is; it was called "firepower" once,
  which said nothing about being relative to a season.

WHICH GAMES COUNT IS THE SCOPE'S DECISION

`record` follows the scope, so the displayed won-lost is the record for what is
being ranked: the regular season alone, the regular season plus the bracket, or
the bracket alone. One real team went 12-1 and then lost its first playoff game,
which is 12-1 under `regular` and 12-2 under `both`.

Strength and scoring stay on the **regular season** in every scope except
`playoffs`. All-play over playoff weeks would be meaningless -- only the surviving
teams are still playing, so most of the league has no score to compare against.

HARDWARE is added on top rather than blended in, because it is not a rate -- it
is a small number of one-off events, and a 14-week body of work should not be
outweighed by a single-elimination bracket. It is listed in its own column so any
ranking can be read with it and without it.

Every component is reported alongside the rating. A single opaque number nobody
can audit is not worth having, and the weights below are a judgement call that
should be easy to argue with.
"""

import statistics

import league_stats

# A judgement call, stated openly. Strength leads because it is the least noisy
# measure of how a team played; record carries real weight because the standings
# are what happened; scoring is the smallest share because it is already most of
# what strength measures, and is here to separate teams that strength ties.
WEIGHTS = {"strength": 0.45, "record": 0.30, "scoring": 0.25}

# Named weightings, so the common questions are one click rather than three drags.
# Each is a real question somebody asks of a list like this:
#
#   BALANCED   -- the documented default above.
#   MERIT      -- who actually played best, discounting the schedule they drew.
#   STANDINGS  -- who won, full stop; the league as it was lived.
#   SCOREBOARD -- who put up the points, whatever it bought them.
#
# Given as percentages because they are normalised by their sum anyway, so these
# are ratios and need not total 100.
PRESETS = (
    (
        "balanced",
        "Balanced",
        {"strength": 45, "record": 30, "scoring": 25},
        "The default. Leans on strength, but credits the standings and rewards a "
        "team that out-scored its era.",
    ),
    (
        "merit",
        "Merit",
        {"strength": 70, "record": 10, "scoring": 20},
        "Who actually played best. Nearly ignores the record, so the schedule a "
        "team drew stops flattering or punishing it.",
    ),
    (
        "standings",
        "Standings",
        {"strength": 10, "record": 80, "scoring": 10},
        "Who won, full stop. The league as it was lived, luck and all.",
    ),
    (
        "scoreboard",
        "Scoreboard",
        {"strength": 20, "record": 10, "scoring": 70},
        "Who put up the points, whatever it bought them.",
    ),
)
DEFAULT_PRESET = "balanced"

# Accolade points, added to the 0-100 base rather than blended into it. Ordered
# champion >> #1 seed > playoff berth, with the title by far the largest single
# award.
#
# 🔑 A RUN IS PAID PER PLAYOFF WIN, NOT PER PLACEMENT. Enumerating runner-up and
# final four separately produced a hole: across eight completed seasons of two real
# leagues the runner-up went 2-1 or 1-1 *every time*, so a team that won two games
# and lost the final scored the same as one that lost in round one. Bill James's
# Hall of Fame Monitor -- the same idea, points per honour -- credits a pennant
# winner who loses the World Series 5 against 6 for winning it, not 0. Paying per
# win gets that ordering for free, needs no rule per round, and scales to any
# bracket size, which matters because this league has run both five and six spots.
#
# A playoff win means one that kept the team alive. Consolation and fifth-place
# games are excluded upstream in `history_data.postseason`, including the ones
# played between two teams that both qualified -- see the Klorgon case there.
#
# Sizing: the title is worth roughly a tenth of a season's rating. Deliberately
# not more, because a championship is mostly luck here -- measured over those
# eight seasons the top seed won it twice, the average champion was the third
# seed, and two champions were the 7th and 10th best teams of their season by
# regular-season rating. The trophy is worth honouring; it is not evidence.
CHAMPION = 10.0
TOP_SEED = 3.0
DIVISION_WINNER = 2.0
PLAYOFF_BERTH = 1.5
PLAYOFF_WIN = 1.0

# The accolades won over the fourteen weeks rather than in the bracket. These are
# the only ones a regular-season view may show: qualifying, a division and the top
# seed are all earned by the record, while a title, a lost final and a run of
# playoff wins are bracket results with no business in a table that excludes the
# bracket.
REGULAR_ACCOLADES = ("Playoffs", "Division winner", "#1 overall seed")

# The three ways to read a season, and what each one measures.
#
#   REGULAR -- the regular season on its own, accolades excluded from the rating
#   and bracket accolades not even listed. The largest sample, and the only scope
#   where every team played the same number of games.
#
#   BOTH -- regular-season rates with accolades added on top. A team is judged on
#   the fourteen weeks it played and then credited for what it did with them.
#
#   PLAYOFFS -- the bracket only, and only the teams that reached it. The smallest
#   sample by far (one to three games), so it says more about a hot fortnight than
#   about a team; that is the point of looking at it separately.
SCOPES = ("regular", "both", "playoffs")
DEFAULT_SCOPE = "both"

# A z-score of +/-3 is the edge of the scale. Six sigma of spread covers every
# team-season measured with room to spare, and clamping means one freak season
# cannot compress everyone else into the middle.
Z_RANGE = 6.0


def _scaled_z(value, mean, sigma):
    """A z-score mapped onto 0-1, with 0.5 as the league average.

    Sigma is zero only if every team scored identically, which has never happened
    but would otherwise divide by zero; an exactly average league is 0.5 for
    everyone, which is the right answer.
    """
    if not sigma:
        return 0.5
    z = (value - mean) / sigma
    return min(1.0, max(0.0, 0.5 + z / Z_RANGE))


def scoped_record(team, scope):
    """(wins, losses, ties) for the games the scope is about.

    The displayed won-lost and the `record` rate come from the same call, so the
    table cannot show 12-1 while rating a 12-2. A real case: one team went 12-1 in
    the regular season and lost its first playoff game, which is 12-1 under
    `regular`, 12-2 under `both`, and 0-1 under `playoffs`.

    The playoff figures count only championship-path games -- byes, consolation and
    anything after elimination are dropped upstream in `history_data.postseason`.
    """
    regular = (team["wins"], team["losses"], team["ties"])
    playoff = (
        team.get("playoff_wins") or 0,
        team.get("playoff_losses") or 0,
        team.get("playoff_ties") or 0,
    )
    if scope == "regular":
        return regular
    if scope == "playoffs":
        return playoff
    return tuple(r + p for r, p in zip(regular, playoff))


def _win_pct(record):
    """Ties as half a win, matching league_stats and the standings."""
    wins, losses, ties = record
    played = wins + losses + ties
    if not played:
        return 0.0
    return (wins + 0.5 * ties) / played


def _weeks_scored(entry):
    """Weeks this team actually put up points.

    The denominator for PPG, and not the same as games played: in an odd-sized
    league a bye week scores points but settles no game, and dividing a 15-week
    points total by 14 games would inflate every team in the league that had one.
    """
    return sum(1 for week in entry["weeks"] if week["points"])


# Every accolade in the order a legend should list them. "1 playoff win" stands in
# for the whole family, which carries its own count.
ALL_ACCOLADES = (
    "Champion",
    "Runner-up",
    "1 playoff win",
    "Playoffs",
    "Division winner",
    "#1 overall seed",
)


def accolades_for(scope):
    """The accolades a scope can actually produce, in display order.

    One definition, so a legend cannot advertise a badge the table never prints --
    which it did: the playoff view dropped `Playoffs` from its rows and went on
    explaining it underneath.
    """
    if scope == "regular":
        return tuple(l for l in ALL_ACCOLADES if l in REGULAR_ACCOLADES)
    if scope == "playoffs":
        return tuple(l for l in ALL_ACCOLADES if l != "Playoffs")
    return ALL_ACCOLADES


def hardware(team, playoff_spots, scope=DEFAULT_SCOPE):
    """Accolade points and the labels that earned them, for one scope.

    Under `regular` the bracket did not happen: it scores nothing, and it is not
    listed either. Showing CHAMP beside a rating that deliberately ignores the
    championship invites the reader to assume it counted.

    `final_standing` is ESPN's rankCalculatedFinal, where 1 is the champion and 0
    means the season never finished. Only the title scores; a lost final is
    labelled and nothing below that, because the depth of a run is already paid
    per playoff win (see PLAYOFF_WIN) and a placement badge on top of it said the
    same thing twice.

    A berth is read from the seed rather than the final standing: the standing is
    a playoff *result*, and a team can finish below teams that never qualified.
    """
    points = 0.0
    labels = []
    standing = team.get("final_standing") or 0

    if standing == 1:
        points += CHAMPION
        labels.append("Champion")
    elif standing == 2:
        labels.append("Runner-up")

    # Byes, consolation games and anything played after elimination are already
    # excluded upstream, so every win counted here kept the team alive.
    wins = team.get("playoff_wins") or 0
    if wins:
        points += PLAYOFF_WIN * wins
        labels.append(f"{wins} playoff win" + ("s" if wins != 1 else ""))

    # A berth says nothing in the playoff scope: every team in that table is there
    # because it qualified, so the badge would be on every row and the points a
    # constant that moves no ranking.
    seed = team.get("seed") or 0
    if seed and playoff_spots and seed <= playoff_spots and scope != "playoffs":
        points += PLAYOFF_BERTH
        labels.append("Playoffs")

    # The top seed supersedes a division: it is the better claim, and the team
    # holding it always won its division anyway, so showing both would be saying
    # the same thing twice and paying for it twice.
    if seed == 1:
        points += TOP_SEED
        labels.append("#1 overall seed")
    elif team.get("division_winner"):
        points += DIVISION_WINNER
        labels.append("Division winner")

    if scope == "regular":
        return 0.0, [label for label in labels if label in REGULAR_ACCOLADES]
    return round(points, 2), labels


def _rates(entries, teams, points_key, scope):
    """Strength, record and scoring for one slice of a season.

    `entries` is a weekly_scores-shaped list, so the all-play computation is the
    same one the single-season report shows and the two cannot disagree. PPG
    divides by weeks **scored**, which is not the count of games: a bye scores
    without settling anything, and dividing a 15-week total by 14 games would
    inflate every team in an odd-sized league.
    """
    all_play = {
        row["name"]: league_stats.win_pct(row["total"])
        for row in league_stats.all_play_records(entries)
    }
    scored = {entry["name"]: _weeks_scored(entry) for entry in entries}
    present = {entry["name"] for entry in entries}

    ppg = {}
    for team in teams:
        name = team["name"]
        if name not in present:
            continue
        weeks = scored.get(name, 0)
        ppg[name] = team[points_key] / weeks if weeks else 0.0

    values = [v for v in ppg.values() if v]
    mean = statistics.fmean(values) if values else 0.0
    sigma = statistics.pstdev(values) if len(values) > 1 else 0.0

    rates = {}
    for team in teams:
        name = team["name"]
        if name not in present:
            continue
        record = scoped_record(team, scope)
        rates[name] = {
            "strength": all_play.get(name, 0.0),
            "record": _win_pct(record),
            "scoring": _scaled_z(ppg[name], mean, sigma),
            "won_lost": record,
            "ppg": ppg[name],
            "ppg_mean": mean,
        }
    return rates


def season_rows(season, scope=DEFAULT_SCOPE):
    """Every eligible team in one season, with its three normalised rates.

    In the playoff scope the population is the bracket, not the league: a team
    that did not qualify has no playoff season to rank, so it is absent rather
    than present with zeroes.
    """
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}; expected one of {SCOPES}")

    teams = season["teams"]
    if scope == "playoffs":
        entries = season.get("playoff_weeks") or []
        rates = _rates(entries, teams, "playoff_points_for", scope)
    else:
        entries = season.get("weekly_scores") or []
        rates = _rates(entries, teams, "points_for", scope)

    rows = []
    for team in teams:
        name = team["name"]
        if name not in rates:
            continue
        rate = rates[name]
        accolade_points, labels = hardware(team, season.get("playoff_spots"), scope)

        base = 100.0 * (
            WEIGHTS["strength"] * rate["strength"]
            + WEIGHTS["record"] * rate["record"]
            + WEIGHTS["scoring"] * rate["scoring"]
        )
        wins, losses, ties = rate["won_lost"]
        rows.append(
            {
                "year": season["year"],
                "name": name,
                # Every manager of this team-season. A history fetched before
                # co-management was handled carries a single "owner" instead.
                "managers": team.get("managers")
                or ([team["owner"]] if team.get("owner") else []),
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "points_for": team["playoff_points_for"]
                if scope == "playoffs"
                else team["points_for"],
                "ppg": round(rate["ppg"], 2),
                "ppg_mean": round(rate["ppg_mean"], 2),
                "strength": round(rate["strength"], 4),
                "record": round(rate["record"], 4),
                "scoring": round(rate["scoring"], 4),
                "base": round(base, 2),
                "hardware": accolade_points,
                "accolades": labels,
                "rating": round(base + accolade_points, 2),
                "final_standing": team.get("final_standing") or 0,
                "seed": team.get("seed") or 0,
                "made_playoffs": bool(team.get("made_playoffs")),
                "playoff_games": team.get("playoff_games", 0),
                "num_teams": season["num_teams"],
                "weeks_in_season": season["weeks_in_season"],
            }
        )
    return rows


def ranked_seasons(history):
    """The seasons eligible for the all-time list, and the years left out.

    Returns `(seasons, excluded_years)`. **A season still being played is
    excluded, not discounted.** Three weeks of results is not a small sample of a
    season, it is a different quantity: measured on a real league, a 3-0 start
    four weeks into 2026 came out second best all time, because a short sample
    sits further from its league's mean on every rate at once, and mid-season
    ESPN already reports a live playoff seed that hands out a berth nobody has
    earned. The excluded years are reported so the omission is visible rather
    than looking like missing data.
    """
    seasons = history.get("seasons") or []
    ranked = [s for s in seasons if s.get("complete")]
    excluded = sorted(s["year"] for s in seasons if not s.get("complete"))
    return ranked, excluded


def team_rows(history, scope=DEFAULT_SCOPE):
    """Every eligible team-season in the league's history, best rating first.

    Ties break on the components in weight order, then on year and name, so the
    ordering is total and a rerun cannot shuffle equal rows.
    """
    seasons, _ = ranked_seasons(history)
    rows = []
    for season in seasons:
        rows.extend(season_rows(season, scope))
    rows.sort(
        key=lambda r: (
            -r["rating"],
            -r["strength"],
            -r["record"],
            -r["scoring"],
            -r["year"],
            r["name"],
        )
    )
    for place, row in enumerate(rows, 1):
        row["rank"] = place
    return rows


def career_keys(row):
    """Every manager this team-season counts towards.

    One definition, used by both the grouping here and the renderer that joins a
    manager row back to its seasons -- two spellings of "whose season is this"
    would silently split or merge careers in the live table only.

    A co-managed season counts for **each** manager, so the pair who shared a
    team both get credit for what it did. That double-counts a shared title in
    the league's totals, which is the intended reading: both of them won it.

    ESPN returns no owner at all for an abandoned team; those are keyed by team
    name rather than all collapsing into one phantom manager.
    """
    return row["managers"] or [f"__team__{row['name']}"]


def owner_rows(rows):
    """One row per manager, best average rating first.

    Averaged rather than summed: a manager who played five seasons should not
    outrank a better one who played three. Seasons played is shown beside it,
    because an average over two years is a different claim from an average over
    five.

    """
    groups = {}
    for row in rows:
        for key in career_keys(row):
            groups.setdefault(key, []).append(row)

    owners = []
    for key, seasons in groups.items():
        ratings = [s["rating"] for s in seasons]
        best = max(seasons, key=lambda s: s["rating"])
        owners.append(
            {
                # The grouping key travels with the row so the renderer can join
                # a manager back to their seasons and recompute the average live.
                "owner_id": key,
                # The key *is* the manager's name, except for an abandoned team
                # keyed by its own name.
                "owner": seasons[0]["name"] if key.startswith("__team__") else key,
                "seasons": len(seasons),
                "avg_rating": round(statistics.fmean(ratings), 2),
                "best_rating": best["rating"],
                "best_year": best["year"],
                "best_team": best["name"],
                "titles": sum(1 for s in seasons if s["final_standing"] == 1),
                "berths": sum(1 for s in seasons if "Playoffs" in s["accolades"]),
                "wins": sum(s["wins"] for s in seasons),
                "losses": sum(s["losses"] for s in seasons),
                "ties": sum(s["ties"] for s in seasons),
                "avg_strength": round(
                    statistics.fmean([s["strength"] for s in seasons]), 4
                ),
                "years": sorted(s["year"] for s in seasons),
            }
        )

    owners.sort(key=lambda o: (-o["avg_rating"], -o["titles"], o["owner"]))
    for place, owner in enumerate(owners, 1):
        owner["rank"] = place
    return owners


def summarise(history, rows):
    """The one-line facts about the whole history, for the section header.

    `skipped` is what ESPN refused (almost always an older season with no
    cookies); `excluded` is what was read but is not over yet. Two different
    reasons for a missing year, and a reader who is told neither will assume the
    league did not exist.
    """
    seasons, excluded = ranked_seasons(history)
    years = sorted(s["year"] for s in seasons)
    return {
        "seasons": len(seasons),
        "first_year": years[0] if years else None,
        "last_year": years[-1] if years else None,
        "team_seasons": len(rows),
        "skipped": history.get("skipped") or [],
        "excluded": excluded,
    }
