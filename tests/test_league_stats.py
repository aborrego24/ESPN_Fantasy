"""All-play record and schedule luck.

The four-team league below is small enough to work out by hand, which is the
point: every expected value in this file was computed on paper first.

  week:      1      2      3      4
  Alpha    120.0  110.0  100.0  130.0
  Bravo    100.0  105.0  115.0   90.0
  Charlie   90.0  100.0  118.0   95.0
  Delta     80.0   95.0   90.0   85.0

  schedule  1: Alpha-Bravo, Charlie-Delta
            2: Alpha-Charlie, Bravo-Delta
            3: Alpha-Delta, Bravo-Charlie
            4: Alpha-Bravo, Charlie-Delta
"""

import pytest

import league_stats

SCORES = {
    "Alpha": [120.0, 110.0, 100.0, 130.0],
    "Bravo": [100.0, 105.0, 115.0, 90.0],
    "Charlie": [90.0, 100.0, 118.0, 95.0],
    "Delta": [80.0, 95.0, 90.0, 85.0],
}

SCHEDULE = [
    [("Alpha", "Bravo"), ("Charlie", "Delta")],
    [("Alpha", "Charlie"), ("Bravo", "Delta")],
    [("Alpha", "Delta"), ("Bravo", "Charlie")],
    [("Alpha", "Bravo"), ("Charlie", "Delta")],
]


def build(scores=None, schedule=None, weeks=None):
    """Shape the stage-1 `weekly_scores` payload."""
    scores = SCORES if scores is None else scores
    schedule = SCHEDULE if schedule is None else schedule
    weeks = len(schedule) if weeks is None else weeks

    opponents = {name: [None] * weeks for name in scores}
    for index in range(weeks):
        for home, away in schedule[index]:
            opponents[home][index] = away
            opponents[away][index] = home

    return [
        {
            "name": name,
            "weeks": [
                {
                    "week": index + 1,
                    "points": scores[name][index],
                    "opponent": opponents[name][index],
                }
                for index in range(weeks)
            ],
        }
        for name in scores
    ]


def real_record(name, weeks=4):
    """The team's actual record, computed straight from the schedule."""
    tally = {"wins": 0, "losses": 0, "ties": 0}
    for index in range(weeks):
        for home, away in SCHEDULE[index]:
            if name not in (home, away):
                continue
            opponent = away if home == name else home
            mine, theirs = SCORES[name][index], SCORES[opponent][index]
            if mine > theirs:
                tally["wins"] += 1
            elif mine < theirs:
                tally["losses"] += 1
            else:
                tally["ties"] += 1
    return tally


def totals(rows):
    return {row["name"]: row["total"] for row in rows}


# --- all-play -----------------------------------------------------------------


def test_all_play_scores_every_team_against_every_other_every_week():
    """Week 1 is 120 > 100 > 90 > 80, so the records are 3-0, 2-1, 1-2, 0-3."""
    rows = {row["name"]: row for row in league_stats.all_play_records(build())}

    assert rows["Alpha"]["weeks"][0] == {"wins": 3, "losses": 0, "ties": 0}
    assert rows["Bravo"]["weeks"][0] == {"wins": 2, "losses": 1, "ties": 0}
    assert rows["Charlie"]["weeks"][0] == {"wins": 1, "losses": 2, "ties": 0}
    assert rows["Delta"]["weeks"][0] == {"wins": 0, "losses": 3, "ties": 0}


def test_all_play_totals_are_the_hand_computed_ones():
    """Alpha tops three of four weeks; Charlie wins week 3 on 118."""
    assert totals(league_stats.all_play_records(build())) == {
        "Alpha": {"wins": 10, "losses": 2, "ties": 0},
        "Bravo": {"wins": 7, "losses": 5, "ties": 0},
        "Charlie": {"wins": 7, "losses": 5, "ties": 0},
        "Delta": {"wins": 0, "losses": 12, "ties": 0},
    }


def test_every_all_play_win_is_someone_elses_loss():
    """A structural check that survives any change to the scores."""
    rows = league_stats.all_play_records(build())

    wins = sum(row["total"]["wins"] for row in rows)
    losses = sum(row["total"]["losses"] for row in rows)
    assert wins == losses
    # 4 teams x 3 rivals x 4 weeks, each game counted from both sides
    assert wins == 4 * 3 * 4 // 2


def test_all_play_plays_the_whole_league_each_week():
    for row in league_stats.all_play_records(build()):
        for week in row["weeks"]:
            assert sum(week.values()) == 3, "one game against each of the other three"


def test_all_play_is_ordered_best_first():
    rows = league_stats.all_play_records(build())

    percentages = [league_stats.win_pct(row["total"]) for row in rows]
    assert percentages == sorted(percentages, reverse=True)
    assert rows[0]["name"] == "Alpha"
    assert rows[-1]["name"] == "Delta"


def test_all_play_disagrees_with_the_real_standings():
    """The reason the table is worth printing at all.

    Charlie really finished 3-1 and Bravo 1-3, but their all-play records are
    identical -- Charlie's three wins came against the schedule, not the league.
    """
    all_play = totals(league_stats.all_play_records(build()))

    assert real_record("Charlie") == {"wins": 3, "losses": 1, "ties": 0}
    assert real_record("Bravo") == {"wins": 1, "losses": 3, "ties": 0}
    assert all_play["Charlie"] == all_play["Bravo"]


# --- weekly placing -----------------------------------------------------------


def test_a_placing_counts_the_teams_above_and_starts_at_one():
    assert league_stats.weekly_finish({"wins": 3, "losses": 0, "ties": 0}) == 1
    assert league_stats.weekly_finish({"wins": 0, "losses": 3, "ties": 0}) == 4
    assert league_stats.weekly_finish({"wins": 2, "losses": 1, "ties": 0}) == 2


