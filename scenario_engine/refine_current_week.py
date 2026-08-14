import json
import sys

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
            if opponent in seen:
                continue
            seen.add(name)
            seen.add(opponent)
            week.append({"team1": name, "team2": opponent})
        weeks.append(week)
    return weeks


def calculate_magic_numbers(standings, playoff_spots, num_weeks, remaining_weeks):
    cutoff_wins = standings[playoff_spots - 1]["wins"]
    first_team_in = standings[playoff_spots - 1]

    # Find the first team a game back from a playoff spot
    first_team_out = None
    for team in standings[playoff_spots:]:
        if team["wins"] < cutoff_wins:
            first_team_out = team
            break

    # Nobody outside the bracket is behind on wins (everyone tied, e.g. week 1),
    # so fall back to whoever holds the first non-playoff seat.
    if first_team_out is None and len(standings) > playoff_spots:
        first_team_out = standings[playoff_spots]

    if first_team_out is None:  # every team is in a playoff spot
        return standings

    for team in standings:
        if standings.index(team) < playoff_spots or team["wins"] == first_team_in["wins"]:  # Current Playoff teams
            team["clinch_MN"] = num_weeks + 1 - team["wins"] - first_team_out["losses"]
        else:   # Currently Eliminated Teams
            team["elim_MN"] = remaining_weeks - (first_team_in["wins"] - team["wins"]) + 1
    return standings

def calculate_status(standings, remaining_weeks):
    for team in standings:
        if team.get("clinch_MN") is not None and team["clinch_MN"] <= 0:
            status = "Clinched Playoff Spot"
        elif team.get("elim_MN") is not None and team["elim_MN"] <= 0:
            status = "Eliminated"
        elif team.get("clinch_MN") is not None:
            if team["clinch_MN"] > remaining_weeks:
                status = "Needs help to clinch (Tiebreaker)"
            else:
                status = f"In contention, needs {team['clinch_MN']} win(s) to clinch"
        elif team.get("elim_MN") is not None:
            if team["elim_MN"] > remaining_weeks:
                status = "Needs help to avoid elimination (Tiebreaker)"
            else:
                status = f"In contention, mathematically eliminated with {team['elim_MN']} loss(es)"
        else:
            status = "Status Unknown"  # fallback
        team["status"] = status  # add to each team dict
    return standings


    
def calculate_stats(league_data, playoff_spots, num_weeks, remaining_weeks):
    teams = league_data["teams"]
    sorted_teams = sorted(
        teams,
        key=lambda team: (-team["record"]["wins"], team["record"]["losses"], -team["points_for"])
    )
    standings = []
    for rank, team in enumerate(sorted_teams, start=1):
        standings.append({
            "rank": rank,
            "team_name": team["name"],
            "status": "Unknown",
            "wins": team["record"]["wins"],
            "losses": team["record"]["losses"],
            "clinch_MN": None,
            "elim_MN": None,
            "points_for": team["points_for"]
        })
    standings = calculate_magic_numbers(standings, playoff_spots, num_weeks, remaining_weeks)
    standings = calculate_status(standings, remaining_weeks)
    return standings


if __name__ == "__main__":
    league_data = json.load(sys.stdin)

    playoff_spots = league_data["league_settings"]["playoff_spots"]
    num_weeks = league_data["league_settings"]["weeks_in_season"]
    remaining_weeks = num_weeks - league_data["league_settings"]["current_week"]

    metadata= [{
        "playoff_spots": playoff_spots,
        "num_weeks": num_weeks,
        "remaining_weeks": remaining_weeks,
        "current_week": league_data["league_settings"]["current_week"]
             }]
    next_week_matchups = [
        league_data["next_week_matchups"]
    ]
    remaining_matchups = build_remaining_matchups(league_data["teams"], remaining_weeks)

    # Calculate Magic Numbers
    expanded_data = calculate_stats(league_data, playoff_spots, num_weeks, remaining_weeks)
    # Then overwrite the clinched/eliminated verdict with the exact answer
    expanded_data = playoff_math.apply_verdicts(
        expanded_data, remaining_matchups, playoff_spots
    )
    # A verdict that rests on the total-points tiebreaker is only true while the
    # scoring holds, so record what would have to change.
    expanded_data = playoff_math.attach_dependencies(
        expanded_data, remaining_matchups, playoff_spots
    )
    combined = {
        "league_data": metadata[0],
        "next_week_matchups": next_week_matchups[0],
        "remaining_matchups": remaining_matchups,
        "standings": expanded_data
    }
    print(json.dumps(combined, indent=2))



# Reads the stage-1 payload on stdin, e.g.:
#   python3 scenario_engine/league_data.py --test scenario_engine_tests/week13.json \
#     | python3 scenario_engine/refine_current_week.py
