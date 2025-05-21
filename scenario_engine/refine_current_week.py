import json
import itertools
import copy
import sys

def load_league_data(file_path):
    """ Load the league data from the given JSON file. """
    with open(file_path, "r") as file:
        return json.load(file)
    
def calculate_magic_numbers(standings, playoff_spots, num_weeks, remaining_weeks):
    first_team_out = standings[playoff_spots]
    first_team_in = standings[playoff_spots - 1]
    for team in standings:
        if standings.index(team) < playoff_spots:  # Current Playoff teams
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
    # Path to the JSON file
    #file_path = "LGW_Test/week13.json"
    #output_file = "Expanded_Weeks/week13_refined.json"
    file_path = sys.argv[1]

    # Load league data
    league_data = load_league_data(file_path)

    playoff_spots = league_data["league_settings"]["playoff_spots"]
    num_weeks = league_data["league_settings"]["weeks_in_season"]
    remaining_weeks = num_weeks - league_data["league_settings"]["current_week"]

    metadata= [{
        "playoff_spots": playoff_spots,
        "num_weeks": num_weeks,
        "remaining_weeks": remaining_weeks
             }]
    current_week_matchups = [
        league_data["current_week_matchups"]
    ]
    # Calculate Magic Numbers
    expanded_data = calculate_stats(league_data, playoff_spots, num_weeks, remaining_weeks)
    combined = {
        "league_data": metadata[0],
        "current_week_matchups": current_week_matchups[0],
        "standings": expanded_data 
    }
    print(json.dumps(combined, indent=2))



# Command to run python3 good_files/refine_current_week.py LGW_Test/week13.json