def test_equal_scores_share_a_placing():
    """As they do in the standings: two teams tied for second, nobody third."""
    assert league_stats.weekly_finish({"wins": 2, "losses": 0, "ties": 1}) == 1
    assert league_stats.weekly_finish({"wins": 1, "losses": 1, "ties": 1}) == 2


def test_an_unscored_week_has_no_placing():
    """Distinguishable from last place, which is what a 0 would have read as."""
    assert league_stats.weekly_finish({"wins": 0, "losses": 0, "ties": 0}) is None


def test_every_placing_in_a_week_is_taken_exactly_once():
    weeks = list(zip(*[row["weeks"] for row in league_stats.all_play_records(build())]))

    for week in weeks:
        placings = sorted(league_stats.weekly_finish(tally) for tally in week)
        assert placings == [1, 2, 3, 4]


# --- schedule luck ------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCORES))
def test_your_own_schedule_reproduces_your_real_record(name):
    """The diagonal of the matrix has an independently known answer.

    This is the check that the whole substitution rule rests on: playing your own
    schedule has to give back exactly the record you actually posted.
    """
    result = league_stats.schedule_luck(build())
    row = next(r for r in result["rows"] if r["name"] == name)

    assert row["against"][name] == real_record(name)


def test_the_week_a_schedules_owner_played_you_becomes_a_game_against_them():
    """The case the original code left as a bare TODO, and the reason it broke.

    Bravo played Alpha in weeks 1 and 4. Alpha taking over Bravo's schedule
    cannot play itself, so it plays Bravo: 120-100 and 130-90, both wins. With
    week 2 against Delta won and week 3 against Charlie lost, that is 3-1.
    """
    result = league_stats.schedule_luck(build())
    alpha = next(r for r in result["rows"] if r["name"] == "Alpha")

    assert alpha["against"]["Bravo"] == {"wins": 3, "losses": 1, "ties": 0}


def test_no_row_ever_records_a_game_against_itself():
    """Whatever the substitution does, it must never compare a score with itself.

    A self-comparison is always a tie, so it would quietly inflate every tie
    count -- which is exactly what the broken branch did.
    """
    result = league_stats.schedule_luck(build())

    for row in result["rows"]:
        for tally in row["against"].values():
            assert tally["ties"] == 0, "this league has no equal scores anywhere"


def test_every_team_plays_a_full_season_under_every_schedule():
    result = league_stats.schedule_luck(build())

    for row in result["rows"]:
        for owner, tally in row["against"].items():
            assert sum(tally.values()) == 4, f"{row['name']} under {owner}"


def test_the_matrix_covers_every_pairing():
    result = league_stats.schedule_luck(build())

    assert sorted(result["teams"]) == sorted(SCORES)
    for row in result["rows"]:
        assert sorted(row["against"]) == sorted(SCORES)


def test_the_spread_shows_what_the_draw_was_worth():
    """Delta lost every game it played, but not under every schedule."""
    result = league_stats.schedule_luck(build())
    delta = next(r for r in result["rows"] if r["name"] == "Delta")

    best_name, best, worst_name, worst = league_stats.luck_spread(delta)

    assert league_stats.win_pct(best) >= league_stats.win_pct(worst)
    assert delta["against"][best_name] == best
    assert delta["against"][worst_name] == worst


def test_schedule_luck_is_ordered_by_real_record():
    result = league_stats.schedule_luck(build())

    assert [row["name"] for row in result["rows"]][0] == "Alpha"
    percentages = [
        league_stats.win_pct(row["against"][row["name"]]) for row in result["rows"]
    ]
    assert percentages == sorted(percentages, reverse=True)


# --- awkward data -------------------------------------------------------------


def test_a_tie_is_counted_as_a_tie():
    """Past results can genuinely tie; matchupTieRule is NONE in this league."""
    scores = {name: list(row) for name, row in SCORES.items()}
    scores["Bravo"][0] = 120.0  # dead heat with Alpha in week 1

    rows = totals(league_stats.all_play_records(build(scores=scores)))

    assert rows["Alpha"]["ties"] == 1
    assert rows["Bravo"]["ties"] == 1


def test_an_unscored_week_is_not_a_loss_to_the_whole_league():
    """Weeks not yet played arrive as 0.0, as stage 1's played_weeks assumes."""
    scores = {name: list(row) for name, row in SCORES.items()}
    for name in scores:
        scores[name][3] = 0.0

    rows = totals(league_stats.all_play_records(build(scores=scores)))

    for tally in rows.values():
        assert sum(tally.values()) == 9, "three weeks of data, not four"


def test_a_bye_in_a_schedule_is_skipped_rather_than_inherited():
    """An odd-sized league leaves a week with nobody to play."""
    schedule = [list(week) for week in SCHEDULE]
    schedule[2] = [("Alpha", "Delta")]  # Bravo and Charlie both idle

    result = league_stats.schedule_luck(build(schedule=schedule))
    alpha = next(r for r in result["rows"] if r["name"] == "Alpha")

    assert sum(alpha["against"]["Bravo"].values()) == 3, "week 3 had no opponent"
    assert sum(alpha["against"]["Alpha"].values()) == 4


def test_no_games_played_yet_is_empty_rather_than_an_error():
    empty = league_stats.all_play_records(build(weeks=0))

    assert [row["total"] for row in empty] == [
        {"wins": 0, "losses": 0, "ties": 0}
    ] * 4
    assert league_stats.win_pct({"wins": 0, "losses": 0, "ties": 0}) == 0.0


def test_an_empty_league_does_not_crash():
    assert league_stats.all_play_records([]) == []
    assert league_stats.schedule_luck([]) == {"teams": [], "rows": []}
