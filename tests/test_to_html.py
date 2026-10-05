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


def team(name, wins, losses, points, verdict, margins=None, tiebreak=None,
         top_seed=None, bye=None, division_winner=None):
    return {
        "team_name": name,
        "wins": wins,
        "losses": losses,
        "points_for": points,
        "verdict": verdict,
        "status": verdict,
        "margins": margins or [],
        "tiebreak": tiebreak,
        "top_seed": top_seed,
        "bye": bye,
        "division_winner": division_winner,
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
    logos=None,
    divisions=None,
    division_names=None,
    managers=None,
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
            "logos": logos or {},
            "divisions": divisions,
            "division_names": division_names or {},
            "managers": managers or {},
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


# --- divisional standings ------------------------------------------------------


DIVISIONAL = payload(
    [
        team("East A", 4, 0, 400.0, "clinched", top_seed="clinched"),
        team("West A", 3, 1, 380.0, "clinched", bye="clinched"),
        team("East B", 2, 2, 360.0, "alive"),
        team("West B", 1, 3, 340.0, "alive"),
        team("East C", 0, 4, 300.0, "eliminated"),
        team("West C", 0, 4, 280.0, "eliminated"),
    ],
    divisions={
        "East A": 0, "East B": 0, "East C": 0,
        "West A": 1, "West B": 1, "West C": 1,
    },
    division_names={0: "East Division", 1: "West Division"},
    playoff_spots=4,
)


def test_a_divisional_league_gets_a_view_selector_defaulting_to_overall():
    document = to_html.render(DIVISIONAL)

    # a segmented selector: Overall (active) + one button per division
    assert 'id="std-seg"' in document
    assert '<button data-view="overall" class="on">Overall</button>' in document
    assert ">East Division</button>" in document and ">West Division</button>" in document
    # rigid, square buttons
    assert "border-radius: 0" in document
    # overall is the default view (shown); division views are present but hidden
    assert '<div class="std-view" data-view="overall">' in document
    assert '<div class="std-view" data-view="d0" hidden>' in document
    # the overall view carries every team
    overall = document.split('data-view="overall">')[1].split("</div>")[0]
    for name in ("East A", "West A", "East C", "West C"):
        assert name in overall
    assert_wellformed(document)


def test_a_division_view_is_ranked_within_the_division():
    """Each division view restarts # at 1 and follows that division's record."""
    document = to_html.render(DIVISIONAL)
    east = document.split('data-view="d0" hidden>')[1].split("</div>")[0]

    assert "East A" in east and "West A" not in east, "one division only"
    ranks = re.findall(r'<td class="num">(\d+)</td><td>', east)
    assert ranks[:3] == ["1", "2", "3"], "within-division rank starts at 1"


def test_a_single_division_league_has_no_selector():
    """No divisions -> one table, no switcher, cut line intact."""
    document = to_html.render(BASIC)

    assert 'id="std-seg"' not in document
    assert "playoff cut line" in document


def test_the_division_names_come_through_even_as_json_string_keys():
    """The payload round-trips through JSON, which turns the int ids into strings."""
    data = json.loads(json.dumps(DIVISIONAL))  # ids in division_names become "0"/"1"
    document = to_html.render(data)

    assert ">East Division</button>" in document and ">West Division</button>" in document
    assert "Division 0" not in document, "fell back to the id instead of the name"


# --- races folded into the standings selector ---------------------------------


def _view(document, view_id):
    """The inner HTML of one std-view, by its data-view id (not the button)."""
    marker = f'<div class="std-view" data-view="{view_id}"'
    return document.split(marker)[1].split("</div>")[0]


def test_the_seed_race_is_a_selector_view_of_the_still_alive():
    document = to_html.render(
        payload(
            [
                team("Alpha", 3, 1, 400.0, "clinched", top_seed="alive"),
                team("Bravo", 3, 1, 390.0, "clinched", top_seed="alive"),
                team("Charlie", 1, 3, 300.0, "alive", top_seed="eliminated"),
            ]
        )
    )

    assert ">#1 Seed</button>" in document
    seed = _view(document, "seed")
    assert "Alpha" in seed and "Bravo" in seed
    assert "Charlie" not in seed, "a team out of the #1-seed race is left out"
    # a race view is not a dropdown any more. Checked past the stylesheet, since
    # the all-time weight panel legitimately is a disclosure element.
    assert "<details" not in document.split("</style>")[-1]
    assert_wellformed(document)


def test_no_seed_button_once_the_top_seed_is_clinched():
    document = to_html.render(
        payload(
            [
                team("Alpha", 4, 0, 400.0, "clinched", top_seed="clinched"),
                team("Bravo", 2, 2, 300.0, "alive", top_seed="eliminated"),
            ]
        )
    )

    assert ">#1 Seed</button>" not in document


def test_no_seed_button_when_nobody_can_still_take_it():
    document = to_html.render(
        payload([team("Alpha", 1, 0, 10.0, "alive", top_seed="eliminated")])
    )

    assert ">#1 Seed</button>" not in document
    assert 'id="std-seg"' not in document, "no extra views -> no selector at all"


def _divisional_race_payload():
    return payload(
        [
            team("East A", 3, 1, 400.0, "clinched", division_winner="alive"),
            team("East B", 3, 1, 390.0, "alive", division_winner="alive"),
            team("East C", 0, 4, 300.0, "eliminated", division_winner="eliminated"),
            team("West A", 4, 0, 420.0, "clinched", division_winner="clinched"),
            team("West B", 1, 3, 320.0, "alive", division_winner="eliminated"),
            team("West C", 0, 4, 280.0, "eliminated", division_winner="eliminated"),
        ],
        divisions={
            "East A": 0, "East B": 0, "East C": 0,
            "West A": 1, "West B": 1, "West C": 1,
        },
        division_names={0: "East", 1: "West"},
        playoff_spots=4,
    )


def test_the_wildcard_is_a_selector_view_of_the_still_alive_non_winners():
    document = to_html.render(_divisional_race_payload())

    assert ">Wildcard</button>" in document
    wild = _view(document, "wild")
    assert "East B" in wild and "West B" in wild
    assert "West A" not in wild, "a clinched division winner is not a wildcard"
    assert "East C" not in wild, "an eliminated team is not in the race"
    assert "wildcard spot" in document
    assert_wellformed(document)


def test_the_race_views_are_absent_in_a_non_divisional_league_without_a_race():
    document = to_html.render(BASIC)

    assert ">Wildcard</button>" not in document
    assert 'id="std-seg"' not in document


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


def luck_matrix(document):
    return document.split("Schedule Luck")[1].split("</table>")[0]


def all_play_cells(document):
    """The weekly cells, row by row, as (text, css class) pairs."""
    table = document.split("All-Play Record")[1].split("</table>")[0]
    body = table.split("<tbody>")[1]
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", body):
        cells = re.findall(r'<td class="num([^"]*)">([^<]*)</td>', row)
        # the last two are the all-play record and the percentage, not weeks
        rows.append([(text, css.strip()) for css, text in cells[:-2]])
    return rows


def test_a_weekly_cell_is_a_placing_counted_from_one():
    """Not "teams out-scored", which starts at zero for the week's worst score."""
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )

    rows = all_play_cells(document)
    assert [len(row) for row in rows] == [2] * len(names), "one cell per team per week"
    placings = {int(text) for row in rows for text, _ in row}
    assert placings <= set(range(1, len(names) + 1)), "outside 1..teams"
    assert 0 not in placings
    # weekly() gives every team a distinct score, so every place is taken
    for column in zip(*rows):
        assert sorted(int(text) for text, _ in column) == list(
            range(1, len(names) + 1)
        ), "a week's placings must be 1..N with no repeats"


