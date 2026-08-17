"""Stage 5, alternative: the whole report as one self-contained HTML file.

Same input as pretty_print.py, and deliberately the same words -- the header
wording and every scenario phrase come from that module rather than being
restated here, so the two renderers cannot drift apart.

What HTML adds over the terminal is room for the season-review tables, which are
too wide to read in 78 columns: the all-play record week by week, and the
schedule-luck matrix. Both come from the weekly history stage 1 emits, and both
are simply omitted when a payload predates it.

The output needs no server, no network and no assets -- one file you can open,
mail, or keep as a record of where a season stood.
"""

import argparse
import hashlib
import html
import json
import sys

import league_stats
import margins
import pretty_print

def esc(value):
    """Escape for HTML. Team names really do contain apostrophes and quotes."""
    return html.escape(str(value), quote=True)


def title_case(text):
    """Capitalise the first letter of each word, leaving the rest alone.

    str.title() also lower-cases the remainder of every word, so it would turn
    "All-play" into "All-Play" and, worse, an apostrophe into a word boundary --
    "can't" becomes "Can'T". These strings are built from league data, so that
    matters.
    """
    return " ".join(word[:1].upper() + word[1:] for word in text.split(" "))


def monogram(name, abbreviations):
    """The short label to sit beside a team, e.g. 'OVEN'.

    ESPN's own abbreviation where there is one, because a reader recognises it.
    Otherwise the initials of the first few words, so a payload saved before
    stage 1 recorded abbreviations still gets a label rather than a gap.
    """
    abbrev = (abbreviations or {}).get(name)
    if abbrev:
        return abbrev[:5].upper()
    initials = "".join(word[0] for word in name.split() if word[:1].isalnum())
    return (initials[:4] or name[:2]).upper()


def monogram_colour(name):
    """A stable colour per team, derived from the name.

    md5 rather than hash(): the built-in is salted per process, so the same team
    would change colour between runs and two reports of one week would not look
    like the same league. Lightness and saturation are fixed so white text stays
    legible whatever the hue.
    """
    hue = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16) % 360
    return f"hsl({hue} 52% 38%)"


def monogram_html(name, abbreviations):
    return (
        f'<span class="mono" style="background:{monogram_colour(name)}">'
        f"{esc(monogram(name, abbreviations))}</span>"
    )


def record_text(tally):
    """'9-4', or '9-4-1' when there is a tie to report."""
    text = f"{tally['wins']}-{tally['losses']}"
    return f"{text}-{tally['ties']}" if tally["ties"] else text


