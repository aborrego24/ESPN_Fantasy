"""Ranking team-seasons across a league's whole history.

The four-team season below is the same one test_league_stats.py works from, so
the all-play numbers underneath these ratings are already hand-checked there.

  week:      1      2      3      4
  Alpha    120.0  110.0  100.0  130.0     4-0
  Bravo    100.0  105.0  115.0   90.0     1-3
  Charlie   90.0  100.0  118.0   95.0     3-1
  Delta     80.0   95.0   90.0   85.0     0-4

  schedule  1: Alpha-Bravo, Charlie-Delta
            2: Alpha-Charlie, Bravo-Delta
            3: Alpha-Delta, Bravo-Charlie
            4: Alpha-Bravo, Charlie-Delta

The season that matters most here is the second one: the same league with every
score halved. A rating that changes between the two is reading raw points, which
is the whole thing this module exists to avoid.
"""

import pytest

import all_time

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

# Alpha 4-0, Charlie 3-1, Bravo 1-3, Delta 0-4 -- worked out from the grid above.
RECORDS = {
    "Alpha": (4, 0),
    "Bravo": (1, 3),
    "Charlie": (3, 1),
    "Delta": (0, 4),
}

# Alpha was the best team and won it; Charlie lost the final; Bravo and Delta
# missed the two-team bracket.
FINALS = {"Alpha": 1, "Bravo": 3, "Charlie": 2, "Delta": 4}
SEEDS = {"Alpha": 1, "Charlie": 2, "Bravo": 3, "Delta": 4}


def season(
    year=2025,
    scale=1.0,
    complete=True,
    finals=None,
    seeds=None,
    owners=None,
    playoff_spots=2,
):
    """A history-payload season built from the grid above.

    `scale` multiplies every score, which is how the era-normalisation tests ask
    for "the same season in a different scoring environment".
    """
    finals = FINALS if finals is None else finals
    seeds = SEEDS if seeds is None else seeds
    owners = owners or {name: f"own-{name}" for name in SCORES}

    scores = {name: [v * scale for v in vals] for name, vals in SCORES.items()}
    opponents = {name: [None] * len(SCHEDULE) for name in SCORES}
    for index, week in enumerate(SCHEDULE):
        for home, away in week:
            opponents[home][index] = away
            opponents[away][index] = home

    teams = []
    for name in SCORES:
        wins, losses = RECORDS[name]
        teams.append(
            {
                "name": name,
                "owner_id": owners[name],
                "owner": owners[name],
                "wins": wins,
                "losses": losses,
                "ties": 0,
                "points_for": round(sum(scores[name]), 2),
                "final_standing": finals.get(name, 0),
                "seed": seeds.get(name, 0),
            }
        )

    return {
        "year": year,
        "name": "Test League",
        "num_teams": len(SCORES),
        "weeks_in_season": len(SCHEDULE),
        "weeks_played": len(SCHEDULE),
        "complete": complete,
        "playoff_spots": playoff_spots,
        "teams": teams,
        "weekly_scores": [
            {
                "name": name,
                "weeks": [
                    {
                        "week": index + 1,
                        "points": scores[name][index],
                        "opponent": opponents[name][index],
                    }
                    for index in range(len(SCHEDULE))
                ],
            }
            for name in SCORES
        ],
    }


def by_name(rows):
    return {row["name"]: row for row in rows}


def test_every_rate_survives_a_change_of_scoring_era():
    """Halving every score in the league must not move any rate.

    A season total is not comparable across years -- scoring inflation alone would
    put every recent team at the top of an all-time list. Each component is a
    within-season measure, so the identical league played at half the points has
    to produce identical strength, results and firepower.
    """
    rich = by_name(all_time.season_rows(season(year=2024)))
    lean = by_name(all_time.season_rows(season(year=2025, scale=0.5)))

    for name in SCORES:
        assert rich[name]["strength"] == lean[name]["strength"]
        assert rich[name]["record"] == lean[name]["record"]
        assert rich[name]["scoring"] == lean[name]["scoring"]
        assert rich[name]["rating"] == lean[name]["rating"]
        # The raw scoring is still reported, and there it should differ.
        # Compared loosely because both are rounded for display: an odd PPG like
        # 100.75 halves to 50.375, which is stored as 50.38.
        assert rich[name]["ppg"] == pytest.approx(2 * lean[name]["ppg"], abs=0.02)