def test_only_the_weeks_best_and_worst_score_are_marked():
    """Shading the near-misses too coloured most of the table."""
    names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )

    rows = all_play_cells(document)
    for column in zip(*rows):
        marked = {css: text for text, css in column if css}
        assert marked == {"best": "1", "worst": str(len(names))}, (
            f"expected exactly the first and last place marked, got {marked}"
        )


def test_the_placings_agree_with_the_all_play_record_beside_them():
    """The record is the same comparisons counted a different way.

    A team placing Nth out of T out-scored T-N rivals, so the places across a row
    must add up to the wins in the record printed at the end of it.
    """
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    history = weekly(names, weeks=3)
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names], weekly_scores=history
        )
    )

    rows = all_play_cells(document)
    computed = league_stats.all_play_records(history)
    for cells, row in zip(rows, computed):
        assert sum(len(names) - int(text) for text, _ in cells) == row["total"]["wins"]


def test_the_matrix_is_square():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )
    body = luck_matrix(document).split("<tbody>")[1]

    for row in re.findall(r"<tr>(.*?)</tr>", body):
        assert row.count("<td") == len(names) + 1, "one cell per schedule, plus the name"


def test_each_schedule_column_is_labelled_with_whose_schedule_it_is():
    """A bare column number makes the reader count back to the rows to decode it.

    The point of the table is "my scores against your opponents", so a cell is
    unreadable until both the row's team and the column's team are named.
    """
    names = ["Alpha", "Bravo", "Charlie"]
    abbreviations = {"Alpha": "ALF", "Bravo": "BRV", "Charlie": "CHZ"}
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
            abbreviations=abbreviations,
        )
    )
    matrix = luck_matrix(document)
    head, body = matrix.split("<tbody>")

    for name, tag in abbreviations.items():
        assert f">{tag}</span>" in head, f"{name} is not a column head"
    # and the row carries the same tag, so the two axes can be matched up
    for row in re.findall(r"<tr>(.*?)</tr>", body):
        name = re.search(r"</span>([^<]+)</td>", row).group(1)
        assert f">{abbreviations[name]}</span>" in row


def test_colliding_short_labels_fall_back_to_numbers():
    """Two columns sharing a label is worse than a label that carries no meaning.

    Without ESPN's abbreviations the labels are initials, which can collide --
    here on "B". Numbering is then the only unambiguous option left.
    """
    assert to_html.column_labels(["Bravo Two", "Bravo Three"], {}) == ["1", "2"]
    assert to_html.column_labels(["Alpha", "Bravo"], {}) == ["A", "B"]
    assert to_html.column_labels(
        ["Bravo Two", "Bravo Three"], {"Bravo Two": "B2", "Bravo Three": "B3"}
    ) == ["B2", "B3"]


def test_the_axes_are_named_in_the_table_head():
    names = ["Alpha", "Bravo", "Charlie"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )

    assert "borrowing the schedule of" in text_of(luck_matrix(document))


def test_a_one_team_league_does_not_claim_a_team_borrowed_its_own_schedule():
    """The worked example names the first row and the last column, which with a
    single team would be the same team."""
    document = to_html.render(
        payload(
            [team("Alpha", 1, 1, 100.0, "alive")], weekly_scores=weekly(["Alpha"])
        )
    )

    assert "had it played Alpha's schedule" not in text_of(document)
    assert_wellformed(document)


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


# --- strength of schedule / record --------------------------------------------


def test_strength_section_appears_with_a_weekly_history():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )

    assert "Strength of Schedule" in re.findall(r"<h2>(.*?)</h2>", document).__str__()
    assert_wellformed(document)


def test_strength_section_is_omitted_without_a_weekly_history():
    assert "Strength of Schedule" not in to_html.render(BASIC)


def test_sor_is_coloured_by_its_sign():
    """A positive strength of record reads green, a negative one red."""
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    section = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    ).split("Strength of Schedule")[1].split("</table>")[0]

    # every SOR cell carries exactly one direction class, matching its sign
    cells = re.findall(r'<td class="num sos-sor (better|worse)">([^<]*)</td>', section)
    assert cells, "no coloured SOR cells found"
    for css, text in cells:
        assert (css == "better") == text.startswith("+")


def test_the_to_come_column_appears_only_when_games_remain():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    finished = payload(
        [team(n, 1, 1, 100.0, "alive") for n in names], weekly_scores=weekly(names)
    )
    assert "To&nbsp;come" not in to_html.render(finished)

    with_games = payload(
        [team(n, 1, 1, 100.0, "alive") for n in names], weekly_scores=weekly(names)
    )
    with_games["base_league_data"]["remaining_matchups"] = [
        [{"team1": "Alpha", "team2": "Bravo"}, {"team1": "Charlie", "team2": "Delta"}]
    ]
    assert "To&nbsp;come" in to_html.render(with_games)


def test_the_to_come_number_hovers_to_a_week_by_week_breakdown():
    """Each upcoming game is listed as 'week OPP : PPG', matching the engine."""
    import strength

    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    history = weekly(names)
    remaining = [
        [{"team1": "Alpha", "team2": "Bravo"}, {"team1": "Charlie", "team2": "Delta"}]
    ]
    doc_payload = payload(
        [team(n, 1, 1, 100.0, "alive") for n in names],
        weekly_scores=history,
        current_week=2,
    )
    # remaining_matchups lives on base_league_data, not among the league settings
    doc_payload["base_league_data"]["remaining_matchups"] = remaining
    doc = to_html.render(doc_payload)

    section = doc.split("Strength of Schedule")[1].split("</table>")[0]
    # the tooltip data cells are the only class-less spans in the section
    data = re.findall(r"<span>([^<]*)</span>", section)
    triples = {tuple(data[i : i + 3]) for i in range(0, len(data), 3)}

    engine = strength.strength_table(history, remaining)
    expected = set()
    for row in engine:
        for d in row["remaining"]:
            # current_week 2, offset 0 -> week 3
            expected.add(
                (str(3 + d["week_offset"]), to_html.monogram(d["opponent"], {}), f'{d["value"]:.1f}')
            )
    assert triples == expected