CSS = """
:root {
  --ink: #14181d; --dim: #6b7684; --line: #dde3ea; --panel: #f6f8fa;
  --good: #1a7f37; --good-bg: #e7f5ea; --bad: #b42318; --bad-bg: #fdeceb;
  --open: #9a6700; --open-bg: #fdf6e3;
  --bye: #0b6bcb; --bye-bg: #e6f0fb;
  --top: #7c3aed; --top-bg: #f1eafd;
}
* { box-sizing: border-box; }
body {
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  color: var(--ink); margin: 0; padding: 2.5rem 1.5rem 4rem;
  max-width: 1100px; margin-inline: auto; background: #fff;
}
h1 { font-size: 1.75rem; margin: 0 0 .3rem; letter-spacing: -.02em; }
h2 {
  font-size: 1.3rem; letter-spacing: -.01em; font-weight: 700;
  color: var(--ink); margin: 2.75rem 0 .8rem;
  border-bottom: 1px solid var(--line); padding-bottom: .4rem;
}
.counts { color: var(--dim); font-size: .9rem; margin: 0 0 .5rem; }
.counts b { color: var(--ink); }
.counts .c-good { color: var(--good); }
.counts .c-bad { color: var(--bad); }
.counts .c-open { color: var(--open); }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: .4rem .55rem; border-bottom: 1px solid var(--line); }
th { font-size: .72rem; text-transform: uppercase; letter-spacing: .07em; color: var(--dim); font-weight: 600; }
td.num, th.num { text-align: right; }
tr.cut td { border-bottom: 2px solid var(--ink); }
.cutnote { font-size: .72rem; color: var(--dim); padding-top: .5rem; }
.mono {
  display: inline-block; min-width: 3.4rem; padding: .1rem .3rem; margin-right: .5rem;
  border-radius: 4px; color: #fff; font-size: .68rem; font-weight: 700;
  letter-spacing: .04em; text-align: center; vertical-align: .05em;
}
/* The colour carries the verdict on its own. Only the standings table adds the
   chip, because a name set in a small pill reads as less important than the
   sentence beside it -- which is backwards, since the name is the subject. */
.top_seed { color: var(--top); }
.bye { color: var(--bye); }
.clinched { color: var(--good); }
.eliminated { color: var(--bad); }
.alive { color: var(--open); }
.pill {
  display: inline-block; padding: .05rem .45rem; border-radius: 999px;
  font-size: .75rem; font-weight: 600;
}
.pill.top_seed { background: var(--top-bg); }
.pill.bye { background: var(--bye-bg); }
.pill.clinched { background: var(--good-bg); }
.pill.eliminated { background: var(--bad-bg); }
.pill.alive { background: var(--open-bg); }
.team { padding: 1rem 0 .25rem; border-top: 1px solid var(--line); }
.team:first-of-type { border-top: none; }
.team h3 { font-size: 1.05rem; margin: 0 0 .35rem; font-weight: 600; }
.alts { margin: 0; padding-left: 1.1rem; }
.alts li { margin: .15rem 0; }
.alts li + li { list-style: none; margin-left: -1.1rem; }
.alts li + li::before { content: "or "; color: var(--dim); font-style: italic; }
.note { color: var(--dim); font-size: .85rem; margin: .35rem 0 0; }
.empty { color: var(--dim); }
.grid td, .grid th { padding: .3rem .4rem; font-size: .82rem; text-align: center; }
.grid td.name, .grid th.name { text-align: left; white-space: nowrap; font-size: .85rem; }
.grid td.total { font-weight: 700; border-left: 1px solid var(--line); }
/* Named for what they mark rather than for high and low: in the all-play table a
   1 is the best week a team can have, so "hi" would mean the smallest number. */
.best { background: var(--good-bg); color: var(--good); font-weight: 700; }
.worst { background: var(--bad-bg); color: var(--bad); font-weight: 700; }
.grid th .mono { min-width: 0; margin-right: 0; padding: .1rem .25rem; }
.grid td.name .mono { min-width: 2.6rem; }
.self { outline: 2px solid var(--ink); outline-offset: -2px; font-weight: 700; }
.better { background: var(--good-bg); color: var(--good); }
.worse { background: var(--bad-bg); color: var(--bad); }
.lede { color: var(--dim); font-size: .88rem; margin: 0 0 .75rem; max-width: 68ch; }
footer { margin-top: 3rem; color: var(--dim); font-size: .78rem; }
"""


def render_header(standings, league):
    counts = pretty_print.summarise(standings, league)
    return f"""<h1>{esc(title_case(pretty_print.header_title(league)))}</h1>
<p class="counts">
  Playoff spots <b>{league['playoff_spots']}</b>
  &middot; <span class="c-good">Clinched <b>{counts['clinched']}</b></span>
  &middot; Up for grabs <b>{counts['up_for_grabs']}</b>
  &middot; <span class="c-open">Still alive <b>{counts['alive']}</b></span>
  &middot; <span class="c-bad">Eliminated <b>{counts['eliminated']}</b></span>
</p>"""


