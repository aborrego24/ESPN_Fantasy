import sys
import json

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


def find_scenario(scenarios, team):
    for entry in scenarios:
        if entry["team"] == team:
            return entry
    return None


def describe(prefix, alternatives):
    """One line per alternative, e.g. 'a WIN and Momma Gus WIN'.

    An alternative with no conditions means that result alone is enough, so the
    line is just the prefix. Stage 4 only produces that when the outcome really
    does hold regardless of the other games.
    """
    lines = []
    for conditions in alternatives:
        if not conditions:
            lines.append(f"  - {prefix}")
        else:
            joined = " and ".join(f"{c['winner']} WIN" for c in conditions)
            lines.append(f"  - {prefix} and {joined}")
    return lines


def emit(lines):
    for i, line in enumerate(lines):
        if i:
            print("    or ... ")
        print(line)


def paths_for(scenarios, name, key):
    entry = find_scenario(scenarios, name)
    if not entry:
        return None
    paths = entry.get(key)
    if not paths:
        return None
    return describe("a WIN", paths["win"]) + describe("a LOSS", paths["loss"])


def main():
    data = json.load(sys.stdin)
    standings = data["base_league_data"]["standings"]
    scenarios = data["scenarios"]

    print(f"\n===================== {GREEN}CLINCH SCENARIOS{RESET} =====================")
    for team in standings:
        name = team["team_name"]

        if "Clinched" in team["status"]:
            print(f"====== {GREEN}{name}{RESET} Clinched Playoff Spot ======")
            continue

        lines = paths_for(scenarios, name, "clinch")
        if not lines:
            continue
        print(f"====== {GREEN}{name}{RESET} Clinches a playoff spot with: ======")
        emit(lines)

    print(f"\n===================== {RED}ELIMINATION SCENARIOS{RESET} =====================")
    for team in standings:
        name = team["team_name"]

        if "Eliminated" in team["status"]:
            print(f"====== {RED}{name}{RESET} Eliminated from playoffs ======")
            continue

        lines = paths_for(scenarios, name, "elim")
        if not lines:
            continue
        print(f"====== {RED}{name}{RESET} Eliminated from playoffs with: ======")
        emit(lines)


if __name__ == "__main__":
    main()
