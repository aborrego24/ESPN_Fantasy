"""Strength of schedule and strength of record.

The same four-team league as the season-review tests, small enough to work out
by hand:

  week:      1      2      3      4
  Alpha    120.0  110.0  100.0  130.0
  Bravo    100.0  105.0  115.0   90.0
  Charlie   90.0  100.0  118.0   95.0
  Delta     80.0   95.0   90.0   85.0

  schedule  1: Alpha-Bravo, Charlie-Delta
            2: Alpha-Charlie, Bravo-Delta
            3: Alpha-Delta, Bravo-Charlie
            4: Alpha-Bravo, Charlie-Delta

Records come out Alpha 4-0, Charlie 3-1, Bravo 1-3, Delta 0-4, and the per-team
points-per-game are Alpha 115.0, Bravo 102.5, Charlie 100.75, Delta 87.5.
"""

import pytest

import strength

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


def build(scores=SCORES, schedule=SCHEDULE, weeks=None):
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


def row_of(rows, name):
    return next(r for r in rows if r["name"] == name)


# --- strength of schedule: the opponent components -----------------------------


def test_opponent_ppg_is_the_mean_of_who_you_played():
    """Alpha played Bravo, Charlie, Delta, Bravo -> mean of their PPG.

    (102.5 + 100.75 + 87.5 + 102.5) / 4 = 98.3125.
    Delta played Charlie, Bravo, Alpha, Charlie -> (100.75+102.5+115+100.75)/4.
    """
    rows = strength.strength_table(build())

    assert row_of(rows, "Alpha")["opp_ppg"] == pytest.approx(98.3125)
    assert row_of(rows, "Delta")["opp_ppg"] == pytest.approx(104.75)


def test_opponent_record_excludes_your_mutual_games():
    """RPI self-exclusion: Alpha's opponents, judged on games NOT against Alpha.

    Bravo w/o Alpha 1-1, Charlie w/o Alpha 3-0, Delta w/o Alpha 0-3, Bravo again
    0.5 -> mean (0.5 + 1.0 + 0.0 + 0.5) / 4 = 0.5.
    """
    rows = strength.strength_table(build())

    assert row_of(rows, "Alpha")["opp_win_pct"] == pytest.approx(0.5)


def test_a_teams_own_result_never_feeds_its_own_schedule():
    """The point of the exclusion: dropping Alpha's games changes the number.

    Charlie really went 3-1, but against everyone except Alpha it was 2-0 (1.0).
    So an opponent's contribution to a schedule is not just its raw record.
    """
    games = strength._games(*strength._series(build()))

    assert strength._win_pct(games["Charlie"]) == pytest.approx(0.75)
    assert strength._win_pct_excluding(games["Charlie"], "Alpha") == pytest.approx(1.0)


# --- the blended index ---------------------------------------------------------


def test_blend_one_ranks_purely_by_opponent_points():
    rows = strength.strength_table(build(), blend=1.0)
    by_index = [r["name"] for r in rows]
    by_ppg = [
        r["name"]
        for r in sorted(rows, key=lambda r: (-r["opp_ppg"], r["name"]))
    ]

    assert by_index == by_ppg


def test_blend_zero_ranks_purely_by_opponent_record():
    rows = strength.strength_table(build(), blend=0.0)
    by_index = [r["name"] for r in rows]
    by_record = [
        r["name"]
        for r in sorted(rows, key=lambda r: (-r["opp_win_pct"], r["name"]))
    ]

    assert by_index == by_record


def test_the_table_is_sorted_hardest_schedule_first():
    rows = strength.strength_table(build())
    indices = [r["sos"] for r in rows]

    assert indices == sorted(indices, reverse=True)


def test_the_hardest_and_easiest_index_are_one_and_zero():
    """Min-max normalisation pins the extremes."""
    rows = strength.strength_table(build(), blend=1.0)

    assert max(r["sos"] for r in rows) == pytest.approx(1.0)
    assert min(r["sos"] for r in rows) == pytest.approx(0.0)


# --- strength of record --------------------------------------------------------


