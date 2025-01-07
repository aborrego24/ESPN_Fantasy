from espn_api.football import League

# Replace with your league details
league = League(league_id=123564885, year=2024)

# Print team names
# print("Team Names:\n")
# for team in league.teams:
#     print(team.team_name)


print("\n---------------------\n")

standings = league.standings()
print("League Standings:")
for rank, team in enumerate(standings, start=1):
    print(f"{rank}. {team.team_name} - Record: {team.wins}-{team.losses}-{team.ties}")




# Link to API:
#   https://github.com/cwendt94/espn-api/wiki
#   https://github.com/cwendt94/espn-api?tab=readme-ov-file