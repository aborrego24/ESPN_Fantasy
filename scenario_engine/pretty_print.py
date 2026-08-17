import argparse
import json
import sys

import margins

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"

WIDTH = 78

VERDICT_COLOUR = {"bye": CYAN, "clinched": GREEN, "eliminated": RED, "alive": YELLOW}

# The key names the level; the label is what a reader sees. Separate because the
# key also becomes an HTML class, and "clinched bye" is two words.
STATUS_LABEL = {
    "bye": "clinched bye",
    "clinched": "clinched",
    "alive": "alive",
    "eliminated": "eliminated",
}


def display_status(team):
    """Which of the four levels a team is at, best first.

    A bye outranks a plain place because it is strictly more: nobody holds a bye
    without also holding a seat. Kept separate from `verdict`, which stays a
    three-way playoff answer so that code asking "did they clinch a place" still
    counts the teams who did.
    """
    if team.get("bye") == "clinched":
        return "bye"
    return team["verdict"]


def status_label(team):
    """How that level reads."""
    return STATUS_LABEL[display_status(team)]


def rule(title=""):
    if not title:
        return "-" * WIDTH
    pad = WIDTH - len(title) - 2
    left = pad // 2
    return f"{'-' * left} {title} {'-' * (pad - left)}"


def banner(title, visible_len=None):
    """Centre a title in '=' padding.

    `visible_len` lets a colour-wrapped title be padded by how wide it prints
    rather than how many characters it contains.
    """
    length = len(title) if visible_len is None else visible_len
    pad = WIDTH - length - 2
    left = pad // 2
    return f"{'=' * left} {title} {'=' * (pad - left)}"


def find_scenario(scenarios, team):
    for entry in scenarios:
        if entry["team"] == team:
            return entry
    return None


def phrase_alternative(alternative):
    """One alternative as a sentence, e.g. 'a WIN and Momma Gus WIN'.

    A phrase that names the team's own result pins it; one that does not is
    silent about it because it genuinely does not matter. Saying so out loud read
    as a caveat and pulled attention away from the condition that counts.

    Kept free of any terminal formatting so the HTML report words every scenario
    identically -- two renderers phrasing the same result differently would be a
    bug nobody would notice for months.
    """
    needed = [f"{c['winner']} WIN" for c in alternative["conditions"]]
    head = {"win": "a WIN", "loss": "a LOSS"}.get(alternative["own"])

    if head and needed:
        return f"{head} and {' and '.join(needed)}"
    if head:
        return head
    if needed:
        return " and ".join(needed)
    return "any result"


def describe(alternatives):
    """One line per alternative, bulleted for the terminal."""
    return [f"  - {phrase_alternative(a)}" for a in alternatives]


def emit(lines):
    for i, line in enumerate(lines):
        if i:
            print("    or ... ")
        print(line)


def paths_for(scenarios, name, key):
    entry = find_scenario(scenarios, name)
    if not entry:
        return None
    alternatives = entry.get(key)
    if not alternatives:
        return None
    return describe(alternatives)


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
        team.get("tiebreak"),
        weeks_remaining,
        thresholds,
        eliminated=eliminated,
        margins=team.get("margins"),
    )


def summarise(standings, league):
    """Counts for the header: how much is settled and how much is still open."""
    counts = {"clinched": 0, "eliminated": 0, "alive": 0}
    for team in standings:
        counts[team["verdict"]] += 1
    counts["up_for_grabs"] = max(league["playoff_spots"] - counts["clinched"], 0)
    return counts


def header_title(league):
    """Where the season stands, worded for the phase it is in.

    Returned in ordinary case; the terminal banner upper-cases it. Keeping the
    caps out of the wording lets the HTML report share this exact sentence
    instead of title-casing it back into something else.
    """
    remaining = league["remaining_weeks"]
    playoffs_start = league["num_weeks"] + 1

    if remaining == 0:
        return f"Regular season complete  ·  Playoffs begin week {playoffs_start}"
    if remaining == 1:
        # The last week before the playoffs is its own occasion; counting weeks
        # remaining and announcing when the playoffs start says nothing here.
        return "Final week of the regular season"
    return (
        f"Going into week {league['current_week'] + 1}"
        f"  ·  Playoffs begin week {playoffs_start}"
    )


