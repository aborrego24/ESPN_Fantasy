import argparse
import json
import os
import sys

# Known-good leagues, kept as defaults because they are the ones actually used
# and their data is a known quantity. Override with --league-id / --year, or
# ESPN_LEAGUE_ID / ESPN_YEAR.
DEFAULT_LEAGUE_ID = 123564885  # Laminated Greenwood
ALTERNATE_LEAGUE_ID = 339875718  # lambda
DEFAULT_YEAR = 2024


def load_league_data(file_path):
    """Load the league data from the given JSON file."""
    with open(file_path, "r") as file:
        return json.load(file)


def sides_of(matchup):
    """Both teams in a matchup, or (None, None) on a bye.

    espn_api declares home_team/away_team as bare annotations and only assigns
    them when a team id matches, so a bye leaves the attribute unset entirely --
    the library guards its own __repr__ with hasattr for the same reason.
    Reading them directly raises AttributeError on an odd-sized league.
    """
    return getattr(matchup, "home_team", None), getattr(matchup, "away_team", None)


def played_weeks(league):
    """How many regular-season weeks have actually been scored."""
    weeks = league.settings.reg_season_count
    counts = [sum(1 for s in team.scores[:weeks] if s) for team in league.teams]
    return min(counts) if counts else 0


def record_through_week(team, weeks):
    """Recompute a team's record and points from its first `weeks` matchups.

    team.wins / team.losses / team.points_for are CURRENT totals, not as-of-week
    values. Reading them while asking for an earlier week silently mixes a
    finished season's 14-game record with games still listed as remaining, which
    then gets more wins added on top -- a 16-game season, and more teams
    "clinching" than there are seats.

    Walking the weekly scores instead makes any past week answerable correctly.
    A tie is a real outcome here: this league's matchupTieRule is NONE, so equal
    scores stand.
    """
    wins = losses = ties = 0
    points = 0.0
    for index in range(weeks):
        own = team.scores[index]
        against = team.schedule[index].scores[index]
        points += own
        if own > against:
            wins += 1
        elif own < against:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties, round(points, 2)


def build_payload(league, current_week):
    """Shape a League into the stage-1 payload.

    `current_week` is the number of weeks already played, so the next week to be
    decided is `current_week + 1`, and team.schedule[current_week] is its first
    unplayed matchup (schedule is 0-indexed by matchup period).

    Kept separate from argument handling so the ESPN-facing logic can be tested
    against a fake league with no network access.
    """
    weeks_in_season = league.settings.reg_season_count

    teams = []
    for team in league.teams:
        wins, losses, ties, points_for = record_through_week(team, current_week)
        teams.append(
            {
                "name": team.team_name,
                "record": {
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                },
                "points_for": points_for,
                "remaining_schedule": [
                    opponent.team_name
                    for opponent in team.schedule[current_week:weeks_in_season]
                ],
            }
        )

    # The scoreboard is asked for the week the caller named, not whatever week
    # the league happens to think is current -- on a finished season that clamps
    # to the final scoring period, which would describe a different week from
    # the standings above.
    next_week_matchups = []
    if current_week < weeks_in_season:
        for matchup in league.scoreboard(week=current_week + 1):
            home, away = sides_of(matchup)
            if home is None or away is None:
                continue  # bye week: no pair to enumerate
            next_week_matchups.append(
                {"team1": home.team_name, "team2": away.team_name}
            )

    return {
        "league_settings": {
            "num_teams": len(league.teams),
            "playoff_spots": league.settings.playoff_team_count,
            "weeks_in_season": weeks_in_season,
            "current_week": current_week,
            "tiebreaker": "points_for",
        },
        "teams": teams,
        "next_week_matchups": next_week_matchups,
    }


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="league_data.py",
        description="Emit the stage-1 payload for the scenario pipeline.",
    )
    parser.add_argument(
        "week",
        nargs="?",
        type=int,
        help="weeks already played; next week is the one being decided",
    )
    parser.add_argument(
        "--test",
        metavar="PATH",
        help="replay a saved payload instead of calling ESPN (needs no network)",
    )
    parser.add_argument(
        "--league-id",
        type=int,
        default=int(os.environ.get("ESPN_LEAGUE_ID", DEFAULT_LEAGUE_ID)),
        help=f"ESPN league id (default {DEFAULT_LEAGUE_ID})",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=int(os.environ.get("ESPN_YEAR", DEFAULT_YEAR)),
        help=f"season (default {DEFAULT_YEAR})",
    )
    return parser.parse_args(argv), parser


def main(argv=None):
    args, parser = parse_args(sys.argv[1:] if argv is None else argv)

    if args.test:
        print(json.dumps(load_league_data(args.test), indent=2))
        return 0

    if args.week is None:
        parser.error("give a week number, or --test <path_to_file.json>")

    # Imported here so --test mode works without espn_api installed
    from espn_api.football import League

    league = League(league_id=args.league_id, year=args.year)

    weeks_in_season = league.settings.reg_season_count
    if not 0 <= args.week <= weeks_in_season:
        parser.error(
            f"week must be between 0 and {weeks_in_season} for this league, got {args.week}"
        )

    scored = played_weeks(league)
    if args.week > scored:
        parser.error(
            f"only {scored} week(s) have been scored in {args.year}; "
            f"cannot build standings through week {args.week}"
        )

    print(json.dumps(build_payload(league, args.week), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
