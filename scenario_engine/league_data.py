from espn_api.football import League
import sys
import json

# ----------------------------------------
league_id = 123564885  # Greenwood League ID
year = 2024          # year
# ----------------------------------------


def load_league_data(file_path):
    """Load the league data from the given JSON file."""
    with open(file_path, "r") as file:
        return json.load(file)
    

# Check arguments
if len(sys.argv) < 2:
    print("Usage:")
    print("  python3 league_data.py <current_week>")
    print("  python3 league_data.py --test")
    sys.exit(1)

if sys.argv[1] == "--test":
    if len(sys.argv) < 3:
        print("Error: --test requires a path to a JSON file.")
        sys.exit(1)
    
    test_file = sys.argv[2]
    data = load_league_data(test_file)
    print(json.dumps(data, indent=2))
    sys.exit(0)

# Otherwise, treat as IRL mode
try:
    current_week = int(sys.argv[1])
except ValueError:
    print("Error: current_week must be an integer.")
    sys.exit(1)

league = League(league_id=123564885, year=2024)

# League-level settings
league_settings = {
    "num_teams": len(league.teams),
    "playoff_spots": league.settings.playoff_team_count,
    "weeks_in_season": league.settings.reg_season_count,
    "current_week": current_week,
    "tiebreaker": "points_for"
}

# Team info
teams = []
for team in league.teams:
    team_data = {
        "name": team.team_name,
        "record": {
            "wins": team.wins,
            "losses": team.losses,
            "ties": team.ties
        },
        "points_for": round(team.points_for, 2),
        "remaining_schedule": [
            opp.team_name for opp in team.schedule[league_settings["current_week"]:league_settings["weeks_in_season"]]
        ]
    }
    teams.append(team_data)

# Next week matchups
next_week_matchups = []
scoreboard = league.scoreboard(week=league.current_week)

# Map team IDs to team names
team_id_to_name = {team.team_id: team.team_name for team in league.teams}

for matchup in scoreboard:
    next_week_matchups.append({
        "team1": matchup.home_team.team_name,
        "team2": next((t["remaining_schedule"] for t in teams if t["name"] == matchup.home_team.team_name), None)[0]
    })

# Combine all data
output = {
    "league_settings": league_settings,
    "teams": teams,
    f"next_week_matchups": next_week_matchups
}

# Print JSON
print(json.dumps(output, indent=2))


# Link to API:
#   https://github.com/cwendt94/espn-api/wiki
#   https://github.com/cwendt94/espn-api?tab=readme-ov-file