"""Check the engine's claims against what actually happened.

The tool makes falsifiable statements. This replays a completed season week by
week and holds every statement against the real result:

  1. SOUNDNESS   -- a team called "clinched" must actually have made the
                    playoffs, and one called "eliminated" must actually have
                    missed. This is the claim that matters; a single violation
                    means the engine is wrong.
  2. MONOTONICITY -- a verdict must never reverse. Clinched in week N means
                    clinched in every later week.
  3. COMPLETENESS -- once the season is over, every team must be decided, and
                    the clinched set must be exactly the real playoff field.
  4. BYES        -- a team told it has a first-round bye must actually have sat
                    out the first playoff week, and once the season is over the
                    bye set must be exactly the set that did.
  5. CONDITIONS  -- given what really happened the following week, the stated
                    conditions must predict the right status. Checked both ways:
                    conditions met => outcome happened, and outcome happened =>
                    some stated alternative was met.

Ground truth is ESPN's own `final_standing`. Note that is the *post-playoff*
finish, not regular-season seeding -- a consolation-bracket winner can rank
above a team with a better record -- so the playoff field is the set of teams
whose final_standing is within the playoff spot count.

    python3 tools/backtest.py 2024 2025
"""

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scenario_engine"),
)

import generate_perms
import league_data
import margins
import playoff_math
import refine_current_week
import refine_hypothetical
from espn_api.football import League

LEAGUE_ID = int(os.environ.get("ESPN_LEAGUE_ID", "123564885"))


def verdicts_at(league, week):
    """Run stages 1-2 as of `week` and return {team: verdict} plus the payload."""
    payload = league_data.build_payload(league, week)
    settings = payload["league_settings"]
    remaining = settings["weeks_in_season"] - week
    standings = refine_current_week.calculate_stats(
        payload, settings["playoff_spots"], settings["weeks_in_season"], remaining
    )
    remaining_matchups = refine_current_week.build_remaining_matchups(
        payload["teams"], remaining
    )
    envelope = margins.swing_envelope(remaining, margins.load_thresholds())
    standings = playoff_math.apply_verdicts(
        standings,
        remaining_matchups,
        settings["playoff_spots"],
        swing_envelope=envelope,
        bye_spots=settings.get("bye_spots", 0),
        divisions=refine_current_week.divisions_in_order(
            standings, payload.get("divisions")
        ),
    )
    base = {
        "league_data": {
            "playoff_spots": settings["playoff_spots"],
            "num_weeks": settings["weeks_in_season"],
            "remaining_weeks": remaining,
            "current_week": week,
        },
        "next_week_matchups": payload["next_week_matchups"],
        "remaining_matchups": remaining_matchups,
        "standings": standings,
    }
    byes = {t["team_name"] for t in standings if t.get("bye") == "clinched"}
    return {t["team_name"]: t["verdict"] for t in standings}, base, byes


def actual_winners(league, week):
    """Who really won each matchup in `week`, keyed by the matchup pairing."""
    results = {}
    for team in league.teams:
        opponent = team.schedule[week - 1]
        own = team.scores[week - 1]
        against = opponent.scores[week - 1]
        if own > against:
            results[frozenset((team.team_name, opponent.team_name))] = team.team_name
    return results


def really_had_a_bye(league, weeks, spots):
    """Playoff teams that played no game in the first playoff week."""
    played = set()
    for matchup in league.scoreboard(week=weeks + 1):
        home = getattr(matchup, "home_team", None)
        away = getattr(matchup, "away_team", None)
        scored = getattr(matchup, "home_score", 0) or getattr(matchup, "away_score", 0)
        if home is not None and away is not None and scored:
            played |= {home.team_name, away.team_name}
    field = {t.team_name for t in league.teams if t.final_standing <= spots}
    return field - played


