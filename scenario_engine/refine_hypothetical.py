import json
import sys
import copy

import conditions
import margins
import playoff_math


def calculate_magic_numbers(standings, playoff_spots, num_weeks, remaining_weeks):
    cutoff_wins = standings[playoff_spots - 1]["wins"]
    first_team_in = standings[playoff_spots - 1]

    # Find the first team a game back from a playoff spot
    first_team_out = None
    for team in standings[playoff_spots:]:
        if team["wins"] < cutoff_wins:
            first_team_out = team
            break

    # Nobody outside the bracket is behind on wins (everyone tied, e.g. week 1),
    # so fall back to whoever holds the first non-playoff seat.
    if first_team_out is None and len(standings) > playoff_spots:
        first_team_out = standings[playoff_spots]

    if first_team_out is None:  # every team is in a playoff spot
        for i, team in enumerate(standings):
            team["rank"] = i + 1
        return standings

    # recalculate MN, EN and rank
    for i, team in enumerate(standings):
        if i < playoff_spots or team["wins"] == first_team_in["wins"]:  # Currently in
            team["clinch_MN"] = num_weeks + 1 - team["wins"] - first_team_out["losses"]
            team["elim_MN"] = None
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

    # The magic number only ever answered "can one rival pass me". Whether a
    # team actually holds a playoff seat is decided exactly, over every
    # completion of the weeks still left after this one.
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


def describe_side(indices, permutations, matchups, team, team_won):
    """Exact conditions for the outcomes in `indices` where `team` won (or lost).

    The team's own game is held out of the conditions -- it is stated separately
    as "a WIN" or "a LOSS" -- so a team can never appear as a condition of its
    own scenario, and neither can its opponent.

    Returns a list of alternatives, any one of which is sufficient. `[]` means
    that side is impossible; `[[]]` means it needs no other results at all.
    """
    own = own_matchup_index(matchups, team)
    others = [k for k in range(len(matchups)) if k != own]

    selected = set()
    for i in indices:
        permutation = permutations[i]
        won = own is not None and permutation[own] == team
        if won != team_won:
            continue
        outcome = 0
        for bit, k in enumerate(others):
            if permutation[k] == matchups[k]["team2"]:
                outcome |= 1 << bit
        selected.add(outcome)

    described = []
    for implicant in conditions.minimal_dnf(selected, len(others)):
        described.append(
            [
                {
                    "matchup": others[bit],
                    "winner": matchups[others[bit]]["team2" if value else "team1"],
                }
                for bit, value in sorted(implicant.items())
            ]
        )
    return described


def output_scenarios(team, clinched_idx, eliminated_idx, permutations, matchups):
    result = {}
    for label, indices in (("clinch", clinched_idx), ("elim", eliminated_idx)):
        win = describe_side(indices, permutations, matchups, team, True)
        loss = describe_side(indices, permutations, matchups, team, False)
        if win or loss:
            result[label] = {"win": win, "loss": loss}
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
