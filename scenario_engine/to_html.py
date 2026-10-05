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

import all_time
import league_stats
import margins
import pretty_print
import strength

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


def team_mark(name, abbreviations, logo_class=None):
    """A team's inlined logo if --logos captured one, else its monogram chip.

    `logo_class` maps a name to its CSS class (see _logo_styles); the image data
    lives once in that class, so this only emits a reference. The chip is always
    the fallback, so a team whose logo failed to fetch and a report built
    without --logos both read the same as before.
    """
    cls = (logo_class or {}).get(name)
    if cls:
        return (
            f'<span class="logo {cls}" role="img" aria-label="{esc(name)}" '
            f'title="{esc(name)}"></span>'
        )
    return monogram_html(name, abbreviations)


def _logo_styles(logos):
    """(css_rules, {name: class}) with each logo's data URI written exactly once.

    A team's image goes in one CSS rule; every table cell references it by class.
    That is what keeps the mailable file small -- a logo shown in the standings,
    the matchups and the strength table is still inlined a single time.
    """
    rules, classes = [], {}
    for index, (name, uri) in enumerate(sorted(logos.items())):
        cls = f"lg{index}"
        classes[name] = cls
        rules.append(f'.{cls}{{background-image:url("{uri}")}}')
    return "".join(rules), classes


def record_text(tally):
    """'9-4', or '9-4-1' when there is a tie to report."""
    text = f"{tally['wins']}-{tally['losses']}"
    return f"{text}-{tally['ties']}" if tally["ties"] else text


def _standings_record(team):
    """`record_text` for a standings entry, which may carry no tie count at all."""
    return record_text(
        {
            "wins": team.get("wins", 0),
            "losses": team.get("losses", 0),
            "ties": team.get("ties", 0),
        }
    )


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
/* Divisional standings: one table per division, side by side where there is
   room, stacking on a narrow screen (and in email clients that ignore flex). */
/* The standings view switcher: rigid, square segmented buttons on the header. */
.seg { display: inline-flex; margin-left: 1rem; vertical-align: middle; }
.seg button {
  font: inherit; font-size: .8rem; font-weight: 600; line-height: 1.3;
  padding: .15rem .7rem; border: 1px solid var(--line); background: #fff;
  color: var(--dim); cursor: pointer; border-radius: 0; margin-left: -1px;
}
.seg button:first-child { margin-left: 0; }
.seg button.on { background: var(--ink); color: #fff; border-color: var(--ink); }
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
  font-size: .75rem; font-weight: 600; white-space: nowrap;
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
/* Round, not a rounded square: these are avatars -- a manager's uploaded photo or
   an ESPN logo-pack mark -- and a hard-edged crop of a photo reads as a pasted-in
   screenshot next to the text it labels. */
.logo {
  display: inline-block; height: 1.5rem; width: 1.5rem; margin-right: .5rem;
  border-radius: 50%; vertical-align: middle;
  background-size: cover; background-position: center; background-repeat: no-repeat;
}
.grid td.name .logo { height: 1.3rem; width: 1.3rem; }
.self { outline: 2px solid var(--ink); outline-offset: -2px; font-weight: 700; }
.better { background: var(--good-bg); color: var(--good); }
.worse { background: var(--bad-bg); color: var(--bad); }
.lede { color: var(--dim); font-size: .88rem; margin: 0 0 .75rem; max-width: 68ch; }
/* The 68ch cap keeps prose readable beside the narrow season tables. The all-time
   tables are far wider, so a lede capped there stops halfway across the page and
   reads as broken rather than as a measure. */
.lede.wide { max-width: none; }
.controls { display: flex; flex-wrap: wrap; gap: 1.75rem; align-items: center; margin: 0 0 1rem; font-size: .85rem; }
.controls label { display: flex; align-items: center; gap: .5rem; }
.controls .dim { color: var(--dim); font-size: .8rem; }
.controls input[type=range] { vertical-align: middle; }
.tip { position: relative; cursor: help; border-bottom: 1px dotted var(--dim); outline: none; }
.tipbox {
  display: none; position: absolute; right: 0; top: 1.5rem; z-index: 5;
  grid-template-columns: auto auto auto; column-gap: .9rem; row-gap: .12rem;
  background: var(--ink); color: #fff; padding: .5rem .65rem; border-radius: 6px;
  font-size: .74rem; font-weight: 400; text-align: left; white-space: nowrap;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .28);
}
.tip:hover .tipbox, .tip:focus .tipbox { display: grid; }
.tiphead { color: #8b95a1; font-size: .64rem; text-transform: uppercase; letter-spacing: .06em; padding-bottom: .1rem; }
/* The chart is an alternate view of the same section, hidden until the toggle
   flips (so with no JS the table stands). Its axis pickers sit ON the axes -- the
   X picker under the plot, the Y picker down the left -- rather than in the top
   controls, which is why they never show in the table view. */
#sos-chart-view {
  /* `relative` makes this the hover card's offset parent, which is what the card
     measures itself against; without it the card anchors to some ancestor further
     up and lands beside the dot instead of on it. */
  position: relative;
  display: grid; grid-template-columns: auto 1fr; grid-template-rows: 1fr auto;
  align-items: center; gap: .35rem .5rem; margin-top: .5rem;
}
/* display:grid above overrides the `hidden` attribute's display:none, which
   would leak the axis pickers into the table view -- the id+attribute selector
   outranks it and hides the chart until it is chosen. */
#sos-chart-view[hidden] { display: none; }
.chart-y { grid-column: 1; grid-row: 1; }
/* Capped at the viewBox width so the drawing is never scaled up (see svg.at-chart
   for what stretching it did), and centred in its column so the X picker -- which
   centres on the column -- lines up with the middle of the plot. */
#sos-chart {
  grid-column: 2; grid-row: 1; margin: 0 auto;
  width: 100%; max-width: 900px; height: auto;
  font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.chart-x { grid-column: 2; grid-row: 2; justify-self: center; }
/* The picker alone, no "X axis" caption -- it sits on the axis it controls. */
.chart-x, .chart-y { display: inline-flex; align-items: center; gap: .35rem; font-size: .78rem; color: var(--dim); }
.cax { stroke: var(--dim); stroke-width: 1; }
.cref { stroke: var(--line); stroke-width: 1; stroke-dasharray: 3 3; }
.ctick { fill: var(--dim); font-size: 11px; }
.clabel { fill: var(--ink); font-size: 12px; font-weight: 600; }
/* font-size is set per dot so a four-letter abbreviation still fits, as on the
   all-time chart. */