def render_standings(standings, league, abbreviations=None):
    spots = league["playoff_spots"]
    rows = []
    for position, team in enumerate(standings, 1):
        status = pretty_print.display_status(team)
        label = pretty_print.status_label(team)
        # The cut line is drawn under the last team holding a seat
        cut = ' class="cut"' if position == spots else ""
        rows.append(
            f"<tr{cut}><td class=\"num\">{position}</td>"
            f"<td>{monogram_html(team['team_name'], abbreviations)}"
            f"{esc(team['team_name'])}</td>"
            f"<td class=\"num\">{team['wins']}-{team['losses']}</td>"
            f"<td class=\"num\">{team['points_for']:.1f}</td>"
            f'<td><span class="pill {status}">{esc(label)}</span></td></tr>'
        )
    return f"""<h2>Standings</h2>
<table>
<thead><tr><th class="num">#</th><th>Team</th><th class="num">Record</th>
<th class="num">Points for</th><th>Status</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<p class="cutnote">The rule marks the playoff cut line: {spots} spots.</p>"""


def render_matchups(matchups, league, abbreviations=None):
    if not matchups:
        return '<h2>Next Week</h2>\n<p class="empty">No games left to play.</p>'
    rows = "".join(
        f"<tr><td>{monogram_html(m['team1'], abbreviations)}{esc(m['team1'])}</td>"
        f'<td class="empty">vs</td>'
        f"<td>{monogram_html(m['team2'], abbreviations)}{esc(m['team2'])}</td></tr>"
        for m in matchups
    )
    return (
        f"<h2>Week {league['current_week'] + 1} Matchups</h2>\n"
        f"<table><tbody>{rows}</tbody></table>"
    )


def render_scenarios(standings, scenarios, league, thresholds, kind):
    """The clinch or elimination section, in standings order.

    Mirrors pretty_print's structure exactly: a decided team gets a headline, an
    undecided one gets its alternatives, and a section with nothing in it says so
    rather than appearing broken.
    """
    eliminated = kind == "elim"
    heading = "Elimination Scenarios" if eliminated else "Clinch Scenarios"
    settled = "eliminated" if eliminated else "clinched"
    decided_headline = (
        "Eliminated from playoffs" if eliminated else "Clinched playoff spot"
    )
    scoring_headline = (
        "Eliminated on current scoring" if eliminated else "Clinched on current scoring"
    )
    verb = "Eliminated from the playoffs with" if eliminated else "Clinches a playoff spot with"

    weeks_remaining = league["remaining_weeks"]
    blocks = []
    for team in standings:
        name = team["team_name"]
        note = margins.describe(
            team.get("tiebreak"),
            weeks_remaining,
            thresholds,
            eliminated=eliminated,
            margins=team.get("margins"),
        )
        note_html = f'<p class="note">{esc(note)}</p>' if note else ""

        if team["verdict"] == settled:
            headline = decided_headline
            if margins.qualifies_headline(
                team.get("tiebreak"), weeks_remaining, thresholds
            ):
                headline = scoring_headline
            blocks.append(
                f'<div class="team"><h3><span class="{settled}">'
                f"{esc(name)}</span> &mdash; {esc(headline)}</h3>{note_html}</div>"
            )
            continue

        entry = pretty_print.find_scenario(scenarios, name)
        alternatives = entry.get(kind) if entry else None
        if not alternatives:
            continue
        items = "".join(
            f"<li>{esc(pretty_print.phrase_alternative(a))}</li>" for a in alternatives
        )
        blocks.append(
            f'<div class="team"><h3><span class="{team["verdict"]}">{esc(name)}</span>'
            f" &mdash; {esc(verb)}:</h3>"
            f'<ul class="alts">{items}</ul>{note_html}</div>'
        )

    if not blocks:
        wording = "elimination" if eliminated else "clinch"
        blocks.append(
            f'<p class="empty">'
            f"{esc(pretty_print.nothing_yet(wording, weeks_remaining).strip())}</p>"
        )
    return f"<h2>{heading}</h2>\n" + "\n".join(blocks)


