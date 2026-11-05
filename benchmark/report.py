"""
FTIR Contamination Analyzer - the benchmark report

Builds one self-contained web page from results/results.json, in the look of the program's own report. It needs no
data files, so anyone can rebuild it, and every number on the page comes from the results file:

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
     "The extra check only. <code>PVC043</code> is not a whole word, so the label rule missed it."),
    ("Missing points are dropped from Open Specy spectra before analysis, as the program's file reader does.",
     "1,022 of 4,814 spectra have some. The first run crashed on them in a stress test and wrote no results, so this "
     "was fixed before any score was seen."),
    ("Added after the results were seen, as extra reporting: the lead rule on the extended library, answers by how a "
     "spectrum was compared, and the count of probable answers that were not right in the extended table.",
     "No rule, threshold, label or data choice changed, and no number in the protocol's list moved. The first run with "
     "results was repeated from the committed tool, with the same numbers."),
]

# The failures, read by hand. They stay counted as failures: without the sample, nobody can say which side is wrong.
FAILURE_NOTES = [
    "Both EVOH failures come from labels that give two names: <em>ethylene vinyl alcohol</em> as the identity and "
    "<em>polyethylene-vinyl acetate</em> as the class. The program said EVA.",
    "The cellulose failure is labelled <em>cellulose_like organic matter</em>, which is not quite a name for cellulose.",
    "The PS and PET failures, both called PE, come from one contributor.",
]

EXTRA_CSS = """
:root{--second:#C4742F}
.lead{font-size:18px;line-height:1.5;margin:0 0 8px;max-width:760px}
.setname{font-size:14px;color:var(--muted);margin:24px 0 8px}
.stats small{display:block;color:var(--muted);font-size:14px;margin-top:2px;font-variant-numeric:tabular-nums}
.seg{display:flex;gap:2px;height:16px;margin:8px 0 12px}
.seg i{display:block;min-width:2px}.seg i:first-child{border-radius:4px 0 0 4px}.seg i:last-child{border-radius:0 4px 4px 0}
.keys{display:flex;flex-wrap:wrap;gap:4px 20px;font-size:14px;color:var(--ink-2);margin:0;padding:0;list-style:none}
.keys li{display:flex;align-items:center;gap:8px}.keys i{width:10px;height:10px;border-radius:3px;flex:none}
.keys b{font-weight:600;font-variant-numeric:tabular-nums}
.conf{font-size:13px;min-width:760px}.conf th,.conf td{padding:5px 4px;text-align:center;border-bottom:1px solid var(--line);
  font-variant-numeric:tabular-nums}
.conf th:first-child,.conf td:first-child{text-align:left;white-space:nowrap;padding-right:12px}
.conf thead th{font-size:13px;vertical-align:bottom}
.conf tr.gap td{border-bottom:none;padding-top:16px;color:var(--muted);text-align:left}
.conf .sum{color:var(--muted)}
.multi{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.multi figure{border:none;background:none;margin:0;overflow:visible}
.multi figcaption{font-size:14px;color:var(--ink-2);padding:0;margin:0 0 4px}
.chart{display:block;width:100%;height:auto}
.chart text{font:12px 'Inter',system-ui,sans-serif;fill:var(--muted)}
.chart .grid{stroke:var(--line);stroke-width:1}
details{margin-top:12px}summary{cursor:pointer;color:var(--accent-ink);font-size:14px}
.plain{margin:0;padding-left:20px}.plain li{margin:6px 0;max-width:820px}
code{font-family:'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace;font-size:.9em}
@media(max-width:900px){.multi{grid-template-columns:repeat(2,1fr)}.stats{grid-template-columns:repeat(2,1fr)}
  .stats div:nth-child(3){border-left:none}.bar nav{display:none}}
@media(max-width:560px){.stats{grid-template-columns:1fr}.stats div{border-left:none;border-top:1px solid var(--line)}
  .stats div:first-child{border-top:none}}
"""

SEGMENTS = (("right", "Right", "var(--good)"), ("family", "Right family", "var(--warn)"), ("wrong", "Wrong material", "var(--bad)"),
            ("weak_at_truth", "Weak, pointing at the true material", "var(--accent)"),
            ("weak_elsewhere", "Weak, pointing elsewhere", "var(--muted)"),
            ("none", "No reliable match", "var(--line-strong)"))
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


def margin_text(s):
    return f"95% margin {100 * s['low']:.1f} to {100 * s['high']:.1f}%"


def stat(title, s, dot=""):
    mark = f'<i class="dot {dot}"></i>' if dot else ""
    return (f"<div><span>{mark}{h(title)}</span><b>{pct(s['share'])}</b>"
            f"<small>{count(s['k'])} of {count(s['n'])}</small><small>{margin_text(s)}</small></div>")


def stat_strip(line):
    return ('<div class="stats">' + stat("False probable, no reference", line["false_probable"], "bad")
            + stat("Right, of its probable answers", line["strict_right"], "good")
            + stat("Answers probable at all", line["coverage"])
            + stat("True material ranked first", line["best_match"]) + "</div>")


def outcome_bar(line):
    """Where every sample of a material with a reference ended up, as one bar, with its numbers in the key."""
    buckets, silent = line["buckets"], line["no_answer"]
    values = {"right": buckets.get("right", 0), "family": buckets.get("right family", 0), "wrong": buckets.get("wrong", 0),
              "weak_at_truth": silent["weak_at_truth"], "weak_elsewhere": silent["weak_elsewhere"],
              "none": silent["no_reliable_match"]}
    parts = "".join(f'<i style="flex:{values[k]};background:{colour}" title="{h(name)}: {values[k]}"></i>'
                    for k, name, colour in SEGMENTS if values[k])
    keys = "".join(f'<li><i style="background:{colour}"></i>{h(name)} <b>{count(values[k])}</b></li>'
                   for k, name, colour in SEGMENTS)
    words = ", ".join(f"{name}: {values[k]}" for k, name, _ in SEGMENTS)
    return f'<div class="seg" role="img" aria-label="{h(words)}">{parts}</div><ul class="keys">{keys}</ul>'


def row(cells, kinds=()):
    out = []
    for i, cell in enumerate(cells):
        kind = f' class="{kinds[i]}"' if i < len(kinds) and kinds[i] else ""
        out.append(f"<td{kind}>{cell}</td>")
    return "<tr>" + "".join(out) + "</tr>"


def table(headers, rows, numeric_from=1):
    head = "".join(f'<th{" class=num" if i >= numeric_from else ""}>{h(t)}</th>' for i, t in enumerate(headers))
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


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
            + f'<tr class=gap><td colspan={span}>No reference: any number under a material is a false probable</td></tr>'
            + "".join(cells(m) for m in outside))
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
    return ('<details><summary>The same numbers as a table</summary>'
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
    return table(["Set", "Library", "Probable with the rule", "Without it", "Right it held back", "Wrong it stopped",
                  "True materials held back"], rows, 2)


def lead_text(r):
    stopped, lost = held_back(r["lead_rule"])
    wide, wide_lost = held_back(r["extended"]["lead_rule"])
    return (f"With the 16 references the rule stopped {stopped} wrong answers and held back {lost} right ones. With the extended "
            f"library it stopped {wide} and held back {wide_lost}. So on this data it costs answers and buys little. That does not "
            "show it is safe to remove: it exists for two close references, and these sets hold few samples where that happens "
            "and the score is also high. The rule stays as it is until a change is tested on the locked set.")


def relatives(r):
    rows = [row([NAMES.get(t["dataset"], t["dataset"]), h(t["truth"]), h(t["relative"]), t["n"], t["relative_named"], t["wrong"],
                 t["no_answer"]], ["", "", "", "num", "num", "num", "num"]) for t in r["relatives"]]
    return table(["Set", "Material", "Closest reference", "Samples", "Called the relative", "Called something else",
                  "No answer"], rows, 3)


def contributors(r):
    rows = [row([h(c["contributor"]), c["n"], f"{c['right']} of {c['probable']}" if c["probable"] else "-",
                 f"{c['probable']} of {c['in_library']}" if c["in_library"] else "-",
                 f"{c['false_probable']} of {c['not_in_library']}" if c["not_in_library"] else "-"], ["", *["num"] * 4])
            for c in r["per_contributor"]]
    return table(["Contributor", "Spectra", "Right, of probable", "Probable, of with a reference",
                  "False probable, of no reference"], rows)


def extended_table(r):
    e, rows = r["extended"], []
    for dataset in (FIBRES, OPEN_SPECY):
        for label, line in (("16 references", e["default_same_spectra"][dataset]), (f"{e['references']} references", e["extended"][dataset])):
            probable, bad = not_right(line)
            rows.append(row([plain(NAMES[dataset]), plain(label), count(probable), line["strict_right"]["k"], bad,
                             pct(bad / probable if probable else None), count(line["coverage"]["n"]),
                             count(line["false_probable"]["n"])], ["", "", *["num"] * 6]))
    return table(["Set", "Library", "Probable answers", "Right", "Not right", "Share not right", "Samples with a reference",
                  "Samples with none"], rows, 2)


def reading_table(r):
    rows = [row([{"unknown": "As measured: neither reading fitted"}.get(x["reading"], f"As {x['reading']}"), count(x["n"]),
                 x["probable"], pct(x["probable"] / x["n"]), f"{x['median_r']:.2f}"], ["", *["num"] * 4]) for x in r["by_reading"]]
    return table(["Compared", "Spectra", "Probable", "Share", "Median r"], rows)


def stress_text(r):
    faults = [s for s in r["stress"] if s["level"]]
    clean = max(s["false_probable"] for s in r["stress"] if not s["level"])
    worst = max(s["not_right"] for s in faults)
    false_high = max(s["false_probable"] for s in faults)
    return (f"Across {len(faults)} faulted runs, {worst} probable answers on a material with a reference were not right, and false "
            f"probables never passed {false_high}, against {clean} on the clean spectra. Under these faults the program goes "
            "quiet rather than wrong. Baseline drift barely matters. Noise, shifted bands and lower resolution remove answers quickly.")


def failures(r):
    rows = [row([NAMES.get(f["dataset"], f["dataset"]), h(f["truth"]), h(f["best_material"]), f"{f['r']:.3f}", f"{f['gap']:.3f}",
                 h(f["contributor"][:26]), h(f["label"][:60])], ["", "", "", "num", "num", "", ""]) for f in r["failures"]]
    notes = '<ul class="plain" style="margin-top:12px">' + "".join(f"<li>{n}</li>" for n in FAILURE_NOTES) + "</ul>"
    return table(["Set", "True material", "Called", "r", "Lead", "Contributor", "Label"], rows, 3) + notes


def repeat_text(r):
    p = r["repeatability"]
    text = (f"{p['samples']} fibre samples were measured more than once ({p['spectra']} spectra). "
            f"{p['same_verdict_and_material']} of {p['samples']} kept the same verdict and the same material on every repeat. "
            f"The score moved by a median of {p['median_r_spread']:.3f} and at most {p['largest_r_spread']:.3f}.")
    rows = [row([h(d["sample"]), h(d["truth"]), h(", ".join(d["verdicts"])), h(", ".join(d["named"])),
                 h(", ".join(f"{v:.3f}" for v in d["r"]))]) for d in p["different"]]
    return f"<p>{text}</p>" + (table(["Sample", "True material", "Verdicts", "Best material", "r"], rows, 9) if rows else "")


def deviations():
    return '<ul class="plain">' + "".join(f"<li>{what} {why}</li>" for what, why in DEVIATIONS) + "</ul>"


def not_right(line):
    """(probable answers, how many of them were not right), over materials with and without a reference."""
    right, false = line["strict_right"], line["false_probable"]
    return right["n"] + false["k"], right["n"] - right["k"] + false["k"]


def extended_summary(r):
    """Open Specy: (probable, not right) with 16 references, then with the extended library, on the same spectra."""
    e = r["extended"]
    return not_right(e["default_same_spectra"][OPEN_SPECY]), not_right(e["extended"][OPEN_SPECY])


def held_back(lead):
    """(wrong answers the lead rule stopped, right answers it held back), over both data sets."""
    stopped = sum(d["extra_wrong_material"] + d["extra_false_probable"] for d in lead.values())
    return stopped, sum(d["extra_right"] for d in lead.values())


def fibre_shift(r):
    """The fibres answered right at a clean, a 2 cm-1 and a 4 cm-1 shift."""
    rows = stress_rows(r, FIBRES, SHIFT)
    return rows[0]["right"], rows[2]["right"], rows[3]["right"]


def needs_work(r):
    """What the benchmark found that should change. Every number comes from the results file."""
    stopped, lost = held_back(r["lead_rule"])
    (base_all, base_bad), (wide_all, wide_bad) = extended_summary(r)
    clean, two, four = fibre_shift(r)
    return ('<ul class="plain">'
            f"<li><b>Small band shifts cost a lot.</b> A shift of 2 cm⁻¹ took the right fibre answers from {clean} to {two}, and "
            f"4 cm⁻¹ took them to {four}. It fails safe, but spectra with bands shifted that far, for example between instruments, would get few answers.</li>"
            f"<li><b>The lead rule earned nothing here.</b> With 16 references it stopped {stopped} wrong answers and held back "
            f"{lost} right ones.</li>"
            f"<li><b>The extended library did not help.</b> On the same Open Specy spectra, probable answers that were not right "
            f"went from {base_bad} of {base_all} to {wide_bad} of {wide_all}.</li></ul>")


def take_away(r):
    """The result in plain sentences. Every number comes from the results file."""
    f, o = r["headline"][FIBRES], r["headline"][OPEN_SPECY]
    fp, op = f["false_probable"], o["false_probable"]
    lines = [f"On real fibres with no reference in the library, the program said <b>probable {fp['k']} times in {fp['n']}</b> "
             f"({pct(fp['share'])}, {margin_text(fp)}). On the larger Open Specy set it was <b>{count(op['k'])} in {count(op['n'])}</b> "
             f"({pct(op['share'])}, {margin_text(op)}).",
             f"When a material does have a reference, {pct(f['strict_right']['share'])} of its probable answers were exactly right on "
             f"fibres and {pct(o['strict_right']['share'])} on Open Specy.",
             f"The cost of that caution: it says probable on {pct(f['coverage']['share'])} of fibres with a reference and only "
             f"{pct(o['coverage']['share'])} of Open Specy. The true material ranked first on {pct(f['best_match']['share'])} of "
             f"fibres but {pct(o['best_match']['share'])} of Open Specy, so on other labs' processed spectra the program mostly "
             "holds back rather than identifies."]
    return "".join(f'<p class="lead">{line}</p>' for line in lines)


def build(results_path, target):
    """Write the report page and return its path."""
    r = json.loads(Path(results_path).read_text(encoding="utf-8"))
    counts, f, o = r["counts"], r["headline"][FIBRES], r["headline"][OPEN_SPECY]
    table_of = lambda dataset, kind: material_table(
        sorted([m for m in r["per_material"] if m["dataset"] == dataset and m["kind"] == kind], key=lambda m: -m["n"]), kind)
    no = r["without_doubtful"][OPEN_SPECY]
    fonts = "".join(_font_face(name, family, weight) for name, family, weight in WEB_FONTS)
    style = (f"{fonts}:root{{{_tokens(LIGHT)}}}@media screen and (prefers-color-scheme:dark){{:root{{{_tokens(DARK)}}}"
             f"html{{color-scheme:dark}}}}{CSS}{EXTRA_CSS}")
    nav = "".join(f'<a href="#{k}">{v}</a>' for k, v in (("result", "Result"), ("materials", "Materials"), ("lead", "Lead rule"),
                                                        ("stress", "Stress"), ("extended", "Extended"), ("limits", "Limits")))
    open_ftir = r["openftir"]["headline"]
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FTIR Benchmark Report</title>
<style>{style}</style></head><body>
<header class="bar"><div class="bar-in"><span class="brand">{_logo_inline()}<span>FTIR Contamination Analyzer</span></span>
<nav aria-label="Parts of the report">{nav}</nav></div></header>
<main>
<div class="title"><h1>Benchmark on independent data</h1>
<p>{h(r['protocol'])}. Program locked at <code>{h(r['locked_commit'])}</code>, run at <code>{h(r['ran_at_commit'])}</code> on {h(r['ran_on'])}, {r['library']['references']} references.</p></div>

<section id="result"><h2 class="part">The result</h2>
<div class="panel">{take_away(r)}</div>
<div class="panel"><h4>What needs work</h4>{needs_work(r)}</div>
<p class="setname">Fibres: {counts['fibre_samples']} physical samples, the main test</p>{stat_strip(f)}
<p class="setname">Open Specy: {count(o['false_probable']['n'] + o['coverage']['n'])} spectra, many labs, already processed</p>{stat_strip(o)}
<div class="panel"><h4>Materials with a reference: what happened to every sample</h4>
<p class="setname">Fibres</p>{outcome_bar(f)}<p class="setname">Open Specy</p>{outcome_bar(o)}
<p class="small">Right family counts as not right in the strict figure. Counting it as acceptable, the share is {pct(f['family_right']['share'])} on fibres and {pct(o['family_right']['share'])} on Open Specy.
{f['false_probable_same_family']} of the fibre false probables and {o['false_probable_same_family']} of the Open Specy ones named a material of the same family.</p>
<p class="small">Without the {r['without_doubtful']['doubtful_spectra']} Open Specy spectra with a doubtful label: false probable {pct(no['false_probable']['share'])} ({no['false_probable']['k']} of {no['false_probable']['n']}), right of probable {pct(no['strict_right']['share'])} ({no['strict_right']['k']} of {no['strict_right']['n']}). The headline keeps them in.</p></div>
</section>

<section id="materials"><h2 class="part">True material against what was named</h2>
<div class="panel"><h4>Fibres</h4>{confusion(r['per_material'], FIBRES)}</div>
<div class="panel"><h4>Open Specy</h4>{confusion(r['per_material'], OPEN_SPECY)}
<p class="small">Grey numbers beside a material are its sample count. Green is right, red is a wrong or false probable; the depth of colour follows the share of that row.</p></div>
<h2 class="part">Per material</h2>
<div class="panel"><h4>Fibres with a reference</h4>{table_of(FIBRES, IN)}<h4 style="margin-top:24px">Fibres with no reference</h4>{table_of(FIBRES, OUT)}</div>
<div class="panel"><h4>Open Specy with a reference</h4>{table_of(OPEN_SPECY, IN)}<h4 style="margin-top:24px">Open Specy with no reference</h4>{table_of(OPEN_SPECY, OUT)}</div>
<div class="panel"><h4>Close relatives</h4><p class="small">These are in neither headline. Nylon 6 called Nylon 6,6 is a near miss, not a clean answer, so it gets its own column.</p>{relatives(r)}</div>
<div class="panel"><h4>Per contributor, Open Specy</h4><p class="small">So that one large source cannot hide behind the total.</p>{contributors(r)}</div>
<div class="panel"><h4>Repeat measurements</h4>{repeat_text(r)}</div>
<div class="panel"><h4>How the spectrum was compared, Open Specy with a reference</h4><p class="small">Nearly all probable answers come from spectra compared as ATR, the mode of the library.</p>{reading_table(r)}</div>
<div class="panel"><h4>Every wrong answer and false probable</h4>{failures(r)}</div>
</section>

<section id="lead"><h2 class="part">What the lead rule is worth</h2>
<div class="panel"><p>Probable needs r of at least 0.95 and a lead of at least 0.08 over the next different material. This is the same set of answers with the lead taken out, so r alone decides. Nothing in the program was changed to work this out.</p><p>{lead_text(r)}</p>{lead_table(r)}</div>
</section>

<section id="stress"><h2 class="part">Stress tests</h2>
<div class="panel"><p>{stress_text(r)}</p><p class="small">All {counts['fibre_samples']} fibre samples and 500 Open Specy spectra, with one fault added at a time. The first point of each line is the clean spectrum. Right answers start lower for Open Specy because it answers less often.</p>
<ul class="keys"><li><i style="background:{FIRST}"></i>Fibres</li><li><i style="background:{SECOND}"></i>Open Specy</li></ul>
{stress_panels(r, 'Right answers on materials with a reference, %', lambda s: s['right'] / s['n_in'] if s['n_in'] else None)}
{stress_panels(r, 'False probable on materials with no reference, %', lambda s: s['false_probable'] / s['n_out'] if s['n_out'] else None)}
{stress_table(r)}</div>
</section>

<section id="extended"><h2 class="part">Second run: the extended library</h2>
<div class="panel"><p>The same test with the {r['extended']['kept_from_pack']} included Open Specy references added, {r['extended']['references']} in all. References and everything from their clusters are left out of the test ({r['extended']['pack_clusters_left_out']} clusters), which leaves {count(r['extended']['spectra'])} spectra. Both libraries are scored on that same set, so the rows compare fairly. A material counts as having a reference if the library in that row holds it, so most fibres move from none to with a reference. Those newly covered fibres gained {r['extended']['extended'][FIBRES]['strict_right']['k'] - r['extended']['default_same_spectra'][FIBRES]['strict_right']['k']} right answers.</p>{extended_table(r)}</div>
</section>

<section id="limits"><h2 class="part">Limits of this benchmark</h2>
<div class="panel"><h4>Disclosures</h4><ul class="plain">
<li>OpenFTIR scores were seen while the program was built, and it is the source of the library, so it is out of every headline. As an extra check, its {r['counts']['openftir']} unused spectra gave {open_ftir['false_probable']['k']} false probable in {open_ftir['false_probable']['n']}, and {open_ftir['strict_right']['k']} right of {open_ftir['strict_right']['n']} probable answers. A same-lab check is easy; it only shows nothing is broken.</li>
<li>Scores for a handful of fibre samples were seen before the protocol, while checking the file could be read.</li>
<li>The Open Specy pack was used to set the family limit (0.85), so that limit gets no credit here.</li>
<li>The verdict rules (0.95, 0.08, 0.60) were not set on either test set.</li>
<li>Labels and counts were read before the protocol was written. Spectrum scores were not.</li></ul></div>
<div class="panel"><h4>Weaknesses of the data</h4><ul class="plain">
<li><b>Open Specy has no physical-sample ID.</b> Each spectrum counts once, so repeats of one item cannot be removed. Its margins are widened using {count(counts['open_specy_clusters_test'])} clusters of contributor, label and material to allow for this.</li>
<li>Open Specy spectra are already processed, on a 6 cm⁻¹ step, from 804 to 3198 cm⁻¹, with a hole at 2196 to 2424 cm⁻¹. A real measurement has more to compare, so a low answer rate here may understate the program.</li>
<li>Fibres are one form of a material. This says little about films, powders or particles from a fab.</li>
<li>Most Open Specy spectra are environmental microplastics, not fab contamination, and may be weathered.</li>
<li>The library comes from one source, so a second lab's sample of the same material may simply differ.</li>
<li>This tests identification only, not a person's sign-off or the rest of the workflow.</li></ul></div>
<div class="panel"><h4>What is left out</h4><ul class="plain">
<li>{count(counts['open_specy_locked'])} Open Specy spectra are the locked set, unscored, kept for calibrated confidence and for checking any fix.</li>
<li>{r['left_out']['open_specy']['NIST']} NIST spectra and {count(r['left_out']['open_specy']['no material'])} with no material. {counts['copies_left_out']} spectra were copies of a reference.</li></ul></div>
<div class="panel"><h4>Deviations from the protocol</h4>{deviations()}</div>
<p class="small">Library checksum <code>{h(r['library']['sha256'])}</code>. Rebuild this page with <code>python -m benchmark --report-only</code>.</p>
</section>
</main></body></html>"""
    target = Path(target)
    target.write_text(page, encoding="utf-8")
    return target
