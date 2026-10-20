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

Short names used in this file:
    h = html.escape (makes text safe to put into a web page)    r = one Result
    i = the number of a spectrum in the report    ev = band evidence    w = one band position
    t = theme colours (the report always uses the light theme; the page has its own dark mode)

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import base64
import html
from pathlib import Path

import matplotlib
import pandas as pd

from . import __author__, __title__, __version__, config
from .analytical import analytical_steps
from .checks import BELOW_ZERO_TEXT, describe_co2
from .evidence import fab_sources
from .peaks import band_label
from .plots import result_svg
from .records import DECISIONS, append_audit_log, append_signature, readable_time, who_text
from .theme import DARK, FONT_SANS, FONTS, LIGHT, LOGO_SVG, WEB_FONTS

try:                                         # interactive figures if Plotly is installed, vector images if not
    from plotly.offline import get_plotlyjs

    from .interactive import analytical_figure, figure_html, result_figure
    INTERACTIVE = True
except ImportError:
    INTERACTIVE = False

h = html.escape

# Verdict -> (style, symbol, word) for the coloured labels
LOOK = {"probable": ("good", "&#10003;", "Probable"), "weak": ("warn", "?", "Weak"),
        "no reliable match": ("none", "&ndash;", "No reliable match")}


def pill(verdict):
    kind, symbol, word = LOOK[verdict]
    return f'<span class="pill {kind}">{symbol}&nbsp;{word}</span>'


def flag_pills(flags):
    return "".join(f'<span class="pill {kind}">!&nbsp;{h(label[:1].upper() + label[1:])}</span>'
                   for label, kind in flags)


def _font_face(file_name, weight):
    """An @font-face rule with the font file embedded, so the page looks the same on every computer."""
    path = FONTS / file_name
    if not path.exists():
        return ""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return (f"@font-face{{font-family:'{FONT_SANS}';font-weight:{weight};font-style:normal;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2')}}")


def _tokens(t):
    """The theme colours as CSS variables."""
    keys = ["paper", "surface", "surface_2", "line", "line_strong", "ink", "ink_2", "muted", "accent",
            "accent_ink", "accent_soft", "primary", "on_primary", "header", "header_ink", "header_muted",
            "good", "good_bg", "warn", "warn_bg",
            "none", "none_bg", "bad", "bad_bg"]
    return ";".join(f"--{k.replace('_', '-')}:{t[k]}" for k in keys)


CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font:15px/1.55 'Inter',-apple-system,BlinkMacSystemFont,system-ui,'Segoe UI',Roboto,sans-serif}
.top{background:var(--header);color:var(--header-ink)}
.top-in{max-width:1120px;margin:0 auto;padding:22px 20px;display:flex;align-items:center;gap:16px}
.top svg.logo{width:52px;height:52px;flex:none}
.top h1{font-size:24px;font-weight:600;margin:0;line-height:1.2}
.top p{margin:2px 0 0;color:var(--header-muted);font-size:14px}
main{max-width:1120px;margin:0 auto;padding:24px 20px 56px}
h2{font-size:18px;font-weight:600;margin:0 0 12px}
h3{font-size:22px;font-weight:600;margin:0}
h4{font-size:15px;font-weight:600;margin:0 0 8px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px;margin-bottom:16px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-bottom:16px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 18px;margin:0}
dt{color:var(--muted)}dd{margin:0}
.mono{font-family:'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;word-break:break-all;color:var(--ink-2)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
th{color:var(--muted);font-weight:500}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}a{color:var(--accent-ink)}
.pill{display:inline-block;border-radius:999px;padding:2px 11px;font-size:13px;font-weight:600;
  margin:2px 6px 2px 0;white-space:nowrap}