def test_a_finished_season_has_no_hover_and_no_to_come_cell():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    doc = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names], weekly_scores=weekly(names)
        )
    )
    section = doc.split("Strength of Schedule")[1].split("</table>")[0]

    assert "tipbox" not in section


def test_preseason_strength_appears_from_projections_before_any_game():
    """No weekly history, but projections and a schedule -> a preseason SOS."""
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    p = payload([team(n, 0, 0, 0.0, "alive") for n in names])  # no weekly_scores
    p["base_league_data"]["projected_ppg"] = {
        "Alpha": 130.0, "Bravo": 120.0, "Charlie": 110.0, "Delta": 100.0
    }
    p["base_league_data"]["remaining_matchups"] = [
        [{"team1": "Alpha", "team2": "Bravo"}, {"team1": "Charlie", "team2": "Delta"}]
    ]
    doc = to_html.render(p)
    headings = re.findall(r"<h2>(.*?)</h2>", doc)

    assert any("Preseason" in h for h in headings)
    assert "weak predictor" in doc, "the low-confidence caveat must be shown"
    assert "tipbox" in doc, "the schedule hover must be present"
    assert "Strength of Schedule &amp; Record" not in doc, "the in-season table needs games"
    assert_wellformed(doc)


def test_sos_display_recentres_on_50_and_widens_the_gap():
    """The engine's ratio (1.0 = average) is shown recentred on 50 and amplified.

    An average schedule reads 50, and a 0.10 spread in the ratio opens to a
    40-point spread on screen instead of the ~10 a bare *100 would give. Rounded
    to one decimal so near-equal schedules still separate.
    """
    assert to_html._sos_display(1.0) == 50.0
    assert to_html._sos_display(None) is None
    assert to_html._sos_display(1.05) - to_html._sos_display(0.95) == pytest.approx(40.0)
    assert to_html._sos_display(1.0011) == 50.4  # 50 + 0.44, to one decimal


def test_played_games_show_the_in_season_table_not_the_preseason_one():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    p = payload(
        [team(n, 1, 1, 100.0, "alive") for n in names], weekly_scores=weekly(names)
    )
    p["base_league_data"]["projected_ppg"] = {n: 100.0 for n in names}
    doc = to_html.render(p)

    assert "Strength of Schedule &amp; Record" in doc
    assert "Preseason" not in doc


def test_the_chart_view_and_axis_pickers_are_present():
    """The section can be flipped to a scatter with selectable axes."""
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    doc = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names], weekly_scores=weekly(names)
        )
    )

    # The same two-button segmented control the all-time pane uses, not a select.
    assert 'id="sos-view-seg"' in doc, "no Table/Chart toggle"
    assert '<button data-view="table" class="on">' in doc, "table is the default"
    assert '<button data-view="chart">' in doc
    assert 'id="sos-x"' in doc and 'id="sos-y"' in doc, "no axis pickers"
    assert 'id="sos-chart"' in doc, "no chart svg"
    # every metric is offered on both axes
    for key, _ in to_html.CHART_METRICS:
        assert f'value="{key}"' in doc
    # default axes are the SOS/SOR quadrant
    for key in ("sos", "sor"):
        assert re.search(rf'<option value="{key}" data-gloss="[^"]*" selected>', doc), key
    assert_wellformed(doc)


def test_the_chart_and_its_axis_pickers_stay_hidden_in_table_view():
    """Regression: the pickers live in #sos-chart-view, whose display:grid
    overrode the `hidden` attribute, leaking the X/Y selects into table view."""
    doc = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in ("Alpha", "Bravo", "Charlie")],
            weekly_scores=weekly(["Alpha", "Bravo", "Charlie"]),
        )
    )

    assert '<div id="sos-chart-view" hidden>' in doc, "chart view starts hidden"
    # ...and the CSS must not let display:grid win over that hidden attribute
    assert "#sos-chart-view[hidden]" in doc


def test_each_axis_picker_explains_its_metric_on_a_question_mark():
    """The plain-words labels at the axis ends are gone -- the ticks say where a
    dot sits. What a metric *means* hangs off the `?` beside its picker, where it
    can be a sentence instead of two words squeezed against the frame."""
    doc = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in ("Alpha", "Bravo", "Charlie")],
            weekly_scores=weekly(["Alpha", "Bravo", "Charlie"]),
        )
    )

    assert 'id="sos-x-hint"' in doc and 'id="sos-y-hint"' in doc
    # The gloss rides on the option, so the hint always matches the choice.
    for key, _, gloss in to_html.SEASON_METRICS:
        assert f'data-gloss="{gloss}"' in doc, key
    # And the old axis-end phrasing is gone from both charts.
    for dropped in ("tough schedule", "underachieving", "low scorer for its year"):
        assert dropped not in doc
    assert "function mean(" in doc, "no average divider for metrics without a fixed one"