def check_season(year):
    league = League(league_id=LEAGUE_ID, year=year)
    weeks = league.settings.reg_season_count
    spots = league.settings.playoff_team_count
    names = [t.team_name for t in league.teams]

    # Ground truth: ESPN's own post-playoff finish
    made_playoffs = {t.team_name for t in league.teams if t.final_standing <= spots}

    print(f"\n{'=' * 78}")
    print(f"{year}  --  {len(names)} teams, {weeks} weeks, {spots} playoff spots")
    print(f"{'=' * 78}")
    failures = []
    points_shifts = []

    # Does the seeding model match reality at all?
    final_payload = league_data.build_payload(league, weeks)
    final_standings = refine_current_week.calculate_stats(final_payload, spots, weeks, 0)
    final_divisions = refine_current_week.divisions_in_order(
        final_standings, final_payload.get("divisions")
    )
    order = playoff_math.seed_order(
        [t["wins"] for t in final_standings],
        [t["points_for"] for t in final_standings],
        final_divisions,
    )
    model_field = {final_standings[i]["team_name"] for i in order[:spots]}

    # Seeding going INTO the playoffs, which is the order the engine models.
    # final_standing is the post-playoff finish and is shown separately, because
    # numbering the field by it implies a seeding it is not: a consolation winner
    # can outrank a better regular-season team.
    divisional = len(getattr(league.settings, "division_map", None) or {1: None}) > 1
    print(
        f"ESPN's actual playoff field ({len(made_playoffs)}), by the engine's seeding"
        + (" (division winners first)" if divisional else "")
        + ":"
    )
    finish = {t.team_name: t.final_standing for t in league.teams}
    for seed, index in enumerate(order[:spots], 1):
        t = final_standings[index]
        print(
            f"   seed {seed}  {t['team_name']}  ({t['wins']}-{t['losses']}, "
            f"PF {t['points_for']:.1f})  -> finished #{finish[t['team_name']]}"
        )

    if model_field == made_playoffs:
        label = "division winners first" if divisional else "record, then points"
        print(f"\n[OK]   seeding model ({label}) reproduces the real field")
    else:
        print(f"\n[FAIL] seeding model disagrees with ESPN")
        print(f"       model says: {sorted(model_field)}")
        print(f"       ESPN says:  {sorted(made_playoffs)}")
        failures.append(f"{year}: seeding model does not reproduce the real playoff field")

    # Pass 1: every week's verdicts, before checking anything -- the condition
    # check for week N needs to know what really happened in week N+1.
    history = {}
    bases = {}
    byes = {}
    for week in range(0, weeks + 1):
        history[week], bases[week], byes[week] = verdicts_at(league, week)

    print(f"\n{'wk':>3}  {'clinched':>8} {'elim':>5} {'alive':>5}   soundness")
    for week in range(0, weeks + 1):
        verdicts, base = history[week], bases[week]

        clinched = {n for n, v in verdicts.items() if v == "clinched"}
        eliminated = {n for n, v in verdicts.items() if v == "eliminated"}
        alive = {n for n, v in verdicts.items() if v == "alive"}

        # 1. SOUNDNESS
        wrong_clinch = clinched - made_playoffs
        wrong_elim = eliminated & made_playoffs
        note = "ok"
        if wrong_clinch:
            note = f"WRONG: clinched but missed: {sorted(wrong_clinch)}"
            failures.append(f"{year} wk{week}: clinched but missed playoffs: {sorted(wrong_clinch)}")
        if wrong_elim:
            note = f"WRONG: eliminated but made it: {sorted(wrong_elim)}"
            failures.append(f"{year} wk{week}: eliminated but made playoffs: {sorted(wrong_elim)}")

        # never more decided than there are places
        if len(clinched) > spots:
            failures.append(f"{year} wk{week}: {len(clinched)} clinched for {spots} spots")
            note = f"WRONG: {len(clinched)} clinched for {spots} spots"
        if len(eliminated) > len(names) - spots:
            failures.append(f"{year} wk{week}: {len(eliminated)} eliminated, only {len(names)-spots} can miss")

        print(f"{week:>3}  {len(clinched):>8} {len(eliminated):>5} {len(alive):>5}   {note}")

        # 4. CONDITIONS -- compare against what really happened next week
        if week < weeks:
            problems, shifted = check_conditions(league, base, week, history)
            failures.extend(f"{year} {p}" for p in problems)
            points_shifts.extend(f"{year} {p}" for p in shifted)

    # 2. MONOTONICITY
    for week in range(0, weeks):
        for name in names:
            before, after = history[week][name], history[week + 1][name]
            if before == "clinched" and after != "clinched":
                failures.append(f"{year}: {name} clinched in wk{week} but {after} in wk{week+1}")
            if before == "eliminated" and after != "eliminated":
                failures.append(f"{year}: {name} eliminated in wk{week} but {after} in wk{week+1}")

    # 3. COMPLETENESS
    final = history[weeks]
    undecided = [n for n, v in final.items() if v == "alive"]
    if undecided:
        failures.append(f"{year}: still undecided after the final week: {undecided}")
    final_clinched = {n for n, v in final.items() if v == "clinched"}
    if final_clinched != made_playoffs:
        failures.append(
            f"{year}: final clinched set {sorted(final_clinched)} != real field {sorted(made_playoffs)}"
        )
    else:
        print(f"\n[OK]   after the final week, the clinched set is exactly the real playoff field")

    # 4. BYES
    bye_spots = league_data.bye_spots(league)
    if not bye_spots:
        print(f"[--]   no bye claims made for {year} (bye_spots=0)")
    else:
        actual = really_had_a_bye(league, weeks, spots)
        for week in range(0, weeks + 1):
            wrong = byes[week] - actual
            if wrong:
                failures.append(
                    f"{year} wk{week}: told {sorted(wrong)} they had a first-round "
                    f"bye; they played in week {weeks + 1}"
                )
        if byes[weeks] != actual:
            failures.append(
                f"{year}: final bye set {sorted(byes[weeks])} != really idle "
                f"{sorted(actual)}"
            )
        else:
            print(
                f"[OK]   the {bye_spots} teams told they had a bye are exactly the "
                f"{len(actual)} who sat out week {weeks + 1}"
            )

    return failures


