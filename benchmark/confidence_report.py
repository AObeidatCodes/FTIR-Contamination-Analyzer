"""
FTIR Contamination Analyzer - the confidence report

Builds one self-contained web page from results/confidence_results.json, in the look of the benchmark report. It needs
no data files, and every number on the page comes from the results file:

    python -m benchmark.confidence --report-only

Short names used in this file:
    r = the results    d = the figures for one group

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import json
from pathlib import Path

from ftir_analyzer.report import CSS, _font_face, _logo_inline, _tokens
from ftir_analyzer.theme import DARK, LIGHT, WEB_FONTS

from .report import EXTRA_CSS, h, pct, row, stat, table

# Anything that differs from PROTOCOL_CONFIDENCE.md: it must be listed here, with what it changed.
DEVIATIONS = ["The report and README were reworded after the results were seen. No number or rule changed."]

MORE_CSS = """
.bars{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}
.bars figure{border:none;background:none;margin:0;overflow:visible}
.bars figcaption{font-size:14px;color:var(--ink-2);padding:0;margin:0 0 4px}
@media(max-width:700px){.bars{grid-template-columns:1fr}}
"""


def named_stat(title, size, limit):
    return (f"<div><span>{h(title)}</span><b>{size['median']:g} of 16</b>"
            f"<small>{size['n']} spectra</small><small>limit: {limit}</small></div>")


def strip(r):
    a, b, limit = r["versions"]["A"]["test"], r["versions"]["B"]["test"], r["short_list"]
    return ('<div class="stats">' + stat("All spectra: right material named", a["all"]["coverage"], "good")
            + named_stat("All spectra: materials named", a["all"]["lengths"], limit)
            + stat("ATR: right material named", b["ATR"]["coverage"], "good")
            + named_stat("ATR: materials named", b["ATR"]["lengths"], limit) + "</div>")


def result_rows(r):
    """One row per way of setting the minimum score, on the test spectra."""
    rows = []
    names = (("All spectra, one minimum", "A", "all", r["bars"]["A"]["one bar"]), ("All spectra, three minimums", "B", "all", None),
             ("Compared as ATR", "B", "ATR", r["bars"]["B"]["ATR"]),
             ("Compared as transmission", "B", "transmission", r["bars"]["B"]["transmission"]),
             ("Neither reading fitted", "B", "as measured", r["bars"]["B"]["as measured"]))
    for name, version, key, minimum in names:
        d = r["versions"][version]["test"][key]
        c, s = d["coverage"], d["lengths"]
        rows.append(row([h(name), "-" if minimum is None else f"{minimum:.2f}", f"{pct(c['share'])} ({c['k']} of {c['n']})",
                         f"{100 * c['low']:.1f} to {100 * c['high']:.1f}%", f"{s['median']:g}", s["empty"], s["one"], s["two_three"],
                         s["four_up"], "yes" if d["useful"] else "no"], ["", *["num"] * 9]))
    return table(["Spectra", "Minimum score", "Right material named", "95% range", "Typical number named", "None", "1", "2 to 3",
                  "4 or more", "Usable"], rows)


def picture(data, minimum, title):
    """The scores of the right material as bars, with a line at the minimum score: what is right of the line passes."""
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
        colour = "var(--accent)" if stop > minimum + 0.001 else "var(--line-strong)"
        marks += (f'<rect x="{x(start):.1f}" y="{height - bottom - tall:.1f}" width="{x(stop) - x(start) - 2:.1f}" height="{tall:.1f}" '
                  f'fill="{colour}"><title>r {start:.2f} to {stop:.2f}: {number} spectra</title></rect>')
    ticks = "".join(f'<text x="{x(v):.1f}" y="{height - 6}" text-anchor="middle">{v:g}</text>' for v in (0, 0.5, 1))
    axis = f'<line class="grid" x1="{left}" x2="{width - right}" y1="{height - bottom}" y2="{height - bottom}"/>'
    line = (f'<line x1="{x(minimum):.1f}" x2="{x(minimum):.1f}" y1="{top}" y2="{height - bottom}" stroke="var(--ink)" stroke-width="2"/>'
            f'<title>Minimum score: {minimum:.2f}</title>')
    return (f'<figure><figcaption>{h(title)}: minimum {minimum:.2f}</figcaption><svg class="chart" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="{h(title)}, minimum score {minimum:.2f}">{axis}{marks}{line}{ticks}</svg></figure>')


def pictures(r):
    groups, minimums = r["groups"], r["bars"]["B"]
    parts = [picture(r["picture"], r["bars"]["A"]["one bar"], "All spectra"),
             picture(groups["ATR"]["picture"], minimums["ATR"], "Compared as ATR"),
             picture(groups["transmission"]["picture"], minimums["transmission"], "Compared as transmission"),
             picture(groups["as measured"]["picture"], minimums["as measured"], "Neither reading fitted")]
    return f'<div class="bars">{"".join(parts)}</div>'


def material_table(r):
    a, b = r["versions"]["A"]["test"]["per_material"], r["versions"]["B"]["test"]["per_material"]
    rows = [row([h(name), a[name]["n"], f"{a[name]['hits']}", f"{a[name]['median_list']:g}", f"{b[name]['hits']}",
                 f"{b[name]['median_list']:g}"], ["", *["num"] * 5]) for name in sorted(a, key=lambda n: -a[n]["n"])]
    return table(["Material", "Test spectra", "One minimum: right material named", "Typical number named",
                  "Three minimums: right material named", "Typical number named"], rows)


def other_table(r):
    rows = []
    for name, version in (("One minimum", "A"), ("Three minimums", "B")):
        v = r["versions"][version]
        no, fibres, relatives = v["no_reference"], v["fibres_no_reference"], v["relatives"]
        rows.append(row([name, f"{no['empty']} of {no['n']}", f"{no['median']:g}", f"{fibres['empty']} of {fibres['n']}",
                         f"{fibres['median']:g}", f"{relatives['relative_on_list']} of {relatives['n']}"], ["", *["num"] * 5]))
    return table(["Minimum score", "Open Specy, no reference: nothing named", "Typical number named",
                  "Fibres, no reference: nothing named", "Typical number named", "Close relatives: relative named"], rows)


def fibre_table(r):
    rows = []
    for name, version in (("One minimum", "A"), ("Three minimums", "B")):
        d = r["versions"][version]["fibres"]["all"]
        c, s = d["coverage"], d["lengths"]
        rows.append(row([name, f"{c['k']} of {c['n']}", f"{100 * c['low']:.1f} to {100 * c['high']:.1f}%", f"{s['median']:g}", s["one"],
                         s["two_three"], s["four_up"]], ["", *["num"] * 6]))
    return table(["Minimum score", "Right material named", "95% range", "Typical number named", "1", "2 to 3", "4 or more"], rows)


def usable(r):
    tests = (r["versions"]["A"]["test"], r["versions"]["B"]["test"])
    return [key for test in tests for key, d in test.items() if isinstance(d, dict) and d.get("useful")]


def summary(r):
    """The result in plain sentences. Every number comes from the results file."""
    a, b = r["versions"]["A"]["test"], r["versions"]["B"]["test"]
    minimum, atr = r["bars"]["A"]["one bar"], r["bars"]["B"]["ATR"]
    found = usable(r)
    first = ("We tested whether the app can say how sure it is, using a measured figure instead of the score. "
             + ("It did not work well enough to use, so the app is unchanged." if not found
                else f"It worked well enough for: {h(', '.join(found))}. Adding it to the app needs a separate decision."))
    lines = [first,
             f"To include the right material 9 times out of 10, the app has to name about {a['all']['lengths']['median']:g} of its "
             f"16 materials. For spectra compared as ATR it is about {b['ATR']['lengths']['median']:g}. We set a limit of "
             f"{r['short_list']} before the test, because a longer list does not help anyone.",
             f"The right material often scores low on spectra from other labs. To avoid missing it, the minimum score has to be "
             f"very low ({minimum:.2f}, or {atr:.2f} for ATR), and then wrong materials pass as well."]
    return "".join(f'<p class="lead">{line}</p>' for line in lines)


def deviations():
    if not DEVIATIONS:
        return "<p>None.</p>"
    return '<ul class="plain">' + "".join(f"<li>{d}</li>" for d in DEVIATIONS) + "</ul>"


def build(results_path, target):
    """Write the report page and return its path."""
    r = json.loads(Path(results_path).read_text(encoding="utf-8"))
    counts, b = r["counts"], r["versions"]["B"]
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
<div class="title"><h1>Can the app say how sure it is?</h1>
<p>{h(r['protocol'])}. Program locked at <code>{h(r['locked_commit'])}</code>, run at <code>{h(r['ran_at_commit'])}</code> on {h(r['ran_on'])}.</p></div>

<h2 class="part">Result</h2>
<div class="panel">{summary(r)}</div>
{strip(r)}

<h2 class="part">What we did</h2>
<div class="panel"><p>The score r is not a percentage: 0.93 does not mean 93% sure. So we took spectra whose material is known and looked at the score the right material got on each one.</p>
<p>From {counts['calibration']} of them we found the minimum score that lets the right material through 90% of the time. Then we used that minimum on {counts['test']} other spectra. The app named every material at or above it, and we counted how often the right one was among them, and how many it named.</p>
<p>The charts show the scores of the right material. Blue bars pass the minimum score, grey bars do not. The method is called conformal prediction.</p>
{pictures(r)}</div>

<h2 class="part">All results on the test spectra</h2>
<div class="panel"><p class="small">Usable means the 95% range reaches 90% and the typical number named is at most {r['short_list']}. This was decided before the test.</p>{result_rows(r)}</div>

<h2 class="part">When the verdict is probable</h2>
<div class="panel"><p>{probable['n']} test spectra got a probable verdict. That material was among those named {probable['on_list']} times, and it was the only one named {probable['alone']} times.</p></div>

<h2 class="part">Materials with no reference, and close relatives</h2>
<div class="panel"><p>For a material with no reference, the right result is to name nothing. On Open Specy this rarely happened, because the minimum score is so low. On fibres it happened more often.</p>{other_table(r)}</div>

<h2 class="part">Fibres</h2>
<div class="panel"><p>The fibres took no part in setting the minimum score, and they had been scored before, so this is a second look and not proof. With the ATR minimum, {fibre_atr['lengths']['one']} of {fibre_atr['coverage']['n']} fibres with a reference had exactly one material named.</p>{fibre_table(r)}</div>

<h2 class="part">Per material</h2>
<div class="panel"><p class="small">An average can hide a poor material. EVOH and PK have no spectra in this set.</p>{material_table(r)}</div>

<h2 class="part">Limits</h2>
<div class="panel"><h4>Not fully blind</h4><ul class="plain">
<li>Using separate minimums for ATR and transmission was decided after seeing the benchmark, where ATR spectra scored much higher. Those were other spectra, but the choice was not blind.</li>
<li>The limit of {r['short_list']} was also set after seeing the benchmark.</li>
<li>The labels and counts of these spectra had been read before the test. Their scores had not.</li></ul></div>
<div class="panel"><h4>Weaknesses</h4><ul class="plain">
<li>Everything in the benchmark report still applies: Open Specy spectra are processed, coarse, mostly environmental, and have no physical-sample ID.</li>
<li>Spectra were split by source, so the two halves differ: {counts['calibration_clusters']} source groups set the minimum and {counts['test_clusters']} tested it. That may be why the result came out above 90% in some rows and below in others.</li>
<li>The test spectra hold {counts['doubtful_in_test']} doubtful labels, because of how the sources fell, so removing them changes nothing.</li>
<li>These figures say little about a fab. A lab would have to repeat this on its own spectra.</li>
<li>These spectra have now been used, so a later change to the verdict rule needs fresh data.</li></ul></div>
<div class="panel"><h4>Deviations from the protocol</h4>{deviations()}</div>
<p class="small">Library checksum <code>{h(r['library']['sha256'])}</code>. Rebuild this page with <code>python -m benchmark.confidence --report-only</code>.</p>
</main></body></html>"""
    target = Path(target)
    target.write_text(page, encoding="utf-8")
    return target