def test_sor_is_your_win_pct_minus_the_benchmarks():
    """Worked by hand for Alpha against the average-team benchmark.

    Alpha's opponents scored 100, 100, 90, 90 in the weeks it played them. Across
    the 16 league scores an average team beats a 100 with probability 0.46875 and
    a 90 with 0.78125, so its expected win rate over Alpha's slate is 0.625.
    Alpha really went 4-0 (1.0), so SOR = 1.0 - 0.625 = 0.375.
    """
    alpha = row_of(strength.strength_table(build()), "Alpha")

    assert alpha["benchmark_win_pct"] == pytest.approx(0.625)
    assert alpha["actual_win_pct"] == pytest.approx(1.0)
    assert alpha["sor"] == pytest.approx(0.375)


def test_sor_rewards_a_good_record_against_a_hard_schedule():
    """Two teams with the same record, one with tougher opponents, ranked by SOR.

    A and B both score 100 every week and both go 1-1, and both face F1 and F2 --
    but in swapped weeks, and the foes scored differently in each. A's opponents
    put up 150 and 90 against it; B's put up 105 and 20. So the same league-average
    benchmark beats A's slate less often (0.4375) than B's (0.5625), and A's
    identical 1-1 earns the higher SOR: +0.0625 vs -0.0625.
    """
    scores = {
        "A": [100.0, 100.0],
        "B": [100.0, 100.0],
        "F1": [150.0, 20.0],
        "F2": [105.0, 90.0],
    }
    schedule = [
        [("A", "F1"), ("B", "F2")],  # A loses to 150, B loses to 105
        [("A", "F2"), ("B", "F1")],  # A beats 90, B beats 20
    ]
    rows = strength.strength_table(build(scores, schedule))
    a, b = row_of(rows, "A"), row_of(rows, "B")

    assert a["actual_win_pct"] == pytest.approx(0.5)
    assert b["actual_win_pct"] == pytest.approx(0.5)
    assert a["benchmark_win_pct"] == pytest.approx(0.4375)
    assert b["benchmark_win_pct"] == pytest.approx(0.5625)
    assert a["sor"] == pytest.approx(0.0625)
    assert b["sor"] == pytest.approx(-0.0625)


def test_the_elite_benchmark_is_harder_to_beat_than_the_average_one():
    """An elite benchmark out-scores more opponents, so every SOR is lower."""
    average = strength.strength_table(build(), benchmark="average")
    elite = strength.strength_table(build(), benchmark="elite")

    for name in SCORES:
        assert row_of(elite, name)["benchmark_win_pct"] >= row_of(
            average, name
        )["benchmark_win_pct"]
        assert row_of(elite, name)["sor"] <= row_of(average, name)["sor"]


# --- the forward half of SOS ---------------------------------------------------


def test_remaining_matchups_feed_the_full_season_schedule():
    """A team whose remaining opponent is strong gets a harder full SOS.

    One week played, one to come. Weak plays Strong next; its played SOS is low
    (it faced Mid) but its full SOS must rise toward Strong's PPG.
    """
    scores = {
        "Strong": [150.0],
        "Mid": [100.0],
        "Weak": [90.0],
        "Other": [80.0],
    }
    schedule = [[("Strong", "Other"), ("Weak", "Mid")]]
    remaining = [[{"team1": "Weak", "team2": "Strong"}, {"team1": "Mid", "team2": "Other"}]]

    rows = strength.strength_table(build(scores, schedule), remaining_matchups=remaining)
    weak = row_of(rows, "Weak")

    assert weak["sos_played"] == pytest.approx(100.0), "only faced Mid so far"
    assert weak["sos_remaining"] == pytest.approx(150.0), "Strong is next"
    # full SOS averages both opponents: (100 + 150) / 2 = 125
    assert weak["opp_ppg"] == pytest.approx(125.0)


def test_no_remaining_matchups_leaves_the_forward_half_empty():
    rows = strength.strength_table(build())

    for row in rows:
        assert row["sos_remaining"] is None
        # with nothing to come, full SOS is the played SOS
        assert row["opp_ppg"] == pytest.approx(row["sos_played"])


# --- degenerate input ----------------------------------------------------------


def test_a_payload_with_no_played_weeks_yields_nothing():
    """Preseason: strength on actual results has nothing to say yet."""
    empty = [{"name": n, "weeks": []} for n in ("A", "B")]

    assert strength.strength_table(empty) == []


def test_a_duplicate_name_is_refused():
    dupe = [
        {"name": "Same", "weeks": [{"week": 1, "points": 100.0, "opponent": "Same"}]},
        {"name": "Same", "weeks": [{"week": 1, "points": 90.0, "opponent": "Same"}]},
    ]
    with pytest.raises(ValueError):
        strength.strength_table(dupe)
