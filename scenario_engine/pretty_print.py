import sys
import json

import margins

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
DIM = "\033[2m"


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


def nothing_yet(kind, weeks_remaining):
    """Say so explicitly when a section has nothing to report.

    Early in a season no team can clinch or be eliminated yet, and printing an
    empty section under a heading reads as a broken tool rather than as an
    answer.
    """
    weeks = "1 week" if weeks_remaining == 1 else f"{weeks_remaining} weeks"
    if weeks_remaining <= 0:
        return "  Nothing left to decide - the regular season is over."
    return (
        f"  No team can be decided by {kind} next week - "
        f"too much is still unplayed with {weeks} to go."
    )


def tiebreak_note(team, weeks_remaining, thresholds, eliminated=False):
    """The clause qualifying a verdict that rests on the tiebreaker."""
    return margins.describe(
        team.get("tiebreak"), weeks_remaining, thresholds, eliminated=eliminated
    )


def main():
    data = json.load(sys.stdin)
    standings = data["base_league_data"]["standings"]
    scenarios = data["scenarios"]
    weeks_remaining = data["base_league_data"]["league_data"]["remaining_weeks"]
    thresholds = margins.load_thresholds()

    print(f"\n===================== {GREEN}CLINCH SCENARIOS{RESET} =====================")
    reported = 0
    for team in standings:
        name = team["team_name"]

        if team["verdict"] == "clinched":
            headline = "Clinched Playoff Spot"
            if margins.qualifies_headline(team.get("tiebreak"), weeks_remaining, thresholds):
                headline = "Clinched on current scoring"
            print(f"====== {GREEN}{name}{RESET} {headline} ======")
            reported += 1
            note = tiebreak_note(team, weeks_remaining, thresholds)
            if note:
                print(f"       {DIM}{note}{RESET}")
            continue

        lines = paths_for(scenarios, name, "clinch")
        if not lines:
            continue
        reported += 1
        print(f"====== {GREEN}{name}{RESET} Clinches a playoff spot with: ======")
        emit(lines)
        note = tiebreak_note(team, weeks_remaining, thresholds)
        if note:
            print(f"       {DIM}{note}{RESET}")

    if not reported:
        print(nothing_yet("clinch", weeks_remaining))

    print(f"\n===================== {RED}ELIMINATION SCENARIOS{RESET} =====================")
    reported = 0
    for team in standings:
        name = team["team_name"]

        if team["verdict"] == "eliminated":
            headline = "Eliminated from playoffs"
            if margins.qualifies_headline(team.get("tiebreak"), weeks_remaining, thresholds):
                headline = "Eliminated on current scoring"
            print(f"====== {RED}{name}{RESET} {headline} ======")
            reported += 1
            note = tiebreak_note(team, weeks_remaining, thresholds, eliminated=True)
            if note:
                print(f"       {DIM}{note}{RESET}")
            continue

        lines = paths_for(scenarios, name, "elim")
        if not lines:
            continue
        reported += 1
        print(f"====== {RED}{name}{RESET} Eliminated from playoffs with: ======")
        emit(lines)
        note = tiebreak_note(team, weeks_remaining, thresholds, eliminated=True)
        if note:
            print(f"       {DIM}{note}{RESET}")

    if not reported:
        print(nothing_yet("elimination", weeks_remaining))


if __name__ == "__main__":
    main()
