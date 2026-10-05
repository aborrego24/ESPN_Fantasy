"""Stage 0: shaping many ESPN seasons into one history payload.

Exercised against a fake league, with no network access. Everything here was
found by running the real thing against a real league, so each test names the
season that broke it.

The fake carries only what this module reads: per-week scores, a schedule, a
final standing, a seed and owners. It deliberately does **not** fill
wins/losses/points_for with the right values -- espn_api reports current totals
there, and a test should fail if those are trusted instead of recomputed.
"""

import pytest

import history_data


class FakeSettings:
    def __init__(self, weeks, playoff_spots, name="Test League"):
        self.reg_season_count = weeks
        self.playoff_team_count = playoff_spots
        self.name = name
        self.division_map = {}


class FakeTeam:
    _next_id = 1

    def __init__(self, name, scores, final_standing=0, seed=0, owners=None):
        self.team_name = name
        self.scores = list(scores)
        self.schedule = []
        self.final_standing = final_standing
        self.standing = seed
        self.owners = owners if owners is not None else [
            {"id": f"swid-{name}", "firstName": name, "lastName": "Manager"}
        ]
        # Wrong on purpose: current totals, not as-of-week values.
        self.wins = self.losses = self.ties = 99
        self.points_for = 99999.0
        self.team_abbrev = name[:4].upper()
        self.team_id = FakeTeam._next_id
        FakeTeam._next_id += 1


class FakeLeague:
    def __init__(self, teams, weeks, year=2025, playoff_spots=2, schedule=None):
        self.teams = teams
        self.year = year
        self.settings = FakeSettings(weeks, playoff_spots)
        self.previousSeasons = []
        for team in teams:
            for week in range(1, weeks + 1):
                for home, away in (schedule or {}).get(week, []):
                    if home is team:
                        team.schedule.append(away)
                    elif away is team:
                        team.schedule.append(home)
            # A week with no pairing is a bye, which espn_api reports as the team
            # facing itself.
            while len(team.schedule) < weeks:
                team.schedule.append(team)


def four_team_league(year=2025, weeks=4, finals=(1, 3, 2, 4), seeds=(1, 3, 2, 4)):
    a = FakeTeam("Alpha", [120.0, 110.0, 100.0, 130.0], finals[0], seeds[0])
    b = FakeTeam("Bravo", [100.0, 105.0, 115.0, 90.0], finals[1], seeds[1])
    c = FakeTeam("Charlie", [90.0, 100.0, 118.0, 95.0], finals[2], seeds[2])
    d = FakeTeam("Delta", [80.0, 95.0, 90.0, 85.0], finals[3], seeds[3])
    schedule = {
        1: [(a, b), (c, d)],
        2: [(a, c), (b, d)],
        3: [(a, d), (b, c)],
        4: [(a, b), (c, d)],
    }
    return FakeLeague([a, b, c, d], weeks, year, 2, schedule)


def test_a_season_in_progress_stops_at_the_weeks_played():
    """Found on a real 2026 season three weeks in.

    ESPN pre-creates every remaining matchup with both sides on 0.0, and equal
    scores read as a tie -- so asking for all 14 weeks returned 3-0-11 and put a
    3-0 team at a .607 win percentage.
    """
    a = FakeTeam("Alpha", [120.0, 110.0, 100.0, 0.0, 0.0])
    b = FakeTeam("Bravo", [100.0, 105.0, 115.0, 0.0, 0.0])
    league = FakeLeague([a, b], weeks=5, schedule={w: [(a, b)] for w in range(1, 6)})

    payload = history_data.season_payload(league)
    assert payload["weeks_played"] == 3
    assert payload["complete"] is False

    alpha = [t for t in payload["teams"] if t["name"] == "Alpha"][0]
    assert (alpha["wins"], alpha["losses"], alpha["ties"]) == (2, 1, 0)
    assert alpha["points_for"] == 330.0


def test_a_bye_does_not_make_a_finished_season_look_unfinished():
    """Found on a real finished 9-team / 15-week season, which was being dropped.

    A bye scores 0, so the count of weeks *every* team scored in can never reach
    the season length in an odd-sized league -- two teams byed and the whole year
    was excluded from the rankings. The frontier of the season is how far anyone
    got, not how far everyone got.
    """
    a = FakeTeam("Alpha", [120.0, 110.0, 0.0], final_standing=1, seed=1)
    b = FakeTeam("Bravo", [100.0, 0.0, 115.0], final_standing=2, seed=2)
    c = FakeTeam("Charlie", [0.0, 105.0, 90.0], final_standing=3, seed=3)
    league = FakeLeague(
        [a, b, c],
        weeks=3,
        schedule={1: [(a, b)], 2: [(a, c)], 3: [(b, c)]},
    )

    assert history_data.weeks_with_play(league, 3) == 3
    payload = history_data.season_payload(league)
    assert payload["weeks_played"] == 3
    assert payload["complete"] is True


