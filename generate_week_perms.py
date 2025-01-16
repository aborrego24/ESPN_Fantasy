import json
import itertools


def load_league_data(file_path):
    """
    Load the league data from the given JSON file.
    """
    with open(file_path, "r") as file:
        return json.load(file)


def generate_matchup_permutations(matchups):
    """
    Generate all possible win/loss permutations for the given matchups.
    
    Args:
        matchups (list): A list of dictionaries representing the matchups.
                         Example: [{ "team1": "A", "team2": "B" }]
    
    Returns:
        list: A list of permutations, where each permutation is a list of results.
              Example: [["A", "B", "A", "B"], ["B", "A", "A", "B"]]
    """
    # Each matchup has two possible outcomes: team1 wins or team2 wins
    possible_outcomes = [(matchup["team1"], matchup["team2"]) for matchup in matchups]

    # Generate all combinations of outcomes
    permutations = list(itertools.product(*possible_outcomes))

    return permutations


def display_permutations(permutations):
    """
    Display all permutations in a readable format.
    """
    for i, perm in enumerate(permutations, start=1):
        print(f"Permutation {i}: {perm}")


if __name__ == "__main__":
    # Path to the JSON file
    file_path = "LGW_Test/week13.json"

    # Load league data
    league_data = load_league_data(file_path)

    # Get the current week's matchups
    matchups = league_data["current_week_matchups"]

    # Generate all permutations for the matchups
    permutations = generate_matchup_permutations(matchups)

    # Display permutations
    print(f"Total permutations: {len(permutations)}")
    display_permutations(permutations)
