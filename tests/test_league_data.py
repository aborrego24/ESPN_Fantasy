"""Stage 1: shaping an ESPN League into the pipeline payload.

This path was previously untestable -- the module executed everything at import
time, including a live network call -- so none of it was covered. It is now
exercised against a fake league, with no network access.

The fake mirrors the parts of espn_api the code touches, including the awkward
part: Matchup declares home_team/away_team as bare annotations and only assigns
them when a team id matches, so on a bye the attribute does not exist at all.
"""

import json
import sys

import pytest

import league_data


class FakeSettings:
    def __init__(self, weeks, playoff_spots):
        self.reg_season_count = weeks
        self.playoff_team_count = playoff_spots


class FakeTeam:
    """Carries per-week scores, since records are recomputed from them.

    wins/losses/ties/points_for are the CURRENT totals espn_api reports. They
    are deliberately set to values that disagree with the weekly scores, so a
    test fails if the code reads them instead of recomputing.

    team_id is what espn_api actually guarantees to be unique, so it is assigned
    automatically and never repeats -- a fake that let two teams share an id
    would hide exactly the bug the id exists to prevent.
    """

    _next_id = 1

    def __init__(
        self,
        name,
        scores,
        wins=99,
        losses=99,
        ties=99,
        points_for=99999.0,
        team_id=None,
        team_abbrev=None,
        logo_url=None,
    ):
        self.team_name = name
        self.scores = list(scores)
        self.wins = wins
        self.losses = losses
        self.ties = ties
        self.points_for = points_for
        self.schedule = []
        if team_id is None:
            team_id = FakeTeam._next_id
            FakeTeam._next_id += 1
        self.team_id = team_id
        self.team_abbrev = team_abbrev
        self.logo_url = logo_url


class FakeMatchup:
    """Set home/away only when given, mirroring espn_api's bye behaviour."""

    def __init__(self, home=None, away=None):
        if home is not None:
            self.home_team = home
        if away is not None:
            self.away_team = away


class FakeLeague:
    def __init__(self, teams, weeks, playoff_spots, schedule_by_week, current_week=None):
        self.teams = teams
        self.settings = FakeSettings(weeks, playoff_spots)
        # schedule_by_week[w] is a list of (home, away) for 1-based week w
        self._schedule = schedule_by_week
        # Deliberately wrong: on a finished season espn_api clamps this to the
        # final scoring period, so any code trusting it describes another week.
        self.current_week = current_week if current_week is not None else weeks
        self.scoreboard_calls = []
        for team in teams:
            for week in range(1, weeks + 1):
                for home, away in self._schedule.get(week, []):
                    if home is team:
                        team.schedule.append(away)
                    elif away is team:
                        team.schedule.append(home)

    def scoreboard(self, week=None):
        self.scoreboard_calls.append(week)
        return [
            FakeMatchup(home, away) for home, away in self._schedule.get(week, [])
        ]


def four_team_league(weeks=4, playoff_spots=2, current_week_override=None):
    # Week:              1      2      3      4
    a = FakeTeam("Alpha", [120.0, 110.0, 100.0, 130.0])
    b = FakeTeam("Bravo", [100.0, 105.0, 115.0, 90.0])
    c = FakeTeam("Charlie", [90.0, 100.0, 118.0, 95.0])
    d = FakeTeam("Delta", [80.0, 95.0, 90.0, 85.0])
    schedule = {
        1: [(a, b), (c, d)],
        2: [(a, c), (b, d)],
        3: [(a, d), (b, c)],
        4: [(a, b), (c, d)],
    }
    return FakeLeague(
        [a, b, c, d], weeks, playoff_spots, schedule, current_week_override
    )


def test_payload_has_the_shape_stage_two_expects():
    payload = league_data.build_payload(four_team_league(), current_week=2)

    assert set(payload) == {
        "league_settings",
        "teams",
        "next_week_matchups",
        "weekly_scores",
        "abbreviations",
        "logos",
        "divisions",
        "division_names",
        "projected_ppg",
    }
    assert payload["league_settings"] == {
        "num_teams": 4,
        "playoff_spots": 2,
        "bye_spots": 0,
        "weeks_in_season": 4,
        "current_week": 2,
        "tiebreaker": "points_for",
    }
    assert [t["name"] for t in payload["teams"]] == [
        "Alpha",
        "Bravo",
        "Charlie",
        "Delta",
    ]
    # Alpha beat Bravo 120-100 in week 1 and Charlie 110-100 in week 2
    assert payload["teams"][0]["record"] == {"wins": 2, "losses": 0, "ties": 0}
    assert payload["teams"][0]["points_for"] == 230.0