def test_the_season_chart_dot_can_be_hovered_for_team_manager_and_record():
    """A four-letter abbreviation cannot say whose team it is or how it is doing,
    so the mark carries the three as data and a card shows them."""
    names = ["Alpha", "Bravo"]
    doc = to_html.render(
        payload(
            [team(n, 2, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
            managers={"Alpha": ["Ann Lee", "Bo Roy"], "Bravo": ["Cy Dee"]},
        )
    )

    assert 'id="sos-tip"' in doc, "no hover card"
    assert 'class="cpt-mark"' in doc, "dots are not one hover target"
    assert 'data-team="Alpha"' in doc
    assert 'data-manager="Lee · Roy"' in doc, "co-managed shows surnames"
    assert 'data-manager="Cy Dee"' in doc, "a lone manager keeps their full name"
    assert 'data-record="2-1"' in doc


def test_the_all_time_pickers_explain_their_metrics_too():
    doc = to_html.render(BASIC, history=HISTORY)

    assert 'id="at-x-hint"' in doc and 'id="at-y-hint"' in doc
    for key, _, gloss in to_html.AT_METRICS:
        assert f'data-gloss="{gloss}"' in doc, key


def test_the_season_chart_numbers_and_grids_every_axis():
    """Same treatment as the all-time chart: gridlines, a number per tick, and a
    tick value that matches the column in the table beside it."""
    js = to_html.STRENGTH_JS
    table = js.split("var TICK = {")[1].split("\n  };")[0]

    for key, _ in to_html.CHART_METRICS:
        assert f"{key}: {{ step:" in table, f"{key} has no gridline spacing"
    assert table.count("mode: 'abs'") == len(to_html.CHART_METRICS), (
        "every season metric reads on sight, so all are labelled with their value"
    )
    assert "class=\"cref\"" in js, "no gridlines"
    assert "class=\"atframe\"" in js, "no frame around the plot"


def test_a_fixed_domain_keeps_the_tick_at_its_far_end():
    """-0.3 / 0.1 is -2.9999999999999996, so a bare ceil() rounds up and drops the
    -0.300 tick off the SOR axis. Both charts step their ticks with the epsilon."""
    for js in (to_html.STRENGTH_JS, to_html.ALL_TIME_JS):
        assert "/ t.step - 1e-9)" in js


def test_an_absolute_tick_lands_on_a_round_number():
    """Stepped out from the plotted mean, Points For read "259 309 359" and every
    gridline sat a fraction away from the value its rounded label claimed."""
    for js in (to_html.STRENGTH_JS, to_html.ALL_TIME_JS):
        assert "Math.ceil((centre - half) / t.step - 1e-9) * t.step" in js


def test_rows_carry_the_fixed_metrics_the_chart_plots():
    """Wins, PPG, Points For and Opp PPG ride on each row for the chart's axes."""
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    standings = [team(n, 3, 1, 448.0, "alive") for n in names]  # 448 over 2 weeks -> 224 ppg
    doc = to_html.render(payload(standings, weekly_scores=weekly(names), current_week=2))
    section = doc.split("Strength of Schedule")[1].split("</table>")[0]

    row = re.search(r"<tr [^>]*>", section).group(0)
    assert 'data-wins="3' in row
    assert 'data-pf="448' in row
    assert 'data-ppg="224' in row  # 448 / 2 weeks
    assert 'data-abbr="' in row and 'data-color="hsl(' in row


def test_the_slider_and_benchmark_controls_are_present():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
        )
    )

    assert 'id="sos-blend"' in document, "no weighting slider"
    assert 'id="sos-bench"' not in document, "the benchmark toggle was removed"
    assert "addEventListener" in document, "no enhancing script"
    assert_wellformed(document)


def test_the_embedded_row_data_matches_the_engine():
    """The slider recomputes SOS in the browser from these attributes, so they
    must equal what the engine computed, or the interactive view would drift from
    the static one it was rendered from."""
    import strength

    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    history = weekly(names)
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names], weekly_scores=history
        )
    )
    section = document.split("Strength of Schedule")[1].split("</table>")[0]
    rows = re.findall(
        r'<tr data-pi="([^"]*)" data-ri="([^"]*)" data-sor="([^"]*)"'
        r'[^>]*>.*?</span>([^<]*)</td>',
        section,
    )
    assert len(rows) == len(names), "one data-bearing row per team"

    engine = {r["name"]: r for r in strength.strength_table(history)}
    for pi, ri, sor, name in rows:
        row = engine[name]
        assert float(pi) == pytest.approx(row["points_index"], abs=1e-6)
        assert float(ri) == pytest.approx(row["record_index"], abs=1e-6)
        assert float(sor) == pytest.approx(row["sor"], abs=1e-6)


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


def test_the_default_report_stays_asset_free():
    """Without --logos the report draws chips only -- no images, no network.

    Logos are opt-in precisely so the default page keeps this property; the
    with-logos case inlines them as data URIs and is covered separately.
    """
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


# --- team logos (opt-in, inlined as data URIs) --------------------------------

LOGO_URI = "data:image/svg+xml;base64,PHN2Zy8+"  # a tiny <svg/>


def test_team_mark_draws_the_logo_when_one_was_inlined():
    # the third argument is the name->class map, not the URIs (which live in CSS)
    mark = to_html.team_mark("Alpha", {"Alpha": "ALF"}, {"Alpha": "lg0"})

    assert mark.startswith('<span class="logo lg0"')
    assert "mono" not in mark, "a logo replaces the chip, not adds to it"


def test_team_mark_falls_back_to_the_chip_without_a_logo():
    assert 'class="mono"' in to_html.team_mark("Alpha", {"Alpha": "ALF"}, {})
    assert 'class="mono"' in to_html.team_mark("Alpha", {"Alpha": "ALF"}, None)
    # a team missing from the logo map still gets its chip
    assert 'class="mono"' in to_html.team_mark("Bravo", {}, {"Alpha": "lg0"})


def test_standings_and_matchups_show_the_logo_when_present():
    names = ["Alpha", "Bravo", "Charlie", "Delta"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            matchups=[
                {"team1": "Alpha", "team2": "Bravo"},
                {"team1": "Charlie", "team2": "Delta"},
            ],
            logos={n: LOGO_URI for n in names},
        )
    )
    standings = document.split("<h2>Standings</h2>")[1].split("</table>")[0]
    matchups = document.split("Matchups</h2>")[1].split("</table>")[0]

    assert standings.count('class="logo ') == 4
    assert matchups.count('class="logo ') == 4
    assert 'class="mono"' not in standings, "logos replace every chip here"
    assert_wellformed(document)


def test_each_logo_is_inlined_exactly_once():
    """The whole point of the refactor: a logo shown in three tables, one copy."""
    names = ["Alpha", "Bravo"]
    uris = {
        "Alpha": "data:image/svg+xml;base64,QUFBQQ==",
        "Bravo": "data:image/svg+xml;base64,QkJCQg==",
    }
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            matchups=[{"team1": "Alpha", "team2": "Bravo"}],
            weekly_scores=weekly(names),
            logos=uris,
        )
    )

    for uri in uris.values():
        assert document.count(uri) == 1, "each URI appears once (in CSS), not per cell"
        assert f'url("{uri}")' in document, "and it is a CSS background rule"
    # yet each team is still marked in several places (standings, matchup, strength)
    assert document.count('class="logo lg') >= 6


def test_a_team_without_a_logo_keeps_its_chip_beside_ones_that_have_them():
    document = to_html.render(
        payload(
            [team("Alpha", 1, 1, 100.0, "alive"), team("Bravo", 1, 1, 90.0, "alive")],
            logos={"Alpha": LOGO_URI},
        )
    )
    standings = document.split("<h2>Standings</h2>")[1].split("</table>")[0]

    assert standings.count('class="logo ') == 1
    assert standings.count('class="mono"') == 1


