"""head_to_head: manager-against-manager records and the manager-page careers.

The fixture is a four-team 2025 plus a two-team 2024, small enough that every
figure below is checkable by hand:

  2025 week 1   A 100 - 90 B      C 110 - 105 D
  2025 week 2   C 120 -  80 A     B  95 -  85 D
  2025 bracket  A 130 - 125 C
  2024 week 1   A 100 -  90 B

A is Ann, B is Bo, D is Ed, and C is co-managed by Cy and Dee.
"""

import json
import sys

sys.path.insert(0, "scenario_engine")
import head_to_head  # noqa: E402


def _team(name, managers, **over):
    team = {
        "name": name, "managers": managers, "wins": 0, "losses": 0, "ties": 0,
        "points_for": 0.0, "playoff_points_for": 0.0, "final_standing": 0, "seed": 0,
        "division": "", "division_winner": False, "made_playoffs": False,
        "playoff_wins": 0, "playoff_losses": 0, "playoff_ties": 0, "playoff_games": 0,
    }
    return {**team, **over}


def _weeks(*games):
    """(week, points, opponent) triples as a weekly_scores entry's weeks."""
    return [{"week": w, "points": p, "opponent": o} for w, p, o in games]


def history():
    s2025 = {
        "year": 2025, "complete": True, "num_teams": 4, "weeks_in_season": 2,
        "playoff_spots": 2, "division_names": {},
        "teams": [
            _team("A", ["Ann"], wins=1, losses=1, points_for=180.0, final_standing=1,
                  seed=2, made_playoffs=True, playoff_wins=1, playoff_games=1),
            _team("B", ["Bo"], wins=1, losses=1, points_for=185.0, final_standing=3, seed=3),
            _team("C", ["Cy", "Dee"], wins=2, points_for=230.0, final_standing=2,
                  seed=1, made_playoffs=True, playoff_losses=1, playoff_games=1),
            _team("D", ["Ed"], losses=2, points_for=190.0, final_standing=4, seed=4),
        ],
        "weekly_scores": [
            # Week 3 is unplayed: 0.0 both sides, which is not a result. Real
            # histories stop at the weeks played, but the guard has to hold.
            {"name": "A", "weeks": _weeks((1, 100.0, "B"), (2, 80.0, "C"), (3, 0.0, "B"))},
            {"name": "B", "weeks": _weeks((1, 90.0, "A"), (2, 95.0, "D"), (3, 0.0, "A"))},
            # C takes a bye in week 3 rather than a blank game.
            {"name": "C", "weeks": _weeks((1, 110.0, "D"), (2, 120.0, "A"), (3, 99.0, None))},
            {"name": "D", "weeks": _weeks((1, 105.0, "C"), (2, 85.0, "B"), (3, 0.0, "C"))},
        ],
        "playoff_weeks": [
            {"name": "A", "weeks": _weeks((3, 130.0, "C"))},
            {"name": "C", "weeks": _weeks((3, 125.0, "A"))},
        ],
    }
    s2024 = {
        "year": 2024, "complete": True, "num_teams": 2, "weeks_in_season": 1,
        "playoff_spots": 0, "division_names": {},
        "teams": [
            _team("A", ["Ann"], wins=1, points_for=100.0, final_standing=2, seed=1),
            _team("B", ["Bo"], losses=1, points_for=90.0, final_standing=1, seed=2),
        ],
        "weekly_scores": [
            {"name": "A", "weeks": _weeks((1, 100.0, "B"))},
            {"name": "B", "weeks": _weeks((1, 90.0, "A"))},
        ],
        "playoff_weeks": [],
    }
    return {"league_id": 1, "skipped": [], "seasons": [s2025, s2024]}


def payload():
    return json.loads(json.dumps(head_to_head.web_payload(history())))  # must serialise


def profile(name):
    return next(m for m in payload()["managers"] if m["manager"] == name)


def scoped(name, scope="both"):
    """One scope's game-derived figures. `both` is the page's default."""
    return profile(name)["scopes"][scope]


def pairing(a, b):
    key = sorted((a, b))
    return next(p for p in payload()["pairings"] if [p["a"], p["b"]] == key)


def test_every_manager_gets_a_page_including_a_co_manager():
    assert [m["manager"] for m in payload()["managers"]] == ["Ann", "Bo", "Cy", "Dee", "Ed"]


def test_a_record_counts_each_game_once_from_each_side():
    assert scoped("Ann", "regular")["record"]["wins"] == 2      # 2025 wk1, 2024 wk1
    assert scoped("Ann", "regular")["record"]["losses"] == 1    # 2025 wk2
    assert scoped("Ann", "regular")["record"]["games"] == 3
    assert scoped("Ed", "regular")["record"] == {
        "wins": 0, "losses": 2, "ties": 0, "games": 2,
        "points_for": 190.0, "points_against": 205.0, "ppg": 95.0, "papg": 102.5,
    }