def test_ppg_is_measured_against_that_seasons_league():
    """Firepower is a z-score, so the league average is 0.5 by construction."""
    rows = all_time.season_rows(season())
    assert all(0.0 <= row["scoring"] <= 1.0 for row in rows)
    # Alpha out-scored the league and Delta was out-scored by it.
    assert by_name(rows)["Alpha"]["scoring"] > 0.5
    assert by_name(rows)["Delta"]["scoring"] < 0.5


def test_ppg_divides_by_weeks_scored_not_games_played():
    """A bye scores no points and settles no game; both denominators drop by one.

    Measured on a real 9-team league, where every team byes at least once. Dividing
    a 4-week points total by 3 games would inflate the whole league.
    """
    payload = season()
    # Give Alpha a bye in week 4: no opponent, no score, and one game fewer.
    payload["weekly_scores"][0]["weeks"][3] = {
        "week": 4,
        "points": 0.0,
        "opponent": None,
    }
    alpha = payload["teams"][0]
    alpha["points_for"] = 120.0 + 110.0 + 100.0
    alpha["wins"], alpha["losses"] = 3, 0

    row = by_name(all_time.season_rows(payload))["Alpha"]
    assert row["ppg"] == 110.0  # 330 over three scored weeks, not 330/4
    assert row["record"] == 1.0  # 3-0, not 3-0-1


def test_hardware_ranks_the_trophies_and_needs_a_finished_bracket():
    """A six-team bracket: the champion wins three, the runner-up two, a
    semifinal loser one, a first-round exit none."""
    champion, _ = all_time.hardware(
        {"final_standing": 1, "seed": 3, "playoff_wins": 3}, 6
    )
    runner_up, _ = all_time.hardware(
        {"final_standing": 2, "seed": 3, "playoff_wins": 2}, 6
    )
    final_four, _ = all_time.hardware(
        {"final_standing": 4, "seed": 3, "playoff_wins": 1}, 6
    )
    berth_only, _ = all_time.hardware(
        {"final_standing": 5, "seed": 3, "playoff_wins": 0}, 6
    )
    assert champion > runner_up > final_four > berth_only > 0
    # The title is the largest single award by a distance -- it alone outweighs
    # everything a deep run without one can earn.
    assert all_time.CHAMPION > runner_up

    # Mid-season ESPN reports 0 for the final standing while still publishing a
    # live seed. Nothing should be credited for the bracket, though leading the
    # league is still worth its top-seed points.
    unfinished, labels = all_time.hardware({"final_standing": 0, "seed": 1}, 4)
    assert "Champion" not in labels and "Final four" not in labels
    assert unfinished == all_time.PLAYOFF_BERTH + all_time.TOP_SEED


def test_a_berth_is_read_from_the_seed_not_the_final_standing():
    """The final standing is a playoff result, and can rank a qualifier below a
    team that never made it. Only the seed says who got in."""
    _, made_it = all_time.hardware({"final_standing": 8, "seed": 2}, 4)
    _, missed = all_time.hardware({"final_standing": 3, "seed": 7}, 4)
    assert "Playoffs" in made_it
    assert "Playoffs" not in missed


def test_a_season_in_progress_is_excluded_rather_than_discounted():
    """Measured: a 3-0 start four weeks into a real season came out second best
    all time, because a short sample sits further from its league mean on every
    rate at once. It has to be left out, and the omission has to be visible."""
    history = {
        "seasons": [season(year=2026, complete=False), season(year=2025)],
        "skipped": [],
    }
    rows = all_time.team_rows(history)

    assert {row["year"] for row in rows} == {2025}
    assert all_time.summarise(history, rows)["excluded"] == [2026]
    assert all_time.summarise(history, rows)["seasons"] == 1