.good{background:var(--good-bg);color:var(--good)}.warn{background:var(--warn-bg);color:var(--warn)}
.none{background:var(--none-bg);color:var(--none)}.bad{background:var(--bad-bg);color:var(--bad)}
.ok{color:var(--good);font-weight:600}.alarm{color:var(--bad);font-weight:600}
.sample-head{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:4px}
.match{font-weight:600;font-size:17px}
.meta{color:var(--muted);font-size:13.5px;margin:0 0 14px}
.facts{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:10px;margin:0 0 12px}
.facts div{padding:10px 16px;border-left:1px solid var(--line)}.facts div:first-child{border-left:none}
.facts b{display:block;font-size:20px;font-weight:600}.facts span{color:var(--muted);font-size:13px}
.next{background:var(--accent-soft);border-radius:10px;padding:12px 16px;margin:0 0 14px}
.next b{color:var(--accent-ink)}.next.alert{background:var(--bad-bg)}.next.alert b{color:var(--bad)}
figure,.figure{margin:0 0 14px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff}
figure svg{display:block;width:100%;height:auto}
.hint{color:var(--muted);font-size:13px;margin:-6px 0 12px}
details.analytical{margin-top:14px;border:1px solid var(--line);border-radius:10px;padding:12px 16px;background:var(--surface-2)}
details.analytical[open]{background:var(--surface)}
details.analytical summary{font-weight:600;color:var(--accent-ink)}
ol.steps{margin:12px 0 14px;padding-left:22px}ol.steps li{margin:0 0 6px}
.boxes{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px;margin-top:4px}
.boxes p,.boxes ul,.boxes ol{margin:0 0 6px}.boxes ul,.boxes ol{padding-left:20px}
.chip{display:inline-block;border:1px solid var(--line);background:var(--surface-2);border-radius:6px;
  padding:1px 8px;margin:2px 4px 2px 0;font-size:13px;color:var(--ink-2)}
.chip.missing{background:transparent;border-style:dashed;color:var(--muted)}
.chip.extra{background:var(--warn-bg);border-color:transparent;color:var(--warn);font-weight:600}
.small{color:var(--muted);font-size:13px}
details{margin-top:12px}details summary{cursor:pointer;color:var(--accent-ink);font-weight:500}details dl{margin-top:10px}
.top-in .who{margin-left:auto;display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}
.top-in .who .pill{margin:0}
a.pill{text-decoration:none}
th{white-space:nowrap}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:0 0 16px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 18px}
.tile b{display:block;font-size:28px;font-weight:600;line-height:1.2;font-variant-numeric:tabular-nums}
.tile span{color:var(--muted);font-size:13.5px}
.tile i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:1px}
.tile.good i{background:var(--good)}.tile.warn i{background:var(--warn)}.tile.none i{background:var(--muted)}
.tile.bad i{background:var(--bad)}
.tile.good,.tile.warn,.tile.none,.tile.bad{background:var(--surface);color:var(--ink)}
.signed{display:flex;gap:14px;align-items:flex-start;background:var(--good-bg);border-radius:10px;padding:14px 18px;
  margin:4px 0 14px}
.signed .mark{flex:none;width:26px;height:26px;border-radius:50%;background:var(--good);color:var(--surface);
  display:flex;align-items:center;justify-content:center;font-weight:700}
.signed p{margin:0 0 4px}.signed .small{margin:0}
.sign td{height:44px}.sign td[contenteditable]{border-bottom:1px dashed var(--line-strong);outline:none}
.sign td[contenteditable]:focus{background:var(--accent-soft)}
.sign td[contenteditable]:empty:before{content:attr(data-hint);color:var(--muted)}
.ink{display:flex;gap:32px;flex-wrap:wrap;margin-top:28px}
.ink div{flex:1;min-width:220px;border-top:1px solid var(--ink-2);padding-top:6px;color:var(--muted);font-size:13px}
h2.part{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
  margin:28px 0 10px}
footer{color:var(--muted);font-size:13px;text-align:center;margin-top:28px}
@media (max-width:700px){.facts,.tiles{grid-template-columns:repeat(2,1fr)}
  .facts div:nth-child(3){border-left:none}.top-in{flex-wrap:wrap}.top-in .who{margin-left:0;justify-content:flex-start}}
