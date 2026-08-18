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
.divisions { display: flex; flex-wrap: wrap; gap: 1.25rem 2.5rem; }
.division { flex: 1 1 340px; min-width: 0; }
.division h3 { font-size: 1rem; margin: .25rem 0 .5rem; font-weight: 600; }
details.race { margin: 1.25rem 0 0; }
details.race > summary { cursor: pointer; font-weight: 700; font-size: 1rem; padding: .2rem 0; }
details.race table { margin-top: .5rem; }
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
.logo {
  display: inline-block; height: 1.5rem; width: 1.5rem; margin-right: .5rem;
  border-radius: 4px; vertical-align: middle;
  background-size: cover; background-position: center; background-repeat: no-repeat;
}
.grid td.name .logo { height: 1.3rem; width: 1.3rem; }
.self { outline: 2px solid var(--ink); outline-offset: -2px; font-weight: 700; }
.better { background: var(--good-bg); color: var(--good); }
.worse { background: var(--bad-bg); color: var(--bad); }
.lede { color: var(--dim); font-size: .88rem; margin: 0 0 .75rem; max-width: 68ch; }
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
  display: grid; grid-template-columns: auto 1fr; grid-template-rows: 1fr auto;
  align-items: center; gap: .35rem .5rem; margin-top: .5rem;
}
/* display:grid above overrides the `hidden` attribute's display:none, which
   would leak the axis pickers into the table view -- the id+attribute selector
   outranks it and hides the chart until it is chosen. */