def test_the_strength_name_cell_carries_the_logo_for_the_chart():
    """The scatter reads the URI off the name cell's logo span at run time, so a
    team with a logo must render that span and one without must not."""
    names = ["Alpha", "Bravo", "Charlie"]
    document = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in names],
            weekly_scores=weekly(names),
            logos={"Alpha": LOGO_URI},
        )
    )
    section = document.split("Strength of Schedule")[1].split("</table>")[0]
    rows = section.split("<tr")
    alpha = next(r for r in rows if ">Alpha<" in r)
    bravo = next(r for r in rows if ">Bravo<" in r)

    assert 'class="logo lg' in alpha, "Alpha's name cell carries the logo span"
    assert 'class="logo lg' not in bravo and 'class="mono"' in bravo, (
        "Bravo has none, so the chart falls back to a circle"
    )


def test_logos_survive_being_switched_off_with_the_stats_section():
    """A logo-bearing payload with stats hidden must still be well-formed."""
    document = to_html.render(
        payload([team("Alpha", 1, 0, 10.0, "alive")], logos={"Alpha": LOGO_URI}),
        {"standings"},
    )
    assert_wellformed(document)


# --- the all-time tab ---------------------------------------------------------


def history_season(year, complete=True, finals=(1, 2), owners=("own-a", "own-b")):
    """A three-team season in the shape tools/fetch_history.py writes.

    Two of the three qualify, so the playoff scope has a real population that is
    smaller than the league -- which is the thing that view has to get right.
    """
    scores = {"Alpha": [120.0, 110.0], "Bravo": [100.0, 105.0], "Charlie": [90.0, 95.0]}
    order = list(scores)
    records = {"Alpha": (2, 0), "Bravo": (1, 1), "Charlie": (0, 2)}
    # Alpha and Bravo met in the final; Charlie missed the bracket entirely.
    playoff = {"Alpha": 130.0, "Bravo": 115.0}
    po_record = {"Alpha": (1, 0), "Bravo": (0, 1)}

    def opponent(name, week):
        return {"Alpha": "Bravo", "Bravo": "Alpha", "Charlie": None}[name]

    return {
        "year": year,
        "name": "Test League",
        "num_teams": 3,
        "weeks_in_season": 2,
        "weeks_played": 2,
        "complete": complete,
        "playoff_spots": 2,
        "teams": [
            {
                "name": name,
                "owner_id": owners[i] if i < len(owners) else f"own-{name}",
                "owner": f"Manager {name}",
                "wins": records[name][0],
                "losses": records[name][1],
                "ties": 0,
                "points_for": sum(scores[name]),
                "final_standing": finals[i] if i < len(finals) else 3,
                "seed": i + 1,
                "made_playoffs": name in playoff,
                "playoff_wins": po_record.get(name, (0, 0))[0],
                "playoff_losses": po_record.get(name, (0, 0))[1],
                "playoff_ties": 0,
                "playoff_points_for": playoff.get(name, 0.0),
                "playoff_games": 1 if name in playoff else 0,
            }
            for i, name in enumerate(order)
        ],
        "weekly_scores": [
            {
                "name": name,
                "weeks": [
                    {
                        "week": w + 1,
                        "points": scores[name][w],
                        "opponent": opponent(name, w),
                    }
                    for w in range(2)
                ],
            }
            for name in order
        ],
        "playoff_weeks": [
            {
                "name": name,
                "weeks": [
                    {
                        "week": 3,
                        "points": playoff[name],
                        "opponent": "Bravo" if name == "Alpha" else "Alpha",
                    }
                ],
            }
            for name in playoff
        ],
    }


HISTORY = {"league_id": 1, "seasons": [history_season(2025), history_season(2024)]}


def test_without_a_history_the_report_is_unchanged():
    """--history is optional, so a report built without one must not grow a tab
    bar, a second pane or a script it did not have before."""
    document = to_html.render(BASIC)

    # The stylesheet is one constant and always carries the tab rules; what must
    # be absent is the markup that uses them.
    assert '<nav class="tabs"' not in document
    assert 'class="tabpane"' not in document
    assert "All-Time" not in text_of(document)


def test_a_history_adds_a_second_pane_defaulting_to_this_season():
    document = to_html.render(BASIC, history=HISTORY)
    assert_wellformed(document)

    # Both panes ship in the page; exactly one of them is visible, and it is the
    # season -- so with scripting off the current report still reads as before.
    assert document.count('class="tabpane"') == 2
    assert 'class="tabpane" data-tab="season"' in document
    assert 'class="tabpane" data-tab="alltime" hidden' in document
    # The season pane still holds the whole existing report.
    season_pane = document.split('data-tab="season">')[1].split('data-tab="alltime"')[0]
    assert "Standings" in season_pane
    assert "Clinch Scenarios" in season_pane


def test_the_all_time_pane_ranks_every_completed_team_season():
    document = to_html.render(BASIC, history=HISTORY)
    pane = document.split('data-tab="alltime"')[2]

    assert "Best Team-Seasons" in pane
    assert "Manager Careers" in pane
    # Three scopes are rendered. The default one holds two seasons of three teams,
    # so six ranked rows plus the three manager careers behind them.
    default = at_view(pane, "both")
    ranked = default.split('<tbody class="at-teams">')[1].split("</tbody>")[0]
    managers = default.split('<tbody class="at-owners">')[1].split("</tbody>")[0]
    assert ranked.count("at-rating") == 6
    assert managers.count("at-rating") == 3


def test_a_season_still_in_progress_is_simply_absent():
    """It is not ranked and not explained: the counts line says which years are in,
    which is all a reader needs."""
    history = {
        "seasons": [history_season(2026, complete=False), history_season(2025)],
        "skipped": [],
    }
    pane = to_html.render(BASIC, history=history).split('data-tab="alltime"')[2]

    assert "Seasons <b>1</b>" in pane
    assert '<p class="note">' not in pane
    ranked = pane.split('<tbody class="at-teams">')[1].split("</tbody>")[0]
    assert "2026" not in ranked, "not ranked against finished years"
    overlay = pane.split('<tbody class="at-current" hidden>')[1].split("</tbody>")[0]
    assert "2026" in overlay, "but available to the chart's opt-in overlay"


def test_a_season_espn_refused_is_reported_separately():
    """Refused and unfinished are different reasons, and a reader told neither
    will assume the league did not exist."""
    history = {
        "seasons": [history_season(2025)],
        "skipped": [{"year": 2021, "reason": "access denied (no ESPN_S2 / SWID set)"}],
    }
    pane = to_html.render(BASIC, history=history).split('data-tab="alltime"')[2]

    assert "2021" in pane
    assert "could not be read" in pane


def test_an_empty_history_says_so_rather_than_rendering_a_bare_heading():
    history = {"seasons": [history_season(2026, complete=False)], "skipped": []}
    document = to_html.render(BASIC, history=history)
    pane = document.split('data-tab="alltime"')[2]

    assert_wellformed(document)
    assert "No completed season" in pane
    assert "Best Team-Seasons" not in pane