def test_ranks_are_dense_and_the_order_is_total():
    history = {"seasons": [season(year=2024), season(year=2025)], "skipped": []}
    rows = all_time.team_rows(history)

    assert [row["rank"] for row in rows] == list(range(1, 9))
    # Two identical seasons: the same four ratings twice, so only the year can
    # separate the pairs -- and it must do so the same way every run.
    assert rows == all_time.team_rows(history)
    assert [(r["name"], r["year"]) for r in rows[:2]] == [("Alpha", 2025), ("Alpha", 2024)]


def test_the_best_team_outranks_the_luckiest_one():
    """Charlie went 3-1 and Bravo 1-3, but Bravo out-scored Charlie on the season.

    Strength carries more weight than firepower, so the team that actually beat
    people has to come out ahead -- otherwise the list is a scoring leaderboard
    with extra steps.
    """
    rows = by_name(all_time.season_rows(season()))
    assert rows["Bravo"]["ppg"] > rows["Charlie"]["ppg"]
    assert rows["Charlie"]["rating"] > rows["Bravo"]["rating"]


def test_managers_are_grouped_across_renamed_teams():
    """Team names do not survive a season; owner ids do. One manager who renamed
    their team must be one career, not two."""
    first = season(year=2024, owners={n: f"own-{n}" for n in SCORES})
    second = season(year=2025, owners={n: f"own-{n}" for n in SCORES})
    # Alpha's manager renamed the team to "Omega" for the second season.
    for team in second["teams"]:
        if team["name"] == "Alpha":
            team["name"] = "Omega"
    for entry in second["weekly_scores"]:
        if entry["name"] == "Alpha":
            entry["name"] = "Omega"
    for entry in second["weekly_scores"]:
        entry["weeks"] = [
            {**week, "opponent": "Omega" if week["opponent"] == "Alpha" else week["opponent"]}
            for week in entry["weeks"]
        ]

    owners = all_time.owner_rows(all_time.team_rows({"seasons": [first, second]}))
    alpha = [o for o in owners if o["owner"] == "own-Alpha"]
    assert len(alpha) == 1
    assert alpha[0]["seasons"] == 2
    assert alpha[0]["titles"] == 2
    assert alpha[0]["years"] == [2024, 2025]


def test_a_career_is_averaged_so_longevity_alone_does_not_win():
    """A manager with one great season should outrank one with three mediocre
    ones, which summing the ratings would get backwards."""
    good = season(year=2025, owners={n: f"own-{n}" for n in SCORES})
    weak = [
        season(year=y, owners={n: "own-Delta" for n in SCORES}) for y in (2022, 2023)
    ]
    owners = all_time.owner_rows(all_time.team_rows({"seasons": [good, *weak]}))
    ranked = {o["owner"]: o for o in owners}

    assert ranked["own-Alpha"]["seasons"] == 1
    assert ranked["own-Alpha"]["avg_rating"] > ranked["own-Delta"]["avg_rating"]


def test_an_empty_history_reports_nothing_rather_than_failing():
    for history in ({}, {"seasons": []}, {"seasons": [season(complete=False)]}):
        rows = all_time.team_rows(history)
        assert rows == []
        assert all_time.summarise(history, rows)["team_seasons"] == 0
        assert all_time.owner_rows(rows) == []


def test_the_weights_are_a_blend_and_the_rating_is_auditable():
    """Every component that moves the rating is reported beside it, and the base
    is exactly the documented weighted sum -- so a reader can check the number."""
    assert sum(all_time.WEIGHTS.values()) == 1.0

    row = by_name(all_time.season_rows(season()))["Alpha"]
    expected = 100.0 * (
        all_time.WEIGHTS["strength"] * row["strength"]
        + all_time.WEIGHTS["record"] * row["record"]
        + all_time.WEIGHTS["scoring"] * row["scoring"]
    )
    assert row["base"] == round(expected, 2)
    assert row["rating"] == round(row["base"] + row["hardware"], 2)


# --- the three scopes ---------------------------------------------------------


