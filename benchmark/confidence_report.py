"""
FTIR Contamination Analyzer - the confidence report

Builds one self-contained web page from results/confidence_results.json. It needs no data files, and every number on
the page comes from the results file:

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

from .report import EXTRA_CSS, h, pct, row, table

# Anything that differs from PROTOCOL_CONFIDENCE.md: it must be listed here, with what it changed.
DEVIATIONS = ["The report wording was changed after the results were seen. No number or rule changed."]

MORE_CSS = """
.bars{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}
.bars figure{border:none;background:none;margin:0;overflow:visible}
.bars figcaption{font-size:14px;color:var(--ink-2);padding:0;margin:0 0 4px}
@media(max-width:700px){.bars{grid-template-columns:1fr}}
"""


def result_rows(r):
    """One row per threshold, on the test spectra."""
    rows = []
    names = (("All, one threshold", "A", "all", r["bars"]["A"]["one bar"]), ("All, three thresholds", "B", "all", None),
             ("Compared as ATR", "B", "ATR", r["bars"]["B"]["ATR"]),
             ("Compared as transmission", "B", "transmission", r["bars"]["B"]["transmission"]),
             ("Neither reading fitted", "B", "as measured", r["bars"]["B"]["as measured"]))
    for name, version, key, threshold in names:
        d = r["versions"][version]["test"][key]
        c, s = d["coverage"], d["lengths"]
        rows.append(row([h(name), "-" if threshold is None else f"{threshold:.2f}",
                         f"{pct(c['share'])}&nbsp;({c['k']}&nbsp;of&nbsp;{c['n']})",
                         f"{100 * c['low']:.1f}&nbsp;to&nbsp;{100 * c['high']:.1f}%", f"{s['median']:g}", s["empty"], s["one"], s["two_three"],
                         s["four_up"], "yes" if d["useful"] else "no"], ["", *["num"] * 9]))
    return table(["Spectra", "Threshold r", "Coverage", "95% interval", "Median set size", "Empty", "1", "2 to 3", "4 or more",
                  "Usable"], rows)


def picture(data, threshold, title):
    """The true-material scores as a histogram, with a line at the threshold."""
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
        colour = "var(--accent)" if stop > threshold + 0.001 else "var(--line-strong)"
        marks += (f'<rect x="{x(start):.1f}" y="{height - bottom - tall:.1f}" width="{x(stop) - x(start) - 2:.1f}" height="{tall:.1f}" '
                  f'fill="{colour}"><title>r {start:.2f} to {stop:.2f}: {number} spectra</title></rect>')
    ticks = "".join(f'<text x="{x(v):.1f}" y="{height - 6}" text-anchor="middle">{v:g}</text>' for v in (0, 0.5, 1))
    axis = f'<line class="grid" x1="{left}" x2="{width - right}" y1="{height - bottom}" y2="{height - bottom}"/>'
    line = (f'<line x1="{x(threshold):.1f}" x2="{x(threshold):.1f}" y1="{top}" y2="{height - bottom}" stroke="var(--ink)" stroke-width="2"/>'
            f'<title>Threshold: {threshold:.2f}</title>')
    return (f'<figure><figcaption>{h(title)}, r = {threshold:.2f}</figcaption><svg class="chart" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="{h(title)}, threshold {threshold:.2f}">{axis}{marks}{line}{ticks}</svg></figure>')


def pictures(r):
    groups, thresholds = r["groups"], r["bars"]["B"]
    parts = [picture(r["picture"], r["bars"]["A"]["one bar"], "All spectra"),
             picture(groups["ATR"]["picture"], thresholds["ATR"], "Compared as ATR"),
             picture(groups["transmission"]["picture"], thresholds["transmission"], "Compared as transmission"),
             picture(groups["as measured"]["picture"], thresholds["as measured"], "Neither reading fitted")]
    return f'<div class="bars">{"".join(parts)}</div>'


def material_table(r):
    a, b = r["versions"]["A"]["test"]["per_material"], r["versions"]["B"]["test"]["per_material"]
    rows = [row([h(name), a[name]["n"], a[name]["hits"], f"{a[name]['median_list']:g}", b[name]["hits"],
                 f"{b[name]['median_list']:g}"], ["", *["num"] * 5]) for name in sorted(a, key=lambda n: -a[n]["n"])]
    return table(["Material", "Spectra", "Covered, one threshold", "Median set", "Covered, three thresholds", "Median set"], rows)


def other_table(r):
    """The remaining figures the protocol asks for, one row each."""
    a, b = r["versions"]["A"], r["versions"]["B"]

    def line(name, one, three):
        return row([name, one, three], ["", "num", "num"])

    def of(k, n):
        return f"{k} of {n}"

    rows = [line("Open Specy, no reference: empty set", of(a["no_reference"]["empty"], a["no_reference"]["n"]),
                 of(b["no_reference"]["empty"], b["no_reference"]["n"])),
            line("Close relatives: relative in the set", of(a["relatives"]["relative_on_list"], a["relatives"]["n"]),
                 of(b["relatives"]["relative_on_list"], b["relatives"]["n"])),
            line("Probable verdicts: material in the set", of(a["test"]["probable"]["on_list"], a["test"]["probable"]["n"]),
                 of(b["test"]["probable"]["on_list"], b["test"]["probable"]["n"])),
            line("Probable verdicts: set of one", of(a["test"]["probable"]["alone"], a["test"]["probable"]["n"]),
                 of(b["test"]["probable"]["alone"], b["test"]["probable"]["n"])),
            line("Fibres with a reference: coverage", of(a["fibres"]["all"]["coverage"]["k"], a["fibres"]["all"]["coverage"]["n"]),
                 of(b["fibres"]["all"]["coverage"]["k"], b["fibres"]["all"]["coverage"]["n"])),
            line("Fibres with a reference: median set size", f"{a['fibres']['all']['lengths']['median']:g}",
                 f"{b['fibres']['all']['lengths']['median']:g}"),
            line("Fibres with a reference: set of one", of(a["fibres"]["all"]["lengths"]["one"], a["fibres"]["all"]["lengths"]["n"]),
                 of(b["fibres"]["all"]["lengths"]["one"], b["fibres"]["all"]["lengths"]["n"])),
            line("Fibres, no reference: empty set", of(a["fibres_no_reference"]["empty"], a["fibres_no_reference"]["n"]),
                 of(b["fibres_no_reference"]["empty"], b["fibres_no_reference"]["n"]))]
    return table(["Measure", "One threshold", "Three thresholds"], rows)


def usable(r):
    tests = (r["versions"]["A"]["test"], r["versions"]["B"]["test"])
    return [key for test in tests for key, d in test.items() if isinstance(d, dict) and d.get("useful")]


def summary(r):
    """One short paragraph. Every number comes from the results file."""
    a, b = r["versions"]["A"]["test"], r["versions"]["B"]["test"]
    found = usable(r)
    verdict = "Not usable, and the app was not changed." if not found else f"Usable for: {h(', '.join(found))}."
    return (f"{verdict} At the 90% target, the median prediction set held {a['all']['lengths']['median']:g} of the 16 materials, "
            f"or {b['ATR']['lengths']['median']:g} for spectra compared as ATR. The limit set before the test was {r['short_list']}.")


def build(results_path, target):
    """Write the report page and return its path."""
    r = json.loads(Path(results_path).read_text(encoding="utf-8"))
    counts = r["counts"]
    fonts = "".join(_font_face(name, family, weight) for name, family, weight in WEB_FONTS)
    style = (f"{fonts}:root{{{_tokens(LIGHT)}}}@media screen and (prefers-color-scheme:dark){{:root{{{_tokens(DARK)}}}"
             f"html{{color-scheme:dark}}}}{CSS}{EXTRA_CSS}{MORE_CSS}")
    changes = "".join(f"<li>{d}</li>" for d in DEVIATIONS) or "<li>None.</li>"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FTIR Confidence Test</title>
<style>{style}</style></head><body>
<header class="bar"><div class="bar-in"><span class="brand">{_logo_inline()}<span>FTIR Contamination Analyzer</span></span></div></header>
<main>
<div class="title"><h1>Confidence test</h1>
<p>{h(r['protocol'])}. Program locked at <code>{h(r['locked_commit'])}</code>, run at <code>{h(r['ran_at_commit'])}</code> on {h(r['ran_on'])}.</p></div>

<div class="panel" style="margin-top:24px"><p style="margin:0">{summary(r)}</p></div>

<div class="panel"><h4>Method</h4>
<p style="margin:0">Split conformal prediction at 90% coverage, using the Pearson r of the true material. Calibration: {counts['calibration']} spectra. Test: {counts['test']} spectra. Both come from the locked Open Specy set, split by source. A material is in the prediction set if its r reaches the threshold. One threshold was set for all spectra, and one for each way a spectrum was compared. A result is usable if the 95% interval reaches 90% and the median set size is at most {r['short_list']}.</p></div>

<div class="panel"><h4>Results on the test spectra</h4>{result_rows(r)}</div>

<div class="panel"><h4>True-material scores on the calibration spectra</h4>{pictures(r)}</div>

<div class="panel"><h4>Per material, test spectra</h4>{material_table(r)}</div>

<div class="panel"><h4>Other results</h4>{other_table(r)}</div>

<div class="panel"><h4>Limits</h4><ul class="plain">
<li>Using separate thresholds, and the limit of {r['short_list']}, were decided after seeing the benchmark. The labels and counts of these spectra had been read, but not their scores.</li>
<li>The fibres were scored in the benchmark, so they are a second look and not independent proof.</li>
<li>Open Specy spectra are processed, coarse and mostly environmental, and have no physical-sample ID.</li>
<li>The calibration and test spectra come from different sources ({counts['calibration_clusters']} and {counts['test_clusters']} groups), so coverage can differ from 90%.</li>
<li>All doubtful labels fell in the calibration spectra, so removing them changes no test result.</li>
<li>EVOH and PK have no spectra in this test.</li>
<li>These spectra are now used, so a later change to the verdict rule needs fresh data.</li></ul></div>

<div class="panel"><h4>Deviations from the protocol</h4><ul class="plain">{changes}</ul></div>
<p class="small">Library checksum <code>{h(r['library']['sha256'])}</code>. Rebuild: <code>python -m benchmark.confidence --report-only</code></p>
</main></body></html>"""
    target = Path(target)
    target.write_text(page, encoding="utf-8")
    return target