def test_completeness_turns_on_the_final_standing():
    """rankCalculatedFinal is 0 until the bracket settles, and is the only signal
    that says so -- the regular season can be over while the playoffs are not."""
    finished = history_data.season_payload(four_team_league())
    assert finished["complete"] is True

    unsettled = history_data.season_payload(
        four_team_league(finals=(0, 0, 0, 0))
    )
    assert unsettled["weeks_played"] == 4  # the regular season did finish
    assert unsettled["complete"] is False


def test_records_are_recomputed_and_sliced_to_the_regular_season():
    """team.scores runs on into the playoffs, where qualifiers play extra games
    and everyone else plays consolation ones. Only the regular season is read."""
    league = four_team_league(weeks=4)
    for team in league.teams:
        team.scores.extend([200.0, 200.0])  # playoff weeks, must be ignored

    payload = history_data.season_payload(league)
    assert payload["weeks_in_season"] == 4
    records = {t["name"]: (t["wins"], t["losses"]) for t in payload["teams"]}
    assert records == {
        "Alpha": (4, 0),
        "Bravo": (1, 3),
        "Charlie": (3, 1),
        "Delta": (0, 4),
    }
    assert all(len(e["weeks"]) == 4 for e in payload["weekly_scores"])


def test_the_payload_carries_what_the_ranking_needs():
    payload = history_data.season_payload(four_team_league())
    assert set(payload) == {
        "year",
        "name",
        "num_teams",
        "weeks_in_season",
        "weeks_played",
        "complete",
        "playoff_spots",
        "division_names",
        "teams",
        "weekly_scores",
        "playoff_weeks",
    }
    team = payload["teams"][0]
    assert set(team) == {
        "name",
        "managers",
        "wins",
        "losses",
        "ties",
        "points_for",
        "final_standing",
        "seed",
        "division",
        "division_winner",
        "made_playoffs",
        "playoff_wins",
        "playoff_losses",
        "playoff_ties",
        "playoff_points_for",
        "playoff_games",
    }


def test_every_manager_of_a_team_is_recorded():
    """Not just ESPN's first owner. Measured on a real 12-team league, the order
    of a co-managed pair flipped between 2023 and 2024, so crediting owners[0]
    split one continuous franchise across two managers mid-history."""
    pair = FakeTeam(
        "Duo",
        [100.0],
        owners=[
            {"id": "swid-first", "firstName": "First", "lastName": "Owner"},
            {"id": "swid-second", "firstName": "Second", "lastName": "Owner"},
        ],
    )
    assert history_data.owner_names(pair) == ["First Owner", "Second Owner"]

    orphan = FakeTeam("Abandoned", [100.0], owners=[])
    assert history_data.owner_names(orphan) == []


def test_a_nameless_owner_is_dropped_rather_than_keyed_as_blank():
    """An empty name would group every such team under one phantom manager."""
    team = FakeTeam("Ghost", [100.0], owners=[{"id": "swid-x"}])

    assert history_data.owner_names(team) == []


def test_candidate_years_includes_the_season_being_read():
    """espn_api filters previousSeasons to years before the one fetched, so the
    fetched year has to be added back or the newest season is never ranked."""
    league = four_team_league(year=2025)
    league.previousSeasons = [2023, 2024]
    assert history_data.candidate_years(league) == [2025, 2024, 2023]

    # Already present, and still not duplicated.
    league.previousSeasons = [2023, 2024, 2025]
    assert history_data.candidate_years(league) == [2025, 2024, 2023]


def test_weeks_with_play_is_capped_and_handles_a_league_yet_to_start():
    league = four_team_league(weeks=4)
    assert history_data.weeks_with_play(league, 2) == 2  # capped at the limit

    unplayed = FakeLeague([FakeTeam("Alpha", [0.0, 0.0])], weeks=2)
    assert history_data.weeks_with_play(unplayed, 2) == 0
    assert history_data.season_payload(unplayed)["complete"] is False


# --- the bracket --------------------------------------------------------------


def playoff_league(year=2025, spots=2):
    """A four-team season with a two-team bracket and a consolation game.

    Seeds 1 and 2 qualify and meet in week 5; seeds 3 and 4 play the consolation
    ladder, which must not count as playoff football for anyone.
    """
    a = FakeTeam("Alpha", [120.0, 110.0, 100.0, 130.0, 150.0], 1, 1)
    b = FakeTeam("Bravo", [100.0, 105.0, 115.0, 90.0, 140.0], 2, 2)
    c = FakeTeam("Charlie", [90.0, 100.0, 118.0, 95.0, 160.0], 3, 3)
    d = FakeTeam("Delta", [80.0, 95.0, 90.0, 85.0, 170.0], 4, 4)
    schedule = {
        1: [(a, b), (c, d)],
        2: [(a, c), (b, d)],
        3: [(a, d), (b, c)],
        4: [(a, b), (c, d)],
        5: [(a, b), (c, d)],  # week 5 is post-season: a-b bracket, c-d consolation
    }
    league = FakeLeague([a, b, c, d], 4, year, spots, schedule)
    # FakeLeague only wires the regular season; extend the schedule into week 5.
    for home, away in schedule[5]:
        home.schedule.append(away)
        away.schedule.append(home)
    return league