def with_playoffs(payload, qualifiers=("Alpha", "Charlie"), scores=(140.0, 120.0)):
    """Add a one-game bracket between two of the four teams.

    Alpha and Charlie qualified and met; Alpha won. Bravo and Delta did not
    qualify, so they have no playoff season at all.
    """
    points = dict(zip(qualifiers, scores))
    for team in payload["teams"]:
        name = team["name"]
        qualified = name in points
        team["made_playoffs"] = qualified
        team["playoff_points_for"] = points.get(name, 0.0)
        team["playoff_games"] = 1 if qualified else 0
        won = qualified and points[name] == max(points.values())
        team["playoff_wins"] = 1 if won else 0
        team["playoff_losses"] = 1 if qualified and not won else 0
        team["playoff_ties"] = 0
    payload["playoff_weeks"] = [
        {
            "name": name,
            "weeks": [
                {
                    "week": len(SCHEDULE) + 1,
                    "points": points[name],
                    "opponent": [q for q in qualifiers if q != name][0],
                }
            ],
        }
        for name in qualifiers
    ]
    return payload


def test_the_playoff_scope_holds_only_the_teams_that_qualified():
    rows = all_time.season_rows(with_playoffs(season()), "playoffs")
    assert sorted(r["name"] for r in rows) == ["Alpha", "Charlie"]
    assert all(row["made_playoffs"] for row in rows)


def test_the_playoff_scope_rates_the_bracket_not_the_season():
    """A team's playoff row must describe its playoff games. Reusing the regular
    season record here would rank the bracket by the thing it is not about."""
    rows = by_name(all_time.season_rows(with_playoffs(season()), "playoffs"))

    # Alpha won its one bracket game; Charlie lost its one.
    assert (rows["Alpha"]["wins"], rows["Alpha"]["losses"]) == (1, 0)
    assert rows["Alpha"]["record"] == 1.0
    assert (rows["Charlie"]["wins"], rows["Charlie"]["losses"]) == (0, 1)
    assert rows["Charlie"]["record"] == 0.0
    # PPG is the bracket's scoring, not the season's.
    assert rows["Alpha"]["ppg"] == 140.0


def test_the_regular_scope_shows_no_bracket_accolade_at_all():
    """"Regular season only" means the bracket did not happen: it scores nothing,
    and it is not listed either. A CHAMP badge beside a rating that deliberately
    ignores the championship invites the reader to assume it counted.

    Qualifying and the top seed stay, because the record earned both.
    """
    payload = with_playoffs(season(), qualifiers=("Alpha", "Charlie"), scores=(150.0, 100.0))
    champion = by_name(all_time.season_rows(payload, "regular"))["Alpha"]

    assert champion["hardware"] == 0.0
    assert champion["rating"] == champion["base"]
    assert "Champion" not in champion["accolades"]
    assert not any("playoff win" in label for label in champion["accolades"])
    assert set(champion["accolades"]) <= set(all_time.REGULAR_ACCOLADES)
    assert "#1 overall seed" in champion["accolades"], "earned over the fourteen weeks"


def test_the_bracket_accolades_come_back_under_both():
    payload = with_playoffs(season(), qualifiers=("Alpha", "Charlie"), scores=(150.0, 100.0))
    champion = by_name(all_time.season_rows(payload, "both"))["Alpha"]

    assert "Champion" in champion["accolades"]
    assert champion["hardware"] > 0


def test_hardware_scoping_is_decided_in_one_place():
    """The filter lives in `hardware`, so no caller can show a badge the scope
    excludes while another hides it."""
    team = {"final_standing": 1, "seed": 1, "playoff_wins": 3}
    regular_points, regular_labels = all_time.hardware(team, 6, "regular")
    both_points, both_labels = all_time.hardware(team, 6, "both")

    assert regular_points == 0.0
    assert set(regular_labels) == {"Playoffs", "#1 overall seed"}
    assert both_points > 0
    assert "Champion" in both_labels and "3 playoff wins" in both_labels


def test_both_is_the_regular_season_plus_the_accolades():
    regular = by_name(all_time.season_rows(season(), "regular"))
    both = by_name(all_time.season_rows(season(), "both"))

    for name in regular:
        # Identical rates -- the scope changes what is added, not what is measured.
        assert regular[name]["base"] == both[name]["base"]
        assert both[name]["rating"] == pytest.approx(
            regular[name]["rating"] + both[name]["hardware"]
        )
    assert both["Alpha"]["hardware"] > 0


