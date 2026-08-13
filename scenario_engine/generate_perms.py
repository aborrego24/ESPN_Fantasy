import sys
import json
import itertools


def gen_perms(league_data):
    matchups = league_data["next_week_matchups"]
    possible_outcomes = [(matchup["team1"], matchup["team2"]) for matchup in matchups]
    return list(itertools.product(*possible_outcomes))


def generate_matchup_permutations(league_data):
    # Every matchup is enumerated, including games between teams whose fate is
    # already settled. Dropping those used to prune the search, but it left
    # their records frozen while everyone else played on, which moved them
    # relative to teams they should have stayed ahead of -- and the exact
    # engine is fast enough that the pruning bought nothing.
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
