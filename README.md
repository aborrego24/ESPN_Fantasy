# Fantasy Football Playoff Scenarios

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-228%20passing-brightgreen)
![Offline mode](https://img.shields.io/badge/offline%20mode-zero%20dependencies-success)
![Platforms](https://img.shields.io/badge/platforms-ESPN%20(more%20planned)-informational)
![Status](https://img.shields.io/badge/status-works%2C%20actively%20improving-yellow)

Work out **exactly** what has to happen for each team in your fantasy football league to make or miss the playoffs.

Example

```
====== Team A Clinches a playoff spot with: ======
  - a WIN
    or ...
  - a LOSS and Team B WIN and Team C WIN
```

## Contents

- [What it actually does](#what-it-actually-does)
- [Supported platforms](#supported-platforms)
- [Quick start](#quick-start)
- [Usage](#usage)
- [Reading the output](#reading-the-output)
- [How it works](#how-it-works)
- [The concepts](#the-concepts-explained)
- [Running tests](#running-the-tests)
- [Score thresholds](#score-thresholds)
- [Limitations and future improvements](#limitations-and-future-improvements)


## What it actually does

In a fantasy league, the top *N* teams by record make the playoffs, with ties broken by total points scored. Late in the season everyone wants to know the same thing: *What do I need to do this week to clinch?* or *Is my destiny even in my own hands?*

This tool answers those questions **mathematically**. A team has **clinched** only if it makes the playoffs in *every* possible way the rest of the season could play out, and is **eliminated** only if it makes them in *none*. Anything in between gets the precise list of results it needs.

The playoff math is the same whichever site you play on, so the engine knows nothing about any particular platform. It works from records, points, and a remaining schedule. Only the first stage of the pipeline talks to a provider (ESPN, Sleeper, ...).

---

## Supported platforms

| Platform | Status |
|---|---|
| ESPN | Supported |
| Sleeper | Planned |
| Yahoo | Planned |
| NFL.com | Planned |
| Anything else | Bring a payload (see below) |

Adding a platform means writing one new version of stage 1 that emits the same JSON. Nothing downstream changes, because nothing downstream knows where the numbers came from.

That also means you can use this **without any supported platform at all**: hand-write a JSON file in the shape of `scenario_engine_tests/week13.json` and run it through `--test`. That path needs no network and no dependencies.

> Because ESPN is the only provider wired up today, the options and environment variables below are still ESPN-specific (`--league-id`, `ESPN_LEAGUE_ID`). Generalising that naming is on the roadmap.

---

## Quick start

You need **Python 3.11 or newer** (developed on 3.12).

### Try it with no setup at all

The bundled sample data runs with **zero dependencies** — no installs, no account anywhere, no network:

```bash
git clone https://github.com/aborrego24/ESPN_Fantasy.git
cd ESPN_Fantasy
./run_scenarios.sh --test scenario_engine_tests/week13.json

# or the full report as a page
./run_scenarios.sh --test scenario_engine_tests/week13.json --html report.html
```

That's real end-of-season data from a 10-team league, and it exercises everything except the download step.

Once you've pointed it at a live league, `--dump` turns any week into another one of
these, so you only need the network once:

```bash
./run_scenarios.sh --irl 13 --dump my_week13.json     # downloads and saves
./run_scenarios.sh --test my_week13.json              # replays it, offline, forever
```

### Point it at a live league

```bash
python3 -m venv env
# Windows: env\Scripts\activate
source env/bin/activate          
pip install -r requirements.txt

./run_scenarios.sh --irl 12 --league-id 123456789 --year 2026
```


> The repo ships with no league of its own, so you must point it at yours. Your league id is the number in your league's ESPN URL:
> `https://fantasy.espn.com/football/league?leagueId=`**`123456789`**
>
> Supply it in any of three ways (checked in this order): the `--league-id` flag, the `ESPN_LEAGUE_ID` env var, or a `scenario_engine/local_config.py` file. For a value you always use, copy the template once:
> ```bash
> cp scenario_engine/local_config.example.py scenario_engine/local_config.py   # then edit it
> ```
> `local_config.py` is gitignored, so your league id never gets committed.

> **Private leagues** need your two ESPN cookies, `ESPN_S2` and `SWID`. Set them the same way as the league id — as env vars, or in `local_config.py` (both are gitignored / never committed):
> ```bash
> export ESPN_S2='AEB...long-value...'
> export SWID='{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}'
> ```
> Find them in your browser's cookies for `fantasy.espn.com` (keep `SWID`'s braces). A public league needs none of this. If a private league is read without them, the tool says so and how to fix it. On the command line they're deliberately *not* accepted as flags — a secret there shows up in `ps` and shell history.


## Usage

```bash
./run_scenarios.sh --irl <weeks_played>          # download a live league
./run_scenarios.sh --test <path_to_file.json>    # replay saved data, offline
```

`<weeks_played>` is how many weeks are **already finished**. So `--irl 12` means "twelve weeks are in the books, tell me about week 13."

### Options

| Option | What it does | Default |
|---|---|---|
| `--league-id <id>` | Which league to read | required (flag, `ESPN_LEAGUE_ID`, or `local_config.py`) |
| `--year <season>` | Which season | required (flag, `ESPN_YEAR`, or `local_config.py`) |
| `--test <path>` | Replay a saved payload instead of downloading | — |
| `--html <path>` | Write an HTML report instead of printing | prints to the terminal |
| `--dump <path>` | Also save the downloaded data, replayable with `--test` | — |
| `--no-header` | Hide the summary line | shown |
| `--no-standings` | Hide the standings table | shown |
| `--no-matchups` | Hide next week's matchups | shown |
| `--no-stats` | Hide the season-review tables (HTML only) | shown |
| `--history <path>` | Add the All-Time tab from a saved history (HTML only) | — |

Environment variables work too, which is handy if you always use the same league:

```bash
export ESPN_LEAGUE_ID=123456789
export ESPN_YEAR=2026
./run_scenarios.sh --irl 12
```

### The HTML report

Everything the terminal shows, plus two tables that need more than 78 columns:

```bash
./run_scenarios.sh --irl 13 --html report.html
open report.html          # Linux: xdg-open
```

One file, no server, no assets, nothing to install — you can mail it or keep it as a
record of where a season stood. It adds:

**All-play record** — each week, your score against *every* team's rather than just the
one the schedule handed you. This is the honest measure of how you played, and it
regularly disagrees with the standings: in the 2025 season one team sat at 4-9 with the
fourth-best all-play record, while an 8-5 team was in the bottom four. One was unlucky;
the other was not good.

**Schedule luck** — your record had you played each rival's schedule instead of your
own, for all of them. Your real record is on the highlighted diagonal; green cells are
schedules you'd have preferred. The summary underneath names the best and worst draw
available to each team, which is the closest thing to a number for "how much did the
schedule cost me".

Both read only completed weeks, so they take no part in any clinch verdict.

### The All-Time tab

With `--history`, the report grows a second tab ranking **every team-season the league
has ever played** — the best teams of all time, and the managers behind them.

```bash
python3 tools/fetch_history.py --out history.json   # once per finished season
./run_scenarios.sh --irl 14 --html report.html --history history.json
```

History is fetched separately and cached on purpose: it is one download per season,
and a finished season never changes. That also means you can re-render the report, or
re-weight the rating, with no network at all.

> ⚠️ **Older seasons need cookies.** Only the current season and the one before it
> answer unauthenticated — everything earlier returns 401 *even for a public league*.
> Set `ESPN_S2` / `SWID` (see [Point it at a live league](#point-it-at-a-live-league))
> or the history stops after two years. The fetcher says which years it had to skip.

A season total cannot be compared across years — this league has run 9 teams over 15
weeks and 10 over 14 — so every rate is measured **within its own season**:

| Component | Default weight | What it is |
|---|---|---|
| Strength | 45% | All-play win% — the record against the whole league every week, not just the one team the schedule handed you |
| Record | 30% | The real win% — what the standings actually said |
| Scoring | 25% | PPG against that season's league average, where .500 is exactly average, so scoring eras cancel out |

Strength and record overlap deliberately: the gap between them *is* schedule luck, so
a lucky team is credited for its wins without being credited as though it earned them
all. Every component is shown beside the rating, because a number nobody can audit is
not worth having.

**Record follows the scope**, so the won-lost shown is the record for whatever is being
ranked. One real team went 12-1 and lost its first playoff game: that is `12-1` under
Regular Season, `12-2` under Both, and `0-1` under Playoffs. Strength and Scoring stay on
the regular season outside the Playoffs scope — all-play over playoff weeks would be
meaningless, since only the surviving teams are still playing.

Every column except Accolades sorts on click. The `#` column always shows the rating
rank, whatever the table is sorted by, so sorting by PPG still tells you the league's
highest scorer was only the 5th-best team.

**Accolades** are added on top rather than blended in — a 14-week body of work should not
be outweighed by one single-elimination bracket:

| Accolade | Points |
|---|---|
| Champion | 10 |
| #1 seed | 3 |
| Playoff berth | 1.5 |
| Per playoff win | 1 |

The depth of a run is paid **per playoff win, not per placement**. Enumerating
runner-up and final four separately left a hole: across eight completed seasons of two
real leagues the runner-up went 2-1 or 1-1 *every time*, so a team that won two games and
lost the final scored the same as one that lost in round one. Per-win credit fixes the
ordering with no rule per round and scales to any bracket — this league has run both five
and six playoff spots. It follows Bill James's [Hall of Fame
Monitor](https://www.baseball-reference.com/about/leader_glossary.shtml), the same idea
of points-per-honour, which credits a pennant winner who loses the World Series 5 against
6 for winning it — not 0.

The title is sized at roughly a tenth of a season's rating, and deliberately not more,
because in this league a championship is mostly luck: over those eight seasons the top
seed won it **twice**, the average champion was the **third** seed, and two champions were
the 7th and 10th best teams of their own season on regular-season merit. Worth honouring;
not evidence. If you disagree, that is what the Accolades slider is for.

Those weights are **defaults, not verdicts** — the tab carries a slider for each, plus
one that scales accolades, and the ranking re-sorts as you drag. Only the ratio between
the three rates matters, so they are normalised by their sum and you never have to make
them total 100. It all runs in the page from data already on each row, so there is no
round trip and the file still works offline.

#### Three ways to read a season

A selector on the heading switches what is being ranked:

| Scope | Population | Rating | Accolades shown |
|---|---|---|---|
| **Regular Season** | Every team | Regular-season rates, accolades excluded | `PO` and `#1` only |
| **Both** (default) | Every team | Regular-season rates plus accolades | all |
| **Playoffs** | Only teams that qualified | The bracket's own rates, plus accolades | all |

Under Regular Season the bracket did not happen: it scores nothing, and it is not
listed either. A `CHAMP` badge beside a rating that deliberately ignores the
championship invites the reader to assume it counted. Qualifying and the top seed stay,
because the record earned both.

Regular Season is the fairest comparison — the largest sample, and the only view where
everyone played the same number of games. Playoffs is the noisiest by far: one to three
games, so it measures a hot fortnight rather than a good team, which is exactly why it
is worth seeing on its own rather than blended in.

> **On the bracket:** ESPN returns `playoffTierType: NONE` for every post-season
> matchup in this league, so the *rounds* cannot be read — a semifinal is
> indistinguishable from a fifth-place game. Three things are therefore excluded, and
> what is left is the **championship path**:
>
> - **Consolation games between non-qualifiers.** Who qualified *is* reliable, and across
>   eight seasons the qualifying teams play only each other after the regular season — so
>   a game is bracket football only if both sides made it.
> - **Anything after a team's first loss.** The path is single elimination, so a win that
>   comes after elimination is a fifth-place game even when both sides qualified. This
>   caught real cases: 2025 Klorgon lost in round one, won twice on the ladder, and read
>   as 1-2 with credit for a playoff win it never had. Fourteen team-seasons in the
>   12-team league were affected. The losing game itself is kept — the team was alive when
>   it played it.
> - **Byes.** A top seed skipping round one contested nothing, and ESPN is not even
>   consistent about the score (one real bye carries 165 points, another 0).
>
> The result has a property worth checking: every playoff team ends either unbeaten
> (the champion) or with exactly one loss. More than one means consolation games leaked
> back in.

Two kinds of year go missing, and the tab distinguishes them: a season **still in
progress** is excluded rather than discounted (a 3-0 start sits further from its league
average on every rate at once, and would otherwise rank near the top), and a season
**ESPN refused** is reported with its reason.

Manager careers are grouped by **manager name**, not by team name (names do not survive
a season) and not by ESPN owner id, which turns out to be no more durable: in one real
league a manager appears under two different SWIDs, and ESPN flipped the listed order of
a co-managed pair mid-history, so keying on the id or on "the first owner" split one
continuous franchise across two people. A **co-managed season counts for every manager
of that team**, which double-counts a shared title on purpose — both of them won it.
Careers are averaged rather than summed, so a long one does not beat a better short one.

---

## Reading the output

There are four things the tool can tell you about a team, and the wording is deliberate.

### 1. Clinched

```
====== Team C Clinched Playoff Spot ======
```

Mathematically certain. There is no combination of remaining results that keeps this team out.

The standings status goes one level further where the league has them. A **`bye`**
means the team is certain to finish high enough to skip the first playoff round —
the same question as clinching, asked of fewer seats:

```
      TEAM                       RECORD  POINTS FOR  STATUS
   1  Momma Gus                    10-4      1844.4  bye
   2  I can't let you get close    10-4      1795.9  bye
   3  Villoni Boutique #2 Fan       9-5      1817.2  clinched
```

And **`clinched #1 seed`** for a team certain to finish top of the table, which is
reported in every league, byes or not.

Each level implies the ones below it — the #1 seed is a bye is a place — so only the
strongest true claim is shown, and all of them are counted in `Clinched` in the
summary line. The five statuses are `clinched #1 seed`, `clinched bye`, `clinched`,
`alive`, `eliminated`.

### 2. Clinched, but leans on the tiebreaker

```
====== Team A Clinched Playoff Spot ======
       barring a 159-point swing against Team D in the final week
       — the largest on record in this league is 120
```

Because seeding ties are generally broken by *total points scored*, and nobody knows future scores, some verdicts quietly depend on the current points gap holding up. Rather than hide that, the tool names the rival, the gap, and how that gap compares to **what your league has actually produced historically**. A 159-point swing in one week has never happened here — so this is as good as clinched, and you can see why.

### 3. A live race

```
====== Team E Eliminated on current scoring ======
       live points race with Team B — 49 apart with 1 week to play
```

Note the headline says *"on current scoring"*, not *"eliminated."* 49 points-for swing in one week is very possible, so this team has a real path.

### 4. Still to be decided

```
====== Team F Eliminated from playoffs with: ======
  - a WIN and Team A WIN
    or ...
  - a WIN and Team C WIN
    or ...
  - a LOSS
```

---

## How it works

Five small programs, each doing one job, passing [JSON](https://en.wikipedia.org/wiki/JSON) down a [Unix pipeline](https://en.wikipedia.org/wiki/Pipeline_(Unix)):

| Stage | File | Job |
|---|---|---|
| 1 | `league_data.py` | Fetch the league from a provider (or replay a saved file) → records, points, remaining schedule. **The only platform-aware stage.** |
| 2 | `refine_current_week.py` | Sort the standings; decide who has clinched or been eliminated |
| 3 | `generate_perms.py` | Enumerate every win/loss combination for next week |
| 4 | `refine_hypothetical.py` | Replay each combination, re-decide everyone's fate, work out the minimum conditions |
| 5 | `pretty_print.py` **or** `to_html.py` | Turn all that into English, for a terminal or a page |

Stage 5 is where `--html` swaps one renderer for the other. Both read the same payload,
and the wording lives in `pretty_print.py` so the two cannot describe a verdict
differently. `league_stats.py` sits alongside them, computing the season-review tables
from the weekly history stage 1 records.

The All-Time tab hangs off a **stage 0** that is deliberately not in the pipe:
`tools/fetch_history.py` writes every accessible season to a file via `history_data.py`,
and `all_time.py` ranks it when stage 5 is handed that file with `--history`. It is kept
off the live path because it is one download per season, none of it changes once a
season is finished, and no clinch verdict depends on any of it.

Because each stage just reads JSON and writes JSON, you can stop anywhere and look:

```bash
python3 scenario_engine/league_data.py --test scenario_engine_tests/week13.json \
  | python3 scenario_engine/refine_current_week.py \
  | python3 -m json.tool
```


## The concepts, explained

New to this? This is the idea the tool leans on most.

**Divisional seeding** — if your league has divisions, ESPN doesn't seed purely by
record. Every **division winner** is seeded ahead of every team that didn't win one,
with each group then ordered by record and points. That means a team can be seeded
above another *with fewer wins*. The tool models this, so the standings table is
printed in true seed order rather than record order. A single-division league is
unaffected.

**[Magic number](https://en.wikipedia.org/wiki/Magic_number_(sports))** — the classic sports shortcut for "how many more wins do I need." Useful for a quick gut check, but it only compares you against *one* rival at a time, so it can't answer "do I finish in the top six?" This project used to rely on it and gave wrong answers because of it. It has been removed — the exact search below answers the real question, and nothing read the magic number anyway.

## Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

228 tests, about four seconds, **no network needed**. Highlights of what's covered:

- The clinch/elimination engine is checked against **brute force** — 52 randomly generated leagues where every possible season really is enumerated one by one and compared.
- The condition simplifier is verified **exhaustively**: every one of the 65,535 possible outcome subsets (up to four games) is confirmed to be described exactly — never more broadly.
- End to end, for every team and every scenario, the stated conditions are satisfied by *exactly* the outcomes where that result actually occurs.

---

## Score thresholds

To judge whether a points gap is plausible, the tool uses your league's own scoring history rather than a guess. `scenario_engine/score_thresholds.json` records the biggest point swings ever observed over 1–6 week windows.

Regenerate it for your own league:

```bash
ESPN_LEAGUE_ID=123456789 python3 tools/derive_score_thresholds.py 2024 2025
```

---

## Limitations and future improvements

### Known limitations

| Severity | Limitation | Detail |
|---|---|---|
| **High** | One platform so far | ESPN only. The engine is platform-agnostic; only stage 1 needs writing per provider |
| **Low** | Duplicate team names get a tag | ESPN allows two teams to share a name. They're told apart by abbreviation — `Ringers (OVEN)` / `Ringers (SCHU)` — so the label differs slightly from what ESPN shows |
| **Medium** | Future points are frozen | Tiebreaker maths assumes current point totals hold. The output always says when a verdict depends on this |
| **Low** | Conditions cover next week only | Verdicts use the whole remaining season, but the printed conditions describe next week — "you need someone to lose in five weeks" isn't actionable |
| **Low** | Future ties are not simulated | Past ties are read and reported correctly; possible *future* results are only ever win or loss. A tie is rare enough that enumerating it costs more than it explains |

### Planned

- **More platforms** — Sleeper, Yahoo, NFL.com. Each needs one new stage 1 and nothing else
- **Provider-neutral configuration** — rename `--league-id` / `ESPN_*` now that more than one platform is coming
- **A projections mode** — use ESPN's own forecasts for future scoring, clearly labelled as a forecast rather than maths
- **Smarter pruning** — rule out whole classes of outcome earlier
- **Charts in the HTML report** — scoring trends over the season, drawn inline as SVG

---

## Built with

- [espn-api](https://github.com/cwendt94/espn-api) by [@cwendt94](https://github.com/cwendt94) — the Python wrapper that makes ESPN's undocumented fantasy API usable, and currently the project's only provider dependency. This would not exist without it.
