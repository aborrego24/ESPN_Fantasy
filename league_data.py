from espn_api.football import League

# Replace with your league details
league = League(league_id=123564885, year=2024)

# Print team names
for team in league.teams:
    print(team.team_name)
