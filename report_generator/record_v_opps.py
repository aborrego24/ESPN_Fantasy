from espn_api.football import League
import matplotlib.pyplot as plt
import pandas as pd
import json

# ----------------------------------------
# 339875718 lambda, 123564885 greenwood
league_id = 123564885  # Greenwood League ID
year = 2024          # year
# ----------------------------------------

league = League(league_id, year)

rec_v_others = {}
week_in_reg_season = league.settings.reg_season_count
team_opponents = {team.team_name: [] for team in league.teams}
for team in league.teams:
    rec_v_others[team.team_name] = {}
    for other_team in league.teams:
        if other_team.team_name != team.team_name:
            rec_v_others[team.team_name][other_team.team_name] = {"W": 0, "L": 0, "T": 0}


# Calculate each team's opponent's scores
for week in range(1, week_in_reg_season + 1):
    matchups = league.scoreboard(week)
    for game in matchups:
        home = game.home_team.team_name
        away = game.away_team.team_name
        home_score = game.home_score
        away_score = game.away_score

        # Add opponent and their score to each team's weekly list
        team_opponents[home].append((away, away_score))
        team_opponents[away].append((home, home_score))

# print(f"{json.dumps(rec_v_others, indent=2)}")
# Calc team record vs other schedules
for team in league.teams:
    for opp_team in league.teams:
        if team.team_name == opp_team.team_name:
            continue
        # print(f"==== {team.team_name} record vs {opp_team.team_name}'s schedule =======")
        for i, (opp_name, opp_score) in enumerate(team_opponents[opp_team.team_name]):
            # print(f"opname: {opp_name}, oppscore: {opp_score}")
            if team.scores[i] > opp_score:
                rec_v_others[team.team_name][opp_team.team_name]["W"] += 1
            elif team.scores[i] < opp_score:
                rec_v_others[team.team_name][opp_team.team_name]["L"] += 1
            elif team.team_name == opp_name:
                # the teams played, TODO
            else:
                rec_v_others[team.team_name][opp_team.team_name]["T"] += 1


print(f"{json.dumps(rec_v_others, indent=2)}")

