"""
FTIR Contamination Analyzer - measures the unknown groups (PROTOCOL_GROUPS.md)

    python -m benchmark.groups --data benchmark/data     the measurement, then the report
    python -m benchmark.groups --report-only             only the report, from the saved results

Short names used in this file:
    item = one spectrum    r = the results    d = the figures for one data set

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import argparse
import collections
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if "FTIR_ANALYZER_RECORDS" not in os.environ:              # a lab's own references must not change the result
    os.environ["FTIR_ANALYZER_RECORDS"] = tempfile.mkdtemp(prefix="ftir_groups_")

import numpy as np                                                         # noqa: E402

from ftir_analyzer import config                                           # noqa: E402
from ftir_analyzer.analysis import analyse                                 # noqa: E402
from ftir_analyzer.library import load_library                             # noqa: E402
from ftir_analyzer.processing import fingerprint                           # noqa: E402
from ftir_analyzer.report import CSS, _font_face, _logo_inline, _tokens    # noqa: E402
from ftir_analyzer.spectrum_io import Spectrum                             # noqa: E402
from ftir_analyzer.theme import DARK, LIGHT, WEB_FONTS                     # noqa: E402
from ftir_analyzer.unknowns import link_groups, similarity                 # noqa: E402

from . import scoring                                                      # noqa: E402
from .confidence import FIBRE_FILE, HERE, REPO, RESULTS, SPECY_FILE, check_data   # noqa: E402
from .report import EXTRA_CSS, h, pct, row, table                          # noqa: E402
from .sets import FIBRES, OPEN_SPECY, OUT, read_fibres, read_open_specy    # noqa: E402

LOCKED_COMMIT = "6675e0c"
MATCHING = ("ftir_analyzer/analysis.py", "ftir_analyzer/library.py", "ftir_analyzer/processing.py")
USEFUL_PURITY, USEFUL_REACH = 0.90, 0.50
DEVIATIONS = []


def check_program():
    changed = subprocess.run(["git", "diff", "--quiet", LOCKED_COMMIT, "--", *MATCHING], cwd=REPO).returncode
    if changed:
        raise SystemExit(f"The matching code differs from {LOCKED_COMMIT}: this step will not run.")
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()


def fingerprint_of(item, library):
    spectrum = Spectrum(item.key, item.wn, item.y, item.unit, "benchmark", Path("benchmark"), "")
    return fingerprint(analyse(spectrum, library, mode=item.mode, mode_source="benchmark").compared)


def measure(scores, truths, link=config.UNKNOWN_LINK_R, size=config.UNKNOWN_GROUP_SIZE):
    """The protocol's figures for one data set."""
    groups = link_groups(scores, link, size)
    members = [[truths[i] for i in group] for group in groups]
    grouped = sum(len(group) for group in groups)
    majority = sum(collections.Counter(names).most_common(1)[0][1] for names in members)
    a, b = np.nonzero(np.triu(np.asarray(scores) >= link, 1))
    different = sum(truths[i] != truths[j] for i, j in zip(a.tolist(), b.tolist()))
    materials = {}
    for name in sorted(set(truths)):
        in_groups = [names.count(name) for names in members if name in names]
        materials[name] = {"n": truths.count(name), "grouped": sum(in_groups), "groups": len(in_groups)}
    purity, reach = majority / grouped if grouped else None, grouped / len(truths)
    return {"samples": len(truths), "groups": len(groups), "pure_groups": sum(len(set(names)) == 1 for names in members),
            "grouped": grouped, "majority": majority, "purity": purity, "reach": reach,
            "sizes": [len(group) for group in groups], "pairs": len(a), "different_pairs": different,
            "pair_interval": scoring.wilson(different, len(a)), "materials": materials,
            "useful": purity is not None and purity >= USEFUL_PURITY and reach >= USEFUL_REACH}


def run(data_folder, say=print):
    commit = check_program()
    check_data(data_folder)
    started = time.time()
    data_folder = Path(data_folder)
    library = load_library()
    if len(library) != 16 or library.in_house:
        raise SystemExit("This step needs the 16 shipped references and nothing else.")
    fibres = [i for i in read_fibres(data_folder / FIBRE_FILE[0]) if i.replica == 1 and i.kind == OUT]
    specy = [i for i in read_open_specy(data_folder / SPECY_FILE[0])[0] if i.kind == OUT]
    results = {"protocol": "benchmark/PROTOCOL_GROUPS.md, version 3", "locked_commit": LOCKED_COMMIT, "ran_at_commit": commit,
               "ran_on": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"), "link": config.UNKNOWN_LINK_R,
               "size": config.UNKNOWN_GROUP_SIZE, "useful_purity": USEFUL_PURITY, "useful_reach": USEFUL_REACH, "sets": {}}
    for name, items in ((FIBRES, fibres), (OPEN_SPECY, specy)):
        say(f"{name}: {len(items)} spectra")
        scores = similarity([fingerprint_of(item, library) for item in items])
        results["sets"][name] = measure(scores, [item.truth for item in items])
    results["seconds"] = round(time.time() - started)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "groups_results.json").write_text(json.dumps(results, indent=1, default=float), encoding="utf-8")
    return results


