"""Resolve which league to read, keeping real league ids out of the repo.

The repo ships with no league of its own. A value is resolved in this order:

    explicit CLI flag  >  ESPN_LEAGUE_ID / ESPN_YEAR env var  >  local_config.py

`local_config.py` is gitignored. Copy `local_config.example.py` to
`local_config.py` and fill in your own league. If none of the three channels
supplies a value the caller gets None, and the entry point turns that into one
clear sentence rather than a silent default or a traceback.
"""

import os

try:
    import local_config as _local
except ImportError:
    _local = None


def _default(env_var, attr):
    """The default for one setting: env var first, then local_config, else None."""
    env = os.environ.get(env_var)
    if env:
        return int(env)
    return getattr(_local, attr, None) if _local else None


def default_league_id():
    return _default("ESPN_LEAGUE_ID", "LEAGUE_ID")


def default_year():
    return _default("ESPN_YEAR", "YEAR")