def test_co_managers_each_get_the_whole_team_season():
    """Both of them played those games, which is how the careers read it too."""
    assert scoped("Cy", "regular")["record"] == scoped("Dee", "regular")["record"]
    assert scoped("Cy", "regular")["record"]["wins"] == 2


def test_co_managers_never_face_each_other():
    """They shared a team; a pairing between them would be a team playing itself."""
    assert not any({p["a"], p["b"]} == {"Cy", "Dee"} for p in payload()["pairings"])


def test_a_pairing_is_stored_once_from_a_side():
    head = pairing("Ann", "Cy")
    assert (head["a"], head["b"]) == ("Ann", "Cy")
    # Ann lost the regular-season meeting and won the bracket one.
    assert [head["regular"]["wins"], head["regular"]["losses"]] == [0, 1]
    assert [head["playoffs"]["wins"], head["playoffs"]["losses"]] == [1, 0]
    assert head["regular"]["points_for"] == 80.0
    assert head["regular"]["points_against"] == 120.0


def test_every_meeting_is_listed_in_time_order_with_the_bracket_last():
    meetings = pairing("Ann", "Cy")["meetings"]
    assert [(m["year"], m["week"], m["kind"]) for m in meetings] == [
        (2025, 2, "regular"), (2025, 3, "playoffs"),
    ]


def test_an_unplayed_week_is_not_a_result_and_a_bye_is_not_a_game():
    """Week 3 is 0.0 both sides for A, B and D, and a bye for C."""
    assert scoped("Ann", "regular")["record"]["games"] == 3    # not 4
    assert scoped("Cy", "regular")["record"]["games"] == 2     # the bye is not one


def test_playoff_games_are_kept_apart_from_the_regular_season():
    assert scoped("Ann", "playoffs")["record"] == {
        "wins": 1, "losses": 0, "ties": 0, "games": 1,
        "points_for": 130.0, "points_against": 125.0, "ppg": 130.0, "papg": 125.0,
    }
    # ...and never counted into the regular-season rates.
    assert scoped("Ann", "regular")["record"]["points_for"] == 280.0


def test_accolades_come_off_the_final_standing():
    assert profile("Ann")["accolades"] == {
        "championships": 1, "berths": 1, "division_titles": 0,
        "top_seeds": 1, "playoff_wins": 1,
    }
    assert profile("Bo")["accolades"]["championships"] == 1     # 2024
    assert profile("Cy")["accolades"]["top_seeds"] == 1


def test_expected_wins_say_what_the_schedule_was_worth():
    """All-play: 2025 week 1 A beats only B, week 2 A beats nobody; 2024 A beats B."""
    assert scoped("Ann", "regular")["expected"] == {"wins": 2, "losses": 5, "ties": 0}
    assert scoped("Cy", "regular")["expected"] == {"wins": 6, "losses": 0, "ties": 0}
    # 3 games at an all-play 2-5 is 0.857 wins; she actually won 2, so the draw
    # was worth a bit over a win to her.
    assert scoped("Ann", "regular")["expected_wins"] == 0.9
    assert scoped("Cy", "regular")["expected_wins"] == 2.0


def test_a_close_game_is_decided_by_less_than_the_threshold():
    """C-D was 5 apart and counts; A-B was exactly 10 and does not."""
    assert head_to_head.CLOSE_GAME == 10.0
    assert scoped("Cy", "regular")["close"] == {"wins": 1, "losses": 0, "ties": 0}
    assert scoped("Ann", "regular")["close"] == {"wins": 0, "losses": 0, "ties": 0}
    assert scoped("Ed", "regular")["close"] == {"wins": 0, "losses": 1, "ties": 0}


def test_a_streak_carries_across_seasons():
    """Ann won 2024 week 1 and 2025 week 1 before losing: a streak of two, and
    one that only exists if seasons are not treated as separate careers."""
    win = scoped("Ann", "regular")["streaks"]["win"]
    assert win["length"] == 2
    assert win["start"] == {"year": 2024, "week": 1}
    assert win["end"] == {"year": 2025, "week": 1}
    assert scoped("Ann", "regular")["streaks"]["loss"]["length"] == 1


def test_a_streak_reports_where_it_began_and_ended():
    """"Six straight" invites "when?", and a length cannot answer it."""
    ed = scoped("Ed", "regular")["streaks"]
    assert ed["win"] == {"length": 0, "start": None, "end": None}
    assert ed["loss"] == {
        "length": 2, "start": {"year": 2025, "week": 1}, "end": {"year": 2025, "week": 2},
    }