def test_all_time_team_names_are_escaped():
    season = history_season(2025)
    nasty = "Ben's \"<b>Team</b>\" & #2"
    season["teams"][0]["name"] = nasty
    season["weekly_scores"][0]["name"] = nasty
    season["weekly_scores"][1]["weeks"] = [
        {**w, "opponent": nasty} for w in season["weekly_scores"][1]["weeks"]
    ]
    document = to_html.render(BASIC, history={"seasons": [season]})

    assert_wellformed(document)
    assert "<b>Team</b>" not in text_of(document).replace(nasty, "")
    assert nasty in text_of(document)


def test_the_weights_are_adjustable_and_start_at_the_documented_defaults():
    """The rating is a judgement call, so it has to be arguable from the page --
    each component gets a slider, seeded with the weight the module documents."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    for name, weight in to_html.all_time.WEIGHTS.items():
        assert f'id="at-w-{name}"' in pane
        assert f'value="{round(weight * 100)}"' in pane
    # Accolades scale separately: they are added after the blend, not a share of it.
    assert 'id="at-w-hardware"' in pane
    assert 'id="at-reset"' in pane


def test_every_row_carries_the_components_the_sliders_re_rank_from():
    """Re-ranking happens in the page, so each row has to hold its own rates --
    otherwise the sliders would need a round trip the report cannot make."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    row = pane.split('<tbody class="at-teams">')[1].split("</tr>")[0]

    for attr in ("data-strength", "data-record", "data-scoring", "data-hardware"):
        assert attr in row
    assert "data-owner" in row, "the manager table averages these rows by owner"


def test_a_manager_row_joins_to_its_seasons_by_the_same_key():
    """The live average regroups the team rows by owner, so the two tables have to
    spell the franchise key identically or a career silently splits."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    view = at_view(pane, "both")

    ranked = view.split('<tbody class="at-teams">')[1].split("</tbody>")[0]
    managers = view.split('<tbody class="at-owners">')[1].split("</tbody>")[0]
    # A team row carries every manager it counts towards, pipe-separated.
    team_keys = {
        k
        for attr in re.findall(r'<tr data-owner="([^"]+)"', ranked)
        for k in attr.split("|")
    }
    owner_keys = set(re.findall(r'<tr data-owner="([^"]+)"', managers))
    assert team_keys == owner_keys


def test_a_co_managed_team_shows_surnames_but_searches_on_full_names():
    """Two full names is 30-odd characters in a column beside eight others, and
    nearly every team in one real league is co-managed. The filter still has to
    match either half of either name."""
    history = {"seasons": [history_season(2025)], "skipped": []}
    history["seasons"][0]["teams"][0]["managers"] = ["Colton Peffer", "Luke Bernard"]
    pane = to_html.render(BASIC, history=history).split('data-tab="alltime"')[2]
    row = at_view(pane, "both").split('<tbody class="at-teams">')[1].split("</tr>")[0]

    assert ">Peffer · Bernard<" in row, "the cell shows surnames only"
    assert 'data-manager="Colton Peffer Luke Bernard"' in row, "both full names"


def test_a_single_manager_keeps_their_full_name():
    history = {"seasons": [history_season(2025)], "skipped": []}
    history["seasons"][0]["teams"][0]["managers"] = ["Jake Redd"]
    pane = to_html.render(BASIC, history=history).split('data-tab="alltime"')[2]
    row = at_view(pane, "both").split('<tbody class="at-teams">')[1].split("</tr>")[0]

    assert ">Jake Redd<" in row


@pytest.mark.parametrize("scope", ["regular", "both", "playoffs"])
def test_each_scope_is_a_view_in_the_page(scope):
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    assert f'<button data-scope="{scope}"' in pane
    assert f'class="at-view" data-scope="{scope}"' in pane


def test_only_the_default_scope_is_visible():
    """All three ship in the page and the selector swaps them, so with scripting
    off one complete ranking still stands."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    assert f'data-scope="{to_html.all_time.DEFAULT_SCOPE}">' in pane  # not hidden
    hidden = re.findall(r'class="at-view" data-scope="(\w+)" hidden', pane)
    assert set(hidden) == set(to_html.all_time.SCOPES) - {to_html.all_time.DEFAULT_SCOPE}


def test_the_playoff_view_holds_only_the_teams_that_qualified():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    playoffs = at_view(pane, "playoffs")
    regular = at_view(pane, "regular")

    teams_in = playoffs.split('<tbody class="at-teams">')[1].count("<tr")
    teams_all = regular.split('<tbody class="at-teams">')[1].count("<tr")
    assert 0 < teams_in < teams_all


def test_the_regular_season_view_carries_no_accolade_points():
    """The scope buttons say what each view is, so there is no prose to check --
    but nothing in the regular-season view may carry accolade points."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    regular = at_view(pane, "regular")

    assert re.findall(r'data-hardware="([\d.]+)"', regular) != []
    assert set(re.findall(r'data-hardware="([\d.]+)"', regular)) == {"0.0"}


def test_the_two_all_play_columns_say_that_is_what_they_are():
    """Results duplicated the Record column, so it went. "Firepower", then
    "Scoring", both hid that the number is an all-play rate against the season."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    head = pane.split("<thead>")[1].split("</thead>")[0]

    assert ">Results<" not in head
    assert ">Firepower<" not in head
    assert ">All-Play Record<" in head
    assert ">All-Play Scoring<" in head
    assert ">Record<" in head, "the real win-loss column keeps the plain name"
    assert 'id="at-w-record"' in pane, "the slider is renamed too"
    assert 'id="at-w-results"' not in pane


def test_one_vocabulary_drives_heads_axes_and_legend():
    """A metric named three different ways in three places reads as three metrics."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    for key, label, gloss in to_html.AT_METRICS:
        assert f">{label}</option>" in pane, f"{key} axis option"
        assert f"<dt>{label}</dt>" in pane, f"{key} legend entry"
        assert gloss in pane, f"{key} gloss"


def at_view(pane, scope):
    """One scope's view out of the all-time pane.

    Sliced to the next view rather than to the first `</div>`: the view now holds
    nested divs for the table and the chart, so a naive split stops short.
    """
    chunk = pane.split(f'class="at-view" data-scope="{scope}"')[1]
    nxt = chunk.find('class="at-view"')
    return chunk if nxt == -1 else chunk[:nxt]


def both_view(pane):
    """The default scope's view, which is the one that shows bracket badges."""
    return at_view(pane, "both")


