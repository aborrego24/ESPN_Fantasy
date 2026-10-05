"""Stage 0: every season of a league, not just the one being decided.

The rest of the pipeline answers a question about *this* season. This module
answers "what has this league ever done", which needs one fetch per season and
so is kept off the live path entirely -- `tools/fetch_history.py` writes the
result to a file, and the renderer reads that file. Nothing here is on the
critical path of a clinch verdict.

Two facts about ESPN's history, both measured rather than assumed:

  ONLY THE LAST TWO SEASONS ARE PUBLIC. The current year and the one before it
  answer unauthenticated; every season before that returns 401 even for a league
  whose current year is wide open. So a history covering more than two years
  **requires `ESPN_S2` / `SWID`**, and that is not a private-league concern -- it
  applies to public leagues too. `accessible_years` reports what actually
  answered rather than what the league claims, so a run without cookies degrades
  to two seasons instead of failing.

  A LEAGUE CHANGES SHAPE YEAR TO YEAR. Measured on one real league: 9 teams over
  15 regular-season weeks in 2023, 10 teams over 14 in 2024 and 2025; two
  divisions in 2024, one in 2025. Raw season totals are therefore **not**
  comparable across years, which is what `all_time` normalises for.

`status.previousSeasons` lists the seasons ESPN knows about, but it over-reports
what is readable -- it names seasons the endpoint then refuses. It is used only
as the list of candidates to try.
"""

import league_data


def candidate_years(league):
    """Every season this league might answer for, newest first.

    `previousSeasons` is filtered by espn_api to years before the one fetched, so
    the fetched year is added back. Newest first because that is the order the
    report shows and the order a partial run should keep: cookies missing means
    losing the oldest seasons, not a random subset.
    """
    return sorted(set(league.previousSeasons) | {league.year}, reverse=True)


# Managers are read the same way for a history as for the live season, so the one
# definition lives in the platform-facing stage. A season is credited to everyone
# who managed it; two distinct people sharing a name would merge, which has not
# happened in any measured league and is the lesser error.
owner_names = league_data.owner_names


def weeks_with_play(league, limit):
    """How far into the season anyone has scored, capped at `limit`.

    Deliberately **not** `league_data.played_weeks`, which is the count of weeks
    every team scored in and is the right question for stage 1. It is the wrong
    one here: in an odd-sized league a bye scores 0, so a team that byes once can
    never reach the season length, and a finished 9-team / 15-week season reports
    14. Two of its teams then look mid-season and the whole year is dropped from
    the rankings.

    Taking the furthest week anyone scored in separates the two cases the count
    conflates -- one team idle for a week, versus the whole league not having
    played yet.
    """
    last = 0
    for team in league.teams:
        for index in range(min(limit, len(team.scores))):
            if team.scores[index]:
                last = max(last, index + 1)
    return last


def postseason(league, names, weeks_in_season, playoff_ids):
    """Each playoff team's bracket games, in the `weekly_scores` shape.

    **ESPN does not label the bracket.** Every post-season matchup in this league
    comes back with `playoffTierType: NONE`, so the rounds cannot be read off the
    schedule and a semifinal is indistinguishable from a fifth-place game. What
    *is* reliable is who qualified -- measured across three seasons, the teams
    seeded inside the playoff count play only each other after the regular season,
    and the teams outside it play only each other. So a game is a bracket game
    exactly when both sides qualified, and the consolation ladder drops out
    without needing a tier.

    **A bye is not a contest, and is excluded from every playoff rate.** Top seeds
    skip round one, and a team knocked out simply stops playing -- both show up as
    a matchup against itself. ESPN is not even consistent about the score: a real
    league has a bye week carrying 165 points (the lineup scored anyway) and
    another carrying 0. Counting either would credit a week nobody contested, so
    the points are dropped to 0, which is how `league_stats` already spells "no
    data for this week".

    **A GAME AFTER ELIMINATION IS NOT PLAYOFF FOOTBALL EITHER.** Two qualifying
    teams that both lost in round one are put back out against each other for a
    fifth-place ladder, and those games look exactly like bracket games -- both
    sides qualified, both scored. Measured: 2025 Klorgon lost in round one and then
    won twice on that ladder, which read as a 1-2 bracket record and earned credit
    for a playoff win it never had. The championship path is a single-elimination
    run, so a team's playoff season **ends at its first loss** and everything after
    it is consolation, whoever the opponent was.

    Only qualifying teams appear, so the all-play comparison is between the teams
    that were actually still alive in the bracket.
    """
    # Pass one: every contested game, before knowing who survived it. A result
    # needs both sides' scores, so elimination cannot be decided in the same sweep.
    raw = {}
    for team in league.teams:
        if team.team_id not in playoff_ids:
            continue
        weeks = []
        for index in range(weeks_in_season, len(team.scores)):
            opponent = league_data.opponent_in_week(team, index)
            played = opponent is not None and opponent.team_id in playoff_ids
            weeks.append(
                {
                    "week": index + 1,
                    "points": team.scores[index] if played else 0.0,
                    "opponent": names[opponent.team_id] if played else None,
                }
            )
        raw[names[team.team_id]] = weeks

    scored = {
        name: {week["week"]: week["points"] for week in weeks}
        for name, weeks in raw.items()
    }

    # Pass two: walk each team's weeks in order and stop it at its first defeat.
    # The losing game itself stays -- it was a championship game, and the team was
    # alive when it played it. A tie leaves a team alive, since ESPN breaks
    # playoff ties by its own rule rather than eliminating both sides.
    rows = []
    for name, weeks in raw.items():
        alive = True
        kept = []
        for week in weeks:
            opponent = week["opponent"]
            if not alive or opponent is None or not week["points"]:
                kept.append({**week, "points": 0.0, "opponent": None})
                continue
            kept.append(week)
            if week["points"] < scored[opponent][week["week"]]:
                alive = False
        rows.append({"name": name, "weeks": kept})
    return rows


