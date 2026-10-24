"""
FTIR Contamination Analyzer - report

Writes the results of one run as:
    report.html   one self-contained page: opens in any browser, works offline, prints to PDF.
                  The figures are interactive (Plotly): hover to read every value and the band
                  name, zoom, pan, save a 4x PNG. Each spectrum also has an "Analytical view"
                  (closed until clicked) with every step from the raw file to the fingerprint.
                  Without Plotly installed, the figures are embedded as vector graphics (SVG).
                  Contents: who and when, an overview, the summary, one section per spectrum,
                  the review and sign-off (filled in when it was signed in the app, or to be
                  filled in by hand), and the traceability (program, library, validation)
    report.csv    the same results as a table, for Excel or a LIMS
and adds one row per spectrum to the audit log.

How the page looks (the same design system as the window, see theme.py):
    - one quiet bar at the top with the parts of the report and the two things a reviewer checks
      first (is the library validated, is the report signed); it stays in view while scrolling
    - no colour on the frame; colour only for status (probable / weak / no match / a flag) and
      for the data (the library reference in the figures, the score strip)
    - the score strip: every spectrum's score r drawn against the two thresholds of the verdict
      rule (0.60 weak, 0.95 probable), with the next different material as a hollow mark, so the
      lead is the distance between the two marks
    - a light and a dark version (follows the computer's setting); printing always uses light
      paper colours and opens every closed block, so the PDF holds the full traceability
    - calm motion, built into the page (no internet needed): smooth scrolling (Lenis), the title
      and each spectrum's name rise in word by word (GSAP SplitText), and each part fades up once as
      it scrolls into view (GSAP ScrollTrigger). The figures never move once they are shown. With
      "reduce motion" switched on in Windows, or when printing, the page is simply still.

Short names used in this file:
    h = html.escape (makes text safe to put into a web page)    r = one Result
    i = the number of a spectrum in the report    ev = band evidence    w = one band position
    t = theme colours (the report is drawn in the light theme; the page switches to dark itself)
    pct = a position on the score strip, in percent of its width

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import base64
import html
import json
import re
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from . import __author__, __title__, __version__, config
from .analytical import analytical_steps
from .checks import BELOW_ZERO_TEXT, describe_co2, describe_vapour
from .evidence import fab_sources, relative_spectrum
from .peaks import band_label, band_names
from .plots import result_svg
from .records import DECISIONS, append_audit_log, append_signature, readable_time, who_text
from .theme import ASSETS, DARK, FONTS, ICONS, LIGHT, LOGO_SVG, WEB_FONTS

try:                                         # interactive figures if Plotly is installed, vector images if not
    from plotly.offline import get_plotlyjs

    from .interactive import analytical_figure, figure_html, result_figure
    INTERACTIVE = True
except ImportError:
    INTERACTIVE = False

h = html.escape

# Verdict -> (style, icon, word) for the coloured labels. The word always travels with the colour.
LOOK = {"probable": ("good", "circle-check", "Probable"), "weak": ("warn", "circle-help", "Weak"),
        "no reliable match": ("none", "circle-minus", "No reliable match")}
FLAG_ICON = {"bad": "circle-alert", "warn": "triangle-alert"}

# The colour tokens the figures use. In dark mode the page swaps each light colour for its dark
# partner (see THEME_JS), so the figures follow the page without being drawn twice.
FIGURE_COLOURS = ["chart_surface", "chart_sample", "chart_reference", "chart_unexplained", "chart_found",
                  "chart_zone", "chart_grid", "chart_axis", "ink", "ink_2", "muted", "surface", "line",
                  "line_strong", "accent"]


def icon(name):
    """A Lucide icon as inline SVG, 1 em big and hidden from screen readers (the word next to it says it)."""
    svg = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S).strip()
    svg = re.sub(r'\s(class|width|height)="[^"]*"', "", svg)
    return svg.replace("<svg", '<svg class="icon" aria-hidden="true" focusable="false"', 1)


def breakable(name):
    """A sample name, safe for the page, that may wrap after each underscore (and nowhere else):
    '06_PS_calibration_film_transmission' fits a phone screen without cutting a word in half."""
    return h(name).replace("_", "_<wbr>")


def pill(verdict):
    kind, symbol, word = LOOK[verdict]
    return f'<span class="pill {kind}">{icon(symbol)}{word}</span>'


def flag_pills(flags):
    return "".join(f'<span class="pill {kind}">{icon(FLAG_ICON.get(kind, "triangle-alert"))}'
                   f'{h(label[:1].upper() + label[1:])}</span>' for label, kind in flags)


def _font_face(file_name, family, weight):
    """An @font-face rule with the font file embedded, so the page looks the same on every computer."""
    path = FONTS / file_name
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    kind = "woff2" if path.suffix == ".woff2" else "truetype"
    return (f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;font-display:swap;"
            f"src:url(data:font/{kind};base64,{data}) format('{kind}')}}")


def _tokens(t):
    """The theme colours as CSS variables."""
    keys = ["paper", "surface", "surface_2", "line", "line_strong", "ink", "ink_2", "muted", "accent",
            "accent_ink", "accent_soft", "good", "good_bg", "warn", "warn_bg", "none", "none_bg", "bad", "bad_bg"]
    return ";".join(f"--{k.replace('_', '-')}:{t[k]}" for k in keys)


def figure_colour_map():
    """{light colour: dark colour} for every colour the figures use. Two tokens that share a light
    colour must share the dark one too, otherwise the swap would be ambiguous (checked here)."""
    swap = {}
    for key in FIGURE_COLOURS:
        light, dark = LIGHT[key].upper(), DARK[key].upper()
        if swap.setdefault(light, dark) != dark:
            raise ValueError(f"{key}: {light} would turn into two different dark colours")
    if len(set(swap.values())) != len(swap):
        raise ValueError("two light figure colours turn into the same dark colour: the way back is ambiguous")
    return swap


# Type: 14 px for small text, 16 px body, 18 px headings, 24 px title and the overview figures.
# Space: the 8 px grid. Corners: 12 px cards, 8 px controls, as in the window.
CSS = """
*{box-sizing:border-box}
html{color-scheme:light;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
  font:16px/1.55 'Inter',-apple-system,BlinkMacSystemFont,system-ui,'Segoe UI',Roboto,sans-serif;
  -webkit-tap-highlight-color:transparent}
.icon{width:1em;height:1em;flex:none;vertical-align:-0.14em;stroke-width:2.25}
a{color:var(--accent-ink);text-decoration:none;border-radius:4px}
a:hover{text-decoration:underline;text-underline-offset:3px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
[id]{scroll-margin-top:72px}
.skip{position:absolute;left:16px;top:-48px;z-index:20;background:var(--ink);color:var(--paper);
  padding:8px 16px;border-radius:8px}
.skip:focus{top:8px}

/* the bar: product, the parts of the report, the two first checks */
.bar{position:sticky;top:0;z-index:10;background:var(--surface);border-bottom:1px solid var(--line)}
.bar-in{max-width:1136px;margin:0 auto;padding:0 24px;height:56px;display:flex;align-items:center;gap:24px}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;color:var(--ink);white-space:nowrap}
.brand svg.logo{width:28px;height:28px;flex:none}
.bar nav{display:flex;gap:4px}
.bar nav a{color:var(--ink-2);padding:6px 10px;border-radius:8px;font-size:14px;white-space:nowrap}
.bar nav a:hover{background:var(--surface-2);text-decoration:none}
.bar .status{margin-left:auto;display:flex;gap:8px}
.bar .status .pill{margin:0}