def test_logos_are_inlined_only_when_asked(monkeypatch):
    """--logos drives the fetch; without it stage 1 does no image work at all."""
    league = four_team_league()
    for team in league.teams:
        team.logo_url = f"http://logos/{team.team_name}.svg"
    # Stub the fetch+encode so the test needs no network or Pillow
    monkeypatch.setattr(
        league_data.logo,
        "inline_all",
        lambda urls: {name: f"inlined:{url}" for name, url in urls.items()},
    )

    off = league_data.build_payload(league, current_week=2)
    on = league_data.build_payload(league, current_week=2, inline_logos=True)

    assert off["logos"] == {}, "no --logos means no logos, not even the URLs"
    assert on["logos"]["Alpha"] == "inlined:http://logos/Alpha.svg"
    assert set(on["logos"]) == {"Alpha", "Bravo", "Charlie", "Delta"}


def test_division_names_come_from_the_settings_map():
    class Settings:
        division_map = {0: "East", 1: "West"}

    class League:
        settings = Settings()

    assert league_data.division_names_of(League()) == {0: "East", 1: "West"}


def test_division_names_are_empty_for_a_single_division_or_none():
    class OneDivision:
        settings = type("S", (), {"division_map": {0: "The League"}})()

    class NoMap:
        settings = type("S", (), {})()

    assert league_data.division_names_of(OneDivision()) == {}
    assert league_data.division_names_of(NoMap()) == {}


def test_next_week_matchups_come_from_the_requested_week():
    """Regression: the scoreboard used to be asked for league.current_week.

    On a finished season that clamps to the final scoring period, so the
    standings described one week and the matchups another.
    """
    league = four_team_league(current_week_override=4)

    payload = league_data.build_payload(league, current_week=2)

    assert league.scoreboard_calls == [3], "must ask for the week after the one played"
    pairs = {frozenset((m["team1"], m["team2"])) for m in payload["next_week_matchups"]}
    assert pairs == {frozenset(("Alpha", "Delta")), frozenset(("Bravo", "Charlie"))}


def test_next_week_matchups_read_the_matchup_not_the_schedule():
    """Regression: team2 used to be remaining_schedule[0] of the home team.

    That only agreed with reality when the schedule slice and the scoreboard
    lined up exactly, and raised TypeError when the slice was empty.
    """
    payload = league_data.build_payload(four_team_league(), current_week=2)

    for matchup in payload["next_week_matchups"]:
        assert matchup["team1"] != matchup["team2"]

    # Every team plays exactly once next week
    named = [t for m in payload["next_week_matchups"] for t in (m["team1"], m["team2"])]
    assert sorted(named) == ["Alpha", "Bravo", "Charlie", "Delta"]


def test_remaining_schedule_covers_only_unplayed_weeks():
    payload = league_data.build_payload(four_team_league(), current_week=2)

    for team in payload["teams"]:
        assert len(team["remaining_schedule"]) == 2
        assert team["name"] not in team["remaining_schedule"]


def test_the_first_remaining_opponent_agrees_with_next_week():
    """The two views of next week must not disagree -- stage 2 uses both."""
    payload = league_data.build_payload(four_team_league(), current_week=2)
    by_name = {t["name"]: t for t in payload["teams"]}

    for matchup in payload["next_week_matchups"]:
        assert by_name[matchup["team1"]]["remaining_schedule"][0] == matchup["team2"]
        assert by_name[matchup["team2"]]["remaining_schedule"][0] == matchup["team1"]


def test_final_week_played_leaves_no_matchups():
    """Season over: nothing left to enumerate, and no scoreboard call."""
    league = four_team_league()

    payload = league_data.build_payload(league, current_week=4)

    assert payload["next_week_matchups"] == []
    assert all(t["remaining_schedule"] == [] for t in payload["teams"])
    assert league.scoreboard_calls == []


def test_a_bye_week_is_skipped_rather_than_crashing():
    """An odd-sized league leaves home_team/away_team unset on the bye."""
    a = FakeTeam("Alpha", [110.0, 120.0, 100.0])
    b = FakeTeam("Bravo", [100.0, 90.0, 95.0])
    c = FakeTeam("Charlie", [90.0, 105.0, 115.0])
    schedule = {1: [(a, b)], 2: [(a, c)], 3: [(b, c)]}
    league = FakeLeague([a, b, c], 3, 2, schedule)
    # Charlie has a bye in week 2's real scoreboard
    league._schedule[2] = [(a, c), (b, None)]

    payload = league_data.build_payload(league, current_week=1)

    assert payload["next_week_matchups"] == [{"team1": "Alpha", "team2": "Charlie"}]


def test_an_equal_score_is_recorded_as_a_tie():
    """matchupTieRule is NONE in this league, so equal scores stand."""
    league = four_team_league()
    # Make week 1 Alpha vs Bravo a dead heat
    league.teams[0].scores[0] = 100.0

    payload = league_data.build_payload(league, current_week=1)

    assert payload["teams"][0]["record"] == {"wins": 0, "losses": 0, "ties": 1}
    assert payload["teams"][1]["record"] == {"wins": 0, "losses": 0, "ties": 1}


