# Copy this file to local_config.py (which is gitignored) and fill in your
# league. Nothing here is committed, so your league id stays private.
#
#     cp scenario_engine/local_config.example.py scenario_engine/local_config.py
#
# Your league id is in the ESPN Fantasy URL when you view your league:
#     https://fantasy.espn.com/football/league?leagueId=XXXXXXXX
#
# Either value can also be supplied at runtime instead of here, via the
# --league-id / --year flags or the ESPN_LEAGUE_ID / ESPN_YEAR env vars.

LEAGUE_ID = 0  # e.g. 123456789
YEAR = 2024

# Private leagues only. Public leagues can leave these out entirely.
# Copy both from your browser's cookies for fantasy.espn.com (or set them as
# the ESPN_S2 / SWID env vars instead). SWID keeps its surrounding braces {...}.
# ESPN_S2 = "AEB...long-value..."
# SWID = "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"
