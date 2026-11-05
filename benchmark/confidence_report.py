"""
FTIR Contamination Analyzer - the confidence report

Builds one self-contained web page from results/confidence_results.json, in the look of the benchmark report. It needs
no data files, and every number on the page comes from the results file:

    python -m benchmark.confidence --report-only

Short names used in this file:
    r = the results    v = one version's results    d = the figures for one group

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import json
from pathlib import Path

from ftir_analyzer.report import CSS, _font_face, _logo_inline, _tokens
from ftir_analyzer.theme import DARK, LIGHT, WEB_FONTS

from .report import EXTRA_CSS, h, margin_text, pct, row, stat, table

# Anything that differs from PROTOCOL_CONFIDENCE.md: it must be listed here, with what it changed.
DEVIATIONS = []

MORE_CSS = """
.bars{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}
.bars figure{border:none;background:none;margin:0;overflow:visible}
.bars figcaption{font-size:14px;color:var(--ink-2);padding:0;margin:0 0 4px}
@media(max-width:700px){.bars{grid-template-columns:1fr}}
"""


def median_stat(title, size):
    return (f"<div><span>{h(title)}</span><b>{size['median']:g} of 16</b>"
            f"<small>{size['n']} lists</small><small>limit set before the run: 3</small></div>")


def strip(r):
    a, b = r["versions"]["A"]["test"], r["versions"]["B"]["test"]
    return ('<div class="stats">' + stat("One bar: right material on the list", a["all"]["coverage"], "good")
            + median_stat("One bar: typical list", a["all"]["lengths"])
            + stat("Compared as ATR: right material on the list", b["ATR"]["coverage"], "good")
            + median_stat("Compared as ATR: typical list", b["ATR"]["lengths"]) + "</div>")


def group_rows(r):
    """One row per version and group, on the test half."""
    rows = []
    names = (("One bar for all", "A", "all", r["bars"]["A"]["one bar"]), ("Three bars, all", "B", "all", None),
             ("Compared as ATR", "B", "ATR", r["bars"]["B"]["ATR"]),
             ("Compared as transmission", "B", "transmission", r["bars"]["B"]["transmission"]),
             ("As measured, neither reading fits", "B", "as measured", r["bars"]["B"]["as measured"]))
    for name, version, key, bar in names:
        d = r["versions"][version]["test"][key]
        c, s = d["coverage"], d["lengths"]
        rows.append(row([h(name), "-" if bar is None else f"{bar:.2f}", f"{pct(c['share'])} ({c['k']} of {c['n']})",
                         f"{100 * c['low']:.1f} to {100 * c['high']:.1f}%", f"{s['median']:g}", s["empty"], s["one"], s["two_three"],
                         s["four_up"], "yes" if d["valid"] else "no", "yes" if d["short"] else "no",
                         "<b>yes</b>" if d["useful"] else "no"],
                        ["", *["num"] * 11]))
    return table(["Bar", "Height", "Right material on the list", "95% margin", "Median list", "Empty", "1", "2 to 3", "4 or more",
                  "Promise kept", "Short", "Useful"], rows)


def picture(data, bar, title):
    """The true scores as bars, with the bar drawn across them: what is right of the line clears it."""
    edges, counts = data["edges"], data["counts"]
    width, height, left, right, top, bottom = 320, 150, 8, 8, 8, 22
    low, high = edges[0], edges[-1]
    x = lambda v: left + (width - left - right) * (v - low) / (high - low)
    most = max(counts) or 1
    marks = ""
    for start, stop, number in zip(edges, edges[1:], counts):
        if not number:
            continue
        tall = (height - top - bottom) * number / most
        colour = "var(--accent)" if stop > bar + 0.001 else "var(--line-strong)"
        marks += (f'<rect x="{x(start):.1f}" y="{height - bottom - tall:.1f}" width="{x(stop) - x(start) - 2:.1f}" height="{tall:.1f}" '
                  f'fill="{colour}"><title>r {start:.2f} to {stop:.2f}: {number} spectra</title></rect>')
    ticks = "".join(f'<text x="{x(v):.1f}" y="{height - 6}" text-anchor="middle">{v:g}</text>' for v in (0, 0.5, 1))
    axis = f'<line class="grid" x1="{left}" x2="{width - right}" y1="{height - bottom}" y2="{height - bottom}"/>'
    line = (f'<line x1="{x(bar):.1f}" x2="{x(bar):.1f}" y1="{top}" y2="{height - bottom}" stroke="var(--ink)" stroke-width="2"/>'
            f'<title>The bar: {bar:.2f}</title>')
    return (f'<figure><figcaption>{h(title)}: bar {bar:.2f}</figcaption><svg class="chart" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{h(title)}, bar at {bar:.2f}">{axis}{marks}{line}{ticks}</svg></figure>')


def pictures(r):
    groups, bars = r["groups"], r["bars"]["B"]
    parts = [picture(r["picture"], r["bars"]["A"]["one bar"], "All spectra"),
             picture(groups["ATR"]["picture"], bars["ATR"], "Compared as ATR"),
             picture(groups["transmission"]["picture"], bars["transmission"], "Compared as transmission"),
             picture(groups["as measured"]["picture"], bars["as measured"], "As measured")]
    return f'<div class="bars">{"".join(parts)}</div>'


def material_table(r):
    a, b = r["versions"]["A"]["test"]["per_material"], r["versions"]["B"]["test"]["per_material"]
    rows = [row([h(name), a[name]["n"], f"{a[name]['hits']}", f"{a[name]['median_list']:g}", f"{b[name]['hits']}",
                 f"{b[name]['median_list']:g}"], ["", *["num"] * 5]) for name in sorted(a, key=lambda n: -a[n]["n"])]
    return table(["Material", "Test spectra", "One bar: on the list", "One bar: median list", "Three bars: on the list",
                  "Three bars: median list"], rows)


def other_table(r):
    rows = []
    for name, version in (("One bar", "A"), ("Three bars", "B")):
        v = r["versions"][version]
        no, fibres, relatives = v["no_reference"], v["fibres_no_reference"], v["relatives"]
        rows.append(row([name, f"{no['empty']} of {no['n']}", f"{no['median']:g}", f"{fibres['empty']} of {fibres['n']}",
                         f"{fibres['median']:g}", f"{relatives['relative_on_list']} of {relatives['n']}"], ["", *["num"] * 5]))
    return table(["Bar", "Open Specy, no reference: empty list", "Median list", "Fibres, no reference: empty list", "Median list",
                  "Close relatives: relative on the list"], rows)


def fibre_table(r):
    rows = []
    for name, version in (("One bar", "A"), ("Three bars", "B")):
        d = r["versions"][version]["fibres"]["all"]
        c, s = d["coverage"], d["lengths"]
        rows.append(row([name, f"{c['k']} of {c['n']}", f"{100 * c['low']:.1f} to {100 * c['high']:.1f}%", f"{s['median']:g}", s["one"],
                         s["two_three"], s["four_up"]], ["", *["num"] * 6]))
    return table(["Bar", "Right material on the list", "95% margin", "Median list", "1", "2 to 3", "4 or more"], rows)


def any_useful(r):
    tests = (r["versions"]["A"]["test"], r["versions"]["B"]["test"])
    return [key for test in tests for key, d in test.items() if isinstance(d, dict) and d.get("useful")]


def take_away(r):
    """The result in plain sentences. Every number comes from the results file."""
    a, b = r["versions"]["A"]["test"], r["versions"]["B"]["test"]
    bar_all, bar_atr = r["bars"]["A"]["one bar"], r["bars"]["B"]["ATR"]
    useful = any_useful(r)
    lines = [f"<b>The promise held.</b> On {r['counts']['test']} spectra that took no part in setting the bar, the right material "
             f"was on the list {pct(a['all']['coverage']['share'])} of the time with one bar and "
             f"{pct(b['all']['coverage']['share'])} with three, against a target of 90%.",
             f"<b>The lists are too long to help.</b> The typical list held {a['all']['lengths']['median']:g} of the 16 materials. "
             f"For spectra compared as ATR, the best group, it held {b['ATR']['lengths']['median']:g}, against a limit of "
             f"{r['short_list']} set before the run.",
             f"<b>Why.</b> The right material often scores low, so to catch 90% of right answers the bar has to drop to "
             f"{bar_all:.2f} ({bar_atr:.2f} for ATR). At that height wrong materials clear it too."]
    lines.append("<b>Decision.</b> Nothing was useful by the rule set before the run, so the app stays as it is."
                 if not useful else f"<b>Decision.</b> Useful for: {h(', '.join(useful))}. Showing it needs a separate yes.")
    return "".join(f'<p class="lead">{line}</p>' for line in lines)


def deviations():
    if not DEVIATIONS:
        return "<p>None.</p>"
    return '<ul class="plain">' + "".join(f"<li>{d}</li>" for d in DEVIATIONS) + "</ul>"


def build(results_path, target):
    """Write the report page and return its path."""
    r = json.loads(Path(results_path).read_text(encoding="utf-8"))
    counts, a, b = r["counts"], r["versions"]["A"], r["versions"]["B"]
    fonts = "".join(_font_face(name, family, weight) for name, family, weight in WEB_FONTS)
    style = (f"{fonts}:root{{{_tokens(LIGHT)}}}@media screen and (prefers-color-scheme:dark){{:root{{{_tokens(DARK)}}}"
             f"html{{color-scheme:dark}}}}{CSS}{EXTRA_CSS}{MORE_CSS}")
    probable = b["test"]["probable"]
    fibre_atr = b["fibres"]["ATR"]
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FTIR Confidence Report</title>
<style>{style}</style></head><body>
<header class="bar"><div class="bar-in"><span class="brand">{_logo_inline()}<span>FTIR Contamination Analyzer</span></span></div></header>
<main>
<div class="title"><h1>Calibrated confidence</h1>
<p>{h(r['protocol'])}. Program locked at <code>{h(r['locked_commit'])}</code>, run at <code>{h(r['ran_at_commit'])}</code> on {h(r['ran_on'])}.</p></div>

<h2 class="part">The result</h2>
<div class="panel">{take_away(r)}</div>
{strip(r)}

<h2 class="part">How it works</h2>
<div class="panel"><p>The score r is not a probability. So the method measures one. It takes spectra of known material and notes the score of the right material on each. The bar is set so that 90% of those scores clear it. On a new sample, every material at or above the bar goes on a list, and the claim is that the right material is on that list about 90% of the time. This is conformal prediction, in its simplest form.</p>
<p>The bar was set on {counts['calibration']} spectra and tested on {counts['test']} others, never scored before this step. In each picture below, blue is what clears the bar. A low bar means many right answers scored badly.</p>
{pictures(r)}</div>

<h2 class="part">Every version, on the test half</h2>
<div class="panel"><p class="small">Useful means the promise was kept and the median list had at most {r['short_list']} materials, as fixed before the run.</p>{group_rows(r)}</div>

<h2 class="part">When the verdict is probable</h2>
<div class="panel"><p>{probable['n']} test spectra got a probable. With three bars that material was on the list {probable['on_list']} times, and alone on it {probable['alone']} times, so the list adds nothing to a probable here.</p></div>

<h2 class="part">Materials with no reference, and close relatives</h2>
<div class="panel"><p>An empty list is the right answer for a material with no reference. The bar is too low for that on Open Specy. It works better on fibres, where the ATR bar applies.</p>{other_table(r)}</div>

<h2 class="part">The fibre check</h2>
<div class="panel"><p>The fibres set nothing. They show whether a bar set on Open Specy travels to different data. With the ATR bar, {fibre_atr['lengths']['one']} of {fibre_atr['coverage']['n']} fibres with a reference got a list of exactly one material.</p>{fibre_table(r)}</div>

<h2 class="part">Per material</h2>
<div class="panel"><p class="small">An average can hide a poor material. EVOH and PK have no spectra in this set.</p>{material_table(r)}</div>

<h2 class="part">Limits</h2>
<div class="panel"><h4>Disclosures</h4><ul class="plain">
<li>The three-bar version was chosen after seeing the benchmark, where spectra compared as ATR scored much higher. Those were other spectra, but the choice is not blind.</li>
<li>The list limit of {r['short_list']} was also set after seeing the benchmark.</li>
<li>The labels and counts of the locked set had been read. Its scores had not.</li>
<li>The fibres had been scored before, so they are a check and not a proof.</li></ul></div>
<div class="panel"><h4>Weaknesses</h4><ul class="plain">
<li>Everything in the benchmark report still applies: Open Specy spectra are processed, coarse, mostly environmental, and have no physical-sample ID.</li>
<li>Spectra were split by cluster, so the two halves differ: {counts['calibration_clusters']} clusters set the bar and {counts['test_clusters']} tested it. That may be why coverage came out above 90% in some groups and below in others.</li>
<li>The test half holds {counts['doubtful_in_test']} spectra with a doubtful label, because of how the clusters fell, so the figures without them are the same.</li>
<li>A bar set on Open Specy says little about a fab. A lab would have to set its own, on its own measurements.</li>
<li>The test half is now used up, so a later change to the verdict rule needs fresh data.</li></ul></div>
<div class="panel"><h4>Deviations from the protocol</h4>{deviations()}</div>
<p class="small">The promise is {margin_text(a['test']['all']['coverage'])} with one bar. Library checksum <code>{h(r['library']['sha256'])}</code>. Rebuild this page with <code>python -m benchmark.confidence --report-only</code>.</p>
</main></body></html>"""
    target = Path(target)
    target.write_text(page, encoding="utf-8")
    return target
