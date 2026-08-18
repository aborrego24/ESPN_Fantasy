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
         top_seed=None, bye=None):
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


def test_a_divisional_league_gets_one_table_per_division():
    document = to_html.render(DIVISIONAL)

    assert "East Division" in document and "West Division" in document
    # two grouped tables, not one flat standings table
    assert document.count('<div class="division">') == 2
    body = document.split("<h2>Standings</h2>")[1]
    east = body.split("East Division")[1].split("</div>")[0]
    assert "East A" in east and "East B" in east and "East C" in east
    assert "West A" not in east, "divisions do not bleed into each other"
    assert_wellformed(document)


def test_each_division_table_is_ranked_within_the_division():
    """The # column restarts at 1 per division and follows that division's record."""
    document = to_html.render(DIVISIONAL)
    body = document.split("<h2>Standings</h2>")[1]
    east = body.split("East Division")[1].split("</table>")[0]

    order = re.findall(r'<td class="num">(\d+)</td><td>.*?([A-Za-z].*?)</td>', east)
    ranks = [n for n, _ in order]
    assert ranks[:3] == ["1", "2", "3"], "within-division rank starts at 1"


def test_a_single_division_league_keeps_one_table_and_the_cut_line():
    """No divisions -> unchanged behaviour, cut line and all."""
    document = to_html.render(BASIC)

    assert '<div class="divisions">' not in document
    assert "playoff cut line" in document


def test_the_division_names_come_through_even_as_json_string_keys():
    """The payload round-trips through JSON, which turns the int ids into strings."""
    data = json.loads(json.dumps(DIVISIONAL))  # ids in division_names become "0"/"1"
    document = to_html.render(data)

    assert "East Division" in document and "West Division" in document
    assert "Division 0" not in document, "fell back to the id instead of the name"


# --- #1-seed race --------------------------------------------------------------


def test_the_seed_race_lists_who_is_still_alive_for_the_top_seed():
    document = to_html.render(
        payload(
            [
                team("Alpha", 3, 1, 400.0, "clinched", top_seed="alive"),
                team("Bravo", 3, 1, 390.0, "clinched", top_seed="alive"),
                team("Charlie", 1, 3, 300.0, "alive", top_seed="eliminated"),
            ]
        )
    )
    race = document.split("Race for #1 Overall Seed")[1].split("</details>")[0]

    assert "Alpha" in race and "Bravo" in race
    assert "Charlie" not in race, "a team out of the #1-seed race is left out"
    # collapsed on load: the <details> has no `open` attribute
    assert '<details class="race">' in document
    assert 'class="race" open' not in document
    assert_wellformed(document)


def test_no_seed_race_once_the_top_seed_is_clinched():
    """A decided #1 seed is not a race, so the whole section is dropped."""
    document = to_html.render(
        payload(
            [
                team("Alpha", 4, 0, 400.0, "clinched", top_seed="clinched"),
                team("Bravo", 2, 2, 300.0, "alive", top_seed="eliminated"),
            ]
        )
    )

    assert "Race for #1 Overall Seed" not in document


def test_no_seed_race_section_when_nobody_can_still_take_it():
    """If every team is eliminated from the #1 seed, drop the section entirely."""
    document = to_html.render(
        payload([team("Alpha", 1, 0, 10.0, "alive", top_seed="eliminated")])
    )

    assert "Race for #1 Overall Seed" not in document


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

    assert 'id="sos-view"' in doc, "no Table/Chart toggle"
    assert 'id="sos-x"' in doc and 'id="sos-y"' in doc, "no axis pickers"
    assert 'id="sos-chart"' in doc, "no chart svg"
    # every metric is offered on both axes
    for key, _ in to_html.CHART_METRICS:
        assert f'value="{key}"' in doc
    # default axes are the SOS/SOR quadrant
    assert '<option value="sos" selected>' in doc
    assert '<option value="sor" selected>' in doc
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


def test_the_chart_labels_each_quadrant_from_the_chosen_axes():
    """The scatter names its corners; the phrases are chosen live in the browser,
    so what must be present is the phrase table, the joiner and the styling."""
    doc = to_html.render(
        payload(
            [team(n, 1, 1, 100.0, "alive") for n in ("Alpha", "Bravo", "Charlie")],
            weekly_scores=weekly(["Alpha", "Bravo", "Charlie"]),
        )
    )

    assert ".cquad" in doc, "no quadrant-label styling"
    assert "quadLabel(" in doc, "corners are not labelled"
    # every chart metric contributes a low/high phrase pair
    for key, _ in to_html.CHART_METRICS:
        assert f"{key}:" in doc, f"{key} has no quadrant phrase"
    for phrase in ("tough schedule", "wins a lot", "overachieving", "strong opponents"):
        assert phrase in doc
    # count metrics render whole; both axes get a divider (mean where no fixed one)
    assert "isCount(" in doc, "wins ticks are not forced to whole numbers"
    assert "function mean(" in doc, "no average divider for metrics without a fixed one"


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