def test_scoring_reports_the_spread_not_just_the_average():
    scoring = scoped("Ann", "regular")["scoring"]
    assert scoring["ppg"] == round((100 + 80 + 100) / 3, 2)
    # She hit 100 twice; a tie reports the first time she did it.
    assert scoring["high"] == {"points": 100.0, "year": 2024, "week": 1}
    assert scoring["low"] == {"points": 80.0, "year": 2025, "week": 2}
    assert scoring["stdev"] > 0


def test_margins_separate_a_blowout_from_a_nailbiter():
    assert scoped("Ann", "regular")["margins"] == {"avg_win": 10.0, "avg_loss": 40.0}
    assert scoped("Cy", "regular")["margins"]["avg_win"] == 22.5    # 5 and 40


def test_top_scorer_weeks_count_the_leagues_high_score():
    """C posted the week's best in both 2025 weeks; A did in 2024. C's week-3 bye
    scored 99 with nobody else playing, and crowning that would invent a week."""
    assert scoped("Cy", "regular")["top_scorer_weeks"] == 2
    assert scoped("Dee", "regular")["top_scorer_weeks"] == 2
    assert scoped("Ann", "regular")["top_scorer_weeks"] == 1


def test_the_record_against_teams_that_made_the_playoffs():
    """Ann's only game against a qualifier was the one she lost to C."""
    assert scoped("Ann", "regular")["vs_playoff_teams"] == {"wins": 0, "losses": 1, "ties": 0}


def test_a_season_row_carries_the_finish_beside_the_ppg_rank():
    rows = profile("Ann")["season_rows"]
    assert [row["year"] for row in rows] == [2024, 2025]
    assert rows[1] == {
        "year": 2025, "team": "A", "complete": True, "teams": 4,
        "wins": 1, "losses": 1, "ties": 0,
        "points_for": 180.0, "ppg": 90.0, "ppg_rank": 4, "finish": 1,
        "seed": 2, "made_playoffs": True, "division_winner": False, "playoff_wins": 1,
    }


def test_rank_is_on_points_per_game_not_the_total():
    """With an unfinished season folded in, teams have played different numbers
    of weeks, and a total would rank on games played as much as on scoring."""
    hist = history()
    # Give D a third game nobody else played: the most points, the worst average.
    season = hist["seasons"][0]
    for entry in season["weekly_scores"]:
        if entry["name"] == "D":
            entry["weeks"].append({"week": 4, "points": 60.0, "opponent": "C"})
        elif entry["name"] == "C":
            entry["weeks"].append({"week": 4, "points": 50.0, "opponent": "D"})
    for team in season["teams"]:
        if team["name"] == "D":
            team["wins"], team["losses"], team["points_for"] = 1, 2, 250.0
        elif team["name"] == "C":
            team["wins"], team["losses"], team["points_for"] = 2, 1, 280.0
    out = head_to_head.web_payload(hist)
    ranks = {
        row["team"]: row["ppg_rank"]
        for m in out["managers"] for row in m["season_rows"] if row["year"] == 2025
    }
    # D scored the most points of anyone and still ranks last on PPG (83.3).
    assert ranks["D"] == 4
    assert ranks["C"] == 1


def test_co_managers_are_named_with_the_years_they_shared():
    assert profile("Cy")["co_managers"] == [{"manager": "Dee", "years": [2025]}]
    assert profile("Ann")["co_managers"] == []


def test_an_in_progress_season_still_counts_its_games():
    """A game that has been played is a result whether or not its season has
    finished, so the record counts it."""
    hist = history()
    hist["seasons"][0]["complete"] = False
    out = head_to_head.web_payload(hist)
    ann = next(m for m in out["managers"] if m["manager"] == "Ann")
    assert ann["years"] == [2024, 2025]
    assert ann["scopes"]["regular"]["record"]["games"] == 3
    assert ann["season_rows"][1]["complete"] is False


def test_an_in_progress_season_hands_out_no_hardware():
    """Mid-season ESPN publishes a live seed and standing. Counting them would
    award a title, a berth and a #1 seed nobody has earned."""
    hist = history()
    hist["seasons"][0]["complete"] = False
    out = head_to_head.web_payload(hist)
    ann = next(m for m in out["managers"] if m["manager"] == "Ann")
    # 2025 had her champion, in the playoffs, with a bracket win: all dropped.
    # 2024 is still finished, and its #1 seed still counts.
    assert ann["accolades"] == {
        "championships": 0, "berths": 0, "division_titles": 0,
        "top_seeds": 1, "playoff_wins": 0,
    }
    # ...and her games against a live "qualifier" are not credited as such.
    assert ann["scopes"]["regular"]["vs_playoff_teams"] == {"wins": 0, "losses": 0, "ties": 0}


