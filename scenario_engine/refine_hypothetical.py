import json
import sys
import copy

import conditions
import margins
import playoff_math


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

    # Re-seed on the updated records
    standings = sorted(
        data["standings"],
        key=lambda t: (-t["wins"], t["losses"], -t["points_for"])
    )

    # Every team's fate is then decided exactly, over every completion of the
    # weeks still left after this one.
    playoff_spots = data["league_data"]["playoff_spots"]
    later_weeks = base_data.get("remaining_matchups", [])[1:]
    # +1 for next week itself: its win/loss has been applied, but its POINTS
    # have not -- those scores do not exist yet. Sizing the envelope on
    # later_weeks alone treated next week's scoring as already known, so a seat
    # resting on a 30-point gap came back as clinched whatever the result.
    envelope = margins.swing_envelope(len(later_weeks) + 1, margins.load_thresholds())
    standings = playoff_math.apply_verdicts(
        standings, later_weeks, playoff_spots, swing_envelope=envelope
    )
    return standings

def build_team_scenarios(base_data, permutations):
    scenario_map = {}

    # Filter out teams that are already clinched/eliminated
    tracked_teams = {
        team["team_name"]
        for team in base_data["standings"]
        if team.get("verdict", "alive") == "alive"
    }

    for i, perm in enumerate(permutations):
        standings = apply_permutation(base_data, perm)

        for team in standings:
            name = team["team_name"]
            verdict = team["verdict"]
            # print(f"{name}'s status = {status}, i = {i}")

            if name not in tracked_teams:
                continue  # Skip teams already decided

            if name not in scenario_map:
                scenario_map[name] = {
                    "clinched_in": [],
                    "eliminated_in": [],
                    "still_alive_in": []
                }

            if verdict == "clinched":
                scenario_map[name]["clinched_in"].append(i)
            elif verdict == "eliminated":
                scenario_map[name]["eliminated_in"].append(i)
            else:
                scenario_map[name]["still_alive_in"].append(i)

    return scenario_map

def own_matchup_index(matchups, team):
    for i, matchup in enumerate(matchups):
        if team in (matchup["team1"], matchup["team2"]):
            return i
    return None


def describe_scenario(indices, permutations, matchups, team):
    """Minimal exact alternatives for the outcomes in `indices`.

    The team's own game is part of the reduction, not held out of it. Holding it
    out forced every alternative to pin the team's own result, which is exact but
    over-specifies: if a rival winning settles the matter, saying "a WIN and that
    rival WIN" implies your own result mattered when it did not.

    The own-game literal is separated out afterwards, so it renders as "a WIN" or
    "a LOSS" rather than as a condition -- a team still never appears as a
    condition of its own scenario, and neither does its opponent.

    Each alternative is {"own": "win"|"loss"|None, "conditions": [...]}, where
    None means the outcome holds whatever the team itself does.
    """
    own = own_matchup_index(matchups, team)
    count = len(matchups)

    selected = set()
    for i in indices:
        permutation = permutations[i]
        outcome = 0
        for k in range(count):
            if permutation[k] == matchups[k]["team2"]:
                outcome |= 1 << k
        selected.add(outcome)

    alternatives = []
    for implicant in conditions.minimal_dnf(selected, count):
        own_result = None
        needed = []
        for bit, value in sorted(implicant.items()):
            winner = matchups[bit]["team2" if value else "team1"]
            if bit == own:
                own_result = "win" if winner == team else "loss"
            else:
                needed.append({"matchup": bit, "winner": winner})
        alternatives.append({"own": own_result, "conditions": needed})

    # What the team can do about it comes first. An alternative that turns on its
    # own result is actionable; one that turns only on other teams is not, so it
    # is listed second however few conditions it carries. Within each group,
    # fewest requirements first.
    alternatives.sort(key=lambda a: (a["own"] is None, len(a["conditions"])))
    return alternatives


def output_scenarios(team, clinched_idx, eliminated_idx, permutations, matchups):
    result = {}
    for label, indices in (("clinch", clinched_idx), ("elim", eliminated_idx)):
        alternatives = describe_scenario(indices, permutations, matchups, team)
        if alternatives:
            result[label] = alternatives
    return result


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    base_data = payload["base_league_data"]
    permutations = payload["permutations"]

    team_results = build_team_scenarios(base_data, permutations)
    matchups = base_data["next_week_matchups"]

    scenarios = []
    for team, outcomes in team_results.items():
        scenario = output_scenarios(
            team,
            outcomes["clinched_in"],
            outcomes["eliminated_in"],
            permutations,
            matchups,
        )
        scenarios.append({"team": team, **scenario})
    output_payload = {
        "base_league_data": base_data,
        "scenarios": scenarios
    }

    print(json.dumps(output_payload, indent=2))

# Run the whole pipeline with:
#   ./run_scenarios.sh --test scenario_engine_tests/week13.json
