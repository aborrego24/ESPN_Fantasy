import json
import sys
import copy
from itertools import zip_longest


def calculate_magic_numbers(standings, playoff_spots, num_weeks, remaining_weeks):
    cutoff_wins = standings[playoff_spots - 1]["wins"]
    first_team_in = standings[playoff_spots - 1]

    # Find the first team a game back from a playoff spot
    first_team_out = None
    for team in standings[playoff_spots:]:
        if team["wins"] < cutoff_wins:
            first_team_out = team
            break

    # recalculate MN, EN and rank
    for i, team in enumerate(standings):
        if i < playoff_spots or team["wins"] == first_team_in["wins"]:  # Currently in
            team["clinch_MN"] = num_weeks + 1 - team["wins"] - first_team_out["losses"]
            team["elim_MIN"] = None
        else:
            team["elim_MN"] = remaining_weeks - (first_team_in["wins"] - team["wins"]) + 1
            team["clinch_MN"] = None
        team["rank"] = i + 1
    return standings

def calculate_status(standings, remaining_weeks, playoff_spots):
    for team in standings:
        if team.get("clinch_MN") is not None and team["clinch_MN"] <= 0:
            team["status"] = "Clinched Playoff Spot"
        elif team.get("elim_MN") is not None and team["elim_MN"] <= 0:
            team["status"] = "Eliminated"
        elif remaining_weeks == 0:
            # At season end: anyone not clinched or eliminated is on the bubble
            team["status"] = "In contention, need to win tiebreaker"
        elif team.get("clinch_MN") is not None:
            if team["clinch_MN"] > remaining_weeks:
                team["status"] = "Needs help to clinch (Tiebreaker)"
            else:
                team["status"] = f"In contention, needs {team['clinch_MN']} win(s) to clinch"
        elif team.get("elim_MN") is not None:
            if team["elim_MN"] > remaining_weeks:
                team["status"] = "Needs help to avoid elimination (Tiebreaker)"
            else:
                team["status"] = f"In contention, mathematically eliminated with {team['elim_MN']} loss(es)"
        else:
            team["status"] = "Status Unknown"
    return standings


# === Apply permutation and recalculate standings ===
def apply_permutation(base_data, permutation):
    data = copy.deepcopy(base_data)
    data["league_data"]["remaining_weeks"] -= 1
    matchups = data["next_week_matchups"]

    for matchup, winner in zip(matchups, permutation):
        t1, t2 = matchup["team1"], matchup["team2"]
        for team in data["standings"]:
            if team["team_name"] == winner:
                team["wins"] += 1
            elif team["team_name"] in (t1, t2):
                team["losses"] += 1

    # Sort and recalculate
    sorted_teams = sorted(
        data["standings"],
        key=lambda t: (-t["wins"], t["losses"], -t["points_for"])
    )

    # Recalculate magic/elim numbers + status
    playoff_spots = data["league_data"]["playoff_spots"]
    num_weeks = data["league_data"]["num_weeks"]
    remaining_weeks = data["league_data"]["remaining_weeks"]

    standings = calculate_magic_numbers(sorted_teams, playoff_spots, num_weeks, remaining_weeks)
    standings = calculate_status(standings, remaining_weeks, playoff_spots)
    # print(json.dumps(standings, indent=2))
    return standings

def build_team_scenarios(base_data, permutations):
    scenario_map = {}

    # Filter out teams that are already clinched/eliminated
    tracked_teams = {
        team["team_name"]
        for team in base_data["standings"]
        if team["status"] not in {"Clinched Playoff Spot", "Eliminated"}
    }

    for i, perm in enumerate(permutations):
        standings = apply_permutation(base_data, perm)

        for team in standings:
            name = team["team_name"]
            status = team["status"]
            # print(f"{name}'s status = {status}, i = {i}")

            if name not in tracked_teams:
                continue  # Skip teams already decided

            if name not in scenario_map:
                scenario_map[name] = {
                    "clinched_in": [],
                    "eliminated_in": [],
                    "still_alive_in": []
                }

            if "Clinched Playoff Spot" in status:
                scenario_map[name]["clinched_in"].append(i)
            elif "Eliminated" in status:
                scenario_map[name]["eliminated_in"].append(i)
            else:
                scenario_map[name]["still_alive_in"].append(i)

    return scenario_map

