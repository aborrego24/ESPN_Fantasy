"""Stage 5, HTML: the report as a self-contained page.

Two things are worth guarding here beyond "it produced output". The page must be
well-formed and properly escaped -- real team names in this league contain
apostrophes, quotes and a `#` -- and it must say the same things the terminal
says, since a second renderer that words a verdict differently is a bug that
would go unnoticed for a long time.
"""

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

import league_stats
import pretty_print
import to_html

REPO_ROOT = Path(__file__).parent.parent

VOID = {"meta", "br", "hr", "img", "input", "link"}


class Wellformed(HTMLParser):
    """Every tag opened must be closed, in order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
        elif self.stack[-1] != tag:
            self.errors.append(f"</{tag}> closes <{self.stack[-1]}>")
        else:
            self.stack.pop()


def assert_wellformed(document):
    parser = Wellformed()
    parser.feed(document)
    assert not parser.errors, parser.errors
    assert not parser.stack, f"never closed: {parser.stack}"


def text_of(document):
    """Visible text, with tags and the style block removed."""
    chunks = []
    skipping = [False]

    class Extract(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag in ("style", "script"):
                skipping[0] = True

        def handle_endtag(self, tag):
            if tag in ("style", "script"):
                skipping[0] = False

        def handle_data(self, data):
            if not skipping[0]:
                chunks.append(data)

    parser = Extract()
    parser.convert_charrefs = True
    parser.feed(document)
    return " ".join(" ".join(chunks).split())


def team(name, wins, losses, points, verdict, margins=None, tiebreak=None):
    return {
        "team_name": name,
        "wins": wins,
        "losses": losses,
        "points_for": points,
        "verdict": verdict,
        "status": verdict,
        "margins": margins or [],
        "tiebreak": tiebreak,
    }


def weekly(names, weeks=2):
    """Distinct scores per team per week, so no comparison is ever a tie."""
    return [
        {
            "name": name,
            "weeks": [
                {
                    "week": w + 1,
                    "points": 100.0 + 10 * i + w,
                    "opponent": names[(i + 1) % len(names)]
                    if (i + 1) % len(names) != i
                    else None,
                }
                for w in range(weeks)
            ],
        }
        for i, name in enumerate(names)
    ]


def payload(
    standings,
    scenarios=None,
    matchups=None,
    weekly_scores=None,
    abbreviations=None,
    **league,
):
    """Build a stage-4 payload.

    Anything not named above lands in league_data, so a misspelled argument
    becomes a league setting rather than an error -- keep the signature in step
    with the payload when a new key is added.
    """
    settings = {
        "playoff_spots": 2,
        "num_weeks": 4,
        "remaining_weeks": 2,
        "current_week": 2,
    }
    settings.update(league)
    return {
        "base_league_data": {
            "league_data": settings,
            "standings": standings,
            "next_week_matchups": matchups if matchups is not None else [],
            "weekly_scores": weekly_scores or [],
            "abbreviations": abbreviations or {},
        },
        "scenarios": scenarios or [],
    }


BASIC = payload(
    [
        team("Alpha", 3, 0, 400.0, "clinched"),
        team("Bravo", 2, 1, 380.0, "alive", margins=[["Charlie", 12.5]]),
        team("Charlie", 1, 2, 367.5, "alive"),
        team("Delta", 0, 3, 300.0, "eliminated"),
    ],
    scenarios=[
        {
            "team": "Bravo",
            "clinch": [
                {"own": "win", "conditions": []},
                {"own": None, "conditions": [{"matchup": 1, "winner": "Delta"}]},
            ],
        },
        {"team": "Charlie", "elim": [{"own": "loss", "conditions": []}]},
    ],
    matchups=[
        {"team1": "Alpha", "team2": "Bravo"},
        {"team1": "Charlie", "team2": "Delta"},
    ],
)


# --- structure ----------------------------------------------------------------


def test_the_document_is_wellformed():
    assert_wellformed(to_html.render(BASIC))


def test_the_page_is_self_contained():
    """No network, no assets: it has to work from a file:// URL forever."""
    document = to_html.render(BASIC)

    assert "<style>" in document
    assert "<script" not in document
    for pattern in ("http://", "https://", "src=", "@import"):
        assert pattern not in document, f"pulls in {pattern}"


def test_every_section_appears_by_default():
    headings = re.findall(r"<h2>(.*?)</h2>", to_html.render(BASIC))

    assert headings == [
        "Standings",
        "Week 3 Matchups",
        "Clinch Scenarios",
        "Elimination Scenarios",
    ]


def test_sections_can_be_switched_off_individually():
    document = to_html.render(BASIC, {"scenarios"})

    assert "Standings" not in re.findall(r"<h2>(.*?)</h2>", document)
    assert "Clinch Scenarios" in document
    assert "<h1>" not in document