.cpt { fill: #fff; font-weight: 700; }
.cpt-dot { stroke: #fff; stroke-width: 1; }
/* An inlined team photo, cut to a circle with a hairline ring, so it sits among
   the monogram dots as the same kind of mark rather than a pasted-in square. */
.cpt-logo { clip-path: circle(50%); }
.cpt-ring { fill: none; stroke: #fff; stroke-width: 1.5; }
/* One hover target per team, so the card appears over the photo as readily as
   over the abbreviation beneath it. */
.cpt-mark { cursor: default; }
.cpt-mark:hover .cpt-dot, .cpt-mark:hover .cpt-ring { stroke: var(--ink); stroke-width: 2; }
/* Sits below a logo on the chart background, so it needs the dark ink fill the
   on-circle label (white on colour) must not use. */
.cpt-lbl { fill: var(--ink); font-size: 9px; font-weight: 700; }
/* The plain-words label at each end of an axis, naming what more of that metric
   means. A white stroke drawn under the fill keeps them legible over gridlines
   and dots. Shared by both charts. */
.cquad {
  fill: var(--dim); font-size: 11px; font-weight: 700;
  paint-order: stroke; stroke: #fff; stroke-width: 3px; stroke-linejoin: round;
}
/* Top-level tabs: this season's report, versus the league's whole history. Same
   progressive-enhancement rule as the standings selector -- both panes are in the
   page and the buttons only toggle which shows, so with scripting off the current
   season still reads top to bottom. */
.tabs { display: flex; margin: 0 0 .5rem; border-bottom: 1px solid var(--line); }
.tabs button {
  font: inherit; font-size: .92rem; font-weight: 600; line-height: 1.3;
  padding: .5rem .9rem; border: none; background: none; color: var(--dim);
  cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px;
}
.tabs button.on { color: var(--ink); border-bottom-color: var(--ink); }
/* The first heading in a pane has no preceding content to be spaced away from. */
.tabpane > h2:first-child { margin-top: 1.25rem; }
/* Accolades. Named for the achievement rather than reusing the verdict pills:
   a champion is not "clinched", and a reader who learns the colours in one
   section should not have them mean something else in another. */
.pill.champ { background: var(--top-bg); color: var(--top); }
.pill.runner { background: var(--bye-bg); color: var(--bye); }
.pill.four { background: var(--good-bg); color: var(--good); }
.pill.berth { background: var(--panel); color: var(--dim); }
/* One line, never wrapping: a champion's four badges stacked made every row a
   different height, and a table whose rows jump around is hard to scan down. */
.pills { display: inline-flex; flex-wrap: nowrap; gap: .2rem; }
td.acc, th.acc { white-space: nowrap; text-align: left; }
/* A badge explains itself at once on hover or focus. A native `title` tooltip
   needs the pointer held still for a second or two, which reads as broken. */
.pills .pill { cursor: help; position: relative; outline: none; }
.hintbox {
  display: none; position: absolute; left: 50%; transform: translateX(-50%);
  top: 1.55rem; z-index: 6; background: var(--ink); color: #fff;
  padding: .3rem .55rem; border-radius: 6px; font-size: .72rem; font-weight: 400;
  white-space: nowrap; letter-spacing: 0; text-transform: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .28);
}
.pills .pill:hover .hintbox, .pills .pill:focus .hintbox { display: block; }
.pills .pill:focus { box-shadow: 0 0 0 2px var(--ink); }
/* Spelled out once under the table, because nothing on screen advertises that a
   badge can be hovered -- and no tooltip works in print or in an email client. */
.legend { color: var(--dim); font-size: .74rem; margin: .5rem 0 0; line-height: 2; }
.legend .pill { margin-right: .15rem; }
/* Sortable headings. The arrow is drawn on the sorted column only, so the header
   row stays quiet until something is actually sorted by hand. */
th.sort { cursor: pointer; user-select: none; }
th.sort:hover { color: var(--ink); }
th.sort.sorted { color: var(--ink); }
/* The non-breaking space keeps the arrow welded to the last word of the heading.
   With an ordinary space it wrapped onto a line of its own under any two-word
   heading, reading as a stray mark rather than a marker on the column. The
   heading itself is still free to wrap. */
th.sort.sorted[data-dir="desc"]::after { content: "\\00a0\\2193"; }
th.sort.sorted[data-dir="asc"]::after { content: "\\00a0\\2191"; }
/* One all-time view per scope; the selector swaps which is shown, and each
   carries both its team table and its manager table so they cannot disagree. */
.at-view[hidden] { display: none; }
.at-view h3 { font-size: 1.05rem; margin: 2.25rem 0 .35rem; font-weight: 600; }
/* The weight panel: folded away by default, because the presets answer the
   question for almost everybody and four sliders were the wrong first impression.
   A native disclosure element gives the collapse, the keyboard handling and the
   no-JS fallback. */
/* A quiet link, not a panel. It sits at the right of the tools row and opens as a
   popover anchored to itself -- the controls were competing with the table for
   attention, and reaching for them should not shove the table down the page. */
.weights { margin-left: auto; position: relative; }
.weights summary {
  cursor: pointer; font-size: .78rem; font-weight: 600; color: var(--dim);
  list-style: none; white-space: nowrap; padding: .25rem 0;
}
.weights summary:hover { color: var(--ink); }
.weights summary::-webkit-details-marker { display: none; }
.weights summary::before { content: "\\25B8 "; }
.weights[open] summary::before { content: "\\25BE "; }
.weights[open] summary { color: var(--ink); }
.wbody {
  position: absolute; right: 0; top: 1.7rem; z-index: 8; width: max-content;
  max-width: min(46rem, 90vw); padding: .6rem .8rem .8rem; background: #fff;
  border: 1px solid var(--line); border-radius: 6px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, .12);
}
.presets { display: flex; flex-wrap: wrap; gap: .15rem 1.25rem; margin: .5rem 0 .25rem; }
.preset {
  display: flex; align-items: baseline; gap: .4rem; font-size: .82rem;
  cursor: pointer; white-space: nowrap;
}
.preset .dim { font-size: .76rem; }
.wbody .controls { margin: .5rem 0 0; }
/* `display: flex` on .controls outranks the `hidden` attribute's display:none, so
   the weight sliders leaked into view while a named preset was selected. The
   id+attribute selector wins it back. The SOS chart hit this same trap. */
#at-custom[hidden] { display: none; }
/* A small circled question mark, standing in for the ratio that used to be
   printed beside every preset. */
.hint {
  display: inline-flex; align-items: center; justify-content: center;
  width: 1rem; height: 1rem; border-radius: 50%; border: 1px solid var(--line);
  color: var(--dim); font-size: .62rem; font-weight: 700; cursor: help;
  position: relative; outline: none; margin-left: .1rem;
}
.hint:hover, .hint:focus { border-color: var(--ink); color: var(--ink); }
.hint:hover .hintbox, .hint:focus .hintbox { display: block; }
.hint .hintbox { white-space: normal; width: 17rem; text-align: left; }
.at-tools { display: flex; align-items: center; gap: .6rem; margin: 0 0 .6rem; }
.at-tools input[type=search] {
  font: inherit; font-size: .82rem; padding: .25rem .5rem; width: 20rem;
  max-width: 100%; border: 1px solid var(--line); border-radius: 4px;
  color: var(--ink); background: #fff;
}
.at-tools input[type=search]:focus { outline: none; border-color: var(--ink); }
.at-tools > .dim { font-size: .76rem; }
/* `hidden` has to beat the table display roles it would otherwise lose to. */
tr[hidden], tbody[hidden] { display: none; }
.at-chart-view[hidden], .at-table-view[hidden] { display: none; }
/* A quiet checkbox tucked beside the weights link. */
.at-live {
  display: inline-flex; align-items: center; gap: .3rem; font-size: .78rem;
  color: var(--dim); white-space: nowrap; cursor: pointer;
}
.at-live:hover { color: var(--ink); }
/* The parking spot the pickers are moved out of; never shown itself. */
.at-axes { display: none; }
.at-pick {
  display: inline-flex; align-items: center; gap: .35rem;
  font-size: .8rem; color: var(--dim);
}
.at-pick select { font: inherit; font-size: .8rem; }
/* The scatter, laid out with the pickers ON its axes -- Y down the left, X
   centred underneath -- the same arrangement the season chart uses. Positioned so
   the hover card can be placed over it by hand. */
.at-chart-view {
  position: relative;
  display: grid; grid-template-columns: auto 1fr; grid-template-rows: 1fr auto;
  align-items: center; gap: .35rem .5rem;
}
/* display:grid outranks the hidden attribute; without this the chart and its
   pickers would show in table view. Same trap as #sos-chart-view. */
.at-chart-view[hidden] { display: none; }
#at-pick-y { grid-column: 1; grid-row: 1; justify-self: end; }
/* `justify-self`, not `text-align`: the picker is a flex box sized to its
   contents, so centring its text does nothing -- the box itself has to be
   centred in the column. */
#at-pick-x { grid-column: 2; grid-row: 2; justify-self: center; }
svg.at-chart {
  /* Capped at the viewBox width so the drawing is never scaled up. `width: 100%`
     alone stretched a 660-unit chart across a 1050px column, multiplying every
     dot and label by 1.6 -- the dots read as a solid mass and the four-letter
     abbreviations spilled out of them, which looked like the radius being wrong
     rather than the whole canvas being magnified. */
  /* Centred in its column so the X picker, which centres on the column, lines up
     with the middle of the plot rather than sitting slightly off it. */
  grid-column: 2; grid-row: 1; margin: 0 auto;
  width: 100%; max-width: 900px; height: auto; display: block;
  font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
/* A soft frame around the plot so the scatter reads as one figure. */
.atframe { fill: none; stroke: var(--line); stroke-width: 1; }
/* Column definitions, below the tables. Laid out in columns so five one-line
   glosses read as a key rather than as prose the reader has to get past. */
.at-legend {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: .3rem 1.5rem; margin: 1.25rem 0 0; padding-top: .75rem;
  border-top: 1px solid var(--line); font-size: .78rem;
}
.at-legend dt { font-weight: 600; }
.at-legend dd { margin: 0; color: var(--dim); }
.atdot { cursor: default; }
.atdot circle { stroke: #fff; stroke-width: 1; }
.atdot:hover circle { stroke: var(--ink); stroke-width: 2; }
/* An in-progress season is not rankable, so it is drawn as provisional. */
.atdot-live circle { opacity: .55; stroke-dasharray: 2 2; stroke: var(--ink); }
/* font-size is set per dot so a four-letter abbreviation still fits; see drawChart. */
.atdot-lbl { fill: #fff; font-weight: 700; pointer-events: none; }
.at-tip {
  position: absolute; transform: translate(-50%, -100%); z-index: 7;
  background: var(--ink); color: #fff; padding: .3rem .55rem; border-radius: 6px;
  font-size: .74rem; line-height: 1.35; white-space: nowrap; pointer-events: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .28);
}
.at-none { color: var(--dim); font-size: .82rem; margin: .4rem 0 0; }
.wbody .controls .dim { min-width: 2.6rem; display: inline-block; }
/* The accolade control has nothing to scale in the regular-season scope. */
.wbody .controls label.off { opacity: .4; }
.wbody button {
  font: inherit; font-size: .78rem; padding: .15rem .6rem; cursor: pointer;
  border: 1px solid var(--line); background: #fff; color: var(--dim);
}
/* The rating is the column the table exists for, so it is the only bold one. */
td.rating { font-weight: 700; }
td.owner { color: var(--dim); font-size: .8rem; white-space: nowrap; }
footer { margin-top: 3rem; color: var(--dim); font-size: .78rem; }
"""


# SOS comes out of the engine as a ratio to the average schedule (1.0 = average).
# For display it is recentred on 50 and the spread widened, so the league opens
# into a legible gap instead of everyone crowding one number: 50 is an average
# schedule, and the gain sets how far a tougher or easier one moves from it. The
# same two constants drive the interactive script, injected into it below so the
# static and live numbers cannot disagree.
SOS_CENTER = 50
SOS_GAIN = 400


def _sos_display(ratio):
    return None if ratio is None else round(SOS_CENTER + (ratio - 1.0) * SOS_GAIN, 1)


# Progressive enhancement for the strength section, all from data already on each
# row -- no round-trip, no assets. The slider re-blends SOS, and a Table/Chart
# toggle draws an inline-SVG scatter whose axes pick any metric. SOS on an axis
# stays live with the slider; the rest are fixed per team. With scripting off the
# static table stands.
STRENGTH_JS = """
(function () {
  var body = document.getElementById('sos-body');
  if (!body) return;
  var section = document.getElementById('sos-section');
  var blend = document.getElementById('sos-blend');
  var label = document.getElementById('sos-blend-label');
  var viewSeg = document.getElementById('sos-view-seg');
  var xsel = document.getElementById('sos-x');
  var ysel = document.getElementById('sos-y');
  var svg = document.getElementById('sos-chart');
  var tableView = document.getElementById('sos-table-view');
  var chartView = document.getElementById('sos-chart-view');
  var rows = Array.prototype.slice.call(body.getElementsByTagName('tr'));

  // Read each row's logo once, now, while the table view is still shown -- the
  // image lives in a CSS class (inlined a single time), so the scatter pulls the
  // data URI off the cell's computed background rather than duplicating it.
  rows.forEach(function (tr) {
    tr._logo = '';
    var el = tr.querySelector('td.name .logo');
    if (el) {
      var m = (getComputedStyle(el).backgroundImage || '').match(/url\\(["']?(data:[^"')]+)["']?\\)/);
      if (m) tr._logo = m[1];
    }
  });

  function num(s) { var v = parseFloat(s); return isNaN(v) ? null : v; }
  function fmtSor(v) { return (v >= 0 ? '+' : '\\u2212') + Math.abs(v).toFixed(3); }
  function refOf(k) { return k === 'sos' ? SOS_CENTER : (k === 'sor' ? 0 : null); }
  // SOS and SOR get a fixed half-span so dragging the slider moves the dots, not
  // the scale -- SOS spans 15..85 about 50, SOR -0.3..0.3 about 0. The rest scale
  // to their data, since they do not move with the controls.
  var FIXED_SPAN = { sos: 35, sor: 0.3 };

  // Gridline spacing per metric. Every one of these reads on sight, so all are
  // labelled with their own value (`abs`) rather than a distance from average --
  // and the number under a dot then matches the number in the table beside it.
  var TICK = {
    sos: { step: 10, mode: 'abs' },
    sor: { step: 0.1, mode: 'abs' },
    wins: { step: 1, mode: 'abs' },
    ppg: { step: 5, mode: 'abs' },
    oppppg: { step: 5, mode: 'abs' },
    pf: { step: 50, mode: 'abs' }
  };

  function tickText(k, v) {
    // Signed as the column shows it -- except at the reference itself, where a
    // "+0.000" claims a direction the value does not have.
    if (k === 'sor') return Math.abs(v) < 1e-9 ? '0.000' : fmtSor(v);
    return String(Math.round(v));
  }

  // Ticks land on multiples of the step, not on offsets from wherever the plotted
  // mean happens to fall -- otherwise Points For reads "259 309 359", and the
  // gridline under a rounded label sits a fraction away from the value it claims.
  //
  // The epsilon is load-bearing: -0.3 / 0.1 is -2.9999999999999996 in binary
  // floating point, so a bare ceil() rounds up and silently loses the tick at the
  // far end of a fixed domain.
  function ticksOf(k, centre, half) {
    var t = TICK[k];
    if (!t) return [];
    var out = [], hi = centre + half;
    for (var v = Math.ceil((centre - half) / t.step - 1e-9) * t.step; v <= hi + 1e-9; v += t.step) {
      out.push(Math.round(v / t.step) * t.step);
    }
    return out;
  }

  // The value of any metric for a team. SOS is recomputed from the blend so it
  // tracks the slider; the rest are read straight off the row -- one source of
  // truth for the number, whether table or chart.
  function metricVal(tr, key, w) {
    if (key === 'sos') {
      var pi = num(tr.getAttribute('data-pi')), ri = num(tr.getAttribute('data-ri'));
      return (pi === null || ri === null) ? null : SOS_CENTER + (w * pi + (1 - w) * ri - 1) * SOS_GAIN;
    }
    return num(tr.getAttribute('data-' + key));
  }

  function updateTable() {
    var w = parseInt(blend.value, 10) / 100;
    rows.forEach(function (tr) {
      var sos = metricVal(tr, 'sos', w);
      tr._s = (sos === null) ? -Infinity : sos;
      var sv = tr.querySelector('.sos-val');
      if (sv) sv.textContent = (sos === null) ? '\\u2014' : sos.toFixed(1);
      var v = metricVal(tr, 'sor', w);
      var sc = tr.querySelector('.sos-sor');
      if (sc) {
        if (v === null) { sc.textContent = '\\u2014'; sc.className = 'num sos-sor'; }
        else { sc.textContent = fmtSor(v); sc.className = 'num sos-sor ' + (v >= 0 ? 'better' : 'worse'); }
      }
    });
    rows.sort(function (a, b) { return b._s - a._s; });
    rows.forEach(function (tr, i) {
      body.appendChild(tr);
      var rk = tr.querySelector('.sos-rank');
      if (rk) rk.textContent = i + 1;
    });
    if (label) label.textContent =
      Math.round(w * 100) + '% points / ' + Math.round((1 - w) * 100) + '% record';
  }

  function mean(a) { return a.reduce(function (s, v) { return s + v; }, 0) / a.length; }

  function drawChart() {
    if (!svg) return;
    var w = parseInt(blend.value, 10) / 100;
    var xk = xsel.value, yk = ysel.value, pts = [];
    rows.forEach(function (tr) {
      var x = metricVal(tr, xk, w), y = metricVal(tr, yk, w);
      if (x === null || y === null) return;
      pts.push({
        x: x, y: y,
        abbr: tr.getAttribute('data-abbr') || '',
        color: tr.getAttribute('data-color') || '#888',
        logo: tr._logo || '',
        team: tr.getAttribute('data-team') || '',
        manager: tr.getAttribute('data-manager') || '',
        record: tr.getAttribute('data-record') || ''
      });
    });
    if (!pts.length) { svg.innerHTML = ''; return; }

    // Centred on the reference rather than fitted to the data. Wins, PPG and the
    // rest are all positive and tightly clustered, so a domain fitted to them
    // pushed the whole league into one corner. SOS and SOR keep a fixed half-span
    // so dragging the slider moves the dots, not the scale.
    function centre(k, vals) {
      var r = refOf(k);
      if (r !== null) return r;
      // Snapped to the nearest gridline. A rule drawn at the raw average sits
      // between two ticks and reads as a third, unlabelled one -- at 119.6 PPG it
      // looks like a value the chart never names. The span is measured *after*
      // this, so moving the centre cannot push a dot outside the frame.
      var m = mean(vals), t = TICK[k];
      return t ? Math.round(m / t.step) * t.step : m;
    }
    function span(k, vals, c) {
      if (FIXED_SPAN[k] !== undefined) return FIXED_SPAN[k];
      var m = 0;
      vals.forEach(function (v) { m = Math.max(m, Math.abs(v - c)); });
      if (!m) m = Math.abs(c) || 1;
      return m * 1.15;
    }
    var xv = pts.map(function (p) { return p.x; });
    var yv = pts.map(function (p) { return p.y; });
    var cx0 = centre(xk, xv), cy0 = centre(yk, yv);
    var xm = span(xk, xv, cx0), ym = span(yk, yv, cy0);

    var xt = ticksOf(xk, cx0, xm), yt = ticksOf(yk, cy0, ym);
    // mL clears the widest tick number ("-0.300", "1.000"); mB clears one line of
    // them. Nothing else lives in the margins now the axis phrases are gone.
    var W = 900, H = 450, mR = 14, mT = 14, mL = 44, mB = 22;
    // The plotted area is inset from the frame by enough to hold a whole mark, so
    // a team sitting exactly at the end of a fixed domain -- SOS and SOR have no
    // padding by design, and a real league does reach their limits -- is drawn
    // inside the box rather than hanging off it. The bottom inset is deeper
    // because the abbreviation hangs below the dot.
    var pX = 12, pT = 12, pB = 22;
    // Clamped into that inset box, because a fixed domain can be overshot: SOR is
    // pinned to -0.3..0.3 so the slider moves the dots and not the scale, and a
    // real team has come in at +0.572. Without this it is drawn off the chart
    // entirely -- a team good enough to leave the axis vanished from it.
    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
    function SX(v) {
      return clamp(mL + pX + ((v - cx0) + xm) / (2 * xm) * (W - mL - mR - 2 * pX),
                   mL + pX, W - mR - pX);
    }
    function SY(v) {
      return clamp(H - mB - pB - ((v - cy0) + ym) / (2 * ym) * (H - mT - mB - pT - pB),
                   mT + pT, H - mB - pB);
    }
    var e = [];
    e.push('<rect x="' + mL + '" y="' + mT + '" width="' + (W - mL - mR)
      + '" height="' + (H - mT - mB) + '" rx="4" class="atframe"/>');
    // Gridlines first, so the axis rules, the dots and the labels sit on top. A
    // gridline is skipped where a line is already drawn -- down the centre and at
    // the two ends -- since a dashed line over a solid one reads as a thicker rule.
    function spare(pos, centrePos, lo, hi) {
      return Math.abs(pos - centrePos) < 1 || pos - lo < 1 || hi - pos < 1;
    }
    xt.forEach(function (v) {
      var x = SX(v);
      if (!spare(x, SX(cx0), mL, W - mR)) {
        e.push('<line x1="' + x + '" y1="' + mT + '" x2="' + x + '" y2="' + (H - mB) + '" class="cref"/>');
      }
      e.push('<text x="' + x + '" y="' + (H - mB + 13) + '" class="ctick" text-anchor="middle">'
        + tickText(xk, v) + '</text>');
    });
    yt.forEach(function (v) {
      var y = SY(v);
      if (!spare(y, SY(cy0), mT, H - mB)) {
        e.push('<line x1="' + mL + '" y1="' + y + '" x2="' + (W - mR) + '" y2="' + y + '" class="cref"/>');
      }
      e.push('<text x="' + (mL - 6) + '" y="' + (y + 4) + '" class="ctick" text-anchor="end">'
        + tickText(yk, v) + '</text>');
    });
    // The two axis rules through the centre: average schedule, par record.
    e.push('<line x1="' + SX(cx0) + '" y1="' + mT + '" x2="' + SX(cx0) + '" y2="' + (H - mB) + '" class="cax"/>');
    e.push('<line x1="' + mL + '" y1="' + SY(cy0) + '" x2="' + (W - mR) + '" y2="' + SY(cy0) + '" class="cax"/>');
    var R = 9;  // the all-time chart's radius, so the two scatters match
    pts.forEach(function (p, i) {
      var cx = SX(p.x), cy = SY(p.y);
      // Same geometry as the all-time chart -- one radius, one ring, one label
      // size -- so the two scatters read as the same kind of figure. A photo
      // cannot carry legible text on top of it, so where one exists the
      // abbreviation goes just below the dot instead of inside it.
      // Grouped so the whole mark is one hover target, with its index to look the
      // team up on. A four-letter dot cannot say whose team it is or its record.
      e.push('<g class="cpt-mark" data-i="' + i + '">');
      if (p.logo) {
        // --logos inlined this team's image: it fills the dot, clipped round.
        e.push('<image class="cpt-logo" href="' + p.logo + '" x="' + (cx - R) + '" y="' + (cy - R) + '" width="' + (2 * R) + '" height="' + (2 * R) + '" preserveAspectRatio="xMidYMid slice"/>');
        e.push('<circle cx="' + cx + '" cy="' + cy + '" r="' + R + '" class="cpt-ring"/>');
        // The label is wider than the dot it sits under, so it is kept inside the
        // frame on its own account -- a four-letter abbreviation ("BUTT") centred
        // on a dot at the edge hangs out past the border even when the dot does
        // not. Measured: uppercase at this weight and size runs ~7px a character,
        // so half the string is 3.6 each, rounded up rather than down.
        var half = p.abbr.length * 3.6;
        e.push('<text x="' + clamp(cx, mL + half + 2, W - mR - half - 2) + '" y="' + (cy + R + 8) + '" class="cpt-lbl" text-anchor="middle">' + p.abbr + '</text>');
      } else {
        var fs = p.abbr.length > 3 ? 5.5 : p.abbr.length > 2 ? 7 : 8.5;
        e.push('<circle cx="' + cx + '" cy="' + cy + '" r="' + R + '" fill="' + p.color + '" class="cpt-dot"/>');
        e.push('<text x="' + cx + '" y="' + (cy + fs / 3) + '" class="cpt" font-size="' + fs + '" text-anchor="middle">' + p.abbr + '</text>');
      }
      e.push('</g>');
    });
    // No plain-words label at the axis ends: the numbers say where a dot sits, and
    // what the metric means now lives on the `?` beside its picker, where it can
    // be a sentence instead of two words squeezed against the frame.
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.innerHTML = e.join('');

    // Hover gives the three things a four-letter dot cannot: the team's full name,
    // who runs it, and its record. Positioned by hand rather than left to a native
    // tooltip, which takes a second or two and reads as nothing happening.
    var tip = document.getElementById('sos-tip');
    if (!tip) return;
    svg.querySelectorAll('g.cpt-mark').forEach(function (g) {
      g.addEventListener('mouseenter', function () {
        var p = pts[parseInt(g.getAttribute('data-i'), 10)];
        tip.innerHTML = '<b>' + p.team + '</b><br>' + p.manager
          + (p.record ? ' &middot; ' + p.record : '');
        tip.hidden = false;
        // Anchored on the dot, not the group: the group's box also covers the
        // label below it, which is wider and -- when clamped away from the frame
        // edge -- off to one side, so its centre is not the team's position.
        var dot = g.querySelector('image, circle');
        var box = (dot || g).getBoundingClientRect();
        // Measured against the tip's own offset parent, not the svg, which is
        // centred inside it (see the all-time chart for the same trap).
        var host = (tip.offsetParent || svg).getBoundingClientRect();
        tip.style.left = (box.left - host.left + box.width / 2) + 'px';
        tip.style.top = (box.top - host.top - 6) + 'px';
      });
      g.addEventListener('mouseleave', function () { tip.hidden = true; });
    });
  }

  function charting() {
    var on = viewSeg && viewSeg.querySelector('button.on');
    return !!on && on.getAttribute('data-view') === 'chart';
  }

  function showView() {
    var chart = charting();
    if (section) section.className = chart ? 'charting' : '';
    if (tableView) tableView.hidden = chart;
    if (chartView) chartView.hidden = !chart;
    if (chart) drawChart();
  }

  function update() { updateTable(); if (charting()) drawChart(); }

  // The `?` beside a picker explains whichever metric is chosen, read off that
  // option's own gloss so the two can never disagree.
  function describe(sel) {
    if (!sel) return;
    var hint = document.getElementById(sel.id + '-hint');
    if (!hint) return;
    var gloss = sel.options[sel.selectedIndex].getAttribute('data-gloss') || '';
    hint.querySelector('.hintbox').textContent = gloss;
    hint.setAttribute('aria-label', gloss);
  }

  blend.addEventListener('input', update);
  if (viewSeg) viewSeg.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-view]');
    if (!b) return;
    viewSeg.querySelectorAll('button').forEach(function (x) {
      if (x === b) x.classList.add('on'); else x.classList.remove('on');
    });
    showView();
  });
  if (xsel) xsel.addEventListener('change', function () { describe(xsel); drawChart(); });
  if (ysel) ysel.addEventListener('change', function () { describe(ysel); drawChart(); });
  describe(xsel);
  describe(ysel);
  updateTable();
})();
"""


# The standings view switcher: buttons on the section header flip between the
# overall table and each division's own. All views are in the page; the button
# just toggles which is shown, so with scripting off the default overall stands.
STANDINGS_JS = """
(function () {
  var seg = document.getElementById('std-seg');
  if (!seg) return;
  var views = document.querySelectorAll('.std-view');
  seg.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-view]');
    if (!b) return;
    var want = b.getAttribute('data-view');
    views.forEach(function (el) { el.hidden = el.getAttribute('data-view') !== want; });
    seg.querySelectorAll('button').forEach(function (x) {
      if (x === b) x.classList.add('on'); else x.classList.remove('on');
    });
  });
})();
"""


TABS_JS = """
(function () {
  var bar = document.getElementById('tabs');
  if (!bar) return;
  var panes = document.querySelectorAll('.tabpane');
  bar.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-tab]');
    if (!b) return;
    var want = b.getAttribute('data-tab');
    panes.forEach(function (el) { el.hidden = el.getAttribute('data-tab') !== want; });
    bar.querySelectorAll('button').forEach(function (x) {
      if (x === b) x.classList.add('on'); else x.classList.remove('on');
    });
  });
})();
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