def test_the_scopes_can_disagree_about_who_was_best():
    """The point of having three views. Delta went 0-4 and is last on the season;
    give it a bracket run and the playoff view has to say something different."""
    payload = with_playoffs(season(), qualifiers=("Delta", "Alpha"), scores=(200.0, 100.0))

    regular = all_time.season_rows(payload, "regular")
    playoffs = all_time.season_rows(payload, "playoffs")

    assert regular[-1]["name"] == "Delta" or min(
        regular, key=lambda r: r["rating"]
    )["name"] == "Delta"
    assert max(playoffs, key=lambda r: r["rating"])["name"] == "Delta"


def test_a_season_with_no_bracket_data_yields_no_playoff_rows():
    """An in-progress season has no playoffs, and neither does a payload written
    before this existed. Neither may invent a zero-scored bracket."""
    assert all_time.season_rows(season(), "playoffs") == []

    payload = season()
    payload["playoff_weeks"] = []
    assert all_time.team_rows({"seasons": [payload]}, "playoffs") == []


def test_an_unknown_scope_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match="unknown scope"):
        all_time.season_rows(season(), "postseason")


def test_every_scope_ranks_and_the_default_is_both():
    history = {"seasons": [with_playoffs(season())]}
    assert all_time.DEFAULT_SCOPE == "both"
    assert all_time.team_rows(history) == all_time.team_rows(history, "both")

    for scope in all_time.SCOPES:
        rows = all_time.team_rows(history, scope)
        assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


def test_the_career_keys_are_one_definition():
    """The renderer joins manager rows to team rows with this, so a second
    spelling of it would split a career in the live table only."""
    assert all_time.career_keys({"managers": ["Ann Lee"], "name": "Alpha"}) == ["Ann Lee"]
    # An abandoned team has no manager and must not merge with every other one.
    assert all_time.career_keys({"managers": [], "name": "Alpha"}) != (
        all_time.career_keys({"managers": [], "name": "Bravo"})
    )

    rows = all_time.team_rows({"seasons": [season()]})
    keys = {k for r in rows for k in all_time.career_keys(r)}
    assert keys == {o["owner_id"] for o in all_time.owner_rows(rows)}


def test_a_co_managed_season_counts_for_both_managers():
    """Measured on a real league: ESPN flipped the order of a co-managed pair
    between 2023 and 2024, so crediting one of them split a single continuous
    franchise in half and neither career was real. Both get the credit, which
    double-counts a shared title on purpose -- both of them won it."""
    pair = season()
    pair["teams"][0]["managers"] = ["Ann Lee", "Bo Roy"]
    pair["teams"][0]["final_standing"] = 1

    rows = all_time.team_rows({"seasons": [pair]})
    careers = {o["owner"]: o for o in all_time.owner_rows(rows)}

    assert careers["Ann Lee"]["seasons"] == 1
    assert careers["Bo Roy"]["seasons"] == 1
    assert careers["Ann Lee"]["titles"] == careers["Bo Roy"]["titles"] == 1
    assert careers["Ann Lee"]["avg_rating"] == careers["Bo Roy"]["avg_rating"]


def test_a_deep_run_beats_a_first_round_exit():
    """The hole that per-placement scoring left. Measured across eight completed
    seasons of two real leagues, the runner-up went 2-1 or 1-1 *every time* -- so
    paying by placement scored two playoff wins and a lost final the same as
    losing in round one, while a mere berth still scored. Bill James's Hall of
    Fame Monitor credits a pennant winner who loses the World Series 5 against 6
    for winning it, not 0; paying per win gets that ordering with no rule per
    round, and scales to a bracket of any size.
    """
    runner_up, labels = all_time.hardware(
        {"final_standing": 2, "seed": 4, "playoff_wins": 2}, 6
    )
    first_round_exit, _ = all_time.hardware(
        {"final_standing": 5, "seed": 5, "playoff_wins": 0}, 6
    )
    assert runner_up > first_round_exit
    assert runner_up - first_round_exit == 2 * all_time.PLAYOFF_WIN
    # The run is visible, not just priced in.
    assert "Runner-up" in labels and "2 playoff wins" in labels