def print_header(standings, league):
    """Where the league stands at a glance, before any of the detail."""
    counts = summarise(standings, league)

    print(f"\n{BOLD}{banner(header_title(league).upper())}{RESET}")
    print(
        f"  Playoff spots {BOLD}{league['playoff_spots']}{RESET}"
        f"   ·   {GREEN}Clinched {counts['clinched']}{RESET}"
        f"   ·   Up for grabs {BOLD}{counts['up_for_grabs']}{RESET}"
        f"   ·   {YELLOW}Still alive {counts['alive']}{RESET}"
        f"   ·   {RED}Eliminated {counts['eliminated']}{RESET}"
    )


def print_standings(standings, league):
    """Current table, with the playoff cut line drawn in."""
    spots = league["playoff_spots"]
    width = max(len(t["team_name"]) for t in standings)

    print(f"\n{rule('STANDINGS')}")
    print(
        f"{DIM}      {'TEAM':<{width}}  {'RECORD':>6}  {'POINTS FOR':>10}  STATUS{RESET}"
    )
    for position, team in enumerate(standings, 1):
        if position == spots + 1:
            print(f"{DIM}{rule('playoff cut line')}{RESET}")
        record = f"{team['wins']}-{team['losses']}"
        colour = VERDICT_COLOUR.get(display_status(team), "")
        print(
            f"  {position:2d}  {team['team_name']:<{width}}  "
            f"{record:>6}  {team['points_for']:>10.1f}  "
            f"{colour}{status_label(team)}{RESET}"
        )


def print_matchups(matchups, league):
    """Who plays whom next week -- the games every condition refers to."""
    if not matchups:
        print(f"\n{rule('NEXT WEEK')}")
        print("  No games left to play.")
        return

    week = league["current_week"] + 1
    width = max(len(m["team1"]) for m in matchups)
    print(f"\n{rule(f'WEEK {week} MATCHUPS')}")
    for matchup in matchups:
        print(f"  {matchup['team1']:<{width}}  vs  {matchup['team2']}")


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="pretty_print.py",
        description="Render the scenario payload as English.",
    )
    parser.add_argument(
        "--no-header", action="store_true", help="hide the summary header"
    )
    parser.add_argument(
        "--no-standings", action="store_true", help="hide the standings table"
    )
    parser.add_argument(
        "--no-matchups", action="store_true", help="hide next week's matchups"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    data = json.load(sys.stdin)
    base = data["base_league_data"]
    standings = base["standings"]
    scenarios = data["scenarios"]
    league = base["league_data"]
    weeks_remaining = league["remaining_weeks"]
    thresholds = margins.load_thresholds()

    if not args.no_header:
        print_header(standings, league)
    if not args.no_standings:
        print_standings(standings, league)
    if not args.no_matchups:
        print_matchups(base["next_week_matchups"], league)

    print(f"\n{banner(f'{GREEN}CLINCH SCENARIOS{RESET}', len('CLINCH SCENARIOS'))}")
    reported = 0
    for team in standings:
        name = team["team_name"]

        if team["verdict"] == "clinched":
            headline = "Clinched Playoff Spot"
            if margins.qualifies_headline(
                team.get("tiebreak"), weeks_remaining, thresholds
            ):
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

    print(
        f"\n{banner(f'{RED}ELIMINATION SCENARIOS{RESET}', len('ELIMINATION SCENARIOS'))}"
    )
    reported = 0
    for team in standings:
        name = team["team_name"]

        if team["verdict"] == "eliminated":
            headline = "Eliminated from playoffs"
            if margins.qualifies_headline(
                team.get("tiebreak"), weeks_remaining, thresholds
            ):
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