#sos-chart-view[hidden] { display: none; }
.chart-y { grid-column: 1; grid-row: 1; }
#sos-chart { grid-column: 2; grid-row: 1; width: 100%; height: auto; font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
.chart-x { grid-column: 2; grid-row: 2; text-align: center; }
.chart-x label, .chart-y label { display: inline-flex; align-items: center; gap: .4rem; font-size: .78rem; color: var(--dim); }
.cax { stroke: var(--dim); stroke-width: 1; }
.cref { stroke: var(--line); stroke-width: 1; stroke-dasharray: 3 3; }
.ctick { fill: var(--dim); font-size: 11px; }
.clabel { fill: var(--ink); font-size: 12px; font-weight: 600; }
.cpt { fill: #fff; font-size: 9px; font-weight: 700; }
/* Sits below a logo on the chart background, so it needs the dark ink fill the
   on-circle label (white on colour) must not use. */
.cpt-lbl { fill: var(--ink); font-size: 9px; font-weight: 700; }
/* Corner labels naming what each quadrant means for the chosen axes. A white
   stroke drawn under the fill keeps them legible over gridlines and dots. */
.cquad {
  fill: var(--dim); font-size: 11px; font-weight: 700;
  paint-order: stroke; stroke: #fff; stroke-width: 3px; stroke-linejoin: round;
}
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
  var view = document.getElementById('sos-view');
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
  // SOS and SOR get a fixed axis so dragging the slider moves the dots, not the
  // scale -- SOS is pinned 15..85 around 50, SOR 0.3..-0.3 around 0. The rest
  // auto-scale to their data, since they do not move with the controls.
  function fixedDomain(k) { return k === 'sos' ? [15, 85] : (k === 'sor' ? [-0.3, 0.3] : null); }

  // What a low / high value of each metric means, in plain words. A quadrant
  // label joins the phrase for its X direction with the one for its Y direction,
  // so "wins + tough schedule" names the top-right when those are the axes.
  var PHRASE = {
    sos: ['easy schedule', 'tough schedule'],
    sor: ['underachieving', 'overachieving'],
    wins: ['loses a lot', 'wins a lot'],
    ppg: ['scores little', 'scores a lot'],
    oppppg: ['weak opponents', 'strong opponents'],
    pf: ['low total points', 'high total points']
  };
  function quadLabel(xk, yk, xHigh, yHigh) {
    var xp = PHRASE[xk] ? PHRASE[xk][xHigh ? 1 : 0] : '';
    var yp = PHRASE[yk] ? PHRASE[yk][yHigh ? 1 : 0] : '';
    if (xk === yk) return xp;          // same metric on both axes -> one phrase
    return (xp && yp) ? xp + ' \\u00b7 ' + yp : (xp || yp);
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

  function extent(vals) {
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (lo === hi) { lo -= 1; hi += 1; }
    var pad = (hi - lo) * 0.1;
    return [lo - pad, hi + pad];
  }
  // Count metrics (wins) read as whole numbers; the rest keep one decimal.
  function isCount(k) { return k === 'wins'; }
  function fmtAxis(v, k) {
    if (isCount(k)) return String(Math.round(v));
    return Math.abs(v) >= 100 ? String(Math.round(v)) : v.toFixed(1);
  }
  function mean(a) { return a.reduce(function (s, v) { return s + v; }, 0) / a.length; }

  function drawChart() {
    if (!svg) return;
    var w = parseInt(blend.value, 10) / 100;
    var xk = xsel.value, yk = ysel.value, pts = [];
    rows.forEach(function (tr) {
      var x = metricVal(tr, xk, w), y = metricVal(tr, yk, w);
      if (x === null || y === null) return;
      pts.push({ x: x, y: y, abbr: tr.getAttribute('data-abbr') || '', color: tr.getAttribute('data-color') || '#888', logo: tr._logo || '' });
    });
    if (!pts.length) { svg.innerHTML = ''; return; }
    var W = 660, H = 430, mL = 52, mR = 24, mT = 18, mB = 30;
    var xe = fixedDomain(xk) || extent(pts.map(function (p) { return p.x; }));
    var ye = fixedDomain(yk) || extent(pts.map(function (p) { return p.y; }));
    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
    function SX(v) { return clamp(mL + (v - xe[0]) / (xe[1] - xe[0]) * (W - mL - mR), mL, W - mR); }
    function SY(v) { return clamp(H - mB - (v - ye[0]) / (ye[1] - ye[0]) * (H - mT - mB), mT, H - mB); }
    var e = [];
    // Both axes get a divider so the quadrants mean something: a fixed line where
    // one exists (SOS at 50, SOR at 0), otherwise the average of the plotted teams.
    var xr = refOf(xk); if (xr === null) xr = mean(pts.map(function (p) { return p.x; }));
    var yr = refOf(yk); if (yr === null) yr = mean(pts.map(function (p) { return p.y; }));
    if (xr > xe[0] && xr < xe[1]) e.push('<line x1="' + SX(xr) + '" y1="' + mT + '" x2="' + SX(xr) + '" y2="' + (H - mB) + '" class="cref"/>');
    if (yr > ye[0] && yr < ye[1]) e.push('<line x1="' + mL + '" y1="' + SY(yr) + '" x2="' + (W - mR) + '" y2="' + SY(yr) + '" class="cref"/>');
    e.push('<line x1="' + mL + '" y1="' + (H - mB) + '" x2="' + (W - mR) + '" y2="' + (H - mB) + '" class="cax"/>');
    e.push('<line x1="' + mL + '" y1="' + mT + '" x2="' + mL + '" y2="' + (H - mB) + '" class="cax"/>');
    // Axis tick numbers only -- the metric names live in the HTML selects on each
    // axis, so they are not repeated here.
    e.push('<text x="' + mL + '" y="' + (H - mB + 16) + '" class="ctick" text-anchor="start">' + fmtAxis(xe[0], xk) + '</text>');
    e.push('<text x="' + (W - mR) + '" y="' + (H - mB + 16) + '" class="ctick" text-anchor="end">' + fmtAxis(xe[1], xk) + '</text>');
    e.push('<text x="' + (mL - 8) + '" y="' + (H - mB) + '" class="ctick" text-anchor="end">' + fmtAxis(ye[0], yk) + '</text>');
    e.push('<text x="' + (mL - 8) + '" y="' + (mT + 10) + '" class="ctick" text-anchor="end">' + fmtAxis(ye[1], yk) + '</text>');
    pts.forEach(function (p) {
      var cx = SX(p.x), cy = SY(p.y);
      if (p.logo) {
        // --logos inlined this team's image: draw it in place of the circle,
        // abbreviation just below.
        var s = 26;
        e.push('<image href="' + p.logo + '" x="' + (cx - s / 2) + '" y="' + (cy - s / 2) + '" width="' + s + '" height="' + s + '" preserveAspectRatio="xMidYMid slice"/>');
        e.push('<text x="' + cx + '" y="' + (cy + s / 2 + 9) + '" class="cpt-lbl" text-anchor="middle">' + p.abbr + '</text>');
      } else {
        e.push('<circle cx="' + cx + '" cy="' + cy + '" r="13" fill="' + p.color + '"/>');
        e.push('<text x="' + cx + '" y="' + (cy + 3) + '" class="cpt" text-anchor="middle">' + p.abbr + '</text>');
      }
    });
    // Name each corner by what the chosen axes mean there -- top is high Y, right
    // is high X -- so the reading changes with the selects.
    function corner(x, y, anchor, xHigh, yHigh) {
      var t = quadLabel(xk, yk, xHigh, yHigh);
      if (t) e.push('<text x="' + x + '" y="' + y + '" class="cquad" text-anchor="' + anchor + '">' + t + '</text>');
    }
    corner(mL + 6, mT + 14, 'start', false, true);       // top-left:  low X, high Y
    corner(W - mR - 6, mT + 14, 'end', true, true);       // top-right: high X, high Y
    corner(mL + 6, H - mB - 8, 'start', false, false);    // bottom-left:  low X, low Y
    corner(W - mR - 6, H - mB - 8, 'end', true, false);   // bottom-right: high X, low Y
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.innerHTML = e.join('');
  }

  function showView() {
    var chart = view && view.value === 'chart';
    if (section) section.className = chart ? 'charting' : '';
    if (tableView) tableView.hidden = chart;
    if (chartView) chartView.hidden = !chart;
    if (chart) drawChart();
  }

  function update() { updateTable(); if (view && view.value === 'chart') drawChart(); }

  blend.addEventListener('input', update);
  if (view) view.addEventListener('change', showView);
  if (xsel) xsel.addEventListener('change', drawChart);
  if (ysel) ysel.addEventListener('change', drawChart);
  updateTable();
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
    spots = league["playoff_spots"]
    if not divisions:
        table = _standings_table(standings, abbreviations, logo_class, cut_at=spots)
        return (
            f"<h2>Standings</h2>\n{table}"
            f'<p class="cutnote">The rule marks the playoff cut line: {spots} spots.</p>'
        )

    # Divisional: one table per division. Divisions appear in the order their best
    # seed does; within a table teams are in their own record order, and the #
    # column is the within-division rank. Division ids arrive as ints, but JSON
    # turns the division_names keys into strings, so look both up.
    names = division_names or {}
    ordered, seen, groups = [], set(), {}
    for team in standings:
        did = divisions.get(team["team_name"])
        groups.setdefault(did, []).append(team)
        if did not in seen:
            seen.add(did)
            ordered.append(did)

    blocks = []
    for did in ordered:
        teams = sorted(groups[did], key=lambda t: (-t["wins"], -t["points_for"]))
        title = names.get(did) or names.get(str(did)) or f"Division {did}"
        blocks.append(
            f'<div class="division"><h3>{esc(title)}</h3>'
            f"{_standings_table(teams, abbreviations, logo_class)}</div>"
        )
    return (
        f"<h2>Standings</h2>\n"
        f'<div class="divisions">{"".join(blocks)}</div>'
        f'<p class="cutnote">{spots} playoff spots league-wide; '
        f"division winners are seeded first.</p>"
    )


def render_seed_race(standings, abbreviations=None, logo_class=None):
    """The race for the #1 overall seed, as a collapsible section.

    Reads the exact `top_seed` verdict already on each team, so it is the same
    answer the standings badge gives -- gathered here as its own race. Teams
    eliminated from the #1 seed are left out; that is the point of a race.
    """
    # Only a race while it is undecided: once a team has clinched the #1 seed
    # (or nobody can still take it) there is nothing to show.
    if any(t.get("top_seed") == "clinched" for t in standings):
        return ""
    contenders = [t for t in standings if t.get("top_seed") == "alive"]
    if not contenders:
        return ""
    rows = "".join(
        f"<tr><td>{team_mark(t['team_name'], abbreviations, logo_class)}"
        f"{esc(t['team_name'])}</td>"
        f'<td class="num">{t["wins"]}-{t["losses"]}</td>'
        f'<td class="num">{t["points_for"]:.1f}</td></tr>'
        for t in contenders
    )
    return (
        '<details class="race" open><summary>Overall #1 Seed</summary>'
        '<table><thead><tr><th>Team</th><th class="num">Record</th>'
        '<th class="num">Points for</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></details>"
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
CHART_METRICS = [
    ("sos", "SOS"),
    ("sor", "SOR"),
    ("wins", "Wins"),
    ("ppg", "PPG"),
    ("oppppg", "Opp PPG"),
    ("pf", "Points For"),
]


def _metric_options(selected):
    return "".join(
        f'<option value="{key}"{" selected" if key == selected else ""}>{label}</option>'
        for key, label in CHART_METRICS
    )


def render_strength(
    weekly_scores, remaining_matchups=None, abbreviations=None, current_week=0,
    standings=None, logo_class=None
):
    rows = strength.strength_table(weekly_scores, remaining_matchups)
    if not rows:
        return ""
    any_remaining = any(row["sos_remaining"] is not None for row in rows)
    # Per-team season figures the chart's fixed axes need, keyed by name.
    stats = {team["team_name"]: team for team in (standings or [])}

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
            f' data-color="{monogram_colour(row["name"])}">'
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
  <label>View
    <select id="sos-view"><option value="table">Table</option><option value="chart">Chart</option></select>
  </label>
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
<div class="chart-y"><label>Y&nbsp;axis <select id="sos-y">{_metric_options("sor")}</select></label></div>
<svg id="sos-chart" role="img" aria-label="Scatter of two chosen metrics per team"></svg>
<div class="chart-x"><label>X&nbsp;axis <select id="sos-x">{_metric_options("sos")}</select></label></div>
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


def render(payload, show=None):
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
        parts.append(render_seed_race(standings, abbreviations, logo_class))
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