def _playoff_record(entry, points_by_name):
    """A team's won-lost-tied and points across its championship-path games.

    Games after elimination are already blanked by `postseason`, so a team's
    losses here can only ever be the one that knocked it out -- a champion ends
    unbeaten and everyone else ends 0-1 behind however far they got.
    """
    wins = losses = ties = 0
    points = 0.0
    for week in entry["weeks"]:
        if not week["points"] or week["opponent"] is None:
            continue
        points += week["points"]
        against = points_by_name[week["opponent"]][week["week"]]
        if week["points"] > against:
            wins += 1
        elif week["points"] < against:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties, round(points, 2)


def _division_winners(league, division_names):
    """The team ids that won a division, or an empty set if there were none.

    **Read off ESPN's own seeding rather than re-derived.** ESPN seeds division
    winners ahead of every non-winner, so the winner of a division is simply its
    lowest-seeded team -- which is ESPN's answer to the tiebreaker, not this
    repo's guess at it. Measured across the three divisional seasons in two
    leagues, every division winner came out seed 1 or 2, exactly as that rule
    predicts.

    Empty for a single-division league, which is most of them: `division_names_of`
    returns {} unless there is more than one, so a league whose one division is
    called "League Standings" does not hand everybody a division title.
    """
    if len(division_names) <= 1:
        return set()
    best = {}
    for team in league.teams:
        seed = team.standing or 0
        if not seed:
            continue
        current = best.get(team.division_id)
        if current is None or seed < current[1]:
            best[team.division_id] = (team.team_id, seed)
    return {team_id for team_id, _ in best.values()}