@pytest.mark.parametrize(
    "flag,heading",
    [
        ("--no-standings", "Standings"),
        ("--no-matchups", "Matchups"),
    ],
)
def test_the_no_flags_drop_their_section(flag, heading):
    show = to_html.sections(to_html.parse_args([flag]))

    assert heading not in " ".join(re.findall(r"<h2>(.*?)</h2>", to_html.render(BASIC, show)))


# --- escaping -----------------------------------------------------------------


def test_team_names_with_punctuation_are_escaped():
    """Real names here include "I can't let you get close" and 'Villoni #2'."""
    nasty = "Ben's \"Underrated\" <b>Team</b> & #2"
    document = to_html.render(payload([team(nasty, 1, 0, 10.0, "clinched")]))

    assert_wellformed(document)
    assert nasty not in document, "name went in raw"
    assert "<b>Team</b>" not in document
    assert nasty in text_of(document), "escaping must not change what it reads as"


def test_a_team_named_like_a_script_tag_stays_inert():
    document = to_html.render(
        payload([team("<script>alert(1)</script>", 1, 0, 10.0, "alive")])
    )

    assert "<script" not in document
    assert_wellformed(document)


def test_conditions_naming_a_punctuated_team_are_escaped():
    document = to_html.render(
        payload(
            [team("Alpha", 1, 0, 10.0, "alive")],
            scenarios=[
                {
                    "team": "Alpha",
                    "clinch": [
                        {"own": None, "conditions": [{"matchup": 0, "winner": "A&B's"}]}
                    ],
                }
            ],
        )
    )

    assert "A&B's" not in document
    assert "A&amp;B" in document
    assert_wellformed(document)


# --- the same words as the terminal -------------------------------------------


def test_the_headline_is_the_shared_wording():
    for remaining, expected in (
        (0, "Regular Season Complete"),
        (1, "Final Week Of The Regular Season"),
        (3, "Going Into Week 3"),
    ):
        document = to_html.render(
            payload([team("Alpha", 1, 0, 10.0, "alive")], remaining_weeks=remaining)
        )
        assert expected in text_of(document)


def test_every_scenario_phrase_is_one_the_terminal_would_print():
    """The anti-drift check: no phrasing may originate in the HTML renderer."""
    document = text_of(to_html.render(BASIC))

    for entry in BASIC["scenarios"]:
        for key in ("clinch", "elim"):
            for alternative in entry.get(key, []):
                assert pretty_print.phrase_alternative(alternative) in document


def test_an_empty_section_says_so_in_the_shared_wording():
    """A heading with nothing under it reads as a broken tool."""
    document = to_html.render(payload([team("Alpha", 1, 0, 10.0, "alive")]))

    assert pretty_print.nothing_yet("clinch", 2).strip() in text_of(document)
    assert pretty_print.nothing_yet("elimination", 2).strip() in text_of(document)


def test_the_counts_match_the_shared_summary():
    counts = pretty_print.summarise(
        BASIC["base_league_data"]["standings"], BASIC["base_league_data"]["league_data"]
    )
    document = text_of(to_html.render(BASIC))

    assert f"Clinched {counts['clinched']}" in document
    assert f"Eliminated {counts['eliminated']}" in document
    assert f"Still alive {counts['alive']}" in document
    assert f"Up for grabs {counts['up_for_grabs']}" in document


# --- standings ----------------------------------------------------------------


def test_each_team_carries_its_verdict():
    document = to_html.render(BASIC)

    for entry in BASIC["base_league_data"]["standings"]:
        assert f'<span class="pill {entry["verdict"]}">{entry["verdict"]}</span>' in document


def test_the_cut_line_falls_under_the_last_qualifying_team():
    """Two spots, so the rule goes under row two and nowhere else."""
    document = to_html.render(BASIC)
    rows = re.findall(r"<tr(?: class=\"cut\")?><td class=\"num\">(\d+)</td>", document)
    cut_rows = re.findall(r'<tr class="cut"><td class="num">(\d+)</td>', document)

    assert rows[:4] == ["1", "2", "3", "4"]
    assert cut_rows == ["2"]


def test_no_games_left_is_stated_rather_than_left_blank():
    document = to_html.render(
        payload([team("Alpha", 1, 0, 10.0, "clinched")], remaining_weeks=0, matchups=[])
    )

    assert "No games left to play." in text_of(document)


# --- season review tables -----------------------------------------------------


def test_the_review_tables_are_omitted_without_a_weekly_history():
    """Payloads saved before stage 1 emitted it must still render."""
    headings = re.findall(r"<h2>(.*?)</h2>", to_html.render(BASIC))

    assert "All-Play Record" not in headings
    assert "Schedule Luck" not in headings


def test_the_review_tables_appear_once_the_history_is_there():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )
    headings = re.findall(r"<h2>(.*?)</h2>", document)

    assert "All-Play Record" in headings
    assert "Schedule Luck" in headings
    assert "What The Draw Was Worth" in headings
    assert_wellformed(document)


