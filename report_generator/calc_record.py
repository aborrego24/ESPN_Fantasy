from espn_api.football import League
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd
import json

# ----------------------------------------
# 339875718 lambda, 123564885 greenwood
league_id = 123564885  # Greenwood League ID
year = 2024          # year
# ----------------------------------------

league = League(league_id, year)

week_in_reg_season = league.settings.reg_season_count

team_record = {}
total_record = {}

num_teams = len(league.teams)

# team json, list record vs league at each spot in list
for team in league.teams:
    team_record[team.team_name] = [
        {"W": 0, "L": 0, "T": 0} for _ in range(week_in_reg_season)
    ]
    total_record[team.team_name] = [
        {"W": 0, "L": 0, "T": 0}
    ]


for week in range(1, week_in_reg_season + 1):
    matchups = league.scoreboard(week)
    # print(f"matchup: {matchups}")
    current_week_scores = {}
    for game in matchups:
        current_week_scores[game.home_team.team_name] = game.home_score
        current_week_scores[game.away_team.team_name] = game.away_score
    # print(f"current_week_scores: {current_week_scores}")
    for team in current_week_scores:
        # print(f"team: {team}")
        for opp_team in current_week_scores:
            # print(f"oppteam: {opp_team}")
            if team != opp_team:
                if current_week_scores[team] > current_week_scores[opp_team]:
                    # print(f"{team} won, {opp_team} lost")
                    team_record[team][week - 1]["W"] += 1
                    total_record[team][0]["W"] += 1
                elif current_week_scores[team] < current_week_scores[opp_team]:
                    # print(f"{opp_team} won, {team} lost")
                    team_record[team][week - 1]["L"] += 1
                    total_record[team][0]["L"] += 1
                else: 
                    # print("tie")
                    team_record[team][week - 1]["T"] += 1
                    total_record[team][0]["T"] += 1

combined = {
    "weekly_record": team_record,
    "total_record": total_record
}

# ====== Pandas Table Display ======

# Build table data
table_data = {}
for team, weeks in team_record.items():
    row = []
    for w in weeks:
        if w["T"] == 0:
            row.append(f"{w['W']}-{w['L']}")
        else:
            row.append(f"{w['W']}-{w['L']}-{w['T']}")

    total = total_record[team][0]
    if total["T"] == 0:
        row.append(f"{total['W']}-{total['L']}")
    else:
        row.append(f"{total['W']}-{total['L']}-{total['T']}")

    table_data[team] = row

# Fix columns based on actual weeks
num_weeks = len(next(iter(team_record.values())))
columns = [f"Week {i+1}" for i in range(num_weeks)] + ["Total"]

# Create DataFrame
df = pd.DataFrame.from_dict(table_data, orient="index", columns=columns)

# Extract total wins for sorting
df["Total_Wins"] = df["Total"].str.extract(r"^(\d+)-")  # get the 'W' from 'W-L' or 'W-L-T'
df["Total_Wins"] = df["Total_Wins"].astype(int)

# Sort by Total_Wins descending
df = df.sort_values(by="Total_Wins", ascending=False)

# Drop the helper column
df = df.drop(columns=["Total_Wins"])

# Print result
# print(df.to_string())

# Set figure size based on table size
fig, ax = plt.subplots(figsize=(len(df.columns) * 1.2, len(df) * 0.5))

# Hide axes
ax.axis('off')

# Create table from DataFrame
table = ax.table(cellText=df.values, colLabels=df.columns, rowLabels=df.index, loc='center')
table.auto_set_font_size(False)
table.set_fontsize(8)
table.scale(1.2, 1.2)

# Export to PDF
with PdfPages(f"team_records_{league_id}.pdf") as pdf:
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()

print("✅ PDF saved as team_records.pdf")

