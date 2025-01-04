from espn_api.football import League

# Replace with your league details
league = League(league_id=123564885, year=2024)

# Print team names
for team in league.teams:
    print(team.team_name)


# Link to API:
#   https://github.com/cwendt94/espn-api/wiki
#   https://github.com/cwendt94/espn-api?tab=readme-ov-file