def season_payload(league):
    """One season, shaped for the all-time tables.

    Scores are sliced to the **regular season** for every rate: `team.scores`
    runs on into the playoffs, where the teams that qualified play extra games
    and the teams that did not play consolation ones. Mixing those in would
    reward a deep run twice and score the two groups over different denominators.

    The playoff result is still carried, as `final_standing` -- that is the right
    source for hardware, and the only one, since the bracket itself is not
    published. So rates come from the regular season and accolades from the final
    standing, which is the separation the rating relies on.

    Records stop at the weeks actually **played**, not at the length of the
    season. ESPN pre-creates every remaining matchup with both sides on 0.0, and
    `record_through_week` reads equal scores as a tie -- so asking a 3-week-old
    season for 14 weeks returns 3-0-11, and a 3-0 team comes out at a .607 win
    percentage. Stage 1 sidesteps this by refusing a week that has not been
    played; a history has to handle it, because the newest season is normally
    in progress.
    """
    weeks_in_season = league.settings.reg_season_count
    weeks = weeks_with_play(league, weeks_in_season)
    names = league_data.unique_names(league)
    spots = league.settings.playoff_team_count

    # Who qualified. Read from the seed rather than the final standing, which is a
    # playoff *result* and can rank a qualifier below a team that never got in.
    playoff_ids = {
        team.team_id
        for team in league.teams
        if team.standing and spots and team.standing <= spots
    }
    division_names = league_data.division_names_of(league)
    division_winners = _division_winners(league, division_names)
    playoff_weeks = postseason(league, names, weeks_in_season, playoff_ids)
    # {name: {week: points}} so a bracket game can be scored from both sides.
    points_by_name = {
        entry["name"]: {week["week"]: week["points"] for week in entry["weeks"]}
        for entry in playoff_weeks
    }
    playoff_by_name = {entry["name"]: entry for entry in playoff_weeks}

    teams = []
    for team in league.teams:
        wins, losses, ties, points_for = league_data.record_through_week(team, weeks)
        managers = owner_names(team)
        name = names[team.team_id]
        entry = playoff_by_name.get(name)
        po_wins, po_losses, po_ties, po_points = (
            _playoff_record(entry, points_by_name) if entry else (0, 0, 0, 0.0)
        )
        teams.append(
            {
                "name": name,
                # Every manager of this team, so a career can credit each of them.
                # There is deliberately no "primary": see owner_names.
                "managers": managers,
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "points_for": points_for,
                # rankCalculatedFinal: 1 is the champion. 0 means ESPN never
                # settled it, which is what an unfinished season looks like.
                "final_standing": team.final_standing,
                "seed": team.standing,
                "division": division_names.get(getattr(team, "division_id", 0), ""),
                "division_winner": team.team_id in division_winners,
                "made_playoffs": team.team_id in playoff_ids,
                "playoff_wins": po_wins,
                "playoff_losses": po_losses,
                "playoff_ties": po_ties,
                "playoff_points_for": po_points,
                # Byes and consolation games are already excluded, so this is the
                # count of games actually contested in the bracket -- which is
                # itself a measure of how far the team went.
                "playoff_games": po_wins + po_losses + po_ties,
            }
        )

    return {
        "year": league.year,
        "name": league.settings.name,
        "num_teams": len(league.teams),
        "weeks_in_season": weeks_in_season,
        "weeks_played": weeks,
        # Whether this season is over, which decides whether it can be ranked
        # against finished ones at all. `final_standing` is the load-bearing half:
        # ESPN leaves rankCalculatedFinal at 0 until the bracket settles, so a
        # season in progress shows every team on 0 -- while its live `seed` claims
        # a playoff berth nobody has earned yet. The week count is a second
        # opinion, not the test, for the bye reason in `weeks_with_play`.
        "complete": bool(teams)
        and all(team["final_standing"] for team in teams)
        and weeks >= weeks_in_season,
        "playoff_spots": league.settings.playoff_team_count,
        # {id: name} when the season ran divisions, {} otherwise. The league has
        # run both, so this cannot be a property of the league as a whole.
        "division_names": division_names,
        "teams": teams,
        # The same shape stage 1 emits, so league_stats.all_play_records can be
        # reused unchanged on any season in history.
        "weekly_scores": [
            {
                "name": names[team.team_id],
                "weeks": league_data.weekly_history(team, weeks, names),
            }
            for team in league.teams
        ],
        # The bracket, in the same shape and so readable by the same all-play
        # code. Qualifying teams only, byes and consolation games already dropped.
        "playoff_weeks": playoff_weeks,
    }


def build_history(league_id, espn_s2=None, swid=None, years=None, on_season=None):
    """Fetch every accessible season of a league.

    Returns `{"league_id", "seasons": [...], "skipped": [...]}` with seasons
    newest first. A season that refuses to answer is recorded in `skipped` with
    the reason rather than raising: two readable seasons are a usable history,
    and a hard failure on the oldest year would throw away the newer ones.

    `on_season` is called with each year as it is fetched, so a CLI can report
    progress -- each season is several HTTP requests and a decade is slow.
    """
    from espn_api.football import League
    from espn_api.requests.espn_requests import ESPNAccessDenied

    def fetch(year):
        return League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)

    if years is None:
        # The newest season is the one that tells us which others exist, so it is
        # fetched first and then reused rather than requested twice.
        newest = fetch(_latest_year(league_id, espn_s2, swid))
        years = candidate_years(newest)
        fetched = {newest.year: newest}
    else:
        years = sorted(set(years), reverse=True)
        fetched = {}

    seasons, skipped = [], []
    for year in years:
        if on_season:
            on_season(year)
        try:
            league = fetched.get(year) or fetch(year)
            seasons.append(season_payload(league))
        except ESPNAccessDenied:
            skipped.append(
                {
                    "year": year,
                    "reason": "access denied"
                    + ("" if (espn_s2 and swid) else " (no ESPN_S2 / SWID set)"),
                }
            )
        except Exception as error:  # noqa: BLE001 - one bad season must not stop the rest
            skipped.append({"year": year, "reason": f"{type(error).__name__}: {error}"})

    return {"league_id": league_id, "seasons": seasons, "skipped": skipped}


def _latest_year(league_id, espn_s2, swid):
    """The most recent season the league answers for.

    ESPN rolls a league over to the next year before any of it is played, and it
    is not knowable from here which side of that rollover today falls on, so the
    current calendar year is tried and the previous one accepted as the answer.
    """
    from datetime import date

    from espn_api.football import League

    this_year = date.today().year
    for year in (this_year, this_year - 1):
        try:
            League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
            return year
        except Exception:
            continue
    # Nothing answered; let the caller's own fetch raise the real error.
    return this_year
