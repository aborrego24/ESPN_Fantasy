import sys
import json
import itertools

def refine_matchups(data):
    # Get set of teams that are locked (clinched or eliminated)
    locked_statuses = {"Clinched Playoff Spot", "Eliminated"}
    locked_teams = {team["team_name"] for team in data["standings"] if team["status"] in locked_statuses}

    # Filter out matchups where both teams are in the locked set
    filtered_matchups = []
    for matchup in data["current_week_matchups"]:
        team1, team2 = matchup["team1"], matchup["team2"]
        if not (team1 in locked_teams and team2 in locked_teams):
            filtered_matchups.append(matchup)

    # Replace the old matchups with the filtered list
    data["current_week_matchups"] = filtered_matchups
    return data

def gen_perms(league_data):
    matchups = league_data["current_week_matchups"]
    possible_outcomes = [(matchup["team1"], matchup["team2"]) for matchup in matchups]
    return list(itertools.product(*possible_outcomes))

def generate_matchup_permutations(league_data):
    # Remove any matchups between clinched (elim & playoff) teams
    league_data = refine_matchups(league_data)
    return gen_perms(league_data)





if __name__ == "__main__":
    league_data = json.load(sys.stdin)
    permutations = generate_matchup_permutations(league_data)
    # Package and send output as JSON for next script to use
    output_payload = {
        "base_league_data": league_data,
        "permutations": [list(p) for p in permutations]  # convert tuples to lists
    }

    print(json.dumps(output_payload, indent=2))




# python3 good_files/refine_current_week.py LGW_Test/week13.json | python3 good_files/generate_perms.py