def test_accolades_are_one_line_and_abbreviated():
    """A champion's four badges stacked made every row a different height."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    cell = both_view(pane).split('<td class="acc">')[1].split("</td>")[0]

    assert "CHAMP" in cell, "abbreviated"
    assert "flex-wrap: nowrap" in to_html.CSS
    assert "white-space: nowrap" in to_html.CSS

def test_the_accolade_hint_for_playoff_wins_is_just_the_count():
    assert to_html._accolade_pill("2 playoff wins")[2] == "2 playoff wins"


def test_a_playoff_win_pill_keeps_its_count():
    cls, short, title = to_html._accolade_pill("2 playoff wins")
    assert short == "2W"
    assert "2 playoff wins" in title
    assert to_html._accolade_pill("1 playoff win")[1] == "1W"


@pytest.mark.parametrize(
    "key", ["rating", "year", "team", "manager", "record", "ppg", "strength", "scoring"]
)
def test_every_column_but_accolades_is_sortable(key):
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    head = pane.split('<tbody class="at-teams">')[0].split("<thead>")[-1]

    assert f'data-sort="{key}"' in head


def test_the_accolades_heading_is_not_sortable():
    """There is no order to sort a set of badges into."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    head = pane.split('<tbody class="at-teams">')[0].split("<thead>")[-1]
    accolades = [c for c in head.split("<th") if "Accolades" in c]

    assert len(accolades) == 1
    assert "data-sort" not in accolades[0]


def test_a_sortable_column_has_the_data_it_sorts_on():
    """Headings name a data attribute rather than a column index, so a heading
    cannot end up pointing at a different column's values."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    view = at_view(pane, "both")

    for table in view.split("<table")[1:]:
        keys = set(re.findall(r'data-sort="(\w+)"', table.split("</thead>")[0]))
        row = table.split("<tbody")[1].split("</tr>")[0]
        attrs = set(re.findall(r"data-(\w+)=", row))
        # 'rating' is computed live and written onto the row by the script.
        assert keys - {"rating"} <= attrs, keys - {"rating"} - attrs


def test_the_manager_table_is_sortable_too():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    owners = pane.split('<tbody class="at-owners">')[0].split("<thead>")[-1]

    for key in ("manager", "seasons", "record", "titles", "berths", "best", "rating"):
        assert f'data-sort="{key}"' in owners


def test_the_weight_panel_is_collapsed_by_default():
    """Four sliders were the wrong first impression, so the panel folds away and
    the presets answer the question for most readers in one click."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    panel = pane.split('<details class="weights"')[1].split("</details>")[0]

    assert "open" not in pane.split('<details class="weights"')[1][:20], "starts closed"
    assert "<summary>" in panel
    assert "Weights:" in panel


def test_every_preset_is_offered_with_its_ratio_shown():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    panel = pane.split('<details class="weights"')[1].split("</details>")[0]

    for key, label, w, blurb in to_html.all_time.PRESETS:
        assert f'value="{key}"' in panel
        assert f"<b>{label}</b>" in panel
        ratio = ",".join(str(w[n]) for n in ("strength", "record", "scoring"))
        assert f'data-weights="{ratio}"' in panel
    assert 'value="custom"' in panel, "and an escape hatch to the raw sliders"


def test_the_default_preset_is_checked_and_named_in_the_summary():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    panel = pane.split('<details class="weights"')[1].split("</details>")[0]
    default = dict((k, l) for k, l, _, _ in to_html.all_time.PRESETS)[
        to_html.all_time.DEFAULT_PRESET
    ]

    assert f'value="{to_html.all_time.DEFAULT_PRESET}" data-weights' in panel
    assert " checked>" in panel
    assert f'id="at-preset-name">{default}<' in panel


def test_the_default_preset_matches_the_documented_weights():
    """The panel must open on the same weighting the module rates with, or the
    first render disagrees with itself."""
    preset = dict((k, w) for k, _, w, _ in to_html.all_time.PRESETS)[
        to_html.all_time.DEFAULT_PRESET
    ]
    for name, weight in to_html.all_time.WEIGHTS.items():
        assert preset[name] == round(weight * 100)


def test_the_raw_sliders_still_exist_but_start_hidden():
    """A preset writes them, so they have to be in the page for the rating to be
    computed -- just not on show until Custom is chosen."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    assert 'id="at-custom" hidden' in pane
    for name in ("strength", "record", "scoring"):
        assert f'id="at-w-{name}"' in pane

def test_the_playoff_view_drops_the_berth_badge():
    """Every row in it qualified, so PO was on all of them."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    playoffs = at_view(pane, "playoffs")
    body = playoffs.split('<tbody class="at-teams">')[1].split("</tbody>")[0]

    assert ">PO<" not in body
    assert "Made the playoffs" not in body


def test_the_filter_box_is_present_and_searches_the_named_fields():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    assert 'id="at-find"' in pane
    assert 'type="search"' in pane
    row = pane.split('<tbody class="at-teams">')[1].split("</tr>")[0]
    for field in ("data-year", "data-team", "data-manager", "data-accolades"):
        assert field in row, field


def test_the_filter_matches_both_the_word_and_the_badge_code():
    """So "champion" typed from memory and "CHAMP" read off the screen both work."""
    text = to_html._accolade_search_text(["Champion", "2 playoff wins", "#1 overall seed"])

    assert "Champion" in text and "CHAMP" in text
    assert "2 playoff wins" in text and "2W" in text
    assert "#1 overall seed" in text and "#1" in text


def test_the_weight_sliders_cannot_leak_past_the_hidden_attribute():
    """`display: flex` on .controls outranks `hidden`, which had the sliders on
    show while a named preset was selected. The SOS chart hit the same trap."""
    assert "#at-custom[hidden] { display: none; }" in to_html.CSS


def test_a_preset_explains_itself_on_hover_rather_than_printing_its_ratio():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    panel = pane.split('<details class="weights"')[1].split("</details>")[0]

    assert panel.count('class="hint"') == len(to_html.all_time.PRESETS) + 1  # +Custom
    for _, _, w, blurb in to_html.all_time.PRESETS:
        ratio = f'{w["strength"]} / {w["record"]} / {w["scoring"]}'
        assert ratio in panel, "the ratio moved into the tooltip"
        assert blurb.split(".")[0] in panel
    # and is no longer sitting beside the label as a bare number
    assert 'class="dim">45 / 30 / 25</span>' not in panel


def test_there_is_no_legend_under_the_table():
    """Dropped as clutter; the badges explain themselves on hover instead."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    assert 'class="legend"' not in pane
    assert not hasattr(to_html, "_accolade_legend")


def test_the_runner_up_hint_is_just_the_words():
    assert to_html.ACCOLADE_TITLE["2nd"] == "Runner-up"


def test_the_filter_and_the_weights_share_one_thin_row():
    """The controls were competing with the table for attention."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    tools = pane.split('<div class="at-tools">')[1].split("</details></div>")[0]

    assert 'id="at-find"' in tools
    assert 'id="at-weights"' in tools


