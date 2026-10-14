"""Optional stage after refine_hypothetical: attach what a non-to_html renderer needs.

Reads the final payload on stdin and writes it back with two keys added under
`base_league_data`, both holding exactly what to_html computes for itself, so a
renderer that is not to_html (the web frontend) can draw them without
re-implementing the math. to_html still computes both on its own and ignores
these keys.

  stats           -- the season tables: all-play, schedule luck, strength of
                     schedule, and the preseason strength view. Gated as to_html
                     gates them: with games played, the season tables; with none
                     but projections and a schedule, the preseason view;
                     otherwise nothing.
  scenario_notes  -- per team, the clause qualifying a clinched or eliminated
                     verdict. Unlike the stats, this one cannot be derived from
                     the payload at all: it is measured against
                     score_thresholds.json, which never travels in the JSON.
"""
import json
import sys

import league_stats
import margins
import strength


def season_stats(base):
    weekly_scores = base.get("weekly_scores") or []
    stats = {}
    # A preseason payload has a weekly_scores entry per team but no weeks in it.
    if any(entry.get("weeks") for entry in weekly_scores):
        stats["strength"] = strength.strength_table(weekly_scores, base.get("remaining_matchups"))
        stats["all_play"] = league_stats.all_play_records(weekly_scores)
        stats["schedule_luck"] = league_stats.schedule_luck(weekly_scores)
    elif base.get("projected_ppg") and base.get("remaining_matchups"):
        stats["preseason_strength"] = strength.preseason_strength(
            base["projected_ppg"], base["remaining_matchups"]
        )
    return stats


def scenario_notes(base, thresholds=None):
    """{team_name: {note, on_current_scoring}} for the teams that need one.

    A verdict resting on the total-points tiebreaker holds only while the scoring
    holds, and how much of a caveat that is depends on what swings this league
    has actually produced -- which lives in score_thresholds.json, not in the
    payload. So the sentence is rendered here rather than shipping the threshold
    table for a renderer to re-derive it from.

    `on_current_scoring` says the swing is ordinary enough that the bare verdict
    overstates it, and the headline should read "Clinched on current scoring".
    One entry per team, not per kind: margins.describe words a clinch and an
    elimination the same way.
    """
    thresholds = margins.load_thresholds() if thresholds is None else thresholds
    weeks_remaining = base["league_data"]["remaining_weeks"]
    notes = {}
    for team in base["standings"]:
        tiebreak = team.get("tiebreak")
        note = margins.describe(
            tiebreak, weeks_remaining, thresholds, margins=team.get("margins")
        )
        scoring = margins.qualifies_headline(tiebreak, weeks_remaining, thresholds)
        # Most teams have no tiebreak dependency at all; leave them out rather
        # than filling the payload with nulls.
        if note or scoring:
            notes[team["team_name"]] = {"note": note, "on_current_scoring": scoring}
    return notes


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    base = payload["base_league_data"]
    base["stats"] = season_stats(base)
    base["scenario_notes"] = scenario_notes(base)
    json.dump(payload, sys.stdout)