# ---------------------------------------------------------------------------- the report
def result_table(r):
    measures = (("Spectra", lambda d: d["samples"]), ("Groups of 3 or more", lambda d: d["groups"]),
                ("Groups holding one material", lambda d: f"{d['pure_groups']} of {d['groups']}"),
                ("Spectra in a group (at least 50%)", lambda d: f"{pct(d['reach'])}&nbsp;({d['grouped']}&nbsp;of&nbsp;{d['samples']})"),
                ("In their group's main material (at least 90%)", lambda d: f"{pct(d['purity'])}&nbsp;({d['majority']}&nbsp;of&nbsp;{d['grouped']})"),
                ("Linked pairs of different materials", lambda d: f"{pct(d['different_pairs'] / d['pairs'] if d['pairs'] else None)}"
                                                                  f"&nbsp;({d['different_pairs']}&nbsp;of&nbsp;{d['pairs']})"),
                ("95% interval, pairs", lambda d: f"{100 * d['pair_interval'][0]:.1f}&nbsp;to&nbsp;{100 * d['pair_interval'][1]:.1f}%"),
                ("Usable", lambda d: "yes" if d["useful"] else "no"))
    rows = [row([name, value(r["sets"][FIBRES]), value(r["sets"][OPEN_SPECY])], ["", "num", "num"]) for name, value in measures]
    return table(["Measure", "Fibres", "Open Specy"], rows)


def material_table(r):
    rows = []
    for name, label in ((FIBRES, "Fibres"), (OPEN_SPECY, "Open Specy")):
        for material, d in r["sets"][name]["materials"].items():
            rows.append(row([label, h(material), d["n"], d["grouped"], d["groups"]], ["", "", "num", "num", "num"]))
    return table(["Set", "Material", "Spectra", "In a group", "Groups it falls into"], rows, 2)


def summary(r):
    f, o = r["sets"][FIBRES], r["sets"][OPEN_SPECY]

    def said(d, name):
        return (f"{name}: {d['groups']} groups, {pct(d['purity'])} of grouped spectra in their group's main material, "
                f"{pct(d['reach'])} of spectra in a group, {'usable' if d['useful'] else 'not usable'}.")

    return said(f, "Fibres") + " " + said(o, "Open Specy")


def build(results_path, target):
    r = json.loads(Path(results_path).read_text(encoding="utf-8"))
    fonts = "".join(_font_face(name, family, weight) for name, family, weight in WEB_FONTS)
    style = (f"{fonts}:root{{{_tokens(LIGHT)}}}@media screen and (prefers-color-scheme:dark){{:root{{{_tokens(DARK)}}}"
             f"html{{color-scheme:dark}}}}{CSS}{EXTRA_CSS}")
    changes = "".join(f"<li>{d}</li>" for d in DEVIATIONS) or "<li>None.</li>"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FTIR Unknown Groups</title>
<style>{style}</style></head><body>
<header class="bar"><div class="bar-in"><span class="brand">{_logo_inline()}<span>FTIR Contamination Analyzer</span></span></div></header>
<main>
<div class="title"><h1>Unknown groups</h1>
<p>{h(r['protocol'])}. Matching code locked at <code>{h(r['locked_commit'])}</code>, run at <code>{h(r['ran_at_commit'])}</code> on {h(r['ran_on'])}.</p></div>

<div class="panel" style="margin-top:24px"><p style="margin:0">{summary(r)}</p></div>

<div class="panel"><h4>Method</h4>
<p style="margin:0">Each spectrum of a material with no reference is compared with every other using the program's score r on its fingerprint. Two spectra are linked at r of at least {r['link']:g}. A group is every spectrum reached through links, with at least {r['size']} spectra. A result is usable if at least {pct(r['useful_purity'], 0)} of grouped spectra are in their group's main material and at least {pct(r['useful_reach'], 0)} of spectra are in a group.</p></div>

<div class="panel"><h4>Results</h4>{result_table(r)}</div>
<div class="panel"><h4>Per material</h4>{material_table(r)}</div>

<div class="panel"><h4>Limits</h4><ul class="plain">
<li>A look at these fibres was taken before the protocol, and the limit of {r['link']:g} was chosen after it.</li>
<li>All of these spectra were scored against the library before. They were not scored against each other, except that look.</li>
<li>The fibres come from one source. A group across instruments may behave differently.</li>
<li>Open Specy has no physical-sample ID, so a group may hold repeats of one item, which would flatter its figures.</li>
<li>Close materials can join one group, and a difference the labels do not record cannot be seen.</li>
<li>Pairs share samples, so the interval on pairs is narrower than it should be.</li>
<li>These figures say nothing about real fab samples.</li></ul></div>

<div class="panel"><h4>Deviations from the protocol</h4><ul class="plain">{changes}</ul></div>
<p class="small">Rebuild: <code>python -m benchmark.groups --report-only</code></p>
</main></body></html>"""
    target = Path(target)
    target.write_text(page, encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description="Measure the unknown groups (benchmark/PROTOCOL_GROUPS.md).")
    parser.add_argument("--data", default=str(HERE / "data"), help="the folder with the data files")
    parser.add_argument("--report-only", action="store_true", help="rebuild the report from the saved results")
    args = parser.parse_args()
    if not args.report_only:
        run(args.data, say=lambda text: print(text, flush=True))
    print("Report:", build(RESULTS / "groups_results.json", RESULTS / "groups_report.html"))


if __name__ == "__main__":
    main()