def render_all_play(weekly_scores):
    rows = league_stats.all_play_records(weekly_scores)
    if not rows:
        return ""
    weeks = len(rows[0]["weeks"])
    rivals = len(rows) - 1

    head = "".join(f'<th class="num">{i + 1}</th>' for i in range(weeks))
    body = []
    for row in rows:
        cells = []
        for week in row["weeks"]:
            finish = league_stats.weekly_finish(week)
            if finish is None:
                cells.append('<td class="num"></td>')
                continue
            # Only the week's highest and lowest scorer are marked. Shading the
            # near-misses too left most of the table coloured, which reads as
            # decoration rather than as the outliers it is meant to pick out.
            if finish == 1:
                shade = " best"
            elif not week["wins"]:
                shade = " worst"
            else:
                shade = ""
            cells.append(f'<td class="num{shade}">{finish}</td>')
        body.append(
            f'<tr><td class="name">{esc(row["name"])}</td>{"".join(cells)}'
            f'<td class="num total">{record_text(row["total"])}</td>'
            f'<td class="num">{league_stats.win_pct(row["total"]):.3f}</td></tr>'
        )

    return f"""<h2>All-Play Record</h2>
<p class="lede">Each week, every team is scored against <em>every</em> other team rather than
just the one the schedule gave it. The number is where that week's score placed in the
league &mdash; <strong>1 is the week's highest score</strong>, and the marked cells are the
week's highest and lowest. The record on the right is all {weeks * rivals} of those
comparisons: a team well above its real record was beating the league and losing anyway.</p>
<table class="grid">
<thead><tr><th class="name">Team</th>{head}
<th class="num total">All-play</th><th class="num">Pct</th></tr></thead>
<tbody>{''.join(body)}</tbody>
</table>"""


def column_labels(names, abbreviations):
    """Short, unique labels for the schedule-luck columns.

    Full names are far too long for a column head -- truncating them left "Ben's
    Und" beside "Villoni B", which the reader has to guess at. ESPN's
    abbreviations are short and already recognisable, but a payload saved before
    stage 1 recorded them falls back to initials, which are not guaranteed
    unique. Where they collide, number the columns instead: two columns sharing a
    label is worse than a label carrying no meaning.
    """
    labels = [monogram(name, abbreviations) for name in names]
    if len(set(labels)) == len(names):
        return labels
    return [str(i + 1) for i in range(len(names))]


def tag_html(label, name):
    """The chip that ties a row to its column, coloured per team."""
    return (
        f'<span class="mono" style="background:{monogram_colour(name)}">'
        f"{esc(label)}</span>"
    )


def render_schedule_luck(weekly_scores, abbreviations=None):
    result = league_stats.schedule_luck(weekly_scores)
    if not result["rows"]:
        return ""
    order = result["teams"]
    label_of = dict(zip(order, column_labels(order, abbreviations)))

    # Every column head carries its team's own tag and colour, so the schedule a
    # cell belongs to can be read off the column without counting back to a row.
    head = "".join(f'<th class="num">{tag_html(label_of[n], n)}</th>' for n in order)
    body = []
    spread_rows = []
    for row in result["rows"]:
        own = row["against"][row["name"]]
        own_pct = league_stats.win_pct(own)
        cells = []
        for owner in order:
            tally = row["against"][owner]
            pct = league_stats.win_pct(tally)
            if owner == row["name"]:
                css = " self"
            elif pct > own_pct:
                css = " better"
            elif pct < own_pct:
                css = " worse"
            else:
                css = ""
            cells.append(f'<td class="num{css}">{record_text(tally)}</td>')
        body.append(
            f'<tr><td class="name">{tag_html(label_of[row["name"]], row["name"])}'
            f'{esc(row["name"])}</td>{"".join(cells)}</tr>'
        )

        best_name, best, worst_name, worst = league_stats.luck_spread(row)
        spread_rows.append(
            f'<tr><td>{esc(row["name"])}</td>'
            f'<td class="num">{record_text(own)}</td>'
            f'<td class="num better">{record_text(best)}</td>'
            f"<td>{esc(best_name)}</td>"
            f'<td class="num worse">{record_text(worst)}</td>'
            f"<td>{esc(worst_name)}</td></tr>"
        )

    # Naming a real row and a real column beats describing the axes in the
    # abstract, but with one team the two would be the same team and the sentence
    # would say a team borrowed its own schedule.
    example = ""
    if len(order) > 1:
        first, last = order[0], order[-1]
        example = (
            f"So the cell where row {tag_html(label_of[first], first)} meets column "
            f"{tag_html(label_of[last], last)} is what {esc(first)} would have finished "
            f"with had it played {esc(last)}'s schedule. "
        )

    return f"""<h2>Schedule Luck</h2>
<p class="lede">Every team keeps its own scores and takes on someone else's opponents.
<strong>Each row is a team; each column is the team whose schedule it borrowed</strong>, tagged
and coloured to match that team's own row. {example}The outlined cell on the diagonal is a
team playing its own schedule, which is its real record: green beats it, red falls short
of it.</p>
<table class="grid">
<thead><tr><th class="name">Team &darr; &nbsp; borrowing the schedule of &rarr;</th>{head}</tr></thead>
<tbody>{''.join(body)}</tbody>
</table>
<h2>What The Draw Was Worth</h2>
<p class="lede">The best and worst that each team's own scores could have produced against
somebody else's opponents, and whose schedule it would have taken.</p>
<table>
<thead><tr><th>Team</th><th class="num">Real</th><th class="num">Best</th>
<th>with schedule of</th><th class="num">Worst</th><th>with schedule of</th></tr></thead>
<tbody>{''.join(spread_rows)}</tbody>
</table>"""