def test_the_accolade_order_is_champion_then_top_seed_then_a_berth():
    """The ordering asked for, pinned so a later tweak to one constant cannot
    quietly invert it."""
    assert all_time.CHAMPION > all_time.TOP_SEED > all_time.PLAYOFF_BERTH > 0
    # And a title outweighs the whole regular-season resume a top seed can show.
    assert all_time.CHAMPION > all_time.TOP_SEED + all_time.PLAYOFF_BERTH


def test_bracket_wins_scale_to_the_size_of_the_bracket():
    """This league has run both five and six playoff spots, so a bigger bracket
    means one more round -- which per-win credit handles without a new rule."""
    five_team_champ, _ = all_time.hardware(
        {"final_standing": 1, "seed": 1, "playoff_wins": 2}, 5
    )
    six_team_champ, _ = all_time.hardware(
        {"final_standing": 1, "seed": 1, "playoff_wins": 3}, 6
    )
    assert six_team_champ - five_team_champ == all_time.PLAYOFF_WIN


def test_one_bracket_win_reads_as_singular():
    _, labels = all_time.hardware(
        {"final_standing": 4, "seed": 3, "playoff_wins": 1}, 6
    )
    assert "1 playoff win" in labels


# --- record follows the scope -------------------------------------------------


def test_the_record_shown_is_the_record_for_what_is_being_ranked():
    """A real case named the rule: one team went 12-1 and lost its first playoff
    game, which is 12-1 on the regular season and 12-2 once the bracket counts."""
    payload = with_playoffs(season(), qualifiers=("Alpha", "Charlie"), scores=(100.0, 150.0))
    # Alpha was 4-0 and lost its only bracket game.
    regular = by_name(all_time.season_rows(payload, "regular"))["Alpha"]
    both = by_name(all_time.season_rows(payload, "both"))["Alpha"]
    playoffs = by_name(all_time.season_rows(payload, "playoffs"))["Alpha"]

    assert (regular["wins"], regular["losses"]) == (4, 0)
    assert (both["wins"], both["losses"]) == (4, 1)
    assert (playoffs["wins"], playoffs["losses"]) == (0, 1)


def test_the_record_rate_and_the_displayed_record_are_the_same_numbers():
    """The table cannot show 12-2 while rating a 12-1, so both come from one call."""
    payload = with_playoffs(season(), qualifiers=("Alpha", "Charlie"), scores=(100.0, 150.0))
    for scope in all_time.SCOPES:
        for row in all_time.season_rows(payload, scope):
            played = row["wins"] + row["losses"] + row["ties"]
            expected = (row["wins"] + 0.5 * row["ties"]) / played if played else 0.0
            assert row["record"] == pytest.approx(expected, abs=5e-5), (scope, row["name"])


def test_scoped_record_adds_the_bracket_only_for_both():
    team = {
        "wins": 12, "losses": 1, "ties": 0,
        "playoff_wins": 0, "playoff_losses": 1, "playoff_ties": 0,
    }
    assert all_time.scoped_record(team, "regular") == (12, 1, 0)
    assert all_time.scoped_record(team, "both") == (12, 2, 0)
    assert all_time.scoped_record(team, "playoffs") == (0, 1, 0)


def test_a_team_that_missed_the_bracket_has_the_same_record_either_way():
    """Nothing to add, so "both" must not invent a playoff loss for it."""
    team = {
        "wins": 5, "losses": 9, "ties": 0,
        "playoff_wins": 0, "playoff_losses": 0, "playoff_ties": 0,
    }
    assert all_time.scoped_record(team, "regular") == all_time.scoped_record(team, "both")


def test_the_weight_keys_are_the_names_the_report_shows():
    """Renamed from results/firepower. Pinned because the slider ids, the row data
    attributes and the JS key list all have to spell them the same way."""
    assert set(all_time.WEIGHTS) == {"strength", "record", "scoring"}


# --- divisions ----------------------------------------------------------------


