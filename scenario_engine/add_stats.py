"""Optional stage after refine_hypothetical: attach the season stats to the payload.

Reads the final payload on stdin and writes it back with
`base_league_data.stats` added, holding exactly what to_html computes for its
stats sections -- all-play, schedule luck, strength of schedule, and the
preseason strength view -- so a renderer that is not to_html (the web frontend)
can draw them without re-implementing the math. to_html itself still computes
these on its own and ignores this key.

The same gating as to_html: with games played, the season tables; with none but
projections and a schedule, the preseason view; otherwise nothing.
"""
import json
import sys

import league_stats
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


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    payload["base_league_data"]["stats"] = season_stats(payload["base_league_data"])
    json.dump(payload, sys.stdout)