@media print{body{background:#fff}.top{background:#fff;color:var(--ink);border-bottom:2px solid var(--ink)}
  .top p{color:var(--muted)}.panel{break-inside:avoid;border-color:#ccc}details{display:block}
  details summary{display:none}.sign td[contenteditable]:empty:before{content:""}}
"""


def _logo_inline():
    svg = LOGO_SVG.read_text(encoding="utf-8")
    return svg.replace("<svg ", '<svg class="logo" aria-hidden="true" ', 1)


def evidence_html(r):
    ev = r.evidence
    if not ev:
        chips = "".join(f'<span class="chip">{h(b)}</span>' for b in r.checks.tallest_bands) or "none found"
        return f"<p>No match to explain. The tallest bands, to read by hand:</p><p>{chips}</p>"
    found = "".join(f'<span class="chip">{w:.0f}</span>' for w in ev.found)
    missing = "".join(f'<span class="chip missing">{w:.0f} missing</span>' for w in ev.missing)
    text = f"<p>{len(ev.found)} of {ev.n_key} key {h(r.best)} bands are in the sample.</p><p>{found}{missing}</p>"
    if ev.unexplained:
        extra = "".join(f'<span class="chip extra">{h(band_label(w))}</span>' for w in ev.unexplained)
        text += f"<p>Bands the match cannot explain (possible second component):</p><p>{extra}</p>"
    else:
        text += "<p class='small'>Every clear band of the sample is explained by the match.</p>"
    return text


def checks_html(r):
    c = r.checks
    # max(..., 0): a band that dips below its ruler line is shown as 0, not as -0.00
    return (f"<ul><li>Saturation: highest A = {c.max_a:.2f}{' &rarr; <b>saturated</b>' if c.saturated else ''}</li>"
            f"<li>CO<sub>2</sub> artefact: {h(describe_co2(c))}"
            f"{' &rarr; <b>probably no sample</b>' if c.no_sample else ''}</li>"
            f"<li>C&ndash;H: {h(c.ch)} ({max(c.ch_share, 0):.3f} of the tallest band)</li>"
            f"<li>O&ndash;H / N&ndash;H: {h(c.oh)} ({max(c.oh_share, 0):.2f})</li>"
            f"<li>Noise: {c.noise:.4f} A</li>"
            + (f"<li>{h(BELOW_ZERO_TEXT)}</li>" if c.below_zero else "") + "</ul>")


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
    top5 = "".join(f"<li>{h(name)} <span class='small'>{score:.2f}</span></li>" for name, score in r.ranking[:5])
    alert = any(kind == "bad" for _, kind in r.flags)
    match = f'<span class="match">{h(r.match)}</span>' if r.has_match else ""
    key_bands = f"{len(ev.found)} of {ev.n_key}" if ev else "&ndash;"
    return f"""
<section class="panel" id="s{i}">
  <div class="sample-head"><h3>{h(r.name)}</h3>{pill(r.verdict)}{match}{flag_pills(r.flags)}</div>
  <p class="meta">{h(s.path.name)}, measured by {h(r.mode_text)}</p>
  <div class="facts">
    <div><b>{r.r:.2f}</b><span>score (Pearson r)</span></div>
    <div><b>{r.gap:.2f}</b><span>lead over {h(r.runner_up)}</span></div>
    <div><b>{key_bands}</b><span>key bands found</span></div>
    <div><b>{c.max_a:.2f}</b><span>highest absorbance</span></div>
  </div>
  <p class="next{' alert' if alert else ''}"><b>Next step</b>&ensp;{h(r.next_step)}</p>
  {figure_svg}
  <div class="boxes">
    <div><h4>Why this verdict</h4><p>{h(r.reason)}</p><ol>{top5}</ol></div>
    <div><h4>Band evidence</h4>{evidence_html(r)}</div>
    <div><h4>Checks on the raw spectrum</h4>{checks_html(r)}</div>
    <div><h4>Where it can come from in a fab</h4>{sources_html(r, library)}</div>
  </div>
  <details><summary>Raw data and traceability</summary><dl>
    <dt>File</dt><dd class="mono">{h(str(s.path))}</dd>
    <dt>File SHA-256</dt><dd class="mono">{s.sha256}</dd>
    <dt>Unit as measured</dt><dd>{h(s.unit)}, recognised from the {h(s.unit_source)}</dd>
    <dt>Data points</dt><dd>{len(s.wn)}, {s.wn.min():.0f}&ndash;{s.wn.max():.0f} cm<sup>&minus;1</sup></dd>
    <dt>Measuring mode</dt><dd>{h(r.mode_text)}</dd>
    <dt>Tallest bands</dt><dd>{h('; '.join(c.tallest_bands))}</dd></dl></details>
  {analytical}
</section>"""


def validation_html(validation):
    ok = validation.passed
    return (f'<p class="{"ok" if ok else "alarm"}">{"&#10003;" if ok else "!"} Impostor test on this library: '
            f"the best WRONG answer scores {validation.score:.2f} ({h(validation.material)} with itself removed "
            f"&rarr; {h(validation.impostor)}). "
            + ("This is below the 'probable' threshold, so the verdict rule is valid for this library."
               if ok else "This reaches 'probable': re-validate the thresholds before using this report.")
            + "</p>")


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
        return f'<section class="panel"><h2>Reference library</h2>{text}</section>'
    rows = "".join(
        f"<tr><td>{h(i.name)}</td><td>{h(i.category)}</td><td>{h(i.added_by)}</td><td>{h(readable_time(i.added_at))}</td>"
        f"<td>{h(i.confirmation)}</td><td>{h(i.original_name)}</td><td class='mono'>{h(i.sha256[:16])}</td></tr>"
        for i in in_house)
    return (f'<section class="panel"><h2>Reference library</h2>{text}<div class="scroll"><table>'
            "<tr><th>In-house reference</th><th>Category</th><th>Added by</th><th>On</th><th>Identity confirmed by"
            "</th><th>Made from</th><th>File SHA-256</th></tr>"
            f"{rows}</table></div><p class='small'>Every addition and removal is kept in "
            "records/inhouse_library/library_changes.csv, which is only ever appended to.</p></section>")


def settings_html():
    return (f"probable: r &ge; {config.PROBABLE_R} and lead &ge; {config.MIN_GAP}; weak: r &ge; {config.WEAK_R}<br>"
            f"saturated: A &gt; {config.SATURATED_A}; CO<sub>2</sub> warning: &ge; {config.CO2_WARNING} of the tallest band<br>"
            f"C&ndash;H present: &ge; {config.CH_MIN_SHARE:.0%} of the tallest band and &ge; {config.MIN_SN:.0f}&times; noise<br>"
            f"O&ndash;H / N&ndash;H: major &ge; {config.MAJOR:.2f}, minor &ge; {config.MINOR:.2f} of the tallest band")


def overview_html(results):
    """Four tiles: how many probable, weak, no match, and how many with a flag to look at."""
    count = {v: sum(r.verdict == v for r in results) for v in LOOK}
    flagged = sum(bool(r.flags) for r in results)
    tiles = [(LOOK[v][0], count[v], LOOK[v][2].lower() if v != "no reliable match" else "no reliable match")
             for v in LOOK] + [("bad" if flagged else "none", flagged, "with a flag to look at")]
    return '<div class="tiles">' + "".join(
        f'<div class="tile {kind}"><b>{n}</b><span><i></i>{h(word)}</span></div>' for kind, n, word in tiles) + "</div>"


def signoff_html(signoff, n_spectra):
    """The review and sign-off: filled in if the report was signed in the app, otherwise fields to fill in."""
    statement = ("I have looked at the raw spectra and agree with the conclusions above, or I have noted my "
                 "changes.")
    if signoff:
        comment = f"<p>Comment: {h(signoff['comment'])}</p>" if signoff.get("comment") else ""
        return (f'<section class="panel" id="signoff"><h2>Review and sign-off</h2>'
                f'<div class="signed"><div class="mark">&#10003;</div><div>'
                f"<p><b>{h(DECISIONS[signoff['decision']])}</b>, signed by <b>{h(who_text(signoff['name'], signoff['login']))}</b> "
                f"on {h(readable_time(signoff['signed_at'], with_zone=True))}.</p>{comment}"
                f'<p class="small">&ldquo;{statement}&rdquo; Recorded in records/signatures.csv with the '
                f"SHA-256 of this report file ({n_spectra} spectr{'um' if n_spectra == 1 else 'a'}).</p></div></div>"
                '<div class="ink"><div>Signature (on paper)</div><div>Date</div></div></section>')
    cells = "".join(f'<td contenteditable="true" data-hint="{hint}"></td>'
                    for hint in ("your name", "date", "accept / change / re-measure", "a note, if any"))
    return (f'<section class="panel" id="signoff"><h2>Review and sign-off</h2><p>{statement}</p>'
            '<table class="sign"><tr><th>Reviewed by</th><th>Date</th><th>Decision</th><th>Comment</th></tr>'
            f"<tr>{cells}</tr></table>"
            '<p class="small">Not signed in the program. Sign it there (Export report &rarr; Sign), or type into the '
            "fields above and print, or fill them in on paper.</p>"
            '<div class="ink"><div>Signature</div><div>Date</div></div></section>')


def write_html(results, figures, info, path, analytical=None, library=None, signoff=None):
    """The whole report page."""
    summary = "".join(
        f"<tr><td><a href='#s{i}'>{h(r.name)}</a></td><td>{pill(r.verdict)}</td><td>{h(r.match)}</td>"
        f"<td class='num'>{r.r:.2f}</td><td class='num'>{r.gap:.2f}</td><td>{h(r.compared_as)}</td>"
        f"<td>{flag_pills(r.flags) or '&ndash;'}</td></tr>"
        for i, r in enumerate(results))
    analytical = analytical or [""] * len(results)
    sections = "".join(section(i, r, figures[i], analytical[i], library) for i, r in enumerate(results))
    plotly_js = f"<script>{get_plotlyjs()}</script>" if INTERACTIVE else ""
    # a figure inside a closed block has no size yet: redraw it at full width when the block is opened
    resize_js = ("<script>document.querySelectorAll('details').forEach(d=>d.addEventListener('toggle',()=>"
                 "d.querySelectorAll('.js-plotly-plot').forEach(p=>Plotly.Plots.resize(p))));</script>"
                 if INTERACTIVE else "")
    fonts = "".join(_font_face(name, weight) for name, weight in WEB_FONTS)
    style = (f"{fonts}:root{{{_tokens(LIGHT)}}}"
             f"@media (prefers-color-scheme:dark){{:root{{{_tokens(DARK)}}}}}{CSS}")
    n = len(results)
    analysed_by = who_text(info.get("run_by_name", ""), info["run_by"])
    valid = info["validation"].passed
    status = (f'<span class="pill {"good" if valid else "bad"}">{"&#10003;" if valid else "!"}&nbsp;Library '
              f'{"validated" if valid else "NOT validated"}</span>'
              + (f'<a class="pill good" href="#signoff">&#10003;&nbsp;Signed: {h(DECISIONS[signoff["decision"]])}</a>'
                 if signoff else '<a class="pill none" href="#signoff">Not signed yet</a>'))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="{h(__title__)} {__version__} by {h(__author__)}">
<title>FTIR Contamination Report</title><style>{style}</style>{plotly_js}</head><body>
<header class="top"><div class="top-in">{_logo_inline()}<div>
  <h1>FTIR contamination report</h1>
  <p>{n} spectr{"um" if n == 1 else "a"} &middot; {h(readable_time(info['run_at'], with_zone=True))} &middot;
  analysed by {h(analysed_by)}</p></div><div class="who">{status}</div></div></header>
<main>
{overview_html(results)}
<section class="panel"><h2>Summary</h2><div class="scroll"><table>
<tr><th>Sample</th><th>Verdict</th><th>Match</th><th class="num">r</th><th class="num">Lead</th><th>Compared as</th><th>Flags</th></tr>
{summary}</table></div></section>
{sections}
{signoff_html(signoff, n)}
<h2 class="part">Traceability</h2>
<div class="grid2">
  <section class="panel"><h2>Run information</h2><dl>
    <dt>Analysed</dt><dd>{h(readable_time(info['run_at'], with_zone=True))}</dd>
    <dt>By</dt><dd>{h(analysed_by)}</dd>
    <dt>Program</dt><dd>{h(info['program'])}</dd>
    <dt>Code SHA-256</dt><dd class="mono">{info['code_sha256']}</dd>
    <dt>Software</dt><dd>{h(info['software'])}</dd>
    <dt>Library</dt><dd>{h(info['library'])}</dd>
    <dt>Library SHA-256</dt><dd class="mono">{info['library_sha256']}</dd>
    <dt>Settings</dt><dd>{settings_html()}</dd></dl></section>
  <section class="panel"><h2>Validation and data integrity</h2>{validation_html(info['validation'])}
    <ul><li>Raw files are only read, never written. Each file's SHA-256 is recorded, so anyone can prove
    later that the report was made from exactly that file.</li>
    <li>Absorbance conversion, mode correction and the derivative are done on copies and used for matching
    only. The checks look at the raw absorbance.</li>
    <li>Every run is added to the audit log, every signature to the signature log; rows are never changed
    or deleted.</li>
    <li>The program suggests; a person reviews the raw spectra and signs.</li></ul></section>
</div>
{library_html(library)}
<footer>Generated with {h(__title__)} {__version__}, developed by {h(__author__)}</footer>
</main>{resize_js}</body></html>"""
    Path(path).write_text(page, encoding="utf-8")


def results_table(results):
    """The results as a flat table: one row per spectrum, lists turned into text."""
    return pd.DataFrame([{
        "file": r.spectrum.path.name, "sample": r.name, "unit": r.spectrum.unit, "mode": r.mode,
        "mode_source": r.mode_source, "compared_as": r.compared_as, "verdict": r.verdict, "match": r.match, "best": r.best,
        "r": r.r, "gap": r.gap, "second": r.runner_up, "ch": r.checks.ch, "ch_share": r.checks.ch_share,
        "oh": r.checks.oh, "oh_share": r.checks.oh_share, "max_A": r.checks.max_a,
        "co2_share": r.checks.co2_share, "noise": r.checks.noise,
        "key_bands_found": len(r.evidence.found) if r.evidence else "",
        "key_bands": r.evidence.n_key if r.evidence else "",
        "unexplained": "; ".join(f"{w:.0f}" for w in r.evidence.unexplained) if r.evidence else "",
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
    append_audit_log(results, info, audit_log)
    if signoff:
        append_signature(signoff, html_path, len(results), signature_log)
    return html_path