def test_the_top_seed_supersedes_a_division_title():
    """The #1 overall seed always won its division too, so showing both says the
    same thing twice and pays for it twice."""
    top = {"final_standing": 3, "seed": 1, "division_winner": True, "playoff_wins": 0}
    points, labels = all_time.hardware(top, 6)

    assert "#1 overall seed" in labels
    assert "Division winner" not in labels
    assert points == all_time.PLAYOFF_BERTH + all_time.TOP_SEED


def test_the_other_division_winner_gets_the_badge():
    other = {"final_standing": 3, "seed": 2, "division_winner": True, "playoff_wins": 0}
    points, labels = all_time.hardware(other, 6)

    assert "Division winner" in labels
    assert "#1 overall seed" not in labels
    assert points == all_time.PLAYOFF_BERTH + all_time.DIVISION_WINNER


def test_a_division_title_is_worth_less_than_the_top_seed_and_more_than_a_berth():
    assert all_time.TOP_SEED > all_time.DIVISION_WINNER > all_time.PLAYOFF_BERTH


def test_a_division_title_is_a_regular_season_accolade():
    """It is won over the fourteen weeks, so it survives into the regular-season
    view where the bracket badges do not."""
    assert "Division winner" in all_time.REGULAR_ACCOLADES

    champ_who_won_a_division = {
        "final_standing": 1, "seed": 2, "division_winner": True, "playoff_wins": 3,
    }
    _, labels = all_time.hardware(champ_who_won_a_division, 6, "regular")
    assert set(labels) == {"Playoffs", "Division winner"}


def test_a_single_division_season_hands_out_no_division_titles():
    """Most seasons ran one division, and one of them named it "League Standings" --
    which must not make every team a division winner."""
    team = {"final_standing": 3, "seed": 4, "division_winner": False, "playoff_wins": 0}
    _, labels = all_time.hardware(team, 6)
    assert "Division winner" not in labels


def test_there_is_no_final_four_badge():
    """A placement badge below the final said the same thing the per-win credit
    already says, so it went."""
    for standing in (3, 4):
        _, labels = all_time.hardware(
            {"final_standing": standing, "seed": 3, "playoff_wins": 1}, 6
        )
        assert not any("Final four" in label for label in labels)
        assert "1 playoff win" in labels, "the run is still visible, per win"


def test_a_berth_is_not_an_accolade_in_the_playoff_scope():
    """Every team in that table qualified, so the badge would be on every row and
    the points a constant that moves no ranking."""
    team = {"final_standing": 3, "seed": 3, "playoff_wins": 1}
    both_points, both_labels = all_time.hardware(team, 6, "both")
    po_points, po_labels = all_time.hardware(team, 6, "playoffs")

    assert "Playoffs" in both_labels
    assert "Playoffs" not in po_labels
    assert both_points - po_points == all_time.PLAYOFF_BERTH


def test_the_playoff_scope_still_shows_what_was_won_there():
    team = {"final_standing": 1, "seed": 2, "playoff_wins": 3}
    _, labels = all_time.hardware(team, 6, "playoffs")

    assert "Champion" in labels and "3 playoff wins" in labels


def test_the_legend_and_the_table_agree_about_which_badges_exist():
    """One definition of what a scope can produce, because the playoff view once
    dropped `Playoffs` from its rows and went on explaining it underneath."""
    assert "Playoffs" in all_time.accolades_for("both")
    assert "Playoffs" not in all_time.accolades_for("playoffs")
    assert "Champion" not in all_time.accolades_for("regular")
    assert set(all_time.accolades_for("regular")) == set(all_time.REGULAR_ACCOLADES)
    assert not any("Final four" in l for l in all_time.ALL_ACCOLADES)

    # Nothing a scope emits may be missing from its own list.
    payload = with_playoffs(season(), qualifiers=("Alpha", "Charlie"), scores=(150.0, 100.0))
    for scope in all_time.SCOPES:
        allowed = set(all_time.accolades_for(scope))
        for row in all_time.season_rows(payload, scope):
            for label in row["accolades"]:
                key = "1 playoff win" if "playoff win" in label else label
                assert key in allowed, (scope, label)
