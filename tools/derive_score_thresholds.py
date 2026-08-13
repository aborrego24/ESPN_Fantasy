"""Regenerate scenario_engine/score_thresholds.json from league history.

The engine needs to say how plausible a points swing is. Rather than hardcode a
guess, measure it: for every ordered pair of teams and every window of R
consecutive weeks, record how much one out-scored the other by. The largest
value ever observed is the "has never happened" line; the 99th percentile is
the "very unlikely" line.

    python3 tools/derive_score_thresholds.py 2024 2025

Needs network access and espn_api. The output file is committed so the engine
itself stays offline.
"""

import itertools
import json
import os
import sys

from espn_api.football import League

LEAGUE_ID = int(os.environ.get("ESPN_LEAGUE_ID", "123564885"))
MAX_WEEKS = 6
OUTPUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scenario_engine",
    "score_thresholds.json",
)


def weekly_scores(year):
    league = League(league_id=LEAGUE_ID, year=year)
    weeks = league.settings.reg_season_count
    scores = {}
    for team in league.teams:
        # falsy entries are unplayed weeks
        scores[team.team_name] = [s for s in team.scores[:weeks] if s]
    return scores


def differentials(scores, window):
    played = min(len(s) for s in scores.values())
    out = []
    for a, b in itertools.permutations(scores, 2):
        left, right = scores[a][:played], scores[b][:played]
        for start in range(0, played - window + 1):
            gap = sum(left[start : start + window]) - sum(right[start : start + window])
            if gap > 0:
                out.append(gap)
    return sorted(out)


def main(years):
    samples = {w: [] for w in range(1, MAX_WEEKS + 1)}
    provenance = []
    for year in years:
        scores = weekly_scores(year)
        played = min(len(s) for s in scores.values())
        provenance.append({"year": year, "teams": len(scores), "weeks": played})
        for window in samples:
            samples[window].extend(differentials(scores, window))

    by_weeks = {}
    running_max = 0.0
    running_p99 = 0.0
    for window in range(1, MAX_WEEKS + 1):
        values = sorted(samples[window])
        if not values:
            continue
        p99 = values[int(0.99 * len(values)) - 1]
        # A longer window can only offer more room to catch up, so keep both
        # series monotonic -- small samples produce noisy tails otherwise.
        running_max = max(running_max, values[-1])
        running_p99 = max(running_p99, p99)
        by_weeks[str(window)] = {
            "max_observed": round(running_max, 1),
            "p99": round(running_p99, 1),
            "samples": len(values),
        }

    payload = {
        "provenance": {
            "league_id": LEAGUE_ID,
            "seasons": provenance,
            "note": "Point differentials between two teams over N consecutive weeks.",
        },
        "by_weeks_remaining": by_weeks,
    }
    with open(OUTPUT, "w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print(f"wrote {OUTPUT}")
    for window, row in by_weeks.items():
        print(f"  {window} week(s): max={row['max_observed']} p99={row['p99']}")


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [2024, 2025])