def calc_clinching(team, clinched_idx, permutations, base_data, matchups):
    if len(clinched_idx) == 0:
        return [], []
    win_clinch = []
    loss_clinch = []
    matchup_index = next(
        (i for i, m in enumerate(matchups) if team in (m["team1"], m["team2"])), 
        None
    )
    # print(f"clinch clinchedidx: {clinched_idx}")
    for clinch in clinched_idx:
        # team won & clinched
        if team in permutations[clinch]:
            if not win_clinch:
                win_clinch = list(permutations[clinch])
            else:
                win_clinch = [x if x == y else None for x, y in zip_longest(win_clinch, permutations[clinch])]
        # team lost & clinched
        else:
            if not loss_clinch:
                loss_clinch = list(permutations[clinch])                
            else:
                loss_clinch = [x if x == y else None for x, y in zip_longest(loss_clinch, permutations[clinch])]

    # print(f"{team} win clinch before clear own: {win_clinch} ---- loss clinch: {loss_clinch}")
    # Clear team's own game out of the stuff 
    # if loss_clinch and 0 <= matchup_index < len(loss_clinch):
    #     loss_clinch.pop(matchup_index)
    
    # if win_clinch and 0 <= matchup_index < len(win_clinch):
    #     win_clinch.pop(matchup_index)
    return win_clinch, loss_clinch

def calc_elim(team, eliminated_idx, permutations, base_data, matchups):
    if len(eliminated_idx) == 0:
        return [], []
    win_elim = []
    loss_elim = []
    matchup_index = next(
        (i for i, m in enumerate(matchups) if team in (m["team1"], m["team2"])), 
        None
    )
    # print(f"elim elimidx: {eliminated_idx}")
    for elim in eliminated_idx:
        # team won & clinched
        if team in permutations[elim]:
            if not win_elim:
                win_elim = list(permutations[elim])
                # win_elim.pop(matchup_index)
            else:
                win_elim = [x if x == y else None for x, y in zip_longest(win_elim, permutations[elim])]
        # team lost & clinched
        else:
            if not loss_elim:
                loss_elim = list(permutations[elim])
                # loss_elim.pop(matchup_index)
            else:
                loss_elim = [x if x == y else None for x, y in zip_longest(loss_elim, permutations[elim])]
    return win_elim, loss_elim

def output_scenarios(team, clinched_idx, eliminated_idx, permutations, base_data, matchups):
    clinch_scenarios = calc_clinching(team, clinched_idx, permutations, base_data, matchups)
    elim_scenarios = calc_elim(team, eliminated_idx, permutations, base_data, matchups)
    # print(f"clinching scenarios: {clinch_scenarios}")
    # print(f"elim scen: {elim_scenarios}")

    result = {}
    if any(clinch_scenarios):  # At least one of the two lists is non-empty
        result["clinch_scenarios"] = clinch_scenarios
    if any(elim_scenarios):  # At least one of the two lists is non-empty
        result["elim_scenarios"] = elim_scenarios
    # print(f"team: {team} scenarios: {result}")
    return result


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    base_data = payload["base_league_data"]
    permutations = payload["permutations"]

    team_results = build_team_scenarios(base_data, permutations)
    # print(json.dumps(team_results, indent=2))
    # total = len(permutations)
    matchups = base_data["next_week_matchups"]
    # print(json.dumps(matchups, indent=2))

    scenarios = []

    for team, outcomes in team_results.items():
        clinched = outcomes["clinched_in"]
        eliminated = outcomes["eliminated_in"]
        # print(f"team: {team} =====================================")
        # print(f"clinched in: {clinched}")
        # print(f"eliminated in: {eliminated}")
        # print(f"got here for {team}")
        scenario = output_scenarios(team, clinched, eliminated, permutations, base_data, matchups)
        scenarios.append({f"{team}": scenario})
    output_payload = {
        "base_league_data": base_data,
        "scenarios": scenarios
    }

    print(json.dumps(output_payload, indent=2))

# python3 good_files/refine_current_week.py LGW_Test/PC_test.json | python3 good_files/generate_perms.py | python3 good_files/refine_hypothetical.py