def test_the_all_play_totals_shown_are_the_computed_ones():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    history = weekly(names)
    document = text_of(
        to_html.render(
            payload(
                [team(n, 1, 1, 100.0, "alive") for n in names],
                weekly_scores=history,
            )
        )
    )

    for row in league_stats.all_play_records(history):
        assert to_html.record_text(row["total"]) in document


def test_the_matrix_is_square_and_numbered_to_match_its_rows():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )
    matrix = document.split("Schedule Luck")[1].split("</table>")[0]
    body = matrix.split("<tbody>")[1]

    for index, row in enumerate(re.findall(r"<tr>(.*?)</tr>", body), 1):
        assert row.count("<td") == len(names) + 1, "one cell per schedule, plus the name"
        assert f'class="name">{index}. ' in row


def test_the_diagonal_is_marked_as_the_teams_own_record():
    names = ["Alpha", "Bravo", "Charlie"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )
    matrix = document.split("Schedule Luck")[1].split("</table>")[0]

    assert matrix.count('class="num self"') == len(names), "one per row"


def test_record_text_reports_ties_only_when_there_are_any():
    assert to_html.record_text({"wins": 9, "losses": 4, "ties": 0}) == "9-4"
    assert to_html.record_text({"wins": 9, "losses": 4, "ties": 1}) == "9-4-1"


# --- the command itself -------------------------------------------------------


def test_output_goes_to_the_named_file(tmp_path, monkeypatch, capsys):
    destination = tmp_path / "out.html"
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(BASIC)))

    assert to_html.main(["-o", str(destination)]) == 0

    assert destination.read_text().startswith("<!DOCTYPE html>")
    assert "out.html" in capsys.readouterr().err


def test_with_no_output_flag_it_writes_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(BASIC)))

    assert to_html.main([]) == 0

    assert capsys.readouterr().out.startswith("<!DOCTYPE html>")


@pytest.mark.parametrize("name", ["week12.json", "week13.json", "PC_test.json"])
def test_the_real_pipeline_produces_a_wellformed_page(name):
    """Straight through stages 1-4 by subprocess, then rendered."""
    stages = [
        ["scenario_engine/league_data.py", "--test", f"scenario_engine_tests/{name}"],
        ["scenario_engine/refine_current_week.py"],
        ["scenario_engine/generate_perms.py"],
        ["scenario_engine/refine_hypothetical.py"],
    ]
    data = ""
    for stage in stages:
        result = subprocess.run(
            [sys.executable, *stage],
            input=data,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr
        data = result.stdout

    document = to_html.render(json.loads(data))
    assert_wellformed(document)
    assert document.startswith("<!DOCTYPE html>")


# --- team monograms -----------------------------------------------------------


def test_the_espn_abbreviation_is_used_when_there_is_one():
    assert to_html.monogram("Momma Gus", {"Momma Gus": "MGPY"}) == "MGPY"
    assert to_html.monogram("Klorgon", {"Klorgon": "tcgp"}) == "TCGP"


def test_initials_stand_in_when_no_abbreviation_was_recorded():
    """Payloads saved before stage 1 carried abbreviations still get a label."""
    assert to_html.monogram("Momma Gus", {}) == "MG"
    assert to_html.monogram("I can't let you get close", None) == "ICLY"


def test_a_name_with_nothing_to_take_initials_from_still_yields_something():
    assert to_html.monogram("!!!", {}) == "!!"
    assert to_html.monogram("#2", {}) == "#2"


def test_a_monogram_colour_is_stable_across_runs():
    """hash() is salted per process, so a team would change colour every run."""
    first = to_html.monogram_colour("Momma Gus")

    assert first == to_html.monogram_colour("Momma Gus")
    assert first.startswith("hsl(")
    assert first != to_html.monogram_colour("Klorgon")


def test_every_standings_row_and_matchup_side_carries_a_chip():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            matchups=[
                {"team1": "Alpha", "team2": "Bravo"},
                {"team1": "Charlie", "team2": "Delta"},
            ],
            abbreviations={n: n[:3].upper() for n in names},
        )
    )
    standings = document.split("<h2>Standings</h2>")[1].split("</table>")[0]
    matchups = document.split("Matchups</h2>")[1].split("</table>")[0]

    assert standings.count('class="mono"') == 4
    assert matchups.count('class="mono"') == 4
    # the supplied abbreviations must actually be the ones shown, not initials
    for name in names:
        assert f">{name[:3].upper()}<" in standings
    assert_wellformed(document)


def test_a_chip_does_not_reach_out_to_the_network():
    """The whole point of not using ESPN's logo URLs: 6 of 10 need auth."""
    document = to_html.render(BASIC)

    assert "<img" not in document
    for pattern in ("http://", "https://", "src=", "@import"):
        assert pattern not in document


def test_a_punctuated_abbreviation_is_escaped():
    document = to_html.render(
        payload(
            [team("Alpha", 1, 0, 10.0, "alive")],
            abbreviations={"Alpha": "A&B<"},
        )
    )

    assert "A&amp;B" in document
    assert "A&B<" not in document
    assert_wellformed(document)