# --- argument handling --------------------------------------------------------


def test_test_mode_needs_no_network_and_no_week(tmp_path, capsys):
    fixture = tmp_path / "payload.json"
    fixture.write_text(json.dumps({"league_settings": {}, "teams": []}))

    assert league_data.main(["--test", str(fixture)]) == 0

    assert json.loads(capsys.readouterr().out) == {"league_settings": {}, "teams": []}


def test_league_and_year_are_configurable():
    args, _ = league_data.parse_args(["3", "--league-id", "999", "--year", "2025"])

    assert (args.week, args.league_id, args.year) == (3, 999, 2025)


def test_league_and_year_default_to_the_known_league():
    args, _ = league_data.parse_args(["3"])

    assert args.league_id == league_data.DEFAULT_LEAGUE_ID
    assert args.year == league_data.DEFAULT_YEAR


def test_environment_overrides_the_defaults(monkeypatch):
    monkeypatch.setenv("ESPN_LEAGUE_ID", "4242")
    monkeypatch.setenv("ESPN_YEAR", "2019")

    args, _ = league_data.parse_args(["3"])

    assert (args.league_id, args.year) == (4242, 2019)


def test_no_arguments_at_all_is_an_error():
    with pytest.raises(SystemExit):
        league_data.main([])


def test_a_non_integer_week_is_an_error():
    with pytest.raises(SystemExit):
        league_data.main(["not-a-week"])


# --- records must describe the week asked for, not the current one -------------


@pytest.mark.parametrize("week", [0, 1, 2, 3, 4])
def test_games_played_always_equals_the_week_asked_for(week):
    """The regression that produced 7 clinched teams for 6 seats.

    espn_api reports CURRENT totals. Reading them while asking about an earlier
    week gave a finished 14-game record plus 2 games still listed as remaining,
    so the engine built 16-game seasons and everyone clinched.
    """
    payload = league_data.build_payload(four_team_league(), current_week=week)

    for team in payload["teams"]:
        record = team["record"]
        played = record["wins"] + record["losses"] + record["ties"]
        assert played == week, f"{team['name']} shows {played} games at week {week}"
        assert played + len(team["remaining_schedule"]) == 4


def test_current_totals_are_ignored_in_favour_of_the_weekly_scores():
    league = four_team_league()
    for team in league.teams:
        assert team.wins == 99, "fake should disagree with its own scores"

    payload = league_data.build_payload(league, current_week=2)

    assert all(t["record"]["wins"] != 99 for t in payload["teams"])


def test_record_through_week_counts_each_result_once():
    league = four_team_league()
    alpha = league.teams[0]

    assert league_data.record_through_week(alpha, 0) == (0, 0, 0, 0.0)
    # w1 beat Bravo 120-100, w2 beat Charlie 110-100, w3 beat Delta 100-90
    assert league_data.record_through_week(alpha, 3) == (3, 0, 0, 330.0)


def test_points_for_accumulates_only_the_weeks_played():
    league = four_team_league()

    through_two = league_data.build_payload(league, current_week=2)
    through_four = league_data.build_payload(league, current_week=4)

    for early, late in zip(through_two["teams"], through_four["teams"]):
        assert early["points_for"] < late["points_for"]


# --- weekly history, for the season-review tables -----------------------------


@pytest.mark.parametrize("week", [0, 1, 2, 3, 4])
def test_weekly_scores_cover_exactly_the_weeks_played(week):
    payload = league_data.build_payload(four_team_league(), current_week=week)

    assert len(payload["weekly_scores"]) == 4
    for entry in payload["weekly_scores"]:
        assert [w["week"] for w in entry["weeks"]] == list(range(1, week + 1))


def test_weekly_scores_report_the_real_score_and_opponent():
    payload = league_data.build_payload(four_team_league(), current_week=4)
    by_name = {e["name"]: e["weeks"] for e in payload["weekly_scores"]}

    # Alpha: 120 vs Bravo, 110 vs Charlie, 100 vs Delta, 130 vs Bravo
    assert [w["points"] for w in by_name["Alpha"]] == [120.0, 110.0, 100.0, 130.0]
    assert [w["opponent"] for w in by_name["Alpha"]] == [
        "Bravo",
        "Charlie",
        "Delta",
        "Bravo",
    ]


