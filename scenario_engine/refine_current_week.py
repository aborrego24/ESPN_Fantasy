import json
import sys

import margins
import playoff_math


def build_remaining_matchups(teams, remaining_weeks):
    """Pair up each remaining week from the per-team remaining_schedule lists.

    Stage 1 gives every team its own list of upcoming opponents; the exact
    engine needs them as weeks of matchups instead.
    """
    weeks = []
    for week_index in range(remaining_weeks):
        seen = set()
        week = []
        for team in teams:
            name = team["name"]
            schedule = team["remaining_schedule"]
            if name in seen or week_index >= len(schedule):
                continue
            opponent = schedule[week_index]
            # None is a bye: the slot is kept so the weeks stay aligned, but
            # there is no game to enumerate.
            if opponent is None or opponent in seen:
                continue
            seen.add(name)
            seen.add(opponent)
            week.append({"team1": name, "team2": opponent})
        weeks.append(week)
    return weeks


def divisions_in_order(standings, divisions):
    """The name-keyed division map as a list aligned to `standings`.

    The engine indexes teams by position, so the map has to be flattened in the
    standings' own order. Doing that at every point of use, rather than storing a
    list, is what stops a re-sort silently attaching a team to the wrong division.
    """
    if not divisions:
        return None
    return [divisions[team["team_name"]] for team in standings]


def calculate_stats(league_data, playoff_spots, num_weeks, remaining_weeks):
    """Sort the teams into standings order.

    Seeding is (wins, then total points), matching ESPN's
    playoffSeedingRule = TOTAL_POINTS_SCORED. The verdict is added afterwards by
    playoff_math.apply_verdicts, which is what decides anything.

    `playoff_spots`, `num_weeks` and `remaining_weeks` are unused now that the
    magic numbers are gone. They stay in the signature because both callers and
    the tests pass them positionally, and the ordering will need the playoff
    count again the moment per-seed verdicts arrive.
    """
    sorted_teams = sorted(
        league_data["teams"],
        key=lambda team: (
            -team["record"]["wins"],
            team["record"]["losses"],
            -team["points_for"],
        ),
    )
    standings = [
        {
            "team_name": team["name"],
            "wins": team["record"]["wins"],
            "losses": team["record"]["losses"],
            "points_for": team["points_for"],
        }
        for team in sorted_teams
    ]
    return order_by_seed(standings, league_data.get("divisions"))


def order_by_seed(standings, divisions):
    """Put the standings in seeding order, so the table agrees with the verdicts.

    Only reorders a divisional league. There the seeding is not the record order,
    and leaving the table sorted by record produced a self-contradicting report: a
    division winner shown fourth while holding a first-round bye, above a team
    shown third without one.

    A flat league is returned untouched, keeping its existing sort -- which breaks
    ties on losses before points, a shade finer than the engine's comparator, and
    not worth changing for leagues where it has always been right.
    """
    order = divisions_in_order(standings, divisions)
    if order is None:
        return standings
    return [
        standings[i]
        for i in playoff_math.seed_order(
            [t["wins"] for t in standings],
            [t["points_for"] for t in standings],
            order,
        )
    ]


if __name__ == "__main__":
    league_data = json.load(sys.stdin)

    playoff_spots = league_data["league_settings"]["playoff_spots"]
    # 0 when the league has no byes, or when the bracket order cannot be derived
    bye_spots = league_data["league_settings"].get("bye_spots", 0)
    num_weeks = league_data["league_settings"]["weeks_in_season"]
    remaining_weeks = num_weeks - league_data["league_settings"]["current_week"]

    metadata= [{
        "playoff_spots": playoff_spots,
        "bye_spots": bye_spots,
        "num_weeks": num_weeks,
        "remaining_weeks": remaining_weeks,
        "current_week": league_data["league_settings"]["current_week"]
             }]
    next_week_matchups = [
        league_data["next_week_matchups"]
    ]
    remaining_matchups = build_remaining_matchups(league_data["teams"], remaining_weeks)

    expanded_data = calculate_stats(league_data, playoff_spots, num_weeks, remaining_weeks)
    # A verdict resting on the tiebreaker is only true while the scoring holds,
    # so it is only reported as decided when the gap is bigger than any swing
    # this league has produced over the weeks that remain.
    envelope = margins.swing_envelope(remaining_weeks, margins.load_thresholds())
    divisions = league_data.get("divisions")
    expanded_data = playoff_math.apply_verdicts(
        expanded_data,
        remaining_matchups,
        playoff_spots,
        swing_envelope=envelope,
        bye_spots=bye_spots,
        divisions=divisions_in_order(expanded_data, divisions),
    )
    combined = {
        "league_data": metadata[0],
        "next_week_matchups": next_week_matchups[0],
        "remaining_matchups": remaining_matchups,
        "standings": expanded_data,
        # Passed straight through for the season-review tables in stage 5. Absent
        # from older saved payloads, so it stays optional the whole way down.
        "weekly_scores": league_data.get("weekly_scores", []),
        "abbreviations": league_data.get("abbreviations", {}),
        # Name-keyed, so it stays correct however the standings get re-sorted
        "divisions": league_data.get("divisions"),
    }
    print(json.dumps(combined, indent=2))



# Reads the stage-1 payload on stdin, e.g.:
#   python3 scenario_engine/league_data.py --test scenario_engine_tests/week13.json \
#     | python3 scenario_engine/refine_current_week.py