def test_the_scopes_are_the_all_time_ones_and_both_is_the_sum():
    """`both` has to be the two added up, or the toggle would change the facts
    rather than the view of them."""
    out = payload()
    assert out["scopes"] == ["regular", "both", "playoffs"]
    assert out["default_scope"] == "both"
    s = profile("Ann")["scopes"]
    for part in ("wins", "losses", "ties", "games"):
        assert s["both"]["record"][part] == s["regular"]["record"][part] + s["playoffs"]["record"][part]
    assert s["both"]["record"]["points_for"] == round(
        s["regular"]["record"]["points_for"] + s["playoffs"]["record"]["points_for"], 2)


# --- long playoff rounds -----------------------------------------------------


def _long_round_history():
    """2025, one bracket round at matchup period 3 covering weeks 3 and 4.

      A 130 + 170 = 300    C 125 + 125 = 250

    A won the round, so the tally is 1-0 over one game; the two afternoons are
    listed separately for the leaderboards.
    """
    return {
        "league_id": 1, "skipped": [],
        "seasons": [{
            "year": 2025, "complete": True, "num_teams": 2, "weeks_in_season": 2,
            "playoff_spots": 2, "division_names": {},
            "teams": [
                _team("A", ["Ann"], wins=1, points_for=100.0, final_standing=1, seed=1,
                      made_playoffs=True, playoff_wins=1, playoff_games=1),
                _team("C", ["Cy"], losses=1, points_for=90.0, final_standing=2, seed=2,
                      made_playoffs=True, playoff_losses=1, playoff_games=1),
            ],
            "weekly_scores": [
                {"name": "A", "weeks": _weeks((1, 100.0, "C"), (2, 110.0, "C"))},
                {"name": "C", "weeks": _weeks((1, 90.0, "A"), (2, 95.0, "A"))},
            ],
            "playoff_weeks": [
                {"name": "A", "weeks": [{"week": 3, "points": 300.0, "opponent": "C",
                                         "parts": [{"week": 3, "points": 130.0},
                                                   {"week": 4, "points": 170.0}]}]},
                {"name": "C", "weeks": [{"week": 3, "points": 250.0, "opponent": "A",
                                         "parts": [{"week": 3, "points": 125.0},
                                                   {"week": 4, "points": 125.0}]}]},
            ],
        }],
    }


def test_a_long_round_is_listed_by_the_week_but_tallied_once():
    out = json.loads(json.dumps(head_to_head.web_payload(_long_round_history())))
    pair = out["pairings"][0]

    # One contest, decided on the aggregate: counting it twice would invent a
    # result, since C won week 4 outright but lost the round.
    assert pair["playoffs"]["wins"] + pair["playoffs"]["losses"] == 1
    assert pair["playoffs"]["points_for"] == 300.0
    assert pair["playoffs"]["points_against"] == 250.0

    rounds = [m for m in pair["meetings"] if m["kind"] == "playoffs"]
    assert [(m["week"], m["points"], m["opponent_points"]) for m in rounds] == [
        (3, 130.0, 125.0), (4, 170.0, 125.0),
    ]
    # And no row carries the doubled total any more.
    assert 300.0 not in [m["points"] for m in pair["meetings"]]


def test_the_weeks_high_score_is_per_afternoon_not_per_round():
    out = json.loads(json.dumps(head_to_head.web_payload(_long_round_history())))
    led = {m["manager"]: m["scopes"]["playoffs"]["top_scorer_weeks"] for m in out["managers"]}
    # A outscored C in both weeks of the round, so two weeks led -- not one for a
    # round, and not a week credited to C for having the larger of nothing.
    assert led == {"Ann": 2, "Cy": 0}


def test_an_unsplit_round_still_reads_as_one_week():
    # No `parts` is the ordinary case and the fallback when ESPN cannot be split.
    history = _long_round_history()
    for entry in history["seasons"][0]["playoff_weeks"]:
        for week in entry["weeks"]:
            week.pop("parts")
    out = json.loads(json.dumps(head_to_head.web_payload(history)))
    pair = out["pairings"][0]
    rounds = [m for m in pair["meetings"] if m["kind"] == "playoffs"]
    assert [(m["week"], m["points"]) for m in rounds] == [(3, 300.0)]
    assert pair["playoffs"]["wins"] + pair["playoffs"]["losses"] == 1
