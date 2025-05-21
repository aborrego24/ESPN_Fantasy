import json
import argparse
from tabulate import tabulate
# pip install tabulate

def load_league_data(file_path):
    with open(file_path, "r") as file:
        league_data = json.load(file)  # Load JSON data into a Python dictionary
    return league_data

def calculate_standings(league_data):
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
            "wins": team["record"]["wins"],
            "losses": team["record"]["losses"],
            "points_for": team["points_for"]
        })
    return standings

def calc_numbers(standings, playoff_spots, num_weeks, remaining_weeks):
    if len(standings) % 2 == 1:
        return
    
    first_team_out = standings[playoff_spots]
    first_team_in = standings[playoff_spots - 1]
    for team in standings:
        if standings.index(team) < playoff_spots:  # Playoff teams
            magic_num = num_weeks + 1 - team["wins"] - first_team_out["losses"]
            team["magic_num"] = magic_num
            team["elim_num"] = None
        else:   
            team["magic_num"] = None
            elim_num = remaining_weeks - (first_team_in["wins"] - team["wins"]) + 1
            team["elim_num"] = elim_num

    return standings

def better_standings(standings, remaining_weeks):
    simplified_standings = []
    for team in standings:
        if team.get("magic_num") is not None and team["magic_num"] <= 0:
            status = "Clinched Playoff Spot"
        elif team.get("elim_num") is not None and team["elim_num"] <= 0:
            status = "Eliminated"
        else:
            if team.get("magic_num") is not None and team["magic_num"] > remaining_weeks:
                status = "Can go to tiebreaker for playoff spot"
            elif team.get("elim_num") is not None and team["elim_num"] > remaining_weeks:
                status = "Can go to tiebreaker for playoff spot"
            elif team.get("magic_num") is not None:
                status = f"In Contention, needs {team['magic_num']} win{'s' if team['magic_num'] != 1 else ''} to clinch."
            elif team.get("elim_num") is not None:
                status = f"In Contention, needs {team['elim_num']} loss{'es' if team['elim_num'] != 1 else ''} to be mathematically eliminated."
        
        simplified_standings.append({
            "Rank": team["rank"],
            "Team Name": team["team_name"],
            "Record": f"{team['wins']}-{team['losses']}",
            "Magic Num": team['magic_num'] if team['magic_num'] is not None else "N/A",
            "Elim Num": team['elim_num'] if team['elim_num'] is not None else "N/A",
            "Status": status
        })
    
    return simplified_standings

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Calculate playoff scenarios for a fantasy league.")
    parser.add_argument("file", help="Path to the JSON file containing league data.")
    args = parser.parse_args()

    # Load league data from the specified file
    league_data = load_league_data(args.file)

    standings = calculate_standings(league_data)

    playoff_spots = league_data["league_settings"]["playoff_spots"]
    num_weeks = league_data["league_settings"]["weeks_in_season"]
    remaining_weeks = num_weeks - league_data["league_settings"]["current_week"]

    standings = calc_numbers(standings, playoff_spots, num_weeks, remaining_weeks)

    pretty_standings = better_standings(standings, remaining_weeks)

    # Display standings as a table
    print(f"---------------- WEEK {league_data['league_settings']['current_week']} STANDINGS ----------------")
    print(tabulate(pretty_standings, headers="keys", tablefmt="grid"))
