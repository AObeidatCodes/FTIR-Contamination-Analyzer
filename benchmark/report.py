"""
FTIR Contamination Analyzer - the benchmark report

Builds one self-contained web page from results/results.json. It needs no data files, and every number on the page
comes from the results file:

    python -m benchmark --report-only

Short names used in this file:
    r = the results    k = how many    n = out of how many

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import html
import json
from pathlib import Path

from ftir_analyzer.report import CSS, _font_face, _logo_inline, _tokens
from ftir_analyzer.theme import DARK, LIGHT, WEB_FONTS

from .sets import FIBRES, IN, OPEN_SPECY, OUT
from .stress import BLUR, DRIFT, LEVELS, NOISE, SHIFT

# Anything that differs from PROTOCOL.md: the protocol requires it to be listed here, with what it changed.
DEVIATIONS = [
    ("Open Specy spectra with no material: 2,128, not the 2,194 in the protocol.",
     "A count only. 66 of the 2,194 are NIST spectra, which are left out first."),
    ("OpenFTIR label fix, made before anything was scored: <code>GF-PVC043</code> is read as PVC.",
     "This affects the OpenFTIR figures only."),
    ("Missing points are dropped from Open Specy spectra before analysis, as the program's file reader does.",
     "1,022 of 4,814 spectra have some. This was fixed before any score was seen."),
    ("Added after the results were seen: the lead rule on the extended library, results by comparison mode, and the "
     "not-right count in the extended table.", "No rule, threshold, label or data choice changed."),
    ("The report wording was shortened after the results were seen.", "No number changed."),
]

EXTRA_CSS = """
:root{--second:#C4742F}
.keys{display:flex;flex-wrap:wrap;gap:4px 20px;font-size:14px;color:var(--ink-2);margin:0 0 8px;padding:0;list-style:none}
.keys li{display:flex;align-items:center;gap:8px}.keys i{width:10px;height:10px;border-radius:3px;flex:none}
.conf{font-size:13px;min-width:760px}.conf th,.conf td{padding:5px 4px;text-align:center;border-bottom:1px solid var(--line);
  font-variant-numeric:tabular-nums}
.conf th:first-child,.conf td:first-child{text-align:left;white-space:nowrap;padding-right:12px}
.conf thead th{font-size:13px;vertical-align:bottom}
.conf tr.gap td{border-bottom:none;padding-top:16px;color:var(--muted);text-align:left}
.conf .sum{color:var(--muted)}
.multi{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px}
.multi figure{border:none;background:none;margin:0;overflow:visible}
.multi figcaption{font-size:14px;color:var(--ink-2);padding:0;margin:0 0 4px}
.chart{display:block;width:100%;height:auto}
.chart text{font:12px 'Inter',system-ui,sans-serif;fill:var(--muted)}
.chart .grid{stroke:var(--line);stroke-width:1}
details{margin-top:12px}summary{cursor:pointer;color:var(--accent-ink);font-size:14px}
.plain{margin:0;padding-left:20px}.plain li{margin:6px 0;max-width:820px}
code{font-family:'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-size:.9em}
@media(max-width:900px){.multi{grid-template-columns:repeat(2,1fr)}.bar nav{display:none}}
"""

NAMES = {FIBRES: "Fibres", OPEN_SPECY: "Open Specy"}
TESTS = ((NOISE, "Noise"), (DRIFT, "Baseline drift"), (SHIFT, "Shifted bands"), (BLUR, "Lower resolution"))
FIRST, SECOND = "var(--accent)", "var(--second)"          # checked for colour-blind readers, light and dark


def h(text):
    return html.escape(str(text), quote=True)


def pct(value, digits=1):
    return "n/a" if value is None else f"{100 * value:.{digits}f}%"


def count(number):
    return f"{number:,}"


def plain(text):
    """Text that stays on one line in a table."""
    return h(text).replace(" ", "&nbsp;")


def of(s):
    return f"{pct(s['share'])}&nbsp;({count(s['k'])}&nbsp;of&nbsp;{count(s['n'])})"


def interval(s):
    return f"{100 * s['low']:.1f}&nbsp;to&nbsp;{100 * s['high']:.1f}%"


def row(cells, kinds=()):
    out = []
    for i, cell in enumerate(cells):
        kind = f' class="{kinds[i]}"' if i < len(kinds) and kinds[i] else ""
        out.append(f"<td{kind}>{cell}</td>")
    return "<tr>" + "".join(out) + "</tr>"


def table(headers, rows, numeric_from=1):
    head = "".join(f'<th{" class=num" if i >= numeric_from else ""}>{h(t)}</th>' for i, t in enumerate(headers))
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def result_table(r):
    f, o, no = r["headline"][FIBRES], r["headline"][OPEN_SPECY], r["without_doubtful"][OPEN_SPECY]
    measures = (("False probable, no reference", "false_probable"), ("Right, of probable answers", "strict_right"),
                ("Right or right family, of probable answers", "family_right"),
                ("Probable, of samples with a reference", "coverage"), ("True material ranked first", "best_match"))
    rows = [row([name, of(f[key]), interval(f[key]), of(o[key]), interval(o[key])], ["", *["num"] * 4]) for name, key in measures]
    rows += [row([name, "-", "-", of(no[key]), interval(no[key])], ["", *["num"] * 4])
             for name, key in (("False probable, without doubtful labels", "false_probable"),
                               ("Right of probable, without doubtful labels", "strict_right"))]
    return table(["Measure", "Fibres", "95% interval", "Open Specy", "95% interval"], rows)


def outcome_table(r):
    f, o = r["headline"][FIBRES], r["headline"][OPEN_SPECY]

    def values(line):
        buckets, silent = line["buckets"], line["no_answer"]
        return (buckets.get("right", 0), buckets.get("right family", 0), buckets.get("wrong", 0), silent["weak_at_truth"],
                silent["weak_elsewhere"], silent["no_reliable_match"])

    names = ("Probable, right", "Probable, right family", "Probable, wrong", "Weak, true material named", "Weak, other material named",
             "No reliable match")
    rows = [row([name, count(a), count(b)], ["", "num", "num"]) for name, a, b in zip(names, values(f), values(o))]
    return table(["Outcome, samples with a reference", "Fibres", "Open Specy"], rows)


def material_table(items, kind):
    number = ["", *["num"] * 7]
    if kind == IN:
        rows = [row([h(m["truth"]), m["n"], m["right"], m["family"], m["wrong"], m["weak"], m["none"], f"{m['median_r']:.2f}"],
                    number) for m in items]
        return table(["Material", "Samples", "Right", "Right family", "Wrong", "Weak", "No match", "Median r"], rows)
    rows = [row([h(m["truth"]), m["n"], m["false_probable"], m["weak"], m["none"], f"{m['median_r']:.2f}",
                 h(", ".join(f"{k} {v}" for k, v in m["named"].items()) or "-")], [*number[:6], ""]) for m in items]
    return table(["Material", "Samples", "False probable", "Weak", "No match", "Median r", "Named as"], rows)


def confusion(items, dataset):
    """True material down, what was named across. Numbers in the cells, so colour is never the only signal."""
    items = [m for m in items if m["dataset"] == dataset and m["kind"] in (IN, OUT)]
    named = sorted({k for m in items for k in m["named"]})
    inside = [m for m in items if m["kind"] == IN]
    outside = [m for m in items if m["kind"] == OUT]
    head = "<th>True material</th>" + "".join(f"<th>{h(k)}</th>" for k in named) + "<th>Weak</th><th>No match</th>"

    def cells(m):
        out = [f"<td>{h(m['truth'])} <span class=sum>{m['n']}</span></td>"]
        for k in named:
            v = m["named"].get(k, 0)
            colour = "var(--good)" if k == m["truth"] else "var(--bad)"
            tint = f"color-mix(in srgb,{colour} {12 + 60 * v / m['n']:.0f}%,transparent)"
            out.append(f'<td style="background:{tint}" title="{h(m["truth"])} called {h(k)}: {v}">{v}</td>' if v else "<td></td>")
        out += [f'<td class=sum>{m[k] or ""}</td>' for k in ("weak", "none")]
        return "<tr>" + "".join(out) + "</tr>"

    span = len(named) + 3
    body = (f'<tr class=gap><td colspan={span}>With a reference</td></tr>' + "".join(cells(m) for m in inside)
            + f'<tr class=gap><td colspan={span}>No reference</td></tr>' + "".join(cells(m) for m in outside))
    return f'<div class="scroll"><table class="conf"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def level_text(test, level):
    if level == 0:
        return "none"
    return f"{100 * level:g}%" if test in (NOISE, DRIFT) else f"{level:g}"


def line_chart(test, series):
    """One panel of the small multiples, 0 to 100% on one axis. series: [(name, colour, [share or None])]."""
    levels = (0, *LEVELS[test])
    width, height, left, right, top, bottom = 260, 150, 34, 10, 8, 24
    x = lambda i: left + (width - left - right) * i / (len(levels) - 1)
    y = lambda v: top + (height - top - bottom) * (1 - v)
    grid = "".join(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v * 100:.0f}</text>' for v in (0, 0.5, 1))
    ticks = "".join(f'<text x="{x(i):.1f}" y="{height - 6}" text-anchor="middle">{level_text(test, level)}</text>'
                    for i, level in enumerate(levels))
    marks = ""
    for name, colour, values in series:
        points = [(x(i), y(v), v, levels[i]) for i, v in enumerate(values) if v is not None]
        marks += (f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b, _, _ in points)}" fill="none" stroke="{colour}" '
                  'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        marks += "".join(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4" fill="{colour}" stroke="var(--surface)" stroke-width="2">'
                         f'<title>{h(name)}, {level_text(test, lv)}: {100 * v:.1f}%</title></circle>' for a, b, v, lv in points)
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">{grid}{ticks}{marks}</svg>'


def stress_rows(r, dataset, test):
    found = {s["level"]: s for s in r["stress"] if s["dataset"] == dataset and s["test"] == test}
    return [found.get(level) for level in (0, *LEVELS[test])]


def stress_panels(r, title, measure):
    figures = ""
    for test, name in TESTS:
        series = []
        for dataset, colour in ((FIBRES, FIRST), (OPEN_SPECY, SECOND)):
            series.append((NAMES[dataset], colour, [measure(s) if s else None for s in stress_rows(r, dataset, test)]))
        unit = "cm⁻¹" if test in (SHIFT, BLUR) else "of range"
        figures += f"<figure><figcaption>{h(name)}, {unit}</figcaption>{line_chart(test, series)}</figure>"
    return f'<h4>{h(title)}</h4><div class="multi">{figures}</div>'


def stress_table(r):
    rows = []
    for s in r["stress"]:
        if s["level"] == 0:
            continue
        rows.append(row([NAMES[s["dataset"]], h(s["test"]), level_text(s["test"], s["level"]), f"{s['same_answer']} of {s['n']}",
                         f"{s['right']} of {s['n_in']}", s["not_right"], f"{s['false_probable']} of {s['n_out']}"],
                        ["", "", "num", "num", "num", "num", "num"]))
    return ('<details><summary>Table</summary>'
            + table(["Set", "Test", "Level", "Same answer as clean", "Right", "Probable, not right", "False probable"], rows, 2)
            + "</details>")


def lead_table(r):
    rows = []
    for dataset in (FIBRES, OPEN_SPECY):
        for label, lead in (("16 references", r["lead_rule"]), (f"{r['extended']['references']} references", r["extended"]["lead_rule"])):
            d = lead[dataset]
            rows.append(row([plain(NAMES[dataset]), plain(label), count(d["probable_with"]), count(d["probable_without"]),
                             d["extra_right"], d["extra_wrong_material"] + d["extra_false_probable"],
                             h(", ".join(f"{k} {v}" for k, v in d["held"].items()) or "-")], ["", "", *["num"] * 4, ""]))
    return table(["Set", "Library", "Probable with lead", "Without lead", "Right held back", "Wrong stopped",
                  "True materials held back"], rows, 2)


def relatives(r):
    rows = [row([NAMES.get(t["dataset"], t["dataset"]), h(t["truth"]), h(t["relative"]), t["n"], t["relative_named"], t["wrong"],
                 t["no_answer"]], ["", "", "", "num", "num", "num", "num"]) for t in r["relatives"]]
    return table(["Set", "Material", "Closest reference", "Samples", "Probable, the relative", "Probable, other", "No answer"], rows, 3)


def contributors(r):
    rows = [row([h(c["contributor"]), c["n"], f"{c['right']} of {c['probable']}" if c["probable"] else "-",
                 f"{c['probable']} of {c['in_library']}" if c["in_library"] else "-",
                 f"{c['false_probable']} of {c['not_in_library']}" if c["not_in_library"] else "-"], ["", *["num"] * 4])
            for c in r["per_contributor"]]
    return table(["Contributor", "Spectra", "Right, of probable", "Probable, with a reference", "False probable, no reference"], rows)


def not_right(line):
    """(probable answers, how many of them were not right), over materials with and without a reference."""
    right, false = line["strict_right"], line["false_probable"]
    return right["n"] + false["k"], right["n"] - right["k"] + false["k"]


def extended_table(r):
    e, rows = r["extended"], []
    for dataset in (FIBRES, OPEN_SPECY):
        for label, line in (("16 references", e["default_same_spectra"][dataset]), (f"{e['references']} references", e["extended"][dataset])):
            probable, bad = not_right(line)
            rows.append(row([plain(NAMES[dataset]), plain(label), count(probable), line["strict_right"]["k"], bad,
                             pct(bad / probable if probable else None), count(line["coverage"]["n"]),
                             count(line["false_probable"]["n"])], ["", "", *["num"] * 6]))
    return table(["Set", "Library", "Probable", "Right", "Not right", "Share not right", "With a reference", "No reference"], rows, 2)


def reading_table(r):
    rows = [row([{"unknown": "Neither reading fitted"}.get(x["reading"], f"As {x['reading']}"), count(x["n"]),
                 x["probable"], pct(x["probable"] / x["n"]), f"{x['median_r']:.2f}"], ["", *["num"] * 4]) for x in r["by_reading"]]
    return table(["Compared", "Spectra", "Probable", "Share", "Median r"], rows)


def failures(r):
    rows = [row([NAMES.get(f["dataset"], f["dataset"]), h(f["truth"]), h(f["best_material"]), f"{f['r']:.3f}", f"{f['gap']:.3f}",
                 h(f["contributor"][:26]), h(f["label"][:60])], ["", "", "", "num", "num", "", ""]) for f in r["failures"]]
    return table(["Set", "True material", "Called", "r", "Lead", "Contributor", "Label"], rows, 3)


def repeatability(r):
    p = r["repeatability"]
    text = (f"{p['samples']} samples, {p['spectra']} spectra. Same verdict on every repeat: {p['same_verdict']} of {p['samples']}. "
            f"Same verdict and material: {p['same_verdict_and_material']} of {p['samples']}. "
            f"Range of r within a sample: median {p['median_r_spread']:.3f}, largest {p['largest_r_spread']:.3f}.")
    rows = [row([h(d["sample"]), h(d["truth"]), h(", ".join(d["verdicts"])), h(", ".join(d["named"])),
                 h(", ".join(f"{v:.3f}" for v in d["r"]))]) for d in p["different"]]
    return f"<p>{text}</p>" + (table(["Sample", "True material", "Verdicts", "Best material", "r"], rows, 9) if rows else "")


def summary(r):
    """One short paragraph. Every number comes from the results file."""
    f, o = r["headline"][FIBRES], r["headline"][OPEN_SPECY]
    return (f"False probable on materials with no reference: {f['false_probable']['k']} of {f['false_probable']['n']} fibre samples and "
            f"{count(o['false_probable']['k'])} of {count(o['false_probable']['n'])} Open Specy spectra. On materials with a reference, "
            f"{f['strict_right']['k']} of {f['strict_right']['n']} and {o['strict_right']['k']} of {o['strict_right']['n']} probable answers "
            f"were right. The program answered probable on {f['coverage']['k']} of {f['coverage']['n']} and "
            f"{count(o['coverage']['k'])} of {count(o['coverage']['n'])}.")


def build(results_path, target):
    """Write the report page and return its path."""
    r = json.loads(Path(results_path).read_text(encoding="utf-8"))
    counts, e = r["counts"], r["extended"]
    left_out = r["left_out"]["open_specy"]
    table_of = lambda dataset, kind: material_table(
        sorted([m for m in r["per_material"] if m["dataset"] == dataset and m["kind"] == kind], key=lambda m: -m["n"]), kind)
    fonts = "".join(_font_face(name, family, weight) for name, family, weight in WEB_FONTS)
    style = (f"{fonts}:root{{{_tokens(LIGHT)}}}@media screen and (prefers-color-scheme:dark){{:root{{{_tokens(DARK)}}}"
             f"html{{color-scheme:dark}}}}{CSS}{EXTRA_CSS}")
    nav = "".join(f'<a href="#{k}">{v}</a>' for k, v in (("results", "Results"), ("materials", "Materials"), ("lead", "Lead rule"),
                                                        ("stress", "Stress"), ("extended", "Extended"), ("limits", "Limits")))
    open_ftir = r["openftir"]["headline"]
    deviations = "".join(f"<li>{what} {why}</li>" for what, why in DEVIATIONS)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FTIR Benchmark</title>
<style>{style}</style></head><body>
<header class="bar"><div class="bar-in"><span class="brand">{_logo_inline()}<span>FTIR Contamination Analyzer</span></span>
<nav aria-label="Parts of the report">{nav}</nav></div></header>
<main>
<div class="title"><h1>Benchmark</h1>
<p>{h(r['protocol'])}. Program locked at <code>{h(r['locked_commit'])}</code>, run at <code>{h(r['ran_at_commit'])}</code> on {h(r['ran_on'])}, {r['library']['references']} references.</p></div>

<div class="panel" style="margin-top:24px"><p style="margin:0">{summary(r)}</p></div>

<div class="panel"><h4>Method</h4>
<p style="margin:0">The program was run unchanged on spectra not used to build it. Fibres: FasTEX-KCL, {counts['fibre_samples']} physical samples, ATR, first replicate of each. Open Specy: {count(counts['open_specy_test'])} of {count(counts['open_specy_labelled'])} labelled spectra; {count(counts['open_specy_locked'])} were held back. Left out: {left_out['NIST']} NIST spectra, {count(left_out['no material'])} with no material, and {counts['copies_left_out']} copies of a reference. A false probable is a probable verdict on a material with no reference. Close relatives are counted separately. Intervals are 95% Wilson for fibres and, for Open Specy, the wider of Wilson and a cluster bootstrap over {count(counts['open_specy_clusters_test'])} clusters. The two sets are not pooled.</p></div>

<section id="results"><div class="panel"><h4>Results</h4>{result_table(r)}</div>
<div class="panel"><h4>Outcomes</h4>{outcome_table(r)}</div></section>

<section id="materials"><div class="panel"><h4>True material against named material, fibres</h4>{confusion(r['per_material'], FIBRES)}</div>
<div class="panel"><h4>True material against named material, Open Specy</h4>{confusion(r['per_material'], OPEN_SPECY)}</div>
<div class="panel"><h4>Fibres with a reference</h4>{table_of(FIBRES, IN)}<h4 style="margin-top:24px">Fibres with no reference</h4>{table_of(FIBRES, OUT)}</div>
<div class="panel"><h4>Open Specy with a reference</h4>{table_of(OPEN_SPECY, IN)}<h4 style="margin-top:24px">Open Specy with no reference</h4>{table_of(OPEN_SPECY, OUT)}</div>
<div class="panel"><h4>Close relatives</h4>{relatives(r)}</div>
<div class="panel"><h4>Open Specy by contributor</h4>{contributors(r)}</div>
<div class="panel"><h4>Open Specy with a reference, by comparison mode</h4>{reading_table(r)}</div>
<div class="panel"><h4>Fibre repeats</h4>{repeatability(r)}</div>
<div class="panel"><h4>Wrong answers and false probables</h4>{failures(r)}<p class="small">Both EVOH labels also name polyethylene-vinyl acetate.</p></div></section>

<section id="lead"><div class="panel"><h4>Lead rule</h4><p>Probable needs r of at least 0.95 and a lead of at least 0.08 over the next different material. Without lead: r alone, from the stored scores.</p>{lead_table(r)}</div></section>

<section id="stress"><div class="panel"><h4>Stress tests</h4><p>{counts['fibre_samples']} fibre samples and 500 Open Specy spectra, one fault at a time. The first point of each line is the clean spectrum.</p>
<ul class="keys"><li><i style="background:{FIRST}"></i>Fibres</li><li><i style="background:{SECOND}"></i>Open Specy</li></ul>
{stress_panels(r, 'Right on materials with a reference, %', lambda s: s['right'] / s['n_in'] if s['n_in'] else None)}
{stress_panels(r, 'False probable on materials with no reference, %', lambda s: s['false_probable'] / s['n_out'] if s['n_out'] else None)}
{stress_table(r)}</div></section>

<section id="extended"><div class="panel"><h4>Extended library</h4><p>16 shipped references plus {e['kept_from_pack']} from Open Specy. These were later removed from the program. References and their {e['pack_clusters_left_out']} clusters were left out of the test, leaving {count(e['spectra'])} spectra, scored with both libraries. A material counts as having a reference if the library in that row holds it.</p>{extended_table(r)}</div></section>

<section id="limits"><div class="panel"><h4>Limits</h4><ul class="plain">
<li>OpenFTIR is the source of the library and its scores were seen during development, so it is in no figure above. Its {counts['openftir']} unused spectra gave {open_ftir['false_probable']['k']} false probable in {open_ftir['false_probable']['n']} and {open_ftir['strict_right']['k']} right of {open_ftir['strict_right']['n']} probable answers.</li>
<li>Scores for a few fibre samples were seen before the protocol, while checking the file could be read.</li>
<li>The family limit (0.85) was set on Open Specy spectra, so it gets no credit here. The verdict rules (0.95, 0.08, 0.60) were not set on either test set.</li>
<li>Labels and counts were read before the protocol was written. Spectrum scores were not.</li>
<li>Open Specy has no physical-sample ID, so repeats of one item cannot be removed.</li>
<li>Open Specy spectra are processed, on a 6 cm⁻¹ step, from 804 to 3198 cm⁻¹, with a hole at 2196 to 2424 cm⁻¹. Most are environmental microplastics, not fab contamination.</li>
<li>Fibres are one form of a material. The results say little about films, powders or fab particles.</li>
<li>The library comes from one source.</li>
<li>This tests identification only, not review or sign-off.</li></ul></div>
<div class="panel"><h4>Deviations from the protocol</h4><ul class="plain">{deviations}</ul></div>
<p class="small">Library checksum <code>{h(r['library']['sha256'])}</code>. Rebuild: <code>python -m benchmark --report-only</code></p></section>
</main></body></html>"""
    target = Path(target)
    target.write_text(page, encoding="utf-8")
    return target
