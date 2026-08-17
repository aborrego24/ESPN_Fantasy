import argparse
import json
import os
import sys
from collections import Counter

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


class DuplicateTeamNames(Exception):
    """Raised rather than letting two teams silently become one."""


def unique_names(league):
    """A display name per team id, guaranteed unique within the league.

    The whole pipeline treats the team name as the team's identity: the standings
    key on it, the exact engine builds a name-to-index map from it, a permutation
    names its winner by it, and the scenario map buckets by it. **ESPN does not
    require names to be unique**, and when two collide the results are not subtle:

      - a matchup vanishes from the remaining schedule, because the pairing loop
        tracks which teams are already placed by name, so the second team of a
        colliding pair is skipped and its opponent is left unpaired -- the engine
        then decides verdicts over an incomplete season;
      - the two lookups disagree with each other. `state_from_standings` builds a
        dict, so a repeated name resolves to the *last* team, while
        `LeagueState.index_of` uses `list.index` and resolves it to the *first*.

    Threading ids through all five stages would fix the internals and still print
    two identical names in the report, which is its own kind of wrong. So identity
    is repaired here instead, at the single point where data enters, and the name
    stays the label everywhere downstream.

    Only colliding names are touched, so the ordinary case is untouched. The tag
    prefers ESPN's abbreviation because it means something to a reader, and falls
    back to the team id; both come from ESPN and are stable, so a team gets the
    same label on every run and for every week.
    """
    counts = Counter(team.team_name for team in league.teams)

    chosen = {}
    for team in league.teams:
        name = team.team_name
        if counts[name] > 1:
            abbrev = getattr(team, "team_abbrev", None)
            chosen[team.team_id] = f"{name} ({abbrev or team.team_id})"
        else:
            chosen[team.team_id] = name

    # Two teams can share an abbreviation as easily as a name, so the tagged
    # result is not unique by construction. Fall back to the id, which is.
    tagged = Counter(chosen.values())
    for team in league.teams:
        if tagged[chosen[team.team_id]] > 1:
            chosen[team.team_id] = f"{team.team_name} (id {team.team_id})"

    if len(set(chosen.values())) != len(chosen):
        # Only reachable if a team is literally named what a tag produced. Better
        # to refuse than to carry on and merge two teams.
        raise DuplicateTeamNames(
            f"cannot make team names unique: {sorted(chosen.values())}"
        )
    return chosen


def bye_spots(league):
    """How many top seeds skip the first playoff round, or 0 if unknowable.

    **ESPN does not publish the bracket shape.** There is no bye field anywhere in
    `league.settings`; `playoff_matchup_period_length` only says how long a round
    is. So it is derived: a single-elimination bracket seeded to the next power of
    two leaves `2**ceil(log2(N)) - N` teams idle in round one.

    Checked against both completed seasons rather than assumed. In 2025, with six
    spots, seeds 1 and 2 played no week-15 game and the formula gives 2. In 2024,
    with five, three seeds sat out and the formula gives 3.

    Returns 0 when the seeding itself cannot be trusted to be record-then-points.
    That same 2024 check paired the model's third and fifth seeds in round one
    rather than the fourth and fifth a pure record-then-points bracket implies, so
    in a divisional season ESPN evidently seeds division winners first. The
    playoff *field* is still right -- the backtest confirms it both seasons -- but
    the *order* within it is not ours to claim, and a bye is a claim about order.
    """
    spots = league.settings.playoff_team_count
    if spots < 2:
        return 0
    if len(getattr(league.settings, "division_map", None) or {1: None}) > 1:
        return 0
    bracket = 1 << (spots - 1).bit_length()  # next power of two at or above spots
    return bracket - spots


def opponent_in_week(team, index):
    """The team this team played in week `index`, or None if it played nobody.

    Guarded rather than indexed directly. An odd-sized league leaves a week with
    no game, and the team's schedule is then shorter than the season, so
    `team.schedule[index]` raises IndexError -- which took stage 1 down entirely
    before it could report anything.
    """
    opponent = team.schedule[index] if index < len(team.schedule) else None
    # Compared by identity, not by name. Two distinct teams are allowed to share
    # a name, and comparing names made each of them look like the other's own
    # self-matchup -- so both weeks were recorded as byes, and two teams sat at
    # 0-0 having scored a full slate of points.
    if opponent is team:
        return None
    return opponent


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
        points += own
        opponent = opponent_in_week(team, index)
        if opponent is None:
            # A bye scores points but settles nothing, so it counts toward the
            # seeding tiebreaker without becoming a win, a loss or a tie.
            continue
        against = opponent.scores[index]
        if own > against:
            wins += 1
        elif own < against:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties, round(points, 2)


def weekly_history(team, weeks, names):
    """Per-week score and opponent for the first `weeks` matchups.

    Reference data for the season-review tables, which need to compare any two
    teams' scores in the same week -- something the aggregate points_for cannot
    answer. It takes no part in any verdict.

    A bye is reported as an opponent of None, so that a week with no game is not
    inherited as one when another team takes over this schedule.
    """
    history = []
    for index in range(weeks):
        opponent = opponent_in_week(team, index)
        history.append(
            {
                "week": index + 1,
                "points": team.scores[index],
                "opponent": None if opponent is None else names[opponent.team_id],
            }
        )
    return history


def build_payload(league, current_week):
    """Shape a League into the stage-1 payload.

    `current_week` is the number of weeks already played, so the next week to be
    decided is `current_week + 1`, and team.schedule[current_week] is its first
    unplayed matchup (schedule is 0-indexed by matchup period).

    Kept separate from argument handling so the ESPN-facing logic can be tested
    against a fake league with no network access.
    """
    weeks_in_season = league.settings.reg_season_count
    # One mapping, used for every place a team is named below. Building it once
    # is what makes the four views of the schedule agree with each other.
    names = unique_names(league)

    teams = []
    for team in league.teams:
        wins, losses, ties, points_for = record_through_week(team, current_week)
        teams.append(
            {
                "name": names[team.team_id],
                "record": {
                    "wins": wins,
                    "losses": losses,
                    "ties": ties,
                },
                "points_for": points_for,
                # A bye keeps its slot as None rather than being dropped: stage 2
                # pairs teams up by position in this list, so removing an entry
                # would silently shift every later week forward one.
                "remaining_schedule": [
                    None if opponent is None else names[opponent.team_id]
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
                {"team1": names[home.team_id], "team2": names[away.team_id]}
            )

    return {
        "league_settings": {
            "num_teams": len(league.teams),
            "playoff_spots": league.settings.playoff_team_count,
            "bye_spots": bye_spots(league),
            "weeks_in_season": weeks_in_season,
            "current_week": current_week,
            "tiebreaker": "points_for",
        },
        "teams": teams,
        "next_week_matchups": next_week_matchups,
        # Kept top-level rather than on each team: the later stages rebuild the
        # team dicts from a fixed field list, and stage 4 deep-copies the
        # standings once per permutation, so per-team history would be both
        # dropped and copied thousands of times.
        "weekly_scores": [
            {
                "name": names[team.team_id],
                "weeks": weekly_history(team, current_week, names),
            }
            for team in league.teams
        ],
        # ESPN's own short code per team, for the report to label a row with.
        # Keyed by the unique name because that is what the later stages carry;
        # only teams that actually have one appear.
        "abbreviations": {
            names[team.team_id]: team.team_abbrev
            for team in league.teams
            if getattr(team, "team_abbrev", None)
        },
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