main{max-width:1136px;margin:0 auto;padding:32px 24px 64px}
.title h1{font-size:24px;font-weight:600;line-height:1.25;margin:0;text-wrap:balance}
.title p{margin:4px 0 0;color:var(--muted);font-size:14px}
h2{font-size:18px;font-weight:600;line-height:1.3;margin:0 0 16px;text-wrap:balance}
h3{font-size:18px;font-weight:600;line-height:1.3;margin:0;overflow-wrap:break-word;min-width:0}
h4{font-size:16px;font-weight:600;margin:0 0 8px}
h2.part{margin:48px 0 16px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:24px;margin-bottom:16px}
.small,.meta,.hint{color:var(--muted);font-size:14px}
.mono{font-family:'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-size:14px;overflow-wrap:anywhere;
  color:var(--ink-2)}
.num,.stats b,.score,.facts dd,.rank td{font-variant-numeric:tabular-nums}

/* motion (only when the page may move; see MOTION_JS): no CSS smooth scroll under Lenis, and the
   words of a split heading sit in a mask so they can rise into view */
html.motion{scroll-behavior:auto}
html.motion-wait .title h1{opacity:0}
.ok{color:var(--good);font-weight:600}.alarm{color:var(--bad);font-weight:600}

/* status labels: a pastel tint, dark text of the same hue, an icon and a word */
.pill{display:inline-flex;align-items:center;gap:6px;flex:none;border-radius:999px;padding:2px 10px;font-size:14px;
  font-weight:600;white-space:nowrap;margin:2px 6px 2px 0;line-height:1.5}
.good{background:var(--good-bg);color:var(--good)}.warn{background:var(--warn-bg);color:var(--warn)}
.none{background:var(--none-bg);color:var(--none)}.bad{background:var(--bad-bg);color:var(--bad)}
a.pill:hover{text-decoration:none;filter:brightness(0.97)}

/* the overview: four figures in one strip, label above value */
.stats{display:grid;grid-template-columns:repeat(4,1fr);background:var(--surface);border:1px solid var(--line);
  border-radius:12px;margin:24px 0 16px}
.stats div{padding:16px 24px;border-left:1px solid var(--line)}.stats div:first-child{border-left:none}
.stats span{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:14px}
.stats b{display:block;font-size:24px;font-weight:600;line-height:1.3;margin-top:4px}
.dot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--muted)}
.dot.good{background:var(--good)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}

/* tables: rules and alignment, no bands */
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
thead th{color:var(--muted);font-weight:400;font-size:14px;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right}
td.name a{font-weight:600}
td.r{white-space:nowrap}

/* the score strip: r against the two thresholds of the verdict rule */
.strip{position:relative;height:10px;border-radius:999px;overflow:visible;display:flex}
.strip i{display:block;height:100%}
.strip i:nth-child(1){background:var(--none-bg);border-radius:999px 0 0 999px}
.strip i:nth-child(2){background:var(--warn-bg)}
.strip i:nth-child(3){background:var(--good-bg);border-radius:0 999px 999px 0}
.strip b,.strip u{position:absolute;top:50%;width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%}
.strip b{background:var(--ink)}
.strip u{border:2px solid var(--ink-2);background:var(--surface)}
.mini{display:inline-flex;vertical-align:middle;width:72px;height:6px;margin-right:10px}
.mini b{width:8px;height:8px;margin:-4px 0 0 -4px}
.score{margin:16px 0}
.score .strip{max-width:640px}
.ticks{position:relative;max-width:640px;height:22px;font-size:14px;color:var(--muted)}
.ticks span{position:absolute;top:2px;white-space:nowrap}
.ticks span.at{transform:translateX(-50%)}
.ticks span.end{right:0}
.ticks em{font-style:normal}
.legend{display:flex;flex-wrap:wrap;gap:4px 24px;margin:8px 0 0;font-size:15px}
.legend span{display:inline-flex;align-items:center;gap:8px}
.legend .key{width:12px;height:12px;border-radius:50%;flex:none}
.legend .key.best{background:var(--ink)}.legend .key.rival{border:2px solid var(--ink-2)}
.legend em{font-style:normal;color:var(--muted)}