def test_opening_the_weights_does_not_push_the_table_down():
    """The panel is a popover anchored to its own link, not a block in the flow."""
    assert ".weights { margin-left: auto; position: relative; }" in to_html.CSS
    body = to_html.CSS.split(".wbody {")[1].split("}")[0]
    assert "position: absolute" in body
    assert "right: 0" in body


def test_the_all_time_pane_has_a_table_chart_toggle_and_axis_pickers():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    assert 'id="at-view-seg"' in pane
    assert '<button data-view="table" class="on">' in pane, "table is the default"
    assert '<button data-view="chart">' in pane
    assert 'id="at-x"' in pane and 'id="at-y"' in pane
    assert 'id="at-axes" hidden' in pane, "pickers only show in chart view"


def test_the_axis_pickers_cannot_show_in_table_view():
    """They live on the chart's axes, so nothing about them may be visible while
    the table is up. Two rules carry that: the parking spot is display:none, and
    the chart view -- a grid, whose display would otherwise beat the hidden
    attribute -- is explicitly hidden. Same trap as #sos-chart-view."""
    doc = to_html.render(BASIC, history=HISTORY)

    assert ".at-axes { display: none; }" in doc
    assert ".at-chart-view[hidden] { display: none; }" in doc


def test_every_scope_gets_its_own_chart():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]

    for scope in to_html.all_time.SCOPES:
        view = at_view(pane, scope)
        assert 'svg class="at-chart"' in view
        assert 'class="at-tip"' in view, "and its own hover card"
        assert 'class="at-chart-view" hidden' in view


def test_a_dot_carries_what_the_hover_card_shows():
    """A two-letter dot cannot say which year or whose team it was."""
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    row = at_view(pane, "both").split('<tbody class="at-teams">')[1].split("</tr>")[0]

    for attr in ("data-abbr", "data-colour", "data-year", "data-team", "data-manager"):
        assert attr in row, attr


def test_the_chart_is_centred_rather_than_fitted_to_the_data():
    """Every metric here is positive and clustered, so a fitted domain put the whole
    league in one corner and the quadrant labels described nothing."""
    js = to_html.ALL_TIME_JS
    assert "FIXED_CENTRE = { strength: 0.5, record: 0.5, scoring: 0.5 }" in js
    assert "function span(k, vals, c)" in js, "symmetric domain about the centre"


def test_a_bounded_metric_shows_its_whole_scale():
    """A win percentage runs .000 to 1.000 whatever this league did, so the axis
    shows that range instead of stretching the best and worst season to the edges."""
    js = to_html.ALL_TIME_JS

    assert "FIXED_SPAN = { record: 0.5 }" in js
    assert "if (FIXED_SPAN[k] !== undefined) return FIXED_SPAN[k];" in js


def test_every_axis_is_numbered_absolutely_or_relatively():
    """Record and PPG read straight; the three rates only support a distance from
    average, so they are numbered as a signed offset instead."""
    js = to_html.ALL_TIME_JS
    table = js.split("var TICK = {")[1].split("\n  };")[0]

    for absolute in ("record", "ppg"):
        assert f"{absolute}: {{ step:" in table
        assert f"mode: 'abs' }}" in table
    for relative in ("strength", "scoring", "rating"):
        assert f"{relative}: {{ step:" in table
    assert table.count("mode: 'rel'") == 3


def test_no_chart_writes_words_at_its_axis_ends():
    """Replaced by the `?` beside each picker; the helpers that drew them are gone
    rather than left dangling."""
    for js in (to_html.STRENGTH_JS, to_html.ALL_TIME_JS):
        assert "var PHRASE" not in js
        assert "function phrase(" not in js
        assert "function ends(" not in js


def test_the_season_chart_is_centred_too():
    js = to_html.STRENGTH_JS

    assert "function span(k, vals, c)" in js, "symmetric domain about the reference"
    # SOS and SOR keep a fixed scale so the slider moves the dots, not the axis.
    assert "FIXED_SPAN = { sos: 35, sor: 0.3 }" in js


def test_this_season_is_an_opt_in_overlay_next_to_the_weights():
    pane = to_html.render(BASIC, history=HISTORY).split('data-tab="alltime"')[2]
    tools = pane.split('<div class="at-tools">')[1].split("</details></div>")[0]

    assert 'id="at-live"' in tools
    assert 'type="checkbox"' in tools
    assert tools.index('id="at-live"') < tools.index('id="at-weights"')


def test_an_overlay_row_has_no_rank():
    """It was never ranked, which is the whole reason it is held apart."""
    history = {
        "seasons": [history_season(2026, complete=False), history_season(2025)],
        "skipped": [],
    }
    pane = to_html.render(BASIC, history=history).split('data-tab="alltime"')[2]
    overlay = pane.split('<tbody class="at-current" hidden>')[1].split("</tbody>")[0]

    assert '<td class="num at-rank"></td>' in overlay


def test_an_in_progress_season_does_not_overlay_the_playoff_chart():
    """ESPN publishes a live playoff seed mid-season, so the playoff scope produced
    six qualifiers with nothing played -- six identical dots at the origin.

    The 2026 season here is shaped like a real one three weeks in: seeded, and so
    apparently qualified, but with no bracket game behind any of it.
    """
    live = history_season(2026, complete=False)
    for team in live["teams"]:
        team["playoff_wins"] = team["playoff_losses"] = team["playoff_games"] = 0
        team["playoff_points_for"] = 0.0
    live["playoff_weeks"] = [
        {"name": t["name"], "weeks": [{"week": 3, "points": 0.0, "opponent": None}]}
        for t in live["teams"]
        if t["made_playoffs"]
    ]
    history = {"seasons": [live, history_season(2025)], "skipped": []}
    pane = to_html.render(BASIC, history=history).split('data-tab="alltime"')[2]
    playoffs = at_view(pane, "playoffs")
    overlay = playoffs.split('<tbody class="at-current" hidden>')[1].split("</tbody>")[0]

    assert "2026" not in overlay
    # but the regular-season chart may still show it
    regular = at_view(pane, "regular")
    assert "2026" in regular.split('<tbody class="at-current" hidden>')[1]


def test_the_overlay_obeys_the_search_box_too():
    """Overlay rows are never in the table, so `filter` never sets their hidden
    flag -- the chart has to test them against the query itself, or searching one
    manager still draws all of this year's teams beside the matches."""
    doc = to_html.render(BASIC, history=HISTORY)
    script = doc.split("</style>")[-1]

    assert "function matches(tr)" in script, "one shared predicate"
    assert ".filter(matches)" in script, "and the overlay runs through it"