def test_only_qualifying_teams_get_a_bracket():
    payload = history_data.season_payload(playoff_league())
    assert [e["name"] for e in payload["playoff_weeks"]] == ["Alpha", "Bravo"]

    qualified = {t["name"]: t["made_playoffs"] for t in payload["teams"]}
    assert qualified == {
        "Alpha": True,
        "Bravo": True,
        "Charlie": False,
        "Delta": False,
    }


def test_the_consolation_ladder_is_not_playoff_football():
    """Charlie and Delta played in week 5 and scored well. Neither qualified, so
    neither has a playoff record -- otherwise a 4th-place team gets credit for a
    bracket it never entered."""
    payload = history_data.season_payload(playoff_league())
    rows = {t["name"]: t for t in payload["teams"]}

    for name in ("Charlie", "Delta"):
        assert rows[name]["playoff_games"] == 0
        assert rows[name]["playoff_points_for"] == 0.0
        assert rows[name]["playoff_wins"] == rows[name]["playoff_losses"] == 0


def test_the_bracket_record_is_scored_from_both_sides():
    payload = history_data.season_payload(playoff_league())
    rows = {t["name"]: t for t in payload["teams"]}

    # Week 5: Alpha 150, Bravo 140.
    assert (rows["Alpha"]["playoff_wins"], rows["Alpha"]["playoff_losses"]) == (1, 0)
    assert (rows["Bravo"]["playoff_wins"], rows["Bravo"]["playoff_losses"]) == (0, 1)
    assert rows["Alpha"]["playoff_points_for"] == 150.0
    assert rows["Alpha"]["playoff_games"] == 1


def test_a_bye_in_the_bracket_is_not_a_contest():
    """Top seeds skip round one and knocked-out teams stop playing; both come back
    as a team facing itself. ESPN is not even consistent about the score -- a real
    league has a bye week carrying 165 points and another carrying 0 -- so neither
    the points nor a result may be counted."""
    a = FakeTeam("Alpha", [120.0, 110.0, 165.0, 150.0], 1, 1)
    b = FakeTeam("Bravo", [100.0, 105.0, 130.0, 140.0], 2, 2)
    league = FakeLeague(
        [a, b], 2, 2025, 2, {1: [(a, b)], 2: [(a, b)]}
    )
    # Week 3: Alpha byes (faces itself) while Bravo plays nobody either.
    a.schedule.extend([a, b])
    b.schedule.extend([b, a])

    payload = history_data.season_payload(league)
    alpha = [e for e in payload["playoff_weeks"] if e["name"] == "Alpha"][0]
    assert alpha["weeks"][0]["points"] == 0.0, "the bye's 165 is dropped"
    assert alpha["weeks"][0]["opponent"] is None

    rows = {t["name"]: t for t in payload["teams"]}
    # Only week 4 was contested.
    assert rows["Alpha"]["playoff_games"] == 1
    assert rows["Alpha"]["playoff_points_for"] == 150.0


def test_a_season_with_no_post_season_yet_has_an_empty_bracket():
    league = four_team_league(weeks=4)  # scores stop at the regular season
    payload = history_data.season_payload(league)

    assert all(entry["weeks"] == [] for entry in payload["playoff_weeks"])
    assert all(t["playoff_games"] == 0 for t in payload["teams"])


def eliminated_then_winning_league():
    """Four qualifiers, a fifth-place ladder, and the Klorgon case.

    Week 5 (round one):   Alpha 150 beat Bravo 140   |  Charlie 160 beat Delta 120
    Week 6 (final / 5th): Alpha 155 beat Charlie 145 |  Bravo  130 beat Delta 110

    Bravo lost round one and then won on the ladder. That win must not count: it
    came after elimination, even though both sides had qualified.
    """
    a = FakeTeam("Alpha", [120.0, 110.0, 150.0, 155.0], 1, 1)
    b = FakeTeam("Bravo", [100.0, 105.0, 140.0, 130.0], 3, 2)
    c = FakeTeam("Charlie", [90.0, 100.0, 160.0, 145.0], 2, 3)
    d = FakeTeam("Delta", [80.0, 95.0, 120.0, 110.0], 4, 4)
    league = FakeLeague([a, b, c, d], 2, 2025, 4, {1: [(a, b)], 2: [(c, d)]})
    for team in (a, b, c, d):
        del team.schedule[:]
    # Weeks 1-2 regular season, weeks 3-4 post-season.
    for home, away in [(a, b), (c, d)]:
        home.schedule.extend([away, away])
        away.schedule.extend([home, home])
    a.schedule.append(c); c.schedule.append(a)   # week 4: the final
    b.schedule.append(d); d.schedule.append(b)   # week 4: the fifth-place game
    a.schedule.insert(2, b); b.schedule.insert(2, a)
    return league


