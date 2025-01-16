import json
import itertools
import copy


def load_league_data(file_path):
    """ Load the league data from the given JSON file. """
    with open(file_path, "r") as file:
        return json.load(file)


def generate_matchup_permutations(matchups):
    """
    Generate all possible win/loss permutations for the given matchups.
    Returns a list of tuples where each tuple represents a possible outcome.
    """
    possible_outcomes = [(matchup["team1"], matchup["team2"]) for matchup in matchups]
    return list(itertools.product(*possible_outcomes))


def update_standings_for_permutation(league_data, permutation):
    """
    Given a permutation of winners for the current week, update the standings.
    
    Args:
        league_data (dict): The league data containing teams and records.
        permutation (tuple): A tuple of winning teams for the current week's matchups.
    
    Returns:
        list: Updated team records after applying the permutation.
    """
    updated_teams = copy.deepcopy(league_data["teams"])
    team_dict = {team["name"]: team for team in updated_teams}

    for matchup, winner in zip(league_data["current_week_matchups"], permutation):
        loser = matchup["team1"] if winner == matchup["team2"] else matchup["team2"]
        team_dict[winner]["record"]["wins"] += 1
        team_dict[loser]["record"]["losses"] += 1

    return updated_teams


def calculate_numbers(standings, playoff_spots, num_weeks, remaining_weeks):
    """
    Calculate Magic Number for top teams and Elimination Number for bottom teams.
    """
    if len(standings) % 2 == 1:
        return

    first_team_out = standings[playoff_spots]
    first_team_in = standings[playoff_spots - 1]

    for i, team in enumerate(standings):
        if i < playoff_spots:  # Playoff teams
            magic_num = num_weeks + 1 - team["record"]["wins"] - first_team_out["record"]["losses"]
            team["magic_num"] = max(0, magic_num)  # Ensure non-negative
            team["elim_num"] = None
        else:  # Non-playoff teams
            team["magic_num"] = None
            elim_num = remaining_weeks - (first_team_in["record"]["wins"] - team["record"]["wins"]) + 1
            team["elim_num"] = max(0, elim_num)  # Ensure non-negative


def simulate_permutations(league_data):
    """
    Simulate all permutations of matchups for the current week and calculate standings.

    Returns:
        list: A list of dictionaries with permutation results.
    """
    matchups = league_data["current_week_matchups"]
    permutations = generate_matchup_permutations(matchups)

    current_week = league_data["league_settings"]["current_week"]
    remaining_weeks = league_data["league_settings"]["weeks_in_season"] - current_week
    playoff_spots = league_data["league_settings"]["playoff_spots"]
    num_weeks = league_data["league_settings"]["weeks_in_season"]

    results = []

    for i, permutation in enumerate(permutations, start=1):
        updated_standings = update_standings_for_permutation(league_data, permutation)

        # Sort teams based on Wins -> Points For (Tiebreaker)
        sorted_standings = sorted(
            updated_standings, 
            key=lambda team: (-team["record"]["wins"], -team["points_for"])
        )

        # Calculate Magic and Elimination Numbers
        calculate_numbers(sorted_standings, playoff_spots, num_weeks, remaining_weeks)

        # Store permutation results
        standings_summary = {
            "permutation_number": i,
            "week_number": current_week,
            "weeks_remaining": remaining_weeks,
            "standings": []
        }

        for team in sorted_standings:
            standings_summary["standings"].append({
                "team_name": team["name"],
                "wins": team["record"]["wins"],
                "losses": team["record"]["losses"],
                "magic_number": team["magic_num"] if team["magic_num"] is not None else "N/A",
                "elimination_number": team["elim_num"] if team["elim_num"] is not None else "N/A"
            })

        results.append(standings_summary)

    return results


def save_to_file(data, filename):
    """ Save the generated permutations to a JSON file. """
    with open(filename, "w") as file:
        json.dump(data, file, indent=2)

    print(f"✅ Saved {len(data)} permutations to {filename}")


if __name__ == "__main__":
    # Path to the JSON file
    file_path = "LGW_Test/week13.json"
    output_file = "week13_perms.json"

    # Load league data
    league_data = load_league_data(file_path)

    # Simulate permutations and calculate standings
    permutation_results = simulate_permutations(league_data)

    # Save results to a file
    save_to_file(permutation_results, output_file)