def render(payload, show=None):
    """The whole document. `show` names the sections to include."""
    show = show or {"header", "standings", "matchups", "scenarios", "stats"}
    base = payload["base_league_data"]
    standings = base["standings"]
    league = base["league_data"]
    scenarios = payload["scenarios"]
    weekly_scores = base.get("weekly_scores") or []
    abbreviations = base.get("abbreviations") or {}
    thresholds = margins.load_thresholds()

    parts = []
    if "header" in show:
        parts.append(render_header(standings, league))
    if "standings" in show:
        parts.append(render_standings(standings, league, abbreviations))
    if "matchups" in show:
        parts.append(
            render_matchups(base["next_week_matchups"], league, abbreviations)
        )
    if "scenarios" in show:
        parts.append(
            render_scenarios(standings, scenarios, league, thresholds, "clinch")
        )
        parts.append(render_scenarios(standings, scenarios, league, thresholds, "elim"))
    if "stats" in show and weekly_scores:
        parts.append(render_all_play(weekly_scores))
        parts.append(render_schedule_luck(weekly_scores, abbreviations))

    played = league["current_week"]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Playoff scenarios &middot; after week {played}</title>
<style>{CSS}</style>
</head>
<body>
{chr(10).join(p for p in parts if p)}
<footer>Generated from results through week {played} of a
{league['num_weeks']}-week regular season. Clinched and eliminated are exact over
every remaining schedule; a verdict resting on a points gap the scoring could still
close is reported as alive.</footer>
</body>
</html>
"""


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="to_html.py",
        description="Render the scenario payload as one self-contained HTML file.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="write here instead of stdout",
    )
    parser.add_argument("--no-header", action="store_true", help="hide the summary")
    parser.add_argument(
        "--no-standings", action="store_true", help="hide the standings table"
    )
    parser.add_argument(
        "--no-matchups", action="store_true", help="hide next week's matchups"
    )
    parser.add_argument(
        "--no-stats", action="store_true", help="hide the season-review tables"
    )
    return parser.parse_args(argv)


def sections(args):
    show = {"header", "standings", "matchups", "scenarios", "stats"}
    for name in ("header", "standings", "matchups", "stats"):
        if getattr(args, f"no_{name}"):
            show.discard(name)
    return show


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    document = render(json.load(sys.stdin), sections(args))

    if args.output:
        with open(args.output, "w") as handle:
            handle.write(document)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(document)
    return 0


if __name__ == "__main__":
    sys.exit(main())