def test_a_win_after_elimination_is_not_a_playoff_win():
    """Measured on a real season: 2025 Klorgon lost in round one, then won twice
    on the fifth-place ladder, and read as 1-2 with credit for a playoff win it
    never had. The championship path is single elimination, so a team's playoff
    season ends at its first defeat."""
    payload = history_data.season_payload(eliminated_then_winning_league())
    rows = {t["name"]: t for t in payload["teams"]}

    assert (rows["Bravo"]["playoff_wins"], rows["Bravo"]["playoff_losses"]) == (0, 1)
    assert rows["Bravo"]["playoff_games"] == 1
    # Only the round-one loss counted, so only its points did.
    assert rows["Bravo"]["playoff_points_for"] == 140.0


def test_the_losing_game_itself_is_kept():
    """A team was alive when it played the game that knocked it out, so that game
    is championship football -- it is everything *after* it that is not."""
    payload = history_data.season_payload(eliminated_then_winning_league())
    bravo = [e for e in payload["playoff_weeks"] if e["name"] == "Bravo"][0]

    contested = [w for w in bravo["weeks"] if w["opponent"] is not None]
    assert len(contested) == 1
    assert contested[0]["points"] == 140.0
    assert contested[0]["opponent"] == "Alpha"


def test_an_unbeaten_champion_keeps_every_game():
    payload = history_data.season_payload(eliminated_then_winning_league())
    rows = {t["name"]: t for t in payload["teams"]}

    assert (rows["Alpha"]["playoff_wins"], rows["Alpha"]["playoff_losses"]) == (2, 0)
    assert rows["Alpha"]["playoff_points_for"] == 150.0 + 155.0


def test_every_playoff_team_ends_unbeaten_or_with_exactly_one_loss():
    """The shape the championship path guarantees: you keep playing until you
    lose once. More than one loss would mean consolation games leaked in."""
    payload = history_data.season_payload(eliminated_then_winning_league())

    for team in payload["teams"]:
        if not team["made_playoffs"]:
            continue
        assert team["playoff_losses"] <= 1, team["name"]


# --- divisions ----------------------------------------------------------------


def divisional_league(divisions=2):
    """Four teams in two divisions, seeded 1-4.

    ESPN seeds division winners ahead of every non-winner, so the winner of each
    division is its lowest-seeded team -- seeds 1 and 2 here.
    """
    a = FakeTeam("Alpha", [120.0, 110.0], 1, 1)
    b = FakeTeam("Bravo", [100.0, 105.0], 2, 2)
    c = FakeTeam("Charlie", [90.0, 100.0], 3, 3)
    d = FakeTeam("Delta", [80.0, 95.0], 4, 4)
    for team, div in ((a, 0), (b, 1), (c, 0), (d, 1)):
        team.division_id = div
    league = FakeLeague([a, b, c, d], 2, 2024, 2, {1: [(a, c), (b, d)], 2: [(a, d), (b, c)]})
    league.settings.division_map = (
        {0: "Trump", 1: "Biden"} if divisions > 1 else {0: "League Standings"}
    )
    return league


def test_the_division_winner_is_the_lowest_seed_in_each_division():
    """Read off ESPN's own seeding rather than re-deriving its tiebreaker."""
    payload = history_data.season_payload(divisional_league())
    winners = {t["name"]: t["division_winner"] for t in payload["teams"]}

    assert winners == {"Alpha": True, "Bravo": True, "Charlie": False, "Delta": False}
    assert payload["division_names"] == {0: "Trump", 1: "Biden"}


def test_each_team_carries_the_name_of_its_division():
    payload = history_data.season_payload(divisional_league())
    divisions = {t["name"]: t["division"] for t in payload["teams"]}

    assert divisions == {
        "Alpha": "Trump", "Charlie": "Trump", "Bravo": "Biden", "Delta": "Biden",
    }


def test_one_division_means_nobody_won_a_division():
    """A real league called its single division "League Standings"; that must not
    hand a division title to its best team."""
    payload = history_data.season_payload(divisional_league(divisions=1))

    assert payload["division_names"] == {}
    assert not any(t["division_winner"] for t in payload["teams"])
    assert all(t["division"] == "" for t in payload["teams"])