/* one spectrum */
.sample-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin-bottom:4px}
.sample-head h3{margin-right:4px}
.sample-head .pill{margin:0}
.match{font-weight:600;font-size:16px}
.meta{margin:0 0 8px}
.facts{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--line);border-radius:12px;margin:0 0 16px}
.facts div{padding:12px 16px;border-left:1px solid var(--line)}.facts div:first-child{border-left:none}
.facts dt{color:var(--muted);font-size:14px}.facts dd{margin:2px 0 0;font-size:18px;font-weight:600}
.next{display:flex;gap:10px;background:var(--accent-soft);border-radius:12px;padding:12px 16px;margin:0 0 16px}
.next .icon{color:var(--accent-ink);margin-top:4px}
.next b{color:var(--accent-ink)}.next.alert{background:var(--bad-bg)}.next.alert b,.next.alert .icon{color:var(--bad)}
.next p{margin:0}
figure,.figure{margin:0 0 16px;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--surface)}
figure svg{display:block;width:100%;height:auto}
.hint{margin:0 0 8px}
.boxes{display:grid;grid-template-columns:1fr 1fr;gap:24px 32px;margin-top:24px}
.boxes>div{min-width:0}
.boxes p,.boxes ul{margin:0 0 8px}.boxes ul{padding-left:20px}
.rank{font-size:15px;margin-top:8px}
.rank td{padding:6px 0;border:none}
.rank td.num{width:56px}
.rank tr+tr td{color:var(--muted)}
.rank .bar-cell{width:40%;padding-left:16px}
.rank .bar-cell span{display:block;height:3px;border-radius:2px;background:var(--line-strong)}
.rank tr:first-child .bar-cell span{background:var(--ink)}
dl.kv{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:0}
dl.kv dt{color:var(--muted)}dl.kv dd{margin:0;min-width:0}
.chip{display:inline-block;border:1px solid var(--line);background:var(--surface-2);border-radius:8px;
  padding:0 8px;margin:2px 4px 2px 0;font-size:14px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.chip.missing{background:transparent;border-style:dashed;color:var(--muted)}
.chip.extra{background:var(--warn-bg);border-color:transparent;color:var(--warn);font-weight:600}
/* a band you can point at: it marks itself in the figure, and a click pins it and tells about it */
button.chip{font:inherit;font-size:14px;line-height:1.5;cursor:pointer;text-align:left}
button.chip:hover,button.chip:focus-visible{border-color:var(--accent);background:var(--accent-soft);color:var(--accent-ink)}
button.chip[aria-pressed=true]{border-color:var(--accent);background:var(--accent-soft);color:var(--accent-ink);font-weight:600}
.band-card{margin:8px 0 0;padding:12px 16px;border:1px solid var(--accent);border-radius:12px;background:var(--surface-2);
  font-size:15px}
.band-card[hidden]{display:none}
.band-card b{display:block;font-size:16px;margin-bottom:4px}
.band-card p{margin:0 0 6px}.band-card .acts{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.band-card button{font:inherit;font-size:14px;color:var(--accent-ink);background:transparent;border:1px solid var(--line-strong);
  border-radius:8px;padding:2px 10px;cursor:pointer}
.band-card button:hover{background:var(--accent-soft);border-color:var(--accent)}
details{margin-top:16px;border-top:1px solid var(--line);padding-top:12px}
details summary{cursor:pointer;color:var(--accent-ink);font-weight:600;padding:4px 0;border-radius:8px}
details summary:hover{text-decoration:underline;text-underline-offset:3px}
details>dl,details>ol,details>.figure{margin-top:12px}
ol.steps{padding-left:22px}ol.steps li{margin:0 0 8px}
.back{display:inline-block;margin-top:16px;font-size:14px}

/* review and sign-off */
.signed{display:flex;gap:16px;align-items:flex-start;background:var(--good-bg);border-radius:12px;padding:16px;margin:0 0 16px}
.signed>.icon{width:24px;height:24px;color:var(--good)}
.signed p{margin:0 0 4px}.signed .small{margin:0}
.sign td{height:48px}.sign td[contenteditable]{border-bottom:1px dashed var(--line-strong)}
.sign td[contenteditable]:focus{outline:none;background:var(--accent-soft);box-shadow:inset 0 -2px 0 var(--accent)}
.sign td[contenteditable]:empty:before{content:attr(data-hint);color:var(--muted)}
.ink{display:flex;gap:32px;flex-wrap:wrap;margin-top:32px}
.ink div{flex:1;min-width:200px;border-top:1px solid var(--ink-2);padding-top:6px;color:var(--muted);font-size:14px}

/* traceability */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;align-items:start}
.grid2 .panel{margin:0;min-width:0}
.panel>h3{margin-bottom:16px}
.check{display:flex;gap:10px;margin:0 0 12px}.check .icon{margin-top:4px;flex:none}
.check.ok .icon{color:var(--good)}.check.alarm .icon,.check.alarm b{color:var(--bad)}
.check p{margin:0}
/* the in-house references as short labelled rows: seven columns never fit beside the run information */
table.refs thead{display:none}
table.refs,table.refs tbody,table.refs tr{display:block}
table.refs tr{padding:12px 0;border-bottom:1px solid var(--line)}
table.refs tbody tr:last-child{border-bottom:none}
table.refs td{display:grid;grid-template-columns:minmax(6em,9em) 1fr;gap:12px;border:none;padding:2px 0;overflow-wrap:anywhere}
table.refs td:before{content:attr(data-label);color:var(--muted)}
ul.plain{margin:0;padding-left:20px}ul.plain li{margin:0 0 6px}
footer{color:var(--muted);font-size:14px;text-align:center;margin-top:32px}

@media (max-width:900px){.bar nav{display:none}.boxes,.grid2{grid-template-columns:1fr}
  /* the summary as short rows: no columns hidden behind a sideways scroll */
  table.summary thead{display:none}
  table.summary tr{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:6px 12px;padding:12px 0;
    border-bottom:1px solid var(--line)}
  table.summary tbody tr:last-child{border-bottom:none}
  table.summary td{border:none;padding:0;text-align:left}
  table.summary td.name,table.summary td.r,table.summary td.flags{grid-column:1/-1}
  table.summary td.how,table.summary td.lead,table.summary td.noflags{display:none}
}
@media (max-width:700px){
  .bar-in,main{padding-left:16px;padding-right:16px}.panel{padding:16px}
  .status .long{display:none}.bar .status{gap:6px}
  .brand span{display:none}
  .stats{grid-template-columns:1fr 1fr}.stats div,.facts div{padding:12px 16px}
  .stats div:nth-child(3){border-left:none}.stats div:nth-child(n+3){border-top:1px solid var(--line)}
  .ticks em{display:none}
  .facts{grid-template-columns:1fr}.facts div{display:flex;justify-content:space-between;align-items:baseline;gap:16px}
  .facts div+div{border-left:none;border-top:1px solid var(--line)}.facts dd{margin:0;text-align:right}
  dl.kv{grid-template-columns:1fr}dl.kv dd{margin-bottom:6px}
}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
@page{size:A4;margin:12mm}
@media print{
  html{color-scheme:light}
  body{background:#fff;font-size:10pt;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .bar,.skip,.back,.hint{display:none}main{padding:0;max-width:none}
  /* paper is wide enough for the full layout: undo the narrow-screen rows, keep the tint of pills and strips */
  .panel{break-inside:auto;border-color:#ccc;padding:16px}
  h2,h2.part,h3,h4{break-after:avoid}h2.part{margin:24px 0 12px}
  .stats,.facts,.next,.check,.chip,.signed,.score,figure,.figure,tr,dl.kv dt,dl.kv dd,.boxes>div>p{break-inside:avoid}
  .boxes,.grid2{grid-template-columns:1fr 1fr}
  .stats{grid-template-columns:repeat(4,1fr)}.facts{grid-template-columns:repeat(3,1fr)}
  .scroll{overflow:visible}
  table{font-size:9pt}th,td{padding:5px 6px}
  table.summary thead{display:table-header-group}
  table.summary tr{display:table-row;padding:0;border-bottom:none}
  table.summary td{display:table-cell;padding:5px 6px;border-bottom:1px solid var(--line)}
  table.summary td.how,table.summary td.lead,table.summary td.noflags{display:table-cell}
  table.summary .pill{margin:0 4px 2px 0;white-space:normal;border-radius:12px}
  table.summary td:nth-child(2) .pill{white-space:nowrap}
  .pill{font-size:8.5pt;padding:1px 8px}
  .mini,.modebar-container{display:none}
  table.summary td.name{width:27%}table.summary td.name a{overflow-wrap:anywhere}
  table.summary td.flags{width:24%}
  details{border-top:none}details summary{list-style:none;color:var(--ink)}
  .sign td[contenteditable]:empty:before{content:""}a{color:var(--ink)}
}
"""

# Dark mode for the figures, printing, and the closed blocks for the figures inside them.
# FIGURE_SWAP is filled in by write_html: {light colour: dark colour}.
THEME_JS = """
(function(){
  var dark = window.matchMedia('screen and (prefers-color-scheme: dark)');
  var toDark = FIGURE_SWAP, toLight = {};
  Object.keys(toDark).forEach(function(k){ toLight[toDark[k]] = k; });
  var shown = 'light';                                   // the figures are written in light colours
  function swap(value, map){                            // every colour in a layout, deep; data untouched
    if (typeof value === 'string') { return map[value.toUpperCase()] || value; }
    if (Array.isArray(value)) { return value.map(function(v){ return swap(v, map); }); }
    if (value && typeof value === 'object' && !ArrayBuffer.isView(value)) {
      var out = {}; Object.keys(value).forEach(function(k){ out[k] = swap(value[k], map); }); return out;
    }
    return value;
  }
  function paint(mode){
    if (typeof Plotly === 'undefined' || mode === shown) { return; }
    var map = mode === 'dark' ? toDark : toLight;
    document.querySelectorAll('.js-plotly-plot').forEach(function(p){
      var change = {};
      ['paper_bgcolor','plot_bgcolor','font','hoverlabel','legend','shapes','annotations'].forEach(function(k){
        if (p.layout[k] !== undefined) { change[k] = swap(p.layout[k], map); }
      });
      Object.keys(p.layout).forEach(function(k){
        if (/^[xy]axis\\d*$/.test(k)) { change[k] = swap(p.layout[k], map); }
      });
      Plotly.relayout(p, change);
      p.data.forEach(function(trace, n){
        var style = {};
        if (trace.line) { style['line.color'] = swap(trace.line.color, map); }
        if (trace.marker) { style['marker.color'] = swap(trace.marker.color, map);
          if (trace.marker.line) { style['marker.line.color'] = swap(trace.marker.line.color, map); } }
        if (Object.keys(style).length) { Plotly.restyle(p, style, [n]); }
      });
    });
    shown = mode;
  }
  function follow(){ paint(dark.matches ? 'dark' : 'light'); }
  function fit(){                                       // a narrow figure: room on top for the wrapped legend
    if (typeof Plotly === 'undefined' || printing) { return; }
    document.querySelectorAll('.js-plotly-plot').forEach(function(p){
      var top = p.clientWidth < 760 ? 150 : 92;
      if (p.layout.margin && p.layout.margin.t !== top) { Plotly.relayout(p, {'margin.t': top}); }
    });
  }
  var waiting;
  window.addEventListener('resize', function(){ clearTimeout(waiting); waiting = setTimeout(fit, 150); });
  window.addEventListener('load', function(){ fit(); follow(); });
  if (dark.addEventListener) { dark.addEventListener('change', follow); }
  // printing: light figures on white paper, and every closed block opened so nothing is left out
  var opened = [];
  // the figures are drawn at the width of the page on paper (an A4 page less its margins and the panel),
  // with the room on top that the wrapped legend needs, instead of the width of the screen
  // (a figure taller than a page is shortened to one page; legend entries get a fixed width so the
  // text is never cut off, whatever font the printer substitutes)
  var PAPER_WIDTH = 620, PAPER_HEIGHT = 950, printing = false, tall = [];
  function onPaper(){
    if (typeof Plotly === 'undefined') { return; }
    printing = true; tall = [];
    document.querySelectorAll('.js-plotly-plot').forEach(function(p){
      var change = {autosize: false, width: PAPER_WIDTH, 'legend.entrywidthmode': 'pixels', 'legend.entrywidth': 270};
      if (p.layout.height > PAPER_HEIGHT) { tall.push([p, p.layout.height]); change.height = PAPER_HEIGHT; }
      else { change['margin.t'] = 112; }
      Plotly.relayout(p, change);
    });
  }
  function offPaper(){
    if (typeof Plotly === 'undefined') { return; }
    printing = false;
    document.querySelectorAll('.js-plotly-plot').forEach(function(p){
      Plotly.relayout(p, {autosize: true, width: null, 'legend.entrywidthmode': null, 'legend.entrywidth': null});
    });
    tall.forEach(function(t){ Plotly.relayout(t[0], {height: t[1]}); });
    tall = [];
    fit();
  }
  window.addEventListener('beforeprint', function(){
    paint('light');
    document.querySelectorAll('details:not([open])').forEach(function(d){ d.open = true; opened.push(d); });
    onPaper();
  });
  window.addEventListener('afterprint', function(){
    opened.forEach(function(d){ d.open = false; }); opened = []; offPaper(); follow();
  });
  // a figure inside a closed block has no size yet: redraw it at full width when the block is opened
  document.querySelectorAll('details').forEach(function(d){
    d.addEventListener('toggle', function(){
      if (typeof Plotly === 'undefined') { return; }
      d.querySelectorAll('.js-plotly-plot').forEach(function(p){ Plotly.Plots.resize(p); });
    });
  });
})();
"""


# The bands in the "Band evidence" box. Hovering one marks it in the result figure of its spectrum; a click
# pins the mark and opens a short card (what the band usually is, how high it is in the sample and in the
# match) with two buttons: show it in the figure (zoomed), or the whole spectrum again. Clicking a key-band
# triangle in the figure does the same as clicking its button.
BAND_JS = """
(function(){
  if (typeof Plotly === 'undefined') { return; }
  var pinned = {};
  var accent = function(){ return getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#4C6FBF'; };
  var plotOf = function(chip){ return document.getElementById(chip.getAttribute('data-fig')); };
  var bandOf = function(chip){ return Number(chip.getAttribute('data-band')); };
  function mark(p, w){                                   // w = null clears the mark
    if (!p || !p.layout) { return; }
    var shapes = (p.layout.shapes || []).filter(function(s){ return s.name !== 'bandmark'; });
    if (w !== null) {
      shapes.push({name: 'bandmark', type: 'rect', xref: 'x2', yref: 'y2 domain', x0: w - 7, x1: w + 7, y0: 0, y1: 1,
                   fillcolor: accent(), opacity: 0.18, line: {width: 0}, layer: 'below'});
      shapes.push({name: 'bandmark', type: 'line', xref: 'x2', yref: 'y2 domain', x0: w, x1: w, y0: 0, y1: 1,
                   line: {color: accent(), width: 2}});
    }
    Plotly.relayout(p, {shapes: shapes});
  }
  function line(card, tag, text){
    var el = document.createElement(tag); el.textContent = text; card.appendChild(el); return el;
  }
  function percent(v){ return v === null ? 'no data there' : Math.round(v * 100) + ' %'; }
  function fill(card, info, chip){
    card.textContent = '';
    var state = {found: 'a key band of ' + info.match + ', found in the sample',
                 missing: 'a key band of ' + info.match + ', missing from the sample',
                 extra: 'a clear band of the sample that ' + info.match + ' does not explain'}[info.kind];
    line(card, 'b', info.w + ' cm\\u207b\\u00b9: ' + state);
    line(card, 'p', 'Usually: ' + info.name + '.');
    line(card, 'p', 'Height, the tallest band of each spectrum = 100 %: sample ' + percent(info.sample) +
                    ', ' + info.match + ' ' + percent(info.ref) + '.');
    var acts = document.createElement('div'); acts.className = 'acts';
    var zoom = document.createElement('button'); zoom.type = 'button'; zoom.textContent = 'Show it in the figure';
    zoom.addEventListener('click', function(){
      var p = plotOf(chip);
      Plotly.relayout(p, {'xaxis2.range': [info.w + 90, info.w - 90]});
      p.scrollIntoView({block: 'center', behavior: 'smooth'});
    });
    var all = document.createElement('button'); all.type = 'button'; all.textContent = 'Whole spectrum';
    all.addEventListener('click', function(){ Plotly.relayout(plotOf(chip), {'xaxis2.autorange': true}); });
    acts.appendChild(zoom); acts.appendChild(all); card.appendChild(acts);
  }
  function pin(chip){
    var id = chip.getAttribute('data-fig'), card = chip.closest('div').querySelector('.band-card');
    var again = pinned[id] === chip;
    if (pinned[id]) { pinned[id].setAttribute('aria-pressed', 'false'); delete pinned[id]; }
    if (again) { card.hidden = true; mark(plotOf(chip), null); return; }
    pinned[id] = chip; chip.setAttribute('aria-pressed', 'true');
    fill(card, JSON.parse(chip.getAttribute('data-info')), chip); card.hidden = false;
    mark(plotOf(chip), bandOf(chip));
  }
  function rest(chip){ var p = pinned[chip.getAttribute('data-fig')]; mark(plotOf(chip), p ? bandOf(p) : null); }
  document.querySelectorAll('button.chip.band').forEach(function(chip){
    ['mouseenter', 'focus'].forEach(function(e){ chip.addEventListener(e, function(){ mark(plotOf(chip), bandOf(chip)); }); });
    ['mouseleave', 'blur'].forEach(function(e){ chip.addEventListener(e, function(){ rest(chip); }); });
    chip.addEventListener('click', function(){ pin(chip); });
  });
  window.addEventListener('load', function(){
    document.querySelectorAll('.js-plotly-plot[id^="result"]').forEach(function(p){
      p.on('plotly_click', function(ev){
        var pt = ev.points && ev.points[0];
        if (!pt || pt.data.name !== 'key band of the match, found') { return; }
        var chip = document.querySelector('button.chip.band[data-fig="' + p.id + '"][data-band="' + Math.round(pt.x) + '"]');
        if (chip && pinned[p.id] !== chip) { pin(chip); chip.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }
      });
    });
  });
})();
"""

MOTION_FILES = ["gsap.min.js", "ScrollTrigger.min.js", "SplitText.min.js", "lenis.min.js"]

# The motion of the page. It runs only when the person has not asked for less motion, and every
# animation ends in the normal, still page: nothing is hidden for good if a script fails, and
# printing shows everything (the reveals are finished and removed before the page is printed).
MOTION_JS = """
(function(){
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { return; }
  if (typeof gsap === 'undefined' || typeof ScrollTrigger === 'undefined' || typeof Lenis === 'undefined') { return; }
  gsap.registerPlugin(ScrollTrigger, SplitText);
  document.documentElement.classList.add('motion');

  // smooth scrolling, driven by the same clock as the animations so both move in step
  var lenis = new Lenis({ lerp: 0.11, smoothWheel: true });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
  gsap.ticker.lagSmoothing(0);
  // the links in the bar and the summary glide to their part, 72 px under the bar
  document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      var target = document.querySelector(link.getAttribute('href'));
      if (!target) { return; }
      event.preventDefault();
      lenis.scrollTo(target, { offset: -72 });
      history.replaceState(null, '', link.getAttribute('href'));
    });
  });
  // opening a closed block makes the page longer: measure again
  document.querySelectorAll('details').forEach(function (d) {
    d.addEventListener('toggle', function () { lenis.resize(); ScrollTrigger.refresh(); });
  });

  var reveals = [];
  function rise(heading, delay) {                        // a heading's words rise out of their masks
    var split = SplitText.create(heading, { type: 'words', mask: 'words' });
    return gsap.from(split.words, { yPercent: 105, duration: 0.7, ease: 'power3.out', stagger: 0.05, delay: delay || 0,
      onComplete: function () { split.revert(); } });
  }
  document.fonts.ready.then(function () {                // split only once the real font is in place
    var title = document.querySelector('.title h1');
    if (title) { rise(title, 0.1); }
    document.documentElement.classList.remove('motion-wait');     // the title was kept still until now
    gsap.utils.toArray('.stats, .panel, h2.part').forEach(function (part) {
      var name = part.querySelector('.sample-head h3');
      // opacity only (not visibility): a hidden part can still be found with Ctrl+F
      reveals.push(gsap.from(part, { y: 16, opacity: 0, duration: 0.55, ease: 'power2.out',
        clearProps: 'transform,opacity',
        scrollTrigger: { trigger: part, start: 'top 92%', once: true,
          onEnter: function () { if (name) { rise(name, 0.05); } } } }));
    });
    ScrollTrigger.refresh();
  });
  // printing: every part shown, still
  window.addEventListener('beforeprint', function () {
    reveals.forEach(function (tween) { tween.progress(1); });
    lenis.stop();
  });
  window.addEventListener('afterprint', function () { lenis.start(); });
})();
"""


# In <head>: keeps the title still until its words are split (no flash), and gives up after 2 s
# if the motion script cannot run, so the title is never hidden for good.
MOTION_WAIT = ("<script>if(!matchMedia('(prefers-reduced-motion: reduce)').matches){var d=document.documentElement;"
               "d.classList.add('motion-wait');setTimeout(function(){d.classList.remove('motion-wait')},2000)}</script>")


def _asset(name):
    """A file of assets/js as text (for the page's <style> or <script>); '' if it is missing."""
    path = ASSETS / "js" / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def motion_js():
    """GSAP (core, ScrollTrigger, SplitText; GreenSock standard licence) and Lenis (MIT), built into the
    page so it works offline, then the page's own motion. Nothing if the files are missing."""
    libraries = "".join(_asset(name) for name in MOTION_FILES)
    if not libraries:
        return ""
    return ("<script>/*! Lenis 1.3.27 (MIT, darkroom.engineering); GSAP 3.15.0 (GreenSock standard "
            f"no-charge licence, https://gsap.com/standard-license) */{libraries}</script><script>{MOTION_JS}</script>")


def _logo_inline():
    svg = LOGO_SVG.read_text(encoding="utf-8")
    return svg.replace("<svg ", '<svg class="logo" aria-hidden="true" focusable="false" ', 1)


def score_html(r):
    """The score strip: the score r as a filled dot, the next different material as a hollow one,
    on a 0-1 scale coloured by the verdict rule (grey: no reliable match, amber: weak, green: probable).
    The lead the rule asks for is the distance between the two dots."""
    weak, probable = config.WEAK_R, config.PROBABLE_R
    other = r.r - r.gap

    def pct(x):
        return f"{min(max(x, 0.0), 1.0) * 100:.1f}%"
    strip = (f'<div class="strip" aria-hidden="true"><i style="width:{pct(weak)}"></i>'
             f'<i style="width:{pct(probable - weak)}"></i><i style="width:{pct(1 - probable)}"></i>'
             f'<u style="left:{pct(other)}"></u><b style="left:{pct(r.r)}"></b></div>')
    ticks = (f'<div class="ticks" aria-hidden="true"><span>0</span>'
             f'<span class="at" style="left:{pct(weak)}"><em>weak from </em>{weak:.2f}</span>'
             f'<span class="end"><em>probable from </em>{probable:.2f}</span></div>')
    legend = (f'<p class="legend"><span><i class="key best"></i>{h(r.best)}&ensp;<b>r&nbsp;{r.r:.2f}</b></span>'
              f'<span><i class="key rival"></i>{h(r.runner_up)}&ensp;r&nbsp;{other:.2f}</span>'
              f'<span><em>lead</em>&ensp;<b>{r.gap:.2f}</b>&ensp;<em>(needed: {config.MIN_GAP:.2f})</em></span></p>')
    label = (f"Score r {r.r:.2f} for {r.best}; next different material {r.runner_up} at {other:.2f}; "
             f"weak from {weak:.2f}, probable from {probable:.2f}")
    return f'<div class="score" role="img" aria-label="{h(label)}">{strip}{ticks}{legend}</div>'


def mini_strip(r):
    """The score strip, small, for the summary table (the number stands next to it)."""
    weak, probable = config.WEAK_R, config.PROBABLE_R
    return (f'<span class="strip mini" aria-hidden="true"><i style="width:{weak * 100:.0f}%"></i>'
            f'<i style="width:{(probable - weak) * 100:.0f}%"></i><i style="width:{(1 - probable) * 100:.0f}%"></i>'
            f'<b style="left:{min(max(r.r, 0), 1) * 100:.1f}%"></b></span>')


def height_near(wn, rel, w, tolerance):
    """The tallest relative band height within `tolerance` cm-1 of w, or None if the spectrum has no data there."""
    near = rel[np.abs(wn - w) <= tolerance]
    return float(near.max()) if len(near) else None


def band_chip(r, i, w, kind, text, heights):
    """One band as a button: hovering it marks the band in the figure, clicking pins it and tells about it.
    Without Plotly there is no figure to mark, so the band stays a plain label."""
    cls = {"found": "", "missing": " missing", "extra": " extra"}[kind]
    if not INTERACTIVE:
        return f'<span class="chip{cls}">{text}</span>'
    sample, match = heights
    info = {"w": round(w), "kind": kind, "match": r.best, "name": band_names(w) or "not in the band table",
            "sample": None if sample is None else round(sample, 2), "ref": None if match is None else round(match, 2)}
    return (f'<button type="button" class="chip band{cls}" data-fig="result{i}" data-band="{w:.0f}" '
            f'aria-pressed="false" data-info="{h(json.dumps(info))}">{text}</button>')


def evidence_html(r, i=0, library=None):
    ev = r.evidence
    if not ev:
        chips = "".join(f'<span class="chip">{h(b)}</span>' for b in r.checks.tallest_bands) or "none found"
        return f"<p>No match to explain. The tallest bands, to read by hand:</p><p>{chips}</p>"
    sample = relative_spectrum(r.compared)
    match = relative_spectrum(library.spectra[r.best]) if library is not None else None

    def heights(w):
        return (height_near(*sample, w, config.TOLERANCE_CM), height_near(*match, w, 10) if match else None)

    found = "".join(band_chip(r, i, w, "found", f"{w:.0f}", heights(w)) for w in ev.found)
    missing = "".join(band_chip(r, i, w, "missing", f"{w:.0f} missing", heights(w)) for w in ev.missing)
    text = (f"<p>{len(ev.found)} of {ev.n_key} key {h(r.best)} bands are in the sample.</p><p>{found}{missing}</p>"
            + ('<p class="hint">Hover a band to mark it in the figure; click it to read about it.</p>' if INTERACTIVE else ""))
    if ev.unexplained:
        extra = "".join(band_chip(r, i, w, "extra", h(band_label(w)), heights(w)) for w in ev.unexplained)
        text += f"<p>Bands the match cannot explain (possible second component):</p><p>{extra}</p>"
        text += ("<p><b>Two-component fit.</b> " + h(r.mixture.text() if r.mixture else
                 "No mix of the match and one other library reference explains these bands clearly: "
                 "the second material is probably not in the library.") + "</p>")
    else:
        text += "<p class='small'>Every clear band of the sample is explained by the match.</p>"
    return text + ('<div class="band-card" hidden></div>' if INTERACTIVE else "")


def checks_html(r):
    c = r.checks
    # max(..., 0): a band that dips below its ruler line is shown as 0, not as -0.00
    rows = [("Saturation", f"highest A = {c.max_a:.2f}" + (" &rarr; <b>saturated</b>" if c.saturated else "")),
            ("CO<sub>2</sub> artefact", h(describe_co2(c)) + (" &rarr; <b>probably no sample</b>" if c.no_sample else "")),
            ("C&ndash;H", f"{h(c.ch)} ({max(c.ch_share, 0):.3f} of the tallest band)"),
            ("O&ndash;H / N&ndash;H", f"{h(c.oh)} ({max(c.oh_share, 0):.2f})"),
            ("Noise", f"{c.noise:.4f} A"),
            ("Water vapour", h(describe_vapour(c)))]
    text = '<dl class="kv">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows) + "</dl>"
    return text + (f"<p class='small'>{h(BELOW_ZERO_TEXT)}</p>" if c.below_zero else "")


def ranking_html(r):
    """The five best scores as a small table: name, a thin bar as long as the score, the score."""
    rows = "".join(f'<tr><td>{h(name)}</td><td class="bar-cell"><span style="width:{max(score, 0) * 100:.0f}%">'
                   f'</span></td><td class="num">{score:.2f}</td></tr>' for name, score in r.ranking[:5])
    return f'<table class="rank" aria-label="The five best scores">{rows}</table>'


def sources_html(r, library=None):
    sources = fab_sources(r.best, library) if r.has_match else None
    if not sources:
        return "<p class='small'>Only given when there is a match.</p>"
    return (f"<p>{h(sources[0][:1].upper() + sources[0][1:])}.</p><p><b>Check next:</b> {h(sources[1])}.</p>"
            "<p class='small'>A starting point for the root-cause analysis, not proof.</p>")


def analytical_html(i, r, library, figure):
    """The closed 'Analytical view' block: every step in words, then the interactive step-by-step figure."""
    steps = "".join(f"<li><b>{h(step.title)}.</b> {h(step.explanation)}</li>" for step in analytical_steps(r, library))
    return (f'<details class="analytical" id="steps{i}"><summary>Analytical view: every step from the raw file '
            f'to the fingerprint and the checks</summary><ol class="steps">{steps}</ol>{figure}</details>')


def section(i, r, figure_svg, analytical="", library=None):
    """One spectrum's part of the page."""
    s, c, ev = r.spectrum, r.checks, r.evidence
    alert = any(kind == "bad" for _, kind in r.flags)
    match = f'<span class="match">{h(r.match)}</span>' if r.has_match else ""
    key_bands = f"{len(ev.found)} of {ev.n_key}" if ev else "&ndash;"
    return f"""
<section class="panel sample" id="s{i}" aria-labelledby="t{i}">
  <div class="sample-head"><h3 id="t{i}">{breakable(r.name)}</h3>{pill(r.verdict)}{match}{flag_pills(r.flags)}</div>
  <p class="meta">{h(s.path.name)}, measured by {h(r.mode_text)}</p>
  {score_html(r)}
  <dl class="facts">
    <div><dt>Key bands found</dt><dd>{key_bands}</dd></div>
    <div><dt>Highest absorbance</dt><dd>{c.max_a:.2f}</dd></div>
    <div><dt>Compared as</dt><dd>{h(r.compared_as)}</dd></div>
  </dl>
  <div class="next{' alert' if alert else ''}">{icon('circle-alert' if alert else 'arrow-right')}<p><b>Next step</b>&ensp;{h(r.next_step)}</p></div>
  {figure_svg}
  <div class="boxes">
    <div><h4>Why this verdict</h4><p>{h(r.reason)}</p>{ranking_html(r)}</div>
    <div><h4>Band evidence</h4>{evidence_html(r, i, library)}</div>
    <div><h4>Checks on the raw spectrum</h4>{checks_html(r)}</div>
    <div><h4>Where it can come from in a fab</h4>{sources_html(r, library)}</div>
  </div>
  <details><summary>Raw data and traceability</summary><dl class="kv">
    <dt>File</dt><dd class="mono">{h(str(s.path))}</dd>
    <dt>File SHA-256</dt><dd class="mono">{s.sha256}</dd>
    <dt>Unit as measured</dt><dd>{h(s.unit)}, recognised from the {h(s.unit_source)}</dd>
    <dt>Data points</dt><dd>{len(s.wn)}, {s.wn.min():.0f}&ndash;{s.wn.max():.0f} cm<sup>&minus;1</sup></dd>
    <dt>Measuring mode</dt><dd>{h(r.mode_text)}</dd>
    <dt>Tallest bands</dt><dd>{h('; '.join(c.tallest_bands))}</dd></dl></details>
  {analytical}
  <a class="back" href="#overview">Back to the summary</a>
</section>"""


def validation_html(validation):
    """The impostor test in one line, for the run information: the proof that the 'probable' threshold
    is valid for exactly this library (each reference looked up with itself removed)."""
    ok = validation.passed
    return (f'<span class="{"ok" if ok else "alarm"}">{"Passed" if ok else "FAILED"}</span>: the best wrong answer '
            f"scores {validation.score:.2f} ({h(validation.material)} with itself removed &rarr; "
            f"{h(validation.impostor)}), "
            + (f"below the probable threshold {config.PROBABLE_R:.2f}." if ok else
               f"reaching the probable threshold {config.PROBABLE_R:.2f}: re-validate before using this report."))


def library_html(library):
    """Which references the run used; every in-house reference with who added it and how it was confirmed."""
    if library is None:
        return ""
    in_house = [library.info_of(n) for n in library.in_house]
    open_specy = len(library.open_specy)
    shipped = len(library) - len(in_house) - open_specy
    text = (f"<p>{shipped} shipped references (OpenFTIR, MIT licence)"
            + (f" and {len(in_house)} in-house reference{'s' if len(in_house) != 1 else ''} added by the lab."
               if in_house else ". No in-house references were used.")
            + (f" Extended mode: {open_specy} references from the Open Specy library (CC BY 4.0; Cowger et al. 2021, "
               "Analytical Chemistry 93(21), 7543-7548), validated against every other reference before use."
               if open_specy else "") + "</p>")
    if not in_house:
        return f'<section class="panel"><h3>Reference library</h3>{text}</section>'
    rows = "".join(
        f"<tr><td data-label='In-house reference'>{h(i.name)}</td><td data-label='Category'>{h(i.category)}</td>"
        f"<td data-label='Added by'>{h(i.added_by)}</td><td data-label='On'>{h(readable_time(i.added_at))}</td>"
        f"<td data-label='Identity confirmed by'>{h(i.confirmation)}</td>"
        f"<td data-label='Made from'>{h(i.original_name)}</td>"
        f"<td class='mono' data-label='File SHA-256'>{h(i.sha256[:16])}</td></tr>"
        for i in in_house)
    return (f'<section class="panel"><h3>Reference library</h3>{text}<table class="refs">'
            "<thead><tr><th>In-house reference</th><th>Category</th><th>Added by</th><th>On</th><th>Identity confirmed by"
            "</th><th>Made from</th><th>File SHA-256</th></tr></thead>"
            f"<tbody>{rows}</tbody></table><p class='small'>Every addition and removal is kept in "
            "records/inhouse_library/library_changes.csv, which is only ever appended to.</p></section>")


def settings_html():
    return (f"probable: r &ge; {config.PROBABLE_R} and lead &ge; {config.MIN_GAP}; weak: r &ge; {config.WEAK_R}<br>"
            f"saturated: A &gt; {config.SATURATED_A}; CO<sub>2</sub> warning: &ge; {config.CO2_WARNING} of the tallest band<br>"
            f"C&ndash;H present: &ge; {config.CH_MIN_SHARE:.0%} of the tallest band and &ge; {config.MIN_SN:.0f}&times; noise<br>"
            f"O&ndash;H / N&ndash;H: major &ge; {config.MAJOR:.2f}, minor &ge; {config.MINOR:.2f} of the tallest band")


def overview_html(results):
    """Four figures in one strip: how many probable, weak, no match, and how many with a flag to look at."""
    count = {v: sum(r.verdict == v for r in results) for v in LOOK}
    flagged = sum(bool(r.flags) for r in results)
    cells = [(LOOK[v][0], count[v], LOOK[v][2].lower() if v != "no reliable match" else "no reliable match")
             for v in LOOK] + [("bad" if flagged else "none", flagged, "with a flag to look at")]
    return '<div class="stats">' + "".join(
        f'<div><span><i class="dot {kind}"></i>{h(word)}</span><b>{n}</b></div>' for kind, n, word in cells) + "</div>"


def summary_html(results):
    """The summary table: one row per spectrum, the name links to its section."""
    rows = "".join(
        f"<tr><td class='name'><a href='#s{i}'>{breakable(r.name)}</a></td><td>{pill(r.verdict)}</td><td>{h(r.match)}</td>"
        f"<td class='num r'>{mini_strip(r)}{r.r:.2f}</td><td class='num lead'>{r.gap:.2f}</td>"
        f"<td class='how'>{h(r.compared_as)}</td><td class='flags{"" if r.flags else " noflags"}'>{flag_pills(r.flags) or '&ndash;'}</td></tr>"
        for i, r in enumerate(results))
    return ('<div class="scroll"><table class="summary"><thead><tr><th>Sample</th><th>Verdict</th><th>Match</th>'
            '<th class="num">Score r</th><th class="num">Lead</th><th>Compared as</th><th>Flags</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def signoff_html(signoff, n_spectra):
    """The review and sign-off: filled in if the report was signed in the app, otherwise fields to fill in."""
    statement = ("I have looked at the raw spectra and agree with the conclusions above, or I have noted my "
                 "changes.")
    if signoff:
        comment = f"<p>Comment: {h(signoff['comment'])}</p>" if signoff.get("comment") else ""
        return (f'<section class="panel" id="signoff"><h2>Review and sign-off</h2>'
                f'<div class="signed">{icon("badge-check")}<div>'
                f"<p><b>{h(DECISIONS[signoff['decision']])}</b>, signed by <b>{h(who_text(signoff['name'], signoff['login']))}</b> "
                f"on {h(readable_time(signoff['signed_at'], with_zone=True))}.</p>{comment}"
                f'<p class="small">&ldquo;{statement}&rdquo; Recorded in records/signatures.csv with the '
                f"SHA-256 of this report file ({n_spectra} spectr{'um' if n_spectra == 1 else 'a'}).</p></div></div>"
                '<div class="ink"><div>Signature (on paper)</div><div>Date</div></div></section>')
    fields = (("Reviewed by", "your name"), ("Date", "date"), ("Decision", "accept / change / re-measure"),
              ("Comment", "a note, if any"))
    cells = "".join(f'<td contenteditable="true" role="textbox" aria-label="{label}" data-hint="{hint}"></td>'
                    for label, hint in fields)
    return (f'<section class="panel" id="signoff"><h2>Review and sign-off</h2><p>{statement}</p>'
            '<div class="scroll"><table class="sign"><thead><tr>'
            + "".join(f"<th>{label}</th>" for label, _ in fields)
            + f"</tr></thead><tbody><tr>{cells}</tr></tbody></table></div>"
            '<p class="small">Not signed in the program. Sign it there (Export report &rarr; Sign), or type into the '
            "fields above and print, or fill them in on paper.</p>"
            '<div class="ink"><div>Signature</div><div>Date</div></div></section>')


def write_html(results, figures, info, path, analytical=None, library=None, signoff=None):
    """The whole report page."""
    analytical = analytical or [""] * len(results)
    sections = "".join(section(i, r, figures[i], analytical[i], library) for i, r in enumerate(results))
    plotly_js = f"<script>{get_plotlyjs()}</script>" if INTERACTIVE else ""
    band_js = f"<script>{BAND_JS}</script>" if INTERACTIVE else ""
    theme_js = f"<script>var FIGURE_SWAP = {json.dumps(figure_colour_map())};{THEME_JS}</script>"
    fonts = "".join(_font_face(name, family, weight) for name, family, weight in WEB_FONTS)
    # dark colours only on screen: printed pages always get the light (paper) colours
    style = (f"{fonts}:root{{{_tokens(LIGHT)}}}"
             f"@media screen and (prefers-color-scheme:dark){{:root{{{_tokens(DARK)}}}html{{color-scheme:dark}}}}{CSS}")
    n = len(results)
    analysed_by = who_text(info.get("run_by_name", ""), info["run_by"])
    valid = info["validation"].passed
    # on a phone the badges keep only their first word ("Library", "Signed"): the rest is in .long
    status = (f'<a class="pill {"good" if valid else "bad"}" href="#trace">{icon("shield-check" if valid else "shield-alert")}'
              f'<span>Library<span class="long"> {"validated" if valid else "NOT validated"}</span></span></a>'
              + (f'<a class="pill good" href="#signoff">{icon("badge-check")}<span>Signed<span class="long">: '
                 f'{h(DECISIONS[signoff["decision"]])}</span></span></a>'
                 if signoff else f'<a class="pill none" href="#signoff">{icon("clipboard-list")}<span>Not signed'
                                 '<span class="long"> yet</span></span></a>'))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="{LIGHT['surface']}" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="{DARK['surface']}" media="(prefers-color-scheme: dark)">
<meta name="generator" content="{h(__title__)} {__version__} by {h(__author__)}">
<meta name="author" content="{h(__author__)}">
<title>FTIR Contamination Report</title><style>{style}{_asset("lenis.css")}</style>{MOTION_WAIT}{plotly_js}</head><body>
<a class="skip" href="#overview">Skip to the summary</a>
<header class="bar"><div class="bar-in">
  <span class="brand">{_logo_inline()}<span>{h(__title__)}</span></span>
  <nav aria-label="Parts of the report"><a href="#overview">Summary</a><a href="#s0">Spectra</a>
    <a href="#signoff">Sign-off</a><a href="#trace">Traceability</a></nav>
  <div class="status">{status}</div></div></header>
<main>
<div class="title"><h1>FTIR contamination report</h1>
  <p>{n} spectr{"um" if n == 1 else "a"} &middot; {h(readable_time(info['run_at'], with_zone=True))} &middot;
  analysed by {h(analysed_by)}</p></div>
<section id="overview" aria-label="Overview">
{overview_html(results)}
<div class="panel"><h2>Summary</h2>{summary_html(results)}</div>
</section>
<h2 class="part">Spectra</h2>
{sections}
{signoff_html(signoff, n)}
<h2 class="part" id="trace">Traceability</h2>
<div class="grid2">
  <section class="panel"><h3>Run information</h3><dl class="kv">
    <dt>Analysed</dt><dd>{h(readable_time(info['run_at'], with_zone=True))}</dd>
    <dt>By</dt><dd>{h(analysed_by)}</dd>
    <dt>Program</dt><dd>{h(info['program'])}</dd>
    <dt>Code SHA-256</dt><dd class="mono">{info['code_sha256']}</dd>
    <dt>Software</dt><dd>{h(info['software'])}</dd>
    <dt>Library</dt><dd>{h(info['library'])}</dd>
    <dt>Library SHA-256</dt><dd class="mono">{info['library_sha256']}</dd>
    <dt>Library validation</dt><dd>{validation_html(info['validation'])}</dd>
    <dt>Settings</dt><dd>{settings_html()}</dd></dl></section>
  {library_html(library)}
</div>
<footer>Generated with {h(__title__)} {__version__}, developed by {h(__author__)}</footer>
{band_js}</main>{theme_js}{motion_js()}</body></html>"""
    Path(path).write_text(page, encoding="utf-8")


def results_table(results):
    """The results as a flat table: one row per spectrum, lists turned into text."""
    return pd.DataFrame([{
        "file": r.spectrum.path.name, "sample": r.name, "unit": r.spectrum.unit, "mode": r.mode,
        "mode_source": r.mode_source, "compared_as": r.compared_as, "verdict": r.verdict, "match": r.match, "best": r.best,
        "r": r.r, "gap": r.gap, "second": r.runner_up, "ch": r.checks.ch, "ch_share": r.checks.ch_share,
        "oh": r.checks.oh, "oh_share": r.checks.oh_share, "max_A": r.checks.max_a,
        "co2_share": r.checks.co2_share, "noise": r.checks.noise, "water_vapour": r.checks.vapour if pd.notna(r.checks.vapour) else "",
        "key_bands_found": len(r.evidence.found) if r.evidence else "",
        "key_bands": r.evidence.n_key if r.evidence else "",
        "unexplained": "; ".join(f"{w:.0f}" for w in r.evidence.unexplained) if r.evidence else "",
        "mix_other": r.mixture.other if r.mixture else "",
        "mix_share_other": round(r.mixture.share_other, 3) if r.mixture else "",
        "mix_fit_r": round(r.mixture.r_fit, 4) if r.mixture else "",
        "flags": "; ".join(label for label, _ in r.flags), "next_step": r.next_step,
        "file_sha256": r.spectrum.sha256,
    } for r in results])


def write_report(results, library, info, out_dir, audit_log=config.AUDIT_LOG_FILE, signoff=None,
                 signature_log=config.SIGNATURE_LOG_FILE):
    """Write report.html, report.csv (and report.xlsx) into out_dir, add the run to the audit log, return
    the HTML path. signoff (records.make_signoff): the report is signed, and the signature recorded."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    figures, analytical = [], []
    for i, r in enumerate(results):
        name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in r.name)    # safe file name for PNG export
        if INTERACTIVE:
            hint = '<p class="hint">Hover to read every value and the band name; drag to zoom, double-click to reset.</p>'
            figures.append(hint + '<div class="figure">' + figure_html(result_figure(r, library), f"result{i}", name)
                           + "</div>")
            analytical.append(analytical_html(i, r, library, '<div class="figure">' + figure_html(
                analytical_figure(r, library), f"stepsfig{i}", f"{name}_analytical_view") + "</div>"))
        else:
            # a different "salt" per figure keeps the internal ids of the SVG drawings unique on the page
            with matplotlib.rc_context({"svg.hashsalt": f"ftir-figure-{i}"}):
                figures.append(f"<figure>{result_svg(r, library)}</figure>")
            analytical.append(analytical_html(i, r, library, ""))
    html_path = out_dir / "report.html"
    write_html(results, figures, info, html_path, analytical, library, signoff)
    table = results_table(results)
    table.to_csv(out_dir / "report.csv", index=False, float_format="%.3f")
    try:                                                           # the same table, formatted for Excel
        from .log_views import write_results_workbook
        write_results_workbook(table, info, out_dir / "report.xlsx", signoff)
    except ImportError:                                            # openpyxl not installed: the CSV is enough
        pass
    from .report_pdf import write_pdf                              # the same report as A4 pages (see report_pdf.py)
    write_pdf(results, library, info, out_dir / "report.pdf", signoff)
    append_audit_log(results, info, audit_log)
    if signoff:
        append_signature(signoff, html_path, len(results), signature_log)
    return html_path
