import json

file_path = "test1.json"

def load_league_data(file_path):
    with open(file_path, "r") as file:
        league_data = json.load(file)  # Load JSON data into a Python dictionary
    return league_data

def calculate_standings(league_data):
    # Do this, return a json in order
    # have the team rank, tema name, wins, losses
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

def calc_numbers(standings, playoff_spots, num_weeks, remaning_weeks):
    # Currently only works for single divisions, with even # teams
    if (len(standings) % 2 == 1):
        return
    
    # Calculate Magic/Elimination Number
    first_team_out = standings[playoff_spots]
    first_team_in = standings[playoff_spots - 1]
    # print(f"first team out: {standings[playoff_spots]}")
    for team in standings:
        if standings.index(team) < playoff_spots:  # Playoff teams
            magic_num = num_weeks + 1 - team["wins"] - first_team_out["losses"]
            team["magic_num"] = magic_num
            team["elim_num"] = None
        else:   
            # Currently Eliminated teams
            team["magic_num"] = None
            elim_num = remaning_weeks - (first_team_in["wins"] - team["wins"]) + 1
            team["elim_num"] = elim_num

    return standings


def better_standings(standings, remaining_weeks):
    """
    Simplifies the standings to include team name, win-loss record, and clinching status.
    """
    simplified_standings = []
    for team in standings:
        # Determine clinching/elimination status
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


            
        
        # Add simplified information
        simplified_standings.append({
            "team_name": team["team_name"],
            "record": f"{team['wins']}-{team['losses']}",
            "status": status
        })
    
    return simplified_standings




league_data = load_league_data(file_path)
# print(json.dumps(league_data, indent=4))

standings = calculate_standings(league_data)
# print(json.dumps(standings, indent=4))


# Update the standings with magic/elimination number
playoff_spots = league_data["league_settings"]["playoff_spots"]
num_weeks = league_data["league_settings"]["weeks_in_season"]
remaning_weeks = league_data["league_settings"]["weeks_in_season"] - league_data["league_settings"]["current_week"]
standings = calc_numbers(standings, playoff_spots, num_weeks, remaning_weeks)

# Add information to teams that have either clinched or been eliminated
pretty_standings = better_standings(standings, remaning_weeks)
print(f"-------- WEEK {league_data["league_settings"]["current_week"]} STANDINGS --------")
print(json.dumps(pretty_standings, indent=2))