def _standings_row(position, team, abbreviations, logo_class, cut=False):
    status = pretty_print.display_status(team)
    label = pretty_print.status_label(team)
    cls = ' class="cut"' if cut else ""
    return (
        f'<tr{cls}><td class="num">{position}</td>'
        f"<td>{team_mark(team['team_name'], abbreviations, logo_class)}"
        f"{esc(team['team_name'])}</td>"
        f'<td class="num">{team["wins"]}-{team["losses"]}</td>'
        f'<td class="num">{team["points_for"]:.1f}</td>'
        f'<td><span class="pill {status}">{esc(label)}</span></td></tr>'
    )


def _standings_table(teams, abbreviations, logo_class, cut_at=None):
    rows = "".join(
        _standings_row(i, t, abbreviations, logo_class, cut=(i == cut_at))
        for i, t in enumerate(teams, 1)
    )
    return (
        '<table><thead><tr><th class="num">#</th><th>Team</th>'
        '<th class="num">Record</th><th class="num">Points for</th>'
        f"<th>Status</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def render_standings(
    standings, league, abbreviations=None, logo_class=None,
    divisions=None, division_names=None
):
    """The standings section, with a view selector on the header.

    Overall (the seed-ordered full table) is the default. Extra views become
    square buttons beside it: one per division, then the #1-seed and wildcard
    races when those are still live. All views are in the page; the buttons only
    toggle which shows, so with scripting off the default overall table stands.
    """
    spots = league["playoff_spots"]
    overall = _standings_table(standings, abbreviations, logo_class, cut_at=spots)
    cutnote = (
        f"{spots} playoff spots league-wide; division winners are seeded first."
        if divisions
        else f"The rule marks the playoff cut line: {spots} spots."
    )
    overall_view = f'{overall}<p class="cutnote">{cutnote}</p>'

    # Views beyond the overall table, each a (label, id, inner) that becomes a
    # button. Division ids arrive as ints; JSON turns division_names keys into
    # strings, so look both up.
    extra = []
    if divisions:
        names = division_names or {}
        ordered, seen, groups = [], set(), {}
        for team in standings:
            did = divisions.get(team["team_name"])
            groups.setdefault(did, []).append(team)
            if did not in seen:
                seen.add(did)
                ordered.append(did)
        for k, did in enumerate(ordered):
            teams = sorted(groups[did], key=lambda t: (-t["wins"], -t["points_for"]))
            title = names.get(did) or names.get(str(did)) or f"Division {did}"
            extra.append(
                (title, f"d{k}", _standings_table(teams, abbreviations, logo_class))
            )

    # #1-seed race: only while undecided (nobody has clinched it, someone can).
    if not any(t.get("top_seed") == "clinched" for t in standings):
        contenders = [t for t in standings if t.get("top_seed") == "alive"]
        if contenders:
            extra.append(
                ("#1 Seed", "seed", _race_table(contenders, abbreviations, logo_class))
            )

    # Wildcard race: teams still alive for a spot that have not clinched a division.
    if divisions:
        contenders = [
            t
            for t in standings
            if t.get("verdict") == "alive" and t.get("division_winner") != "clinched"
        ]
        if contenders:
            n = spots - len(set(divisions.values()))
            note = (
                f'<p class="note">{n} wildcard spot{"s" if n != 1 else ""} '
                "for teams that do not win their division.</p>"
            )
            extra.append(
                ("Wildcard", "wild", note + _race_table(contenders, abbreviations, logo_class))
            )

    if not extra:
        return f"<h2>Standings</h2>\n{overall_view}"

    buttons = ['<button data-view="overall" class="on">Overall</button>']
    views = [f'<div class="std-view" data-view="overall">{overall_view}</div>']
    for label, view_id, inner in extra:
        buttons.append(f'<button data-view="{view_id}">{esc(label)}</button>')
        views.append(f'<div class="std-view" data-view="{view_id}" hidden>{inner}</div>')
    return (
        f'<h2>Standings <span class="seg" id="std-seg">{"".join(buttons)}</span></h2>\n'
        f'{"".join(views)}'
        f"<script>{STANDINGS_JS}</script>"
    )