def satisfied_by(permutation, alternatives, team, own):
    """Does what really happened match any stated alternative?

    Each alternative is {"own": "win"|"loss"|None, "conditions": [...]}; `own`
    None means the outcome holds whichever way the team's own game went.
    """
    for alternative in alternatives:
        if not all(
            permutation[c["matchup"]] == c["winner"] for c in alternative["conditions"]
        ):
            continue
        if alternative["own"] is not None:
            won = own is not None and permutation[own] == team
            if (alternative["own"] == "win") != won:
                continue
        return True
    return False


def check_conditions(league, base, week, history):
    """Verify the stated conditions against the real following week.

    Two things are deliberately kept apart here.

    The COMBINATORIAL claim -- "if these results happen, that outcome follows" --
    is the engine's own. It is checked by replaying the real week through stage 4
    and confirming the verdict matches what the conditions predicted. A
    disagreement is a genuine bug.

    The POINTS assumption is not a claim about the future. A prediction made in
    week N freezes total points at week N, because next week's scores do not
    exist yet. When they arrive the tiebreaker picture can move, so the week N+1
    verdict may legitimately differ. That is counted and reported, not failed --
    the alternative would be to demand the tool predict scoring.
    """
    problems = []
    shifted = []
    permutations = generate_perms.generate_matchup_permutations(base)
    team_results = refine_hypothetical.build_team_scenarios(base, permutations)
    matchups = base["next_week_matchups"]
    real = actual_winners(league, week + 1)

    real_perm = []
    for matchup in matchups:
        pair = frozenset((matchup["team1"], matchup["team2"]))
        if pair not in real:  # a tie, or a pairing the scoreboard disagrees about
            return problems, shifted
        real_perm.append(real[pair])
    real_perm = tuple(real_perm)

    # What stage 4 itself says once the real week is applied
    replayed = {
        t["team_name"]: t["verdict"]
        for t in refine_hypothetical.apply_permutation(base, real_perm)
    }

    for team, outcomes in team_results.items():
        scenario = refine_hypothetical.output_scenarios(
            team, outcomes["clinched_in"], outcomes["eliminated_in"], permutations, matchups
        )
        own = refine_hypothetical.own_matchup_index(matchups, team)
        team_won = own is not None and real_perm[own] == team

        for key, target in (("clinch", "clinched"), ("elim", "eliminated")):
            if key not in scenario:
                continue
            stated = satisfied_by(real_perm, scenario[key], team, own)
            predicted = replayed[team] == target

            if stated != predicted:
                problems.append(
                    f"wk{week}: {team} -- {key} conditions say "
                    f"{'yes' if stated else 'no'} but replaying the real week gives "
                    f"{replayed[team]!r}"
                )
            elif stated and history[week + 1][team] != target:
                shifted.append(
                    f"wk{week}: {team} -- predicted {target} and the results came in, "
                    f"but next week's scoring moved it to {history[week+1][team]!r}"
                )
    return problems, shifted


def main(years):
    all_failures = []
    for year in years:
        all_failures.extend(check_season(year))

    print(f"\n{'=' * 78}")
    if all_failures:
        print(f"FAILURES ({len(all_failures)})")
        for failure in all_failures:
            print(f"  - {failure}")
    else:
        print("ALL CHECKS PASSED -- every claim held up against the real results")
    print(f"{'=' * 78}")
    return 1 if all_failures else 0


if __name__ == "__main__":
    sys.exit(main([int(a) for a in sys.argv[1:]] or [2024, 2025]))