def test_the_weekly_history_agrees_with_the_record_built_from_it():
    """Two derivations of the same games must not disagree.

    `record` comes from record_through_week and the history from
    weekly_history; if they ever diverge, one of them is reading the wrong week.
    """
    payload = league_data.build_payload(four_team_league(), current_week=4)
    points = {e["name"]: [w["points"] for w in e["weeks"]] for e in payload["weekly_scores"]}
    opponents = {e["name"]: [w["opponent"] for w in e["weeks"]] for e in payload["weekly_scores"]}

    for team in payload["teams"]:
        name = team["name"]
        wins = losses = ties = 0
        for index, opponent in enumerate(opponents[name]):
            mine, theirs = points[name][index], points[opponent][index]
            if mine > theirs:
                wins += 1
            elif mine < theirs:
                losses += 1
            else:
                ties += 1
        assert team["record"] == {"wins": wins, "losses": losses, "ties": ties}
        assert team["points_for"] == pytest.approx(sum(points[name]))


def test_a_team_is_never_its_own_weekly_opponent():
    payload = league_data.build_payload(four_team_league(), current_week=4)

    for entry in payload["weekly_scores"]:
        for week in entry["weeks"]:
            assert week["opponent"] != entry["name"]


def test_a_future_bye_keeps_its_slot_in_the_remaining_schedule():
    """The slot has to stay, because stage 2 pairs teams up by position.

    Dropping the entry would silently shift every later week one earlier, which
    is worse than the bye it was meant to handle.
    """
    league = four_team_league()
    league.teams[0].schedule[2] = None  # Alpha idle in week 3

    payload = league_data.build_payload(league, current_week=1)
    alpha = payload["teams"][0]

    assert alpha["remaining_schedule"] == ["Charlie", None, "Bravo"]


def test_a_week_with_no_opponent_is_recorded_as_a_bye():
    """A short schedule must read as "no game", not raise IndexError."""
    a = FakeTeam("Alpha", [110.0, 120.0, 100.0])
    b = FakeTeam("Bravo", [100.0, 90.0, 95.0])
    c = FakeTeam("Charlie", [90.0, 105.0, 115.0])
    # Bravo sits out week 2, so its schedule is a week short of the season
    league = FakeLeague([a, b, c], 3, 2, {1: [(a, b)], 2: [(a, c)], 3: [(b, c)]})

    payload = league_data.build_payload(league, current_week=3)
    by_name = {e["name"]: e["weeks"] for e in payload["weekly_scores"]}

    assert [w["opponent"] for w in by_name["Bravo"]] == ["Alpha", "Charlie", None]
    assert [w["points"] for w in by_name["Bravo"]] == [100.0, 90.0, 95.0]


def test_played_weeks_counts_only_scored_weeks():
    league = four_team_league()
    assert league_data.played_weeks(league) == 4

    # A live season: weeks 3 and 4 not yet played
    for team in league.teams:
        team.scores[2] = 0
        team.scores[3] = 0
    assert league_data.played_weeks(league) == 2


# --- projected PPG (preseason) --------------------------------------------------


class FakePlayer:
    def __init__(self, name, eligible_slots, projected_avg_points):
        self.name = name
        self.eligibleSlots = eligible_slots
        self.projected_avg_points = projected_avg_points


class FakeRosterTeam:
    _next_id = 1

    def __init__(self, name, roster):
        self.team_name = name
        self.roster = roster
        self.team_id = FakeRosterTeam._next_id
        FakeRosterTeam._next_id += 1


class FakeProjLeague:
    """Minimal league exposing the raw settings and rosters projected_ppg needs."""

    def __init__(self, teams, slot_counts):
        self.teams = teams

        class _Request:
            def get_league(self):
                return {"settings": {"rosterSettings": {"lineupSlotCounts": slot_counts}}}

        self.espn_request = _Request()


def test_projected_ppg_is_empty_when_the_league_cannot_supply_it():
    """The ordinary fake has no rosters or raw settings, so it degrades to {} --
    and the payload still carries the key."""
    payload = league_data.build_payload(four_team_league(), current_week=2)

    assert payload["projected_ppg"] == {}


def test_projected_ppg_sums_the_best_legal_starting_lineup():
    """Two QBs but one QB slot: only the better starts; the spare QB is benched."""
    team = FakeRosterTeam(
        "A",
        [
            FakePlayer("QB1", ["QB"], 20.0),
            FakePlayer("QB2", ["QB"], 15.0),
            FakePlayer("RB1", ["RB", "RB/WR/TE"], 18.0),
        ],
    )
    # slot ids: 0=QB x1, 2=RB x1, 20=BE x3 (bench never scores)
    league = FakeProjLeague([team], {"0": 1, "2": 1, "20": 3})
    names = {team.team_id: "A"}

    assert league_data.projected_ppg(league, names) == {"A": 38.0}


def test_starting_slots_drops_bench_and_ir():
    league = FakeProjLeague([], {"0": 1, "2": 2, "20": 5, "21": 1})

    assert league_data.starting_slots(league) == {"QB": 1, "RB": 2}