def _race_table(teams, abbreviations, logo_class):
    """A Team/Record/Points table of race contenders (no status, no rank)."""
    rows = "".join(
        f"<tr><td>{team_mark(t['team_name'], abbreviations, logo_class)}"
        f"{esc(t['team_name'])}</td>"
        f'<td class="num">{t["wins"]}-{t["losses"]}</td>'
        f'<td class="num">{t["points_for"]:.1f}</td></tr>'
        for t in teams
    )
    return (
        '<table><thead><tr><th>Team</th><th class="num">Record</th>'
        '<th class="num">Points for</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def render_matchups(matchups, league, abbreviations=None, logo_class=None):
    if not matchups:
        return '<h2>Next Week</h2>\n<p class="empty">No games left to play.</p>'
    rows = "".join(
        f"<tr><td>{team_mark(m['team1'], abbreviations, logo_class)}{esc(m['team1'])}</td>"
        f'<td class="empty">vs</td>'
        f"<td>{team_mark(m['team2'], abbreviations, logo_class)}{esc(m['team2'])}</td></tr>"
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


def _pct(value):
    """A win percentage as .541, or a dash when there is nothing to show."""
    return "&mdash;" if value is None else f"{value:.3f}"


def _ppg(value):
    return "&mdash;" if value is None else f"{value:.1f}"


def _attr(value):
    """A data-attribute number, or empty when there is nothing to carry."""
    return "" if value is None else f"{value:.6f}"


def _sor_cell(value):
    if value is None:
        return '<td class="num sos-sor">&mdash;</td>'
    sign = "+" if value >= 0 else "−"
    css = "better" if value >= 0 else "worse"
    return f'<td class="num sos-sor {css}">{sign}{abs(value):.3f}</td>'


def _schedule_tooltip(display, breakdown, current_week, abbreviations):
    """A number that hovers to a Week/Opp/PPG grid of the games behind it.

    A CSS-only tooltip (no script), so a mailed or printed page shows the same
    breakdown as a stacked list. Shared by the in-season "to come" number and the
    preseason projected schedule.
    """
    cells = [
        '<span class="tiphead">Week</span>'
        '<span class="tiphead">Opp</span>'
        '<span class="tiphead">PPG</span>'
    ]
    for d in breakdown:
        cells.append(
            f'<span>{current_week + 1 + d["week_offset"]}</span>'
            f'<span>{esc(monogram(d["opponent"], abbreviations))}</span>'
            f'<span>{_ppg(d["value"])}</span>'
        )
    return (
        f'<span class="tip" tabindex="0">{display}'
        f'<span class="tipbox">{"".join(cells)}</span></span>'
    )


def _to_come_cell(row, current_week, abbreviations):
    if row["sos_remaining"] is None:
        return '<td class="num">&mdash;</td>'
    tip = _schedule_tooltip(
        _ppg(row["sos_remaining"]), row["remaining"], current_week, abbreviations
    )
    return f'<td class="num">{tip}</td>'


# Metrics the scatter's two axes can pick from. SOS is live (recomputed from the
# slider); the rest are fixed per team, carried as row data.
# Each axis metric with a one-line gloss, which rides on the <option> and is shown
# by the `?` beside the picker. One table so the name and the explanation cannot
# drift apart.
SEASON_METRICS = [
    ("sos", "SOS", "How hard a team&rsquo;s opponents have been &mdash; 50 is average"),
    (
        "sor",
        "SOR",
        "How its win rate compares with what an average team would manage "
        "on the same schedule",
    ),
    ("wins", "Wins", "Games won so far"),
    ("ppg", "PPG", "Its own points per game"),
    ("oppppg", "Opp PPG", "Points per game its opponents average"),
    ("pf", "Points For", "Total points scored so far"),
]
CHART_METRICS = [(key, label) for key, label, _ in SEASON_METRICS]


def _axis_options(metrics, selected):
    """<option>s for an axis picker, each carrying its own one-line gloss.

    The gloss travels on the option rather than sitting in a second table in the
    script, so the `?` beside the picker always describes the metric actually
    chosen and the two cannot drift apart.
    """
    return "".join(
        f'<option value="{key}" data-gloss="{gloss}"'
        f'{" selected" if key == selected else ""}>{label}</option>'
        for key, label, gloss in metrics
    )


def _axis_hint(axis_id):
    """The `?` beside an axis picker; its text is filled in by the chart script."""
    return (
        f'<span class="hint" id="{axis_id}-hint" tabindex="0">?'
        f'<span class="hintbox"></span></span>'
    )


def _metric_options(selected):
    return _axis_options(SEASON_METRICS, selected)


def render_strength(
    weekly_scores, remaining_matchups=None, abbreviations=None, current_week=0,
    standings=None, logo_class=None, managers=None
):
    rows = strength.strength_table(weekly_scores, remaining_matchups)
    if not rows:
        return ""
    any_remaining = any(row["sos_remaining"] is not None for row in rows)
    # Per-team season figures the chart's fixed axes need, keyed by name.
    stats = {team["team_name"]: team for team in (standings or [])}
    managers = managers or {}

    body = []
    for position, row in enumerate(rows, 1):
        display = _sos_display(row["sos"])
        sos = "&mdash;" if display is None else f"{display}"
        ahead = (
            _to_come_cell(row, current_week, abbreviations) if any_remaining else ""
        )
        team = stats.get(row["name"], {})
        points_for = team.get("points_for")
        own_ppg = (
            round(points_for / current_week, 2)
            if points_for is not None and current_week
            else None
        )
        # Everything an axis might plot rides on the row: the normalised SOS
        # components (SOS recomputed live from the slider), the SOR against the
        # average team, and the season figures (fixed). The chart and the table
        # read the same numbers.
        body.append(
            f'<tr data-pi="{_attr(row["points_index"])}" data-ri="{_attr(row["record_index"])}"'
            f' data-sor="{_attr(row["sor"])}"'
            f' data-wins="{_attr(team.get("wins"))}" data-ppg="{_attr(own_ppg)}"'
            f' data-pf="{_attr(points_for)}" data-oppppg="{_attr(row["opp_ppg"])}"'
            f' data-abbr="{esc(monogram(row["name"], abbreviations))}"'
            f' data-color="{monogram_colour(row["name"])}"'
            # For the chart's hover card, which has only a four-letter dot to
            # work with. Full manager names, as in the all-time table.
            f' data-team="{esc(row["name"])}"'
            f' data-manager="{esc(_manager_label(managers.get(row["name"], [])))}"'
            f' data-record="{_standings_record(team)}">'
            f'<td class="num sos-rank">{position}</td>'
            f'<td class="name">{team_mark(row["name"], abbreviations, logo_class)}'
            f'{esc(row["name"])}</td>'
            f'<td class="num total sos-val">{sos}</td>'
            f'<td class="num">{_ppg(row["opp_ppg"])}</td>'
            f'<td class="num">{_pct(row["opp_win_pct"])}</td>'
            f"{ahead}"
            f"{_sor_cell(row['sor'])}</tr>"
        )

    ahead_head = '<th class="num">To&nbsp;come</th>' if any_remaining else ""
    return f"""<h2>Strength of Schedule &amp; Record</h2>
<p class="lede"><strong>SOS</strong> rates how hard a team's opponents are against the league
average: <strong>50 is an average schedule</strong>, above it tougher and below it easier,
blending how much those opponents score with how often they win{" (and the 'to&nbsp;come' column is how hard the schedule still ahead is)" if any_remaining else ""}.
<strong>SOR</strong> is strength of record: how a team's own win rate compares with what an
average league team would manage against the same schedule &mdash; green means it has done better
than its schedule would give that team, red worse. Drag the weighting to re-rank; switch to
<strong>Chart</strong> for a scatter of any two metrics. With no browser the table shows a
50/50 blend against an average team.</p>
<div id="sos-section">
<div class="controls">
  <span class="seg" id="sos-view-seg"><button data-view="table" class="on">Table</button><button data-view="chart">Chart</button></span>
  <label>SOS weighting
    <span class="dim">record</span>
    <input type="range" id="sos-blend" min="0" max="100" value="50">
    <span class="dim">points</span>
    <span id="sos-blend-label" class="dim">50% points / 50% record</span>
  </label>
</div>
<div id="sos-table-view">
<table class="grid">
<thead><tr><th class="num">#</th><th class="name">Team</th>
<th class="num total">SOS</th><th class="num">Opp&nbsp;PPG</th><th class="num">Opp&nbsp;Win%</th>
{ahead_head}<th class="num">SOR</th></tr></thead>
<tbody id="sos-body">{''.join(body)}</tbody>
</table>
</div>
<div id="sos-chart-view" hidden>
<div class="chart-y"><select id="sos-y" aria-label="Y axis metric">{_metric_options("sor")}</select>{_axis_hint("sos-y")}</div>
<svg id="sos-chart" role="img" aria-label="Scatter of two chosen metrics per team"></svg>
<div class="at-tip" id="sos-tip" hidden></div>
<div class="chart-x"><select id="sos-x" aria-label="X axis metric">{_metric_options("sos")}</select>{_axis_hint("sos-x")}</div>
</div>
</div>
<script>var SOS_CENTER={SOS_CENTER},SOS_GAIN={SOS_GAIN};{STRENGTH_JS}</script>"""


def render_preseason_strength(projected_ppg, matchups, abbreviations=None, logo_class=None):
    """SOS before a game is played, from projected opponent scoring.

    No record component and no SOR yet, so this is a plainer, static table than
    the in-season one -- and it is flagged low-confidence, because it rests
    entirely on projections that barely predict.
    """
    rows = strength.preseason_strength(projected_ppg, matchups)
    if not rows:
        return ""

    body = []
    for position, row in enumerate(rows, 1):
        display = _sos_display(row["sos"])
        sos = "&mdash;" if display is None else f"{display}"
        cell = (
            '<td class="num">&mdash;</td>'
            if row["opp_ppg"] is None
            else f'<td class="num">{_schedule_tooltip(_ppg(row["opp_ppg"]), row["schedule"], 0, abbreviations)}</td>'
        )
        body.append(
            f'<tr><td class="num">{position}</td>'
            f'<td class="name">{team_mark(row["name"], abbreviations, logo_class)}'
            f'{esc(row["name"])}</td>'
            f'<td class="num total">{sos}</td>{cell}</tr>'
        )

    return f"""<h2>Strength of Schedule &mdash; Preseason</h2>
<p class="lede"><strong>Before any game is played</strong>, this ranks schedules by how strong each
team's opponents <em>project</em> to score over the season &mdash; 50 is an average schedule,
above it tougher. &#9888; It rests entirely on ESPN's preseason projections, which are a
<strong>weak predictor</strong> (measured correlation with real scoring about 0.07, because a
draft equalises rosters), so read it as a rough hint, not a verdict. Hover a number for the
week-by-week opponents.</p>
<table class="grid">
<thead><tr><th class="num">#</th><th class="name">Team</th>
<th class="num total">SOS</th><th class="num">Proj&nbsp;opp&nbsp;PPG</th></tr></thead>
<tbody>{''.join(body)}</tbody>
</table>"""


# Everything the all-time tab needs to re-rank is already on each row as a data
# attribute, so the sliders and the scope selector work with no round trip and no
# duplicated numbers. With scripting off, the default-scope tables stand exactly as
# rendered -- which is the same rule the standings selector and the SOS slider follow.
ALL_TIME_JS = """
(function () {
  var seg = document.getElementById('at-seg');
  var weights_el = document.getElementById('at-weights');
  if (!seg || !weights_el) return;
  var presets = document.getElementById('at-presets');
  var custom = document.getElementById('at-custom');
  var presetName = document.getElementById('at-preset-name');
  var views = Array.prototype.slice.call(document.querySelectorAll('.at-view'));
  var KEYS = ['strength', 'record', 'scoring'];
  var inputs = {};
  KEYS.concat(['hardware']).forEach(function (k) {
    inputs[k] = document.getElementById('at-w-' + k);
  });
  var defaults = {};
  Object.keys(inputs).forEach(function (k) { defaults[k] = inputs[k].value; });

  function num(el, attr) { return parseFloat(el.getAttribute(attr)) || 0; }

  function weights() {
    var raw = {}, total = 0;
    KEYS.forEach(function (k) {
      raw[k] = parseFloat(inputs[k].value) || 0;
      total += raw[k];
    });
    // All three at zero would divide by zero and rank on accolades alone, which
    // is a legitimate thing to ask for -- so the blend contributes nothing rather
    // than producing NaN.
    KEYS.forEach(function (k) { raw[k] = total ? raw[k] / total : 0; });
    raw.hardware = (parseFloat(inputs.hardware.value) || 0) / 100;
    raw._total = total;
    return raw;
  }

  function ratingOf(tr, w) {
    var base = 0;
    KEYS.forEach(function (k) { base += w[k] * num(tr, 'data-' + k); });
    return 100 * base + w.hardware * num(tr, 'data-hardware');
  }

  // Rank is always by rating, whatever the table is sorted by -- so sorting by
  // PPG still tells you that the league's highest scorer was only the 5th best
  // team. Renumbering on every sort would throw that away.
  function rank(tbody, rows) {
    rows.slice().sort(function (a, b) {
      if (b._r !== a._r) return b._r - a._r;
      return (b._y || 0) - (a._y || 0);
    }).forEach(function (tr, i) {
      var rk = tr.querySelector('.at-rank');
      if (rk) rk.textContent = i + 1;
    });
  }

  // Sort state lives on the table, so the two tables in a view sort independently
  // and a scope switch or a slider drag does not silently reset either one.
  function applySort(table, tbody, rows) {
    var key = table._sortKey || 'rating';
    var dir = table._sortDir || -1;
    var text = table._sortText || false;
    rows.sort(function (a, b) {
      var av, bv;
      if (key === 'rating') { av = a._r; bv = b._r; }
      else if (text) {
        av = (a.getAttribute('data-' + key) || '').toLowerCase();
        bv = (b.getAttribute('data-' + key) || '').toLowerCase();
        if (av !== bv) return (av < bv ? -1 : 1) * -dir;
        av = a._r; bv = b._r;
      } else { av = num(a, 'data-' + key); bv = num(b, 'data-' + key); }
      if (av !== bv) return (av - bv) * dir;
      // A total order, so equal values never shuffle between renders.
      return (b._y || 0) - (a._y || 0);
    });
    rows.forEach(function (tr) { tbody.appendChild(tr); });
    table.querySelectorAll('th[data-sort]').forEach(function (th) {
      var on = th.getAttribute('data-sort') === key;
      th.classList.toggle('sorted', on);
      th.setAttribute('data-dir', on ? (dir < 0 ? 'desc' : 'asc') : '');
    });
  }

  // Every term must match, so "2023 champion" narrows rather than widens, and
  // "kobrossi playoffs" is a useful question. Rank is untouched by filtering: a
  // manager's three rows keep their all-time numbers rather than becoming 1, 2, 3.
  var find = document.getElementById('at-find');
  var found = document.getElementById('at-found');
  var FIELDS = ['year', 'team', 'manager', 'accolades'];

  function haystack(tr) {
    if (tr._hay === undefined) {
      tr._hay = FIELDS.map(function (f) {
        return tr.getAttribute('data-' + f) || '';
      }).join(' ').toLowerCase();
    }
    return tr._hay;
  }

  function searchTerms() {
    return (find && find.value || '').toLowerCase().split(/\\s+/)
      .filter(function (t) { return t; });
  }

  // Shared by the table and the chart's overlay so one search box cannot mean two
  // different things in the two views.
  function matches(tr) {
    var hay = haystack(tr);
    return searchTerms().every(function (t) { return hay.indexOf(t) !== -1; });
  }

  function filter(rows) {
    var terms = searchTerms();
    var shown = 0;
    rows.forEach(function (tr) {
      var hit = matches(tr);
      tr.hidden = !hit;
      if (hit) shown++;
    });
    if (found) {
      found.textContent = terms.length
        ? shown + ' of ' + rows.length + (shown ? '' : ' \\u2014 nothing matched')
        : '';
    }
  }

  // --- the scatter -----------------------------------------------------------
  //
  // Centred on 0,0 rather than auto-scaled to the data. Every metric here is
  // bounded and clustered above zero, so a domain fitted to the points put the
  // whole league in one corner. Each axis is given a symmetric domain about its
  // reference, so the middle of the chart is average by construction.
  //
  // Strength, record and scoring are defined so that .500 IS average, which is why
  // those three get a fixed centre rather than the mean of whatever is plotted.
  var viewSeg = document.getElementById('at-view-seg');
  var axes = document.getElementById('at-axes');
  var xsel = document.getElementById('at-x');
  var ysel = document.getElementById('at-y');
  var live = document.getElementById('at-live');
  var FIXED_CENTRE = { strength: 0.5, record: 0.5, scoring: 0.5 };
  // Every axis is numbered; what differs is whether the number is the metric's own
  // value or its distance from the middle of the chart.
  //   `abs`  -- read it straight: a win percentage, points per game.
  //   `rel`  -- a signed distance from average, which is the only reading a
  //             within-season rate supports. Strength and scoring are rates, so a
  //             step of .05 is shown as the 5 percentage points it is; rating is
  //             already on a 0-100 scale, so its own points are used.
  var TICK = {
    record: { step: 0.1, mode: 'abs' },
    ppg: { step: 5, mode: 'abs' },
    strength: { step: 0.05, mode: 'rel', scale: 100 },
    scoring: { step: 0.05, mode: 'rel', scale: 100 },
    rating: { step: 5, mode: 'rel', scale: 1 }
  };

  // A metric with real bounds gets them, instead of a domain fitted to whoever
  // happens to be plotted. A win percentage runs 0 to 1 whatever this league did,
  // so showing the whole range puts every season in its true place on the scale
  // rather than stretching the best and worst of them to the edges.
  var FIXED_SPAN = { record: 0.5 };

  function tickText(k, v, centre) {
    var t = TICK[k];
    if (!t) return '';
    if (t.mode === 'abs') {
      // Win percentage in the form the sport writes it (.500); points per game as
      // a whole number, since a tenth of a point never decides anything here.
      return k === 'record' ? v.toFixed(3).replace(/^0\\./, '.') : String(Math.round(v));
    }
    var d = Math.round((v - centre) * t.scale);
    return d === 0 ? '0' : (d > 0 ? '+' : '\\u2212') + Math.abs(d);
  }

  // Every step inside the axis domain, the centre included -- it carries a number
  // like any other tick, and only its gridline is left out (see drawChart).
  //
  // The epsilon is load-bearing in both branches: -0.3 / 0.1 is
  // -2.9999999999999996 in binary floating point, so a bare ceil() rounds up and
  // silently loses the tick at the far end of a fixed domain.
  function ticksOf(k, centre, half) {
    var t = TICK[k];
    if (!t) return [];
    var out = [], hi = centre + half;
    if (t.mode === 'abs') {
      // Multiples of the step, so a gridline sits exactly on the round number its
      // label claims rather than a fraction off it.
      for (var v = Math.ceil((centre - half) / t.step - 1e-9) * t.step; v <= hi + 1e-9; v += t.step) {
        out.push(Math.round(v / t.step) * t.step);
      }
      return out;
    }
    // Relative: stepped outward from the centre, which is what guarantees a tick
    // at 0 and a symmetric ladder either side of it.
    for (var n = Math.ceil(-half / t.step - 1e-9); n * t.step <= half + 1e-9; n++) {
      out.push(centre + n * t.step);
    }
    return out;
  }

  function metric(tr, key) {
    return key === 'rating' ? tr._r : num(tr, 'data-' + key);
  }

  function drawChart(view, teamRows) {
    var svg = view.querySelector('svg.at-chart');
    if (!svg) return;
    var tip = view.querySelector('.at-tip');
    var xk = xsel.value, yk = ysel.value;

    var rows = teamRows.filter(function (tr) { return !tr.hidden; });
    if (live && live.checked) {
      var body = view.querySelector('tbody.at-current');
      if (body) {
        // The overlay obeys the search box too. These rows are never in the
        // table, so `filter` never touches their hidden flag -- left unfiltered,
        // searching one manager still drew all ten of this year's teams beside
        // their matches.
        rows = rows.concat(Array.prototype.slice.call(body.getElementsByTagName('tr'))
          .filter(matches));
      }
    }
    var pts = [];
    rows.forEach(function (tr) {
      var x = metric(tr, xk), y = metric(tr, yk);
      if (x === null || y === null || isNaN(x) || isNaN(y)) return;
      pts.push({
        x: x, y: y,
        abbr: tr.getAttribute('data-abbr') || '',
        colour: tr.getAttribute('data-colour') || '#888',
        team: tr.getAttribute('data-team') || '',
        manager: tr.getAttribute('data-manager') || '',
        year: tr.getAttribute('data-year') || '',
        current: tr.hasAttribute('data-current')
      });
    });
    if (!pts.length) { svg.innerHTML = ''; return; }

    function centre(k, vals) {
      if (FIXED_CENTRE[k] !== undefined) return FIXED_CENTRE[k];
      var m = vals.reduce(function (s, v) { return s + v; }, 0) / vals.length;
      // An absolutely-numbered axis snaps its rule to the nearest gridline: drawn
      // at the raw average it sits between two ticks and reads as a third,
      // unlabelled one. A relatively-numbered axis needs no snap -- its labels are
      // offsets, so the rule is "0" wherever the average falls. The span is
      // measured after this, so a snap cannot push a dot outside the frame.
      var t = TICK[k];
      return (t && t.mode === 'abs') ? Math.round(m / t.step) * t.step : m;
    }
    var cx0 = centre(xk, pts.map(function (p) { return p.x; }));
    var cy0 = centre(yk, pts.map(function (p) { return p.y; }));
    // Symmetric domain: the furthest deviation in either direction sets both ends,
    // which is what pins 0,0 to the middle whatever the data does.
    function span(k, vals, c) {
      if (FIXED_SPAN[k] !== undefined) return FIXED_SPAN[k];
      var m = 0;
      vals.forEach(function (v) { m = Math.max(m, Math.abs(v - c)); });
      return (m || 1) * 1.15;
    }
    var xm = span(xk, pts.map(function (p) { return p.x; }), cx0);
    var ym = span(yk, pts.map(function (p) { return p.y; }), cy0);

    // Left and bottom margins carry the tick numbers and, where the axis has
    // them, the end phrases outboard of those.
    var xt = ticksOf(xk, cx0, xm), yt = ticksOf(yk, cy0, ym);
    // mL clears the widest tick number ("-0.300", "1.000"); mB clears one line of
    // them. Nothing else lives in the margins now the axis phrases are gone.
    var W = 900, H = 450, mR = 14, mT = 14, mL = 44, mB = 22;
    // Inset from the frame by a mark's radius, so a dot at the end of a fixed
    // domain (record runs the full .000-1.000) is drawn inside the box.
    var pad = 12;
    function SX(v) { return mL + pad + ((v - cx0) + xm) / (2 * xm) * (W - mL - mR - 2 * pad); }
    function SY(v) { return H - mB - pad - ((v - cy0) + ym) / (2 * ym) * (H - mT - mB - 2 * pad); }
    var e = [];
    e.push('<rect x="' + mL + '" y="' + mT + '" width="' + (W - mL - mR)
      + '" height="' + (H - mT - mB) + '" rx="4" class="atframe"/>');
    // Gridlines first, so the axis rules, the dots and the labels all sit on top.
    // Every tick is numbered, but a gridline is skipped where one is already
    // drawn -- down the centre (the axis rule) and at the two ends (the frame) --
    // since a dashed line on top of a solid one just reads as a thicker rule.
    function spare(pos, centrePos, lo, hi) {
      return Math.abs(pos - centrePos) < 1 || pos - lo < 1 || hi - pos < 1;
    }
    xt.forEach(function (v) {
      var x = SX(v);
      if (!spare(x, SX(cx0), mL, W - mR)) {
        e.push('<line x1="' + x + '" y1="' + mT + '" x2="' + x + '" y2="' + (H - mB) + '" class="cref"/>');
      }
      e.push('<text x="' + x + '" y="' + (H - mB + 13) + '" class="ctick" text-anchor="middle">'
        + tickText(xk, v, cx0) + '</text>');
    });
    yt.forEach(function (v) {
      var y = SY(v);
      if (!spare(y, SY(cy0), mT, H - mB)) {
        e.push('<line x1="' + mL + '" y1="' + y + '" x2="' + (W - mR) + '" y2="' + y + '" class="cref"/>');
      }
      e.push('<text x="' + (mL - 6) + '" y="' + (y + 4) + '" class="ctick" text-anchor="end">'
        + tickText(yk, v, cy0) + '</text>');
    });
    var zx = SX(cx0), zy = SY(cy0);
    e.push('<line x1="' + zx + '" y1="' + mT + '" x2="' + zx + '" y2="' + (H - mB) + '" class="cax"/>');
    e.push('<line x1="' + mL + '" y1="' + zy + '" x2="' + (W - mR) + '" y2="' + zy + '" class="cax"/>');

    // Smaller than the season chart's: this one plots every team-season the league
    // has played, not ten teams, so a 13px dot was a solid mass in the middle.
    var R = 9;
    pts.forEach(function (p, i) {
      var x = SX(p.x), y = SY(p.y);
      var cls = 'atdot' + (p.current ? ' atdot-live' : '');
      // The dot stays one size -- varying it would read as encoding a third
      // metric -- so a long abbreviation is fitted by shrinking its text
      // instead. ESPN abbreviations run to four characters (ICLY, JHHW, ESOF),
      // which at one size overflowed the circle and clipped.
      var fs = p.abbr.length > 3 ? 5.5 : p.abbr.length > 2 ? 7 : 8.5;
      e.push('<g class="' + cls + '" data-i="' + i + '">'
        + '<circle cx="' + x + '" cy="' + y + '" r="' + R + '" fill="' + p.colour + '"/>'
        + '<text x="' + x + '" y="' + (y + fs / 3) + '" class="atdot-lbl"'
        + ' font-size="' + fs + '" text-anchor="middle">' + p.abbr + '</text>'
        + '</g>');
    });

    // No plain-words label at the axis ends: the numbers say where a dot sits, and
    // what the metric means now lives on the `?` beside its picker, where it can
    // be a sentence instead of two words squeezed against the frame.
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.innerHTML = e.join('');

    // Hover gives the three things a two-letter dot cannot: which year, whose team,
    // and its name. Positioned by hand rather than left to a native tooltip, which
    // takes a second or two to show and reads as nothing happening.
    if (!tip) return;
    svg.querySelectorAll('g.atdot').forEach(function (g) {
      g.addEventListener('mouseenter', function () {
        var p = pts[parseInt(g.getAttribute('data-i'), 10)];
        tip.innerHTML = '<b>' + p.year + ' ' + p.team + '</b><br>' + p.manager
          + (p.current ? '<br><i>in progress</i>' : '');
        tip.hidden = false;
        var box = g.querySelector('circle').getBoundingClientRect();
        // Measured against the tip's own offset parent, not the svg: the svg is
        // centred inside it, so using the svg's box left the card adrift by
        // however much whitespace the centring added.
        var host = (tip.offsetParent || svg).getBoundingClientRect();
        tip.style.left = (box.left - host.left + box.width / 2) + 'px';
        tip.style.top = (box.top - host.top - 6) + 'px';
      });
      g.addEventListener('mouseleave', function () { tip.hidden = true; });
    });
  }

  function wireSorting(table, redraw) {
    table.querySelectorAll('th[data-sort]').forEach(function (th) {
      th.addEventListener('click', function () {
        var key = th.getAttribute('data-sort');
        var isText = th.className.indexOf('num') === -1;
        if (table._sortKey === key) {
          table._sortDir = -(table._sortDir || -1);
        } else {
          table._sortKey = key;
          table._sortText = isText;
          // Numbers open high-to-low (the best first); names open A-to-Z.
          table._sortDir = isText ? 1 : -1;
        }
        redraw();
      });
    });
  }

  function update() {
    var w = weights();
    KEYS.forEach(function (k) {
      var out = document.getElementById('at-w-' + k + '-val');
      if (out) out.textContent = Math.round(w[k] * 100) + '%';
    });
    var hw = document.getElementById('at-w-hardware-val');
    if (hw) hw.textContent = w.hardware.toFixed(1) + '\\u00d7';

    var view = views.filter(function (v) { return !v.hidden; })[0];
    if (!view) return;

    // Nothing in the regular-season scope carries accolade points, so the control
    // for them is disabled rather than left live and inert.
    var noHardware = view.getAttribute('data-scope') === 'regular';
    inputs.hardware.disabled = noHardware;
    inputs.hardware.closest('label').classList.toggle('off', noHardware);

    var teamBody = view.querySelector('tbody.at-teams');
    var teamTable = teamBody.closest('table');
    var teamRows = Array.prototype.slice.call(teamBody.getElementsByTagName('tr'));
    var byOwner = {};
    teamRows.forEach(function (tr) {
      tr._r = ratingOf(tr, w);
      tr._y = num(tr, 'data-year');
      var cell = tr.querySelector('.at-rating');
      if (cell) cell.textContent = tr._r.toFixed(1);
      // A co-managed season counts towards each of its managers, so one row can
      // appear under several keys.
      (tr.getAttribute('data-owner') || '').split('|').forEach(function (key) {
        if (key) (byOwner[key] = byOwner[key] || []).push(tr);
      });
    });
    rank(teamBody, teamRows);
    applySort(teamTable, teamBody, teamRows);
    filter(teamRows);

    // The in-progress rows never rank or sort, but the chart reads their rating,
    // so it still has to be computed from the current weights.
    var liveBody = view.querySelector('tbody.at-current');
    if (liveBody) {
      Array.prototype.slice.call(liveBody.getElementsByTagName('tr')).forEach(function (tr) {
        tr._r = ratingOf(tr, w);
      });
    }
    if (charting()) drawChart(view, teamRows);

    // The manager table is the same numbers averaged, so it is derived from the
    // rows above rather than carrying its own copy of them -- one source of truth
    // for a rating, whichever table is showing it.
    var ownerBody = view.querySelector('tbody.at-owners');
    if (!ownerBody) return;
    var ownerTable = ownerBody.closest('table');
    var ownerRows = Array.prototype.slice.call(ownerBody.getElementsByTagName('tr'));
    ownerRows.forEach(function (tr) {
      var seasons = byOwner[tr.getAttribute('data-owner')] || [];
      var sum = 0, best = null;
      seasons.forEach(function (s) {
        sum += s._r;
        if (!best || s._r > best._r) best = s;
      });
      tr._r = seasons.length ? sum / seasons.length : -Infinity;
      tr._y = best ? num(best, 'data-year') : 0;
      var cell = tr.querySelector('.at-rating');
      if (cell) cell.textContent = seasons.length ? tr._r.toFixed(1) : '\\u2014';
      var bestCell = tr.querySelector('.at-best');
      if (bestCell && best) {
        bestCell.textContent = best.getAttribute('data-year');
        tr.setAttribute('data-best', best.getAttribute('data-year'));
      }
    });
    rank(ownerBody, ownerRows);
    applySort(ownerTable, ownerBody, ownerRows);
  }

  // Wired once per table, on every scope's tables, so a view that has never been
  // shown still sorts the moment it is.
  views.forEach(function (v) {
    v.querySelectorAll('table.at-table').forEach(function (t) {
      wireSorting(t, update);
    });
  });

  seg.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-scope]');
    if (!b) return;
    var want = b.getAttribute('data-scope');
    views.forEach(function (v) { v.hidden = v.getAttribute('data-scope') !== want; });
    seg.querySelectorAll('button').forEach(function (x) {
      if (x === b) x.classList.add('on'); else x.classList.remove('on');
    });
    // Switching scope changes which chart is on screen, so the pickers have to
    // follow it -- otherwise they stay parked on the chart that just got hidden.
    showView();
  });
  // A preset writes the three sliders and then behaves exactly like having dragged
  // them, so there is one path to a rating rather than two.
  function choosePreset(radio) {
    var spec = radio.getAttribute('data-weights');
    if (spec) {
      var parts = spec.split(',');
      KEYS.forEach(function (k, i) { inputs[k].value = parts[i]; });
    }
    custom.hidden = !!spec;
    if (presetName) {
      presetName.textContent = radio.parentNode.querySelector('b').textContent;
    }
    update();
  }

  presets.addEventListener('change', function (e) {
    var radio = e.target.closest('input[name="at-preset"]');
    if (radio) choosePreset(radio);
  });

  // Dragging a weight is by definition a custom weighting, so the radio follows
  // the slider rather than the two disagreeing about what is selected.
  KEYS.forEach(function (k) {
    inputs[k].addEventListener('input', function () {
      var custom_radio = presets.querySelector('input[value="custom"]');
      if (custom_radio && !custom_radio.checked) {
        custom_radio.checked = true;
        custom.hidden = false;
        if (presetName) presetName.textContent = 'Custom';
      }
      update();
    });
  });
  inputs.hardware.addEventListener('input', update);
  if (find) find.addEventListener('input', update);

  function charting() {
    var on = viewSeg && viewSeg.querySelector('button.on');
    return !!on && on.getAttribute('data-view') === 'chart';
  }

  // One pair of pickers for three charts: move them into whichever chart is
  // showing, so they sit on that chart's own axes. Parking them back in #at-axes
  // (which is display:none) is what hides them in table view.
  function placePickers(host) {
    var xp = document.getElementById('at-pick-x');
    var yp = document.getElementById('at-pick-y');
    if (!xp || !yp) return;
    var to = host || axes;
    if (!to) return;
    to.appendChild(yp);
    to.appendChild(xp);
  }

  function showView() {
    var chart = charting();
    var shown = null;
    views.forEach(function (v) {
      var tv = v.querySelector('.at-table-view');
      var cv = v.querySelector('.at-chart-view');
      if (tv) tv.hidden = chart;
      if (cv) cv.hidden = !chart;
      if (cv && chart && !v.hidden) shown = cv;
    });
    placePickers(shown);
    update();
  }

  if (viewSeg) viewSeg.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-view]');
    if (!b) return;
    viewSeg.querySelectorAll('button').forEach(function (x) {
      if (x === b) x.classList.add('on'); else x.classList.remove('on');
    });
    showView();
  });
  // The `?` beside a picker explains whichever metric is chosen, read off that
  // option's own gloss so the two can never disagree.
  function describe(sel) {
    if (!sel) return;
    var hint = document.getElementById(sel.id + '-hint');
    if (!hint) return;
    var gloss = sel.options[sel.selectedIndex].getAttribute('data-gloss') || '';
    hint.querySelector('.hintbox').textContent = gloss;
    hint.setAttribute('aria-label', gloss);
  }

  if (xsel) xsel.addEventListener('change', function () { describe(xsel); update(); });
  if (ysel) ysel.addEventListener('change', function () { describe(ysel); update(); });
  if (live) live.addEventListener('change', update);
  describe(xsel);
  describe(ysel);

  var reset = document.getElementById('at-reset');
  if (reset) reset.addEventListener('click', function () {
    Object.keys(inputs).forEach(function (k) { inputs[k].value = defaults[k]; });
    var first = presets.querySelector('input[name="at-preset"]');
    if (first) { first.checked = true; choosePreset(first); } else { update(); }
  });
  update();
})();
"""


# (css class, short pill text) per accolade. Abbreviated because a champion's four
# pills on separate lines made every row a different height, and a table whose rows
# jump around is harder to scan down than one with a tight cell. The full wording
# stays as the pill's title, so hovering still explains it.
ACCOLADE_PILL = {
    "Champion": ("champ", "CHAMP"),
    "Runner-up": ("runner", "2nd"),
    "Playoffs": ("berth", "PO"),
    "Division winner": ("berth", "DW"),
    "#1 overall seed": ("berth", "#1"),
}

ACCOLADE_TITLE = {
    "CHAMP": "Champion — won the league",
    "2nd": "Runner-up",
    "PO": "Made the playoffs",
    "DW": "Division winner",
    "#1": "#1 overall seed",
}


def _accolade_pill(label):
    """One short pill, with the full wording on hover.

    A playoff-win label carries its own count ("2 playoff wins"), so it is matched
    by shape rather than looked up -- otherwise every possible count would need an
    entry of its own.
    """
    if "playoff win" in label:
        count = label.split()[0]
        return "four", f"{count}W", label
    cls, short = ACCOLADE_PILL.get(label, ("berth", label))
    return cls, short, ACCOLADE_TITLE.get(short, label)


def _accolade_pills(labels):
    """The row's badges, each explaining itself on hover or focus.

    The wording is a styled box rather than a `title` attribute. A native tooltip
    is technically correct and practically invisible -- it needs the pointer held
    still for a second or two, which reads as nothing happening. This is the same
    hover pattern the schedule tooltip already uses, so it appears at once.

    `tabindex` so the explanation is reachable by keyboard too, and `aria-label`
    so a screen reader gets the long form rather than "F4".
    """
    if not labels:
        return '<span class="empty">&mdash;</span>'
    pills = []
    for label in labels:
        cls, short, hint = _accolade_pill(label)
        pills.append(
            f'<span class="pill {cls}" tabindex="0" aria-label="{esc(hint)}">'
            f'{esc(short)}<span class="hintbox">{esc(hint)}</span></span>'
        )
    return '<span class="pills">' + "".join(pills) + "</span>"


def _manager_label(managers):
    """The Manager cell: one full name, or surnames when a team is co-managed.

    Two full names is 30-odd characters in a column beside eight others, and in a
    league where nearly every team is co-managed that widened the table for no
    gain -- the surnames identify the pair to anyone reading their own league.
    The full names stay searchable (see data-manager).
    """
    # A literal dash rather than "&mdash;": this value also rides in a data
    # attribute, where it goes through esc() and an entity would show as
    # "&amp;mdash;" on the hover card.
    if not managers:
        return "—"
    if len(managers) == 1:
        return esc(managers[0])
    return esc(" · ".join(name.split()[-1] for name in managers))


def _accolade_search_text(labels):
    """One string holding both the wording and the badge code of each accolade.

    So a filter matches "champion" typed from memory as readily as "CHAMP" read
    off the screen, without the filter itself needing to know the abbreviations.
    """
    parts = []
    for label in labels:
        _, short, _ = _accolade_pill(label)
        parts.extend([label, short])
    return " ".join(parts)


def _all_time_row(row, current=False):
    """One team-season. Monograms rather than logos on purpose.

    The payload's logos are this season's, and a franchise's art changes between
    years -- attaching the 2025 image to the same manager's 2023 team would label
    it as something it never was. A monogram is derived from the name itself, so
    it is always right about the row it sits on.

    The rates, the accolade points and the searchable fields all ride along as
    data attributes, which is what lets the sliders re-rank and the filter narrow
    the table without a round trip -- the same trick the strength section uses.
    """
    return (
        f'<tr data-owner="{esc("|".join(all_time.career_keys(row)))}"'
        f' data-strength="{row["strength"]}" data-record="{row["record"]}"'
        f' data-scoring="{row["scoring"]}" data-hardware="{row["hardware"]}"'
        f' data-year="{row["year"]}" data-ppg="{row["ppg"]}"'
        f' data-abbr="{esc(monogram(row["name"], None))}"'
        f' data-colour="{monogram_colour(row["name"])}"'
        + (' data-current="1"' if current else "")
        # The searchable value is every manager's *full* name even when the cell
        # shows surnames only, so a filter on either half of a name still hits.
        + f' data-team="{esc(row["name"])}"'
        + f' data-manager="{esc(" ".join(row["managers"]))}"'
        # Both the words and the badge codes, so the filter matches "champion"
        # typed from memory and "CHAMP" read off the screen.
        f' data-accolades="{esc(_accolade_search_text(row["accolades"]))}">'
        # An overlay row has no rank: it was never ranked, which is the whole
        # reason it is held apart from the table.
        f'<td class="num at-rank">{row.get("rank", "")}</td>'
        f'<td class="num">{row["year"]}</td>'
        f'<td class="name">{monogram_html(row["name"], None)}{esc(row["name"])}</td>'
        f'<td class="owner">{_manager_label(row["managers"])}</td>'
        f'<td class="num">{record_text(row)}</td>'
        f'<td class="num">{row["ppg"]:.1f}</td>'
        f'<td class="num">{_pct(row["strength"])}</td>'
        f'<td class="num">{_pct(row["scoring"])}</td>'
        f'<td class="acc">{_accolade_pills(row["accolades"])}</td>'
        f'<td class="num rating at-rating">{row["rating"]:.1f}</td></tr>'
    )


def _win_pct_of(tally):
    """A won-lost-tied dict as a win percentage, for sorting a Record column."""
    played = tally["wins"] + tally["losses"] + tally["ties"]
    if not played:
        return 0.0
    return round((tally["wins"] + 0.5 * tally["ties"]) / played, 4)


def _sortable(label, key, numeric=True, title=None):
    """A column heading that sorts the table by `key` when clicked.

    `key` names the row's data attribute rather than a column index, so inserting
    or removing a column cannot silently point a heading at the wrong values.
    Accolades get no key, because there is no order to sort a set of badges into.
    """
    cls = "num sort" if numeric else "sort"
    tip = f' title="{esc(title)}"' if title else ""
    return f'<th class="{cls}" data-sort="{key}"{tip}>{label}</th>'


# One vocabulary for every place a metric is named -- column head, axis picker,
# legend -- so the page cannot call the same number two different things. The
# gloss is deliberately one line: it is read once, to settle one column.
AT_METRICS = [
    ("strength", "All-Play Record", "Record against the entire league every week"),
    ("record", "Record", "Real wins and losses, playoffs included when in scope"),
    (
        "scoring",
        "All-Play Scoring",
        "PPG measured against the league&rsquo;s average PPG that year",
    ),
    ("ppg", "PPG", "Points per game"),
    ("rating", "Rating", "The three above, blended by the weights you set"),
]
# Chart axes offer the same metrics; the order puts the two rates first because
# they are the pair the chart is normally read with.
AT_CHART_METRICS = [(key, label) for key, label, _ in AT_METRICS]
AT_LABEL = {key: label for key, label, _ in AT_METRICS}


def _at_metric_options(selected):
    return _axis_options(AT_METRICS, selected)


def _all_time_legend():
    """What each column is, after the tables rather than in front of them."""
    items = "".join(
        f"<div><dt>{label}</dt><dd>{gloss}</dd></div>" for _, label, gloss in AT_METRICS
    )
    return (
        '\n<dl class="at-legend">'
        + items
        + "<div><dt>Accolades</dt><dd>What the season won &mdash; hover any badge"
        " for the full name</dd></div>"
        + "</dl>\n"
    )


def render_all_time_teams(rows, scope, current=()):
    """The scope's table, plus the same rows as a scatter.

    `current` is the in-progress season's team-seasons. They are kept in their own
    tbody -- never ranked, never sorted, never shown in the table -- so the chart
    can opt them in without the ranking having to pretend a three-week sample is
    comparable to a finished year.
    """
    head = (
        "<tr>"
        + _sortable("#", "rating", title="Rank by rating")
        + _sortable("Year", "year")
        + _sortable("Team", "team", numeric=False)
        + _sortable("Manager", "manager", numeric=False)
        + _sortable("Record", "record", title="Sorted by win percentage")
        + _sortable("PPG", "ppg")
        + _sortable(AT_LABEL["strength"], "strength")
        + _sortable(AT_LABEL["scoring"], "scoring")
        + '<th class="acc">Accolades</th>'
        + _sortable("Rating", "rating")
        + "</tr>"
    )
    body = "".join(_all_time_row(row) for row in rows)
    live = "".join(_all_time_row(row, current=True) for row in current)
    return (
        '<div class="at-table-view">'
        f'<table class="grid at-table"><thead>{head}</thead>'
        f'<tbody class="at-teams">{body}</tbody>'
        f'<tbody class="at-current" hidden>{live}</tbody></table>'
        "</div>"
        '<div class="at-chart-view" hidden>'
        '<svg class="at-chart" xmlns="http://www.w3.org/2000/svg"'
        ' role="img" aria-label="Team-seasons plotted on two chosen metrics"></svg>'
        '<div class="at-tip" hidden></div>'
        "</div>"
    )


def render_all_time_owners(owners):
    rows = "".join(
        f'<tr data-owner="{esc(o["owner_id"])}"'
        f' data-manager="{esc(o["owner"])}" data-seasons="{o["seasons"]}"'
        f' data-record="{_win_pct_of(o)}" data-titles="{o["titles"]}"'
        f' data-berths="{o["berths"]}" data-strength="{o["avg_strength"]}"'
        f' data-best="{o["best_year"]}">'
        f'<td class="num at-rank">{o["rank"]}</td>'
        f'<td class="name">{monogram_html(o["owner"], None)}{esc(o["owner"])}</td>'
        f'<td class="num">{o["seasons"]}</td>'
        f'<td class="num">{record_text(o)}</td>'
        f'<td class="num">{o["titles"]}</td>'
        f'<td class="num">{o["berths"]}</td>'
        f'<td class="num">{_pct(o["avg_strength"])}</td>'
        f'<td class="num at-best">{o["best_year"]}</td>'
        f'<td class="num rating at-rating">{o["avg_rating"]:.1f}</td></tr>'
        for o in owners
    )
    head = (
        "<tr>"
        + _sortable("#", "rating", title="Rank by average rating")
        + _sortable("Manager", "manager", numeric=False)
        + _sortable("Seasons", "seasons")
        + _sortable("Record", "record", title="Sorted by win percentage")
        + _sortable("Titles", "titles")
        + _sortable("Berths", "berths")
        + _sortable(AT_LABEL["strength"], "strength")
        + _sortable("Best", "best", title="The season with their highest rating")
        + _sortable("Avg rating", "rating")
        + "</tr>"
    )
    return (
        # An h2, like Best Team-Seasons above it: the two tables are peers, and a
        # smaller rule-less heading made the second read as a footnote to the first.
        "<h2>Manager Careers</h2>\n"
        '<p class="lede wide">The same rating averaged over every season a manager has '
        "played, because a long career should not outrank a better short one. Seasons "
        "played sits beside it: an average over two years is a weaker claim than an "
        "average over five. A co-managed season counts for <b>both</b> managers, so a "
        "shared title appears on both their records.</p>\n"
        f'<table class="grid at-table"><thead>{head}</thead>'
        f'<tbody class="at-owners">{rows}</tbody></table>'
    )


SCOPE_LABEL = {
    "regular": "Regular Season",
    "both": "Both",
    "playoffs": "Playoffs",
}


def _all_time_controls():
    """Named presets, folded away, with the raw sliders behind a Custom option.

    Four drags to answer "who was best on merit" was the wrong shape for the
    question: almost nobody wants an arbitrary blend, they want one of a handful of
    readings. So the presets do the work and the sliders stay for the rest.

    Built on `<details>` rather than a scripted panel, so it collapses with no
    JavaScript at all and is keyboard- and screen-reader-navigable for free.

    The weights are **normalised by their sum**, so only their ratio matters --
    which is why a preset can be written 70/10/20 without totalling 100.
    Accolades scale separately because they are not a rate: they are added after
    the blend, so a multiplier is the honest control rather than a fourth share.
    """
    presets = "".join(
        f'<label class="preset"><input type="radio" name="at-preset"'
        f' value="{key}" data-weights="{",".join(str(w[n]) for n in ("strength", "record", "scoring"))}"'
        f'{" checked" if key == all_time.DEFAULT_PRESET else ""}>'
        f"<b>{esc(label)}</b>"
        f'<span class="hint" tabindex="0" aria-label="{esc(blurb)}">?'
        f'<span class="hintbox">{w["strength"]} / {w["record"]} / {w["scoring"]}'
        f" &mdash; {esc(blurb)}</span></span>"
        "</label>"
        for key, label, w, blurb in all_time.PRESETS
    )
    sliders = "".join(
        f'<label>{AT_LABEL[name]}'
        f'<input type="range" id="at-w-{name}" min="0" max="100" step="5"'
        f' value="{round(all_time.WEIGHTS[name] * 100)}">'
        f'<span class="dim" id="at-w-{name}-val"></span></label>'
        for name in ("strength", "record", "scoring")
    )
    default_label = next(
        label for key, label, _, _ in all_time.PRESETS if key == all_time.DEFAULT_PRESET
    )
    return (
        # One thin row of table controls: the filter on the left, the weights as a
        # quiet link on the right. The panel opens as a popover anchored to that
        # link, so reaching for it never pushes the table down the page.
        '<div class="at-tools">'
        '<input type="search" id="at-find"'
        ' placeholder="Filter by year, team, manager or accolade">'
        '<span class="dim" id="at-found"></span>'
        '<span class="seg" id="at-view-seg">'
        '<button data-view="table" class="on">Table</button>'
        '<button data-view="chart">Chart</button></span>'
        # Tucked in beside the weights: an in-progress season is not rankable, but
        # there is no harm in seeing where it currently sits on a scatter.
        '<label class="at-live" id="at-live-wrap">'
        '<input type="checkbox" id="at-live"> this season</label>'
        '<details class="weights" id="at-weights">'
        f'<summary>Weights: <span id="at-preset-name">{esc(default_label)}</span>'
        "</summary>"
        '<div class="wbody">'
        f'<div class="presets" id="at-presets">{presets}'
        '<label class="preset"><input type="radio" name="at-preset" value="custom">'
        '<b>Custom</b><span class="hint" tabindex="0"'
        ' aria-label="Set the three weights yourself">?'
        '<span class="hintbox">Set the three weights yourself</span>'
        "</span></label></div>"
        '<div class="controls" id="at-custom" hidden>'
        f"{sliders}</div>"
        '<div class="controls">'
        '<label>Accolades<input type="range" id="at-w-hardware" min="0" max="200"'
        ' step="10" value="100">'
        '<span class="dim" id="at-w-hardware-val"></span></label>'
        '<button type="button" id="at-reset">Reset</button>'
        "</div></div></details></div>"
        # The pickers start here, parked and hidden, and are moved onto the axes of
        # whichever scope's chart is showing (see placePickers). There is one pair
        # rather than one per scope so the two views cannot disagree about which
        # metric is on which axis; parking them in the document is what lets a
        # single pair serve all three charts.
        '<div class="at-axes" id="at-axes" hidden>'
        # No "X"/"Y" letter: the picker sits on the axis it controls, which says
        # which one it is better than a label does.
        f'<div class="at-pick" id="at-pick-y">'
        f'<select id="at-y" aria-label="Y axis metric">'
        f'{_at_metric_options("scoring")}</select>{_axis_hint("at-y")}</div>'
        f'<div class="at-pick" id="at-pick-x">'
        f'<select id="at-x" aria-label="X axis metric">'
        f'{_at_metric_options("strength")}</select>{_axis_hint("at-x")}</div>'
        "</div>"
    )


def render_all_time(history):
    """The whole All-Time pane, or a note explaining why it is empty."""
    rows = all_time.team_rows(history)
    facts = all_time.summarise(history, rows)

    # An in-progress season is simply absent; the counts line above already says
    # which years are in, so there is nothing to explain. A season ESPN *refused*
    # still gets a note -- that one usually means expired cookies, which is worth
    # knowing about.
    caveats = []
    if facts["skipped"]:
        years = ", ".join(str(s["year"]) for s in facts["skipped"])
        caveats.append(
            f"{years} could not be read from ESPN "
            f"({esc(facts['skipped'][0]['reason'])})."
        )
    note = f'<p class="note">{" ".join(caveats)}</p>' if caveats else ""

    if not rows:
        return (
            "<h2>All-Time</h2>\n"
            '<p class="empty">No completed season could be read for this league.</p>'
            f"{note}"
        )

    span = (
        f"{facts['first_year']}&ndash;{facts['last_year']}"
        if facts["first_year"] != facts["last_year"]
        else str(facts["first_year"])
    )
    header = (
        f'<p class="counts">Seasons <b>{facts["seasons"]}</b> ({span})'
        f' &middot; Team-seasons ranked <b>{facts["team_seasons"]}</b>'
        f' &middot; Managers <b>{len(all_time.owner_rows(rows))}</b></p>'
    )

    # One view per scope, all three in the page. Switching scope changes both the
    # population and the tables, so the team and manager tables travel together.
    # The seasons too young to rank. Their rows are built the same way and carried
    # alongside, for the chart's optional "this season" overlay only.
    in_progress = [s for s in (history.get("seasons") or []) if not s.get("complete")]

    buttons, views = [], []
    for scope in all_time.SCOPES:
        scoped = all_time.team_rows(history, scope)
        current = []
        for season in in_progress:
            for row in all_time.season_rows(season, scope):
                # A season in progress has no bracket, but ESPN publishes a live
                # playoff seed all the same -- so the playoff scope produced six
                # qualifiers with nothing played, every rate zero, stacking six
                # identical dots in a corner of the chart. A row only overlays if
                # the scope it is drawn in has real games behind it.
                if scope == "playoffs" and not row["playoff_games"]:
                    continue
                current.append(row)
        on = " class=\"on\"" if scope == all_time.DEFAULT_SCOPE else ""
        hidden = "" if scope == all_time.DEFAULT_SCOPE else " hidden"
        buttons.append(
            f'<button data-scope="{scope}"{on}>{SCOPE_LABEL[scope]}</button>'
        )
        views.append(
            f'<div class="at-view" data-scope="{scope}"{hidden}>'
            + render_all_time_teams(scoped, scope, current)
            + "\n"
            + render_all_time_owners(all_time.owner_rows(scoped))
            + "</div>"
        )

    return (
        header
        + note
        + "\n<h2>Best Team-Seasons "
        + f'<span class="seg" id="at-seg">{"".join(buttons)}</span></h2>\n'
        + _all_time_controls()
        + "\n"
        + "\n".join(views)
        # The column definitions sit after the tables, not before them. Read in
        # front they were a wall of text between the reader and the ranking they
        # came for; read behind, they are there for the one column that puzzled
        # them.
        + _all_time_legend()
        + f"<script>{ALL_TIME_JS}</script>"
    )


def render(payload, show=None, history=None):
    """The whole document. `show` names the sections to include."""
    show = show or {"header", "standings", "matchups", "scenarios", "stats"}
    base = payload["base_league_data"]
    standings = base["standings"]
    league = base["league_data"]
    scenarios = payload["scenarios"]
    weekly_scores = base.get("weekly_scores") or []
    abbreviations = base.get("abbreviations") or {}
    logo_css, logo_class = _logo_styles(base.get("logos") or {})
    divisions = base.get("divisions")
    division_names = base.get("division_names") or {}
    thresholds = margins.load_thresholds()

    parts = []
    if "header" in show:
        parts.append(render_header(standings, league))
    if "standings" in show:
        parts.append(
            render_standings(
                standings, league, abbreviations, logo_class, divisions, division_names
            )
        )
    if "matchups" in show:
        parts.append(
            render_matchups(base["next_week_matchups"], league, abbreviations, logo_class)
        )
    if "scenarios" in show:
        parts.append(
            render_scenarios(standings, scenarios, league, thresholds, "clinch")
        )
        parts.append(render_scenarios(standings, scenarios, league, thresholds, "elim"))
    # A preseason payload carries a weekly_scores entry per team but with no weeks
    # in it, which is still truthy -- so the in-season tables key off real history.
    has_history = any(entry.get("weeks") for entry in weekly_scores)
    if "stats" in show and has_history:
        parts.append(
            render_strength(
                weekly_scores,
                base.get("remaining_matchups"),
                abbreviations,
                league.get("current_week", 0),
                standings,
                logo_class,
                base.get("managers") or {},
            )
        )
        parts.append(render_all_play(weekly_scores))
        parts.append(render_schedule_luck(weekly_scores, abbreviations))
    elif "stats" in show and base.get("projected_ppg") and base.get("remaining_matchups"):
        # No games yet, but projections and a full schedule -> a preseason SOS.
        parts.append(
            render_preseason_strength(
                base["projected_ppg"], base["remaining_matchups"], abbreviations, logo_class
            )
        )

    played = league["current_week"]
    body = chr(10).join(p for p in parts if p)

    # With a history the report becomes two panes; without one it is exactly the
    # document it has always been, down to the absence of a tab bar. That keeps
    # --history genuinely optional rather than restyling every existing report.
    if history:
        body = (
            '<nav class="tabs" id="tabs">'
            '<button data-tab="season" class="on">This Season</button>'
            '<button data-tab="alltime">All-Time</button></nav>\n'
            f'<div class="tabpane" data-tab="season">{body}</div>\n'
            f'<div class="tabpane" data-tab="alltime" hidden>{render_all_time(history)}</div>\n'
            f"<script>{TABS_JS}</script>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Playoff scenarios &middot; after week {played}</title>
<style>{CSS}</style>
{f"<style>{logo_css}</style>" if logo_css else ""}
</head>
<body>
{body}
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
    parser.add_argument(
        "--history",
        metavar="PATH",
        help="a history file from tools/fetch_history.py; adds the All-Time tab",
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

    history = None
    if args.history:
        with open(args.history) as handle:
            history = json.load(handle)

    document = render(json.load(sys.stdin), sections(args), history)

    if args.output:
        with open(args.output, "w") as handle:
            handle.write(document)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(document)
    return 0


if __name__ == "__main__":
    sys.exit(main())
