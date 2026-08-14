"""Tiebreaker dependencies, and how plausible a swing is called."""

import pytest

import margins
import playoff_math
from playoff_math import LeagueState


@pytest.fixture
def thresholds():
    return margins.load_thresholds()


def test_threshold_table_is_monotonic_in_weeks(thresholds):
    """More weeks to play can only offer more room to catch up."""
    rows = thresholds["by_weeks_remaining"]
    keys = sorted(int(k) for k in rows)

    maxes = [rows[str(k)]["max_observed"] for k in keys]
    p99s = [rows[str(k)]["p99"] for k in keys]

    assert maxes == sorted(maxes)
    assert p99s == sorted(p99s)
    for k in keys:
        assert rows[str(k)]["p99"] <= rows[str(k)]["max_observed"]


def test_bands_split_on_the_measured_lines(thresholds):
    row = thresholds["by_weeks_remaining"]["1"]

    assert margins.plausibility(row["max_observed"] + 1, 1, thresholds) == margins.NEVER_OBSERVED
    assert margins.plausibility(row["p99"] + 1, 1, thresholds) == margins.BEYOND_P99
    assert margins.plausibility(row["p99"] - 1, 1, thresholds) == margins.LIVE_RACE


def test_the_same_gap_gets_less_alarming_with_more_weeks_left(thresholds):
    """200 points is impossible in one week and ordinary in five."""
    assert margins.plausibility(200, 1, thresholds) == margins.NEVER_OBSERVED
    assert margins.plausibility(200, 5, thresholds) == margins.LIVE_RACE


def test_weeks_out_of_range_clamp_to_the_widest_window(thresholds):
    available = sorted(int(k) for k in thresholds["by_weeks_remaining"])
    assert margins.plausibility(50, 99, thresholds) == margins.plausibility(
        50, available[-1], thresholds
    )


@pytest.mark.parametrize("weeks", [1, 2, 5])
def test_phrasing_reads_as_english(thresholds, weeks):
    for gap in (10, 150, 400):
        text = margins.describe({"rival": "Momma Gus", "gap": gap}, weeks, thresholds)
        assert text
        assert "Momma Gus" in text
        # Regression: an f-string produced "and week left" for a single week
        assert "week left" not in text
        assert "  " not in text


def test_no_dependency_means_no_note(thresholds):
    assert margins.describe(None, 1, thresholds) is None
    assert margins.qualifies_headline(None, 1, thresholds) is False


def test_only_a_live_race_qualifies_the_headline(thresholds):
    assert margins.qualifies_headline({"rival": "X", "gap": 40}, 1, thresholds) is True
    assert margins.qualifies_headline({"rival": "X", "gap": 400}, 1, thresholds) is False


# --- the dependency search itself ---------------------------------------------


def test_a_clinch_on_wins_alone_has_no_dependency():
    """Nobody can reach this team's win total, so points are irrelevant."""
    state = LeagueState(
        names=["Runaway", "A", "B", "C"],
        wins=[8, 3, 3, 2],
        losses=[0, 5, 5, 6],
        points=[2000.0, 1500.0, 1400.0, 1300.0],
        games=[(0, 1), (2, 3), (0, 2), (1, 3)],
        playoff_spots=2,
    )

    assert playoff_math.status_of(state, 0) == "clinched"
    assert playoff_math.clinch_dependency(state, 0) is None


def test_a_clinch_that_rests_on_the_tiebreaker_names_the_rival_and_the_gap():
    """Season over, one seat, and only total points separates two 5-5 teams."""
    state = LeagueState(
        names=["Holder", "Chaser", "Also"],
        wins=[5, 5, 3],
        losses=[5, 5, 7],
        points=[1900.0, 1750.0, 1200.0],
        games=[],
        playoff_spots=1,
    )

    assert playoff_math.status_of(state, 0) == "clinched"
    assert playoff_math.clinch_dependency(state, 0) == ("Chaser", 150.0)


def test_an_elimination_that_rests_on_the_tiebreaker_names_the_gap():
    state = LeagueState(
        names=["Holder", "Chaser", "Also"],
        wins=[5, 5, 3],
        losses=[5, 5, 7],
        points=[1900.0, 1750.0, 1200.0],
        games=[],
        playoff_spots=1,
    )

    assert playoff_math.status_of(state, 1) == "eliminated"
    assert playoff_math.elimination_dependency(state, 1) == ("Holder", 150.0)


def test_a_dependency_needing_two_rivals_reports_the_binding_one():
    """Two seats, three teams tied 5-5: the leader only drops out if BOTH pass it.

    Probing one rival at a time finds nothing here and would report a bare
    "clinched". The answer is the harder of the two gaps, since that is the one
    somebody actually has to close.
    """
    state = LeagueState(
        names=["Holder", "Near", "Far", "Out"],
        wins=[5, 5, 5, 1],
        losses=[5, 5, 5, 9],
        points=[1900.0, 1880.0, 1600.0, 900.0],
        games=[],
        playoff_spots=2,
    )

    assert playoff_math.status_of(state, 0) == "clinched"
    # Near alone passing leaves Holder 2nd of 2 -- still in.
    near_only = playoff_math._with_points_override(state, 1, 1900.01)
    assert playoff_math.status_of(near_only, 0) == "clinched"

    rival, gap = playoff_math.clinch_dependency(state, 0)
    assert rival == "Far"
    assert gap == 300.0


def test_a_clinch_safe_from_every_rival_has_no_dependency():
    """Three seats, four teams: the 5-5 trio is in whatever the points say."""
    state = LeagueState(
        names=["Holder", "Near", "Far", "Out"],
        wins=[5, 5, 5, 1],
        losses=[5, 5, 5, 9],
        points=[1900.0, 1880.0, 1600.0, 900.0],
        games=[],
        playoff_spots=3,
    )

    assert playoff_math.clinch_dependency(state, 0) is None


def test_dependencies_are_attached_only_to_decided_teams(load_fixture):
    import refine_current_week as stage2

    fixture = load_fixture("week13.json")
    settings = fixture["league_settings"]
    remaining = settings["weeks_in_season"] - settings["current_week"]
    standings = stage2.calculate_stats(
        fixture, settings["playoff_spots"], settings["weeks_in_season"], remaining
    )
    matchups = stage2.build_remaining_matchups(fixture["teams"], remaining)
    standings = playoff_math.apply_verdicts(standings, matchups, settings["playoff_spots"])
    standings = playoff_math.attach_dependencies(
        standings, matchups, settings["playoff_spots"]
    )

    for team in standings:
        assert "tiebreak" in team
        if team["verdict"] == "alive":
            assert team["tiebreak"] is None, (
                "an alive team already states its dependence on results as conditions"
            )
        if team["tiebreak"]:
            assert team["tiebreak"]["gap"] > 0
            assert team["tiebreak"]["rival"] != team["team_name"]
