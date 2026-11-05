"""
FTIR Contamination Analyzer - protocol v4: the shift-tolerant search

Compares the search of today with the one that tries small band shifts, on data no earlier step has read, and applies
the pass rules of benchmark/PROTOCOL_SHIFT.md. The rules are checked by this file, not by a person after the fact.

    read_items         every spectrum of the locked file
    without_material   the library with every reference of one material removed
    answers            the measures for one spectrum, one search
    tally              the counts of many answers
    verdict            do the numbers pass the protocol's rules?

    python -m benchmark.shift                 the whole run, then the report
    python -m benchmark.shift --report-only   the report from the saved results

Short names used in this file:
    wn = wavenumbers (cm-1)    y = one spectrum as measured

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import argparse
import hashlib
import io
import json
import os
import subprocess
import time
import zipfile
import zlib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")              # one thread per worker: the work is split by process

import numpy as np                                                         # noqa: E402
import pandas as pd                                                        # noqa: E402

from ftir_analyzer import config                                           # noqa: E402
from ftir_analyzer.analysis import PROBABLE, analyse                       # noqa: E402
from ftir_analyzer.library import Library, load_library                    # noqa: E402
from ftir_analyzer.report import CSS, _font_face, _logo_inline, _tokens    # noqa: E402
from ftir_analyzer.spectrum_io import Spectrum, SpectrumFileError          # noqa: E402
from ftir_analyzer.theme import DARK, LIGHT, WEB_FONTS                     # noqa: E402

from .report import EXTRA_CSS, h, pct, row, table                          # noqa: E402
from .scoring import SEED, wilson                                          # noqa: E402
from .sets import measured_points                                          # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RESULTS = HERE / "results"
DATA_FILE = HERE / "data" / "shift" / "FTIR-PLASTIC.zip"
DATA_SHA256 = "c8a5a378efcff70e959cfe7af26d7e7131e2508043ee99675328e582aa7b8dd9"
LOCKED_COMMIT = "bb86688"
TABLES = ("FTIR-PLASTIC-c4/FTIR_PLASTIC_c4.csv", "FTIR-PLASTIC-c8/FTIR_PLASTIC_c8.csv")
TRUTH = {"PET": "PET", "HDPE": "PE", "LDPE": "PE", "PVC": "PVC", "PP": "PP", "PS": "PS"}
MODE, UNIT = "ATR", "%T"                                   # every file header says so
SHIFTS = (0, 2, 4)
SLACK = 0.01                                               # 1 percentage point
FALSE_LIMIT = 0.05
CHUNK = 24
WORKERS = max(1, min(10, (os.cpu_count() or 2) - 4))       # leaves the computer usable while it runs
TODAY, TOLERANT = "today", "tolerant"
SEARCHES = {TODAY: (), TOLERANT: config.SHIFT_TEST}
AFTER = ["264 of the tolerant search's 298 false probables, and all 264 of today's, are spectra labelled PS. 300 spectra with "
         "that label have no polystyrene ring band at 700 cm⁻¹ (median height 0.003, against 0.33 in the spectra called PS) "
         "and have a polypropylene methyl band at 1376 cm⁻¹ (0.14, against 0.008). Their r is 0.97 to PP and 0.07 to PS. They "
         "are probably polypropylene with the wrong label. The protocol has no rule for this, so they stay in and rule 1 stands.",
         "The other 34 false probables are new. They are PVC spectra in the 8 cm⁻¹ table, and today's search gives no false "
         "probable on PVC. In a sample of 300 PVC spectra the tolerant search called them PS at r 0.95.",
         "PET lost right answers: 248 today, 188 tolerant. Every other material kept or gained them.",
         "With a band shift of 2 or 4 cm⁻¹ the tolerant search gave the same answers as at shift 0, in right and not right."]

_library, _without = None, {}


@dataclass
class Tally:
    """Counts for one search."""

    spectra: int = 0
    right: int = 0
    not_right: int = 0
    false: int = 0

    def rate(self, name):
        return getattr(self, name) / self.spectra if self.spectra else 0.0


@dataclass(frozen=True)
class Item:
    """One spectrum of the data."""

    key: str
    polymer: str
    resolution: str
    wn: np.ndarray
    y: np.ndarray

    @property
    def truth(self):
        return TRUTH[self.polymer]


# ---------------------------------------------------------------------------- guards
def locked():
    """Stops unless the data and the program are exactly the ones the protocol names."""
    if not DATA_SHA256 or not LOCKED_COMMIT:
        raise SystemExit("The data file and the locked commit are not filled in: this step will not run.")
    if not DATA_FILE.exists():
        raise SystemExit(f"{DATA_FILE.name} is not in {DATA_FILE.parent}: this step will not run.")
    if hashlib.sha256(DATA_FILE.read_bytes()).hexdigest() != DATA_SHA256:
        raise SystemExit("The data file is not the one the protocol names: this step will not run.")
    changed = subprocess.run(["git", "diff", "--quiet", LOCKED_COMMIT, "--", "ftir_analyzer"], cwd=REPO).returncode
    if changed:
        raise SystemExit(f"ftir_analyzer/ differs from the locked commit {LOCKED_COMMIT}: this step will not run.")
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()


# ---------------------------------------------------------------------------- the data
def read_table(handle, resolution):
    """The spectra of one table: six columns of labels, then pairs of wavenumber and %T."""
    frame = pd.read_csv(handle, encoding="latin-1", low_memory=False)
    labels = frame.iloc[:, :6]
    values = frame.iloc[:, 6:].to_numpy(float)
    return [Item(f"{label.IDE}-{resolution}", label.Polymer, resolution, x, y)
            for label, x, y in zip(labels.itertuples(), values[:, 0::2], values[:, 1::2])]


def read_items(path=DATA_FILE):
    """Every spectrum in the zip, read in place: nothing is unpacked to the disk."""
    items = []
    with zipfile.ZipFile(path) as archive:
        for name in TABLES:
            with archive.open(name) as handle:
                items += read_table(io.BytesIO(handle.read()), name.rsplit("_", 1)[-1].removesuffix(".csv"))
    return items


# ---------------------------------------------------------------------------- one spectrum
def without_material(library, material):
    """The same library with every reference of one material removed."""
    kept = {name: spectrum for name, spectrum in library.spectra.items() if library.group_of(name) != material}
    return Library(library.name, library.mode, kept, library.sha256, library.path, library.info)


def direction(key):
    """The direction of the applied shift for one spectrum: fixed by the seed and the spectrum."""
    return int(np.random.default_rng([SEED, zlib.crc32(str(key).encode("utf-8"))]).choice((-1, 1)))


def probable(item, library, shifts, moved=0.0):
    """(the verdict is probable, the material named). A spectrum that cannot be compared has no verdict."""
    wn, y = measured_points(item.wn + moved, item.y)
    spectrum = Spectrum(item.key, wn, y, UNIT, "benchmark", Path("benchmark"), "")
    try:
        result = analyse(spectrum, library, mode=MODE, mode_source="benchmark", shifts=shifts)
    except SpectrumFileError:
        return False, ""
    return result.verdict == PROBABLE, library.group_of(result.best)


def answers(item, library, without, shifts):
    """{shift: (right, not right, false)} for one spectrum and one search. False is measured at shift 0 only."""
    done = {}
    for shift in SHIFTS:
        says, material = probable(item, library, shifts, shift * direction(item.key))
        right = says and material == item.truth
        done[shift] = (right, says and not right, shift == 0 and probable(item, without, shifts)[0])
    return done


def _start_worker():
    global _library, _without
    _library = load_library()
    _without = {material: without_material(_library, material) for material in set(TRUTH.values())}


def _score_chunk(chunk):
    return [{search: answers(item, _library, _without[item.truth], shifts) for search, shifts in SEARCHES.items()}
            for item in chunk]


def tally(outcomes):
    counts = Tally()
    for right, not_right, false in outcomes:
        counts.spectra += 1
        counts.right += right
        counts.not_right += not_right
        counts.false += false
    return counts


# ---------------------------------------------------------------------------- the rules
def verdict(today, tolerant):
    """({rule: passed}, all passed) from {shift: Tally} of each search."""
    _, high = wilson(tolerant[0].false, tolerant[0].spectra)
    rules = {
        "1 false probable": bool(high <= FALSE_LIMIT and tolerant[0].rate("false") <= today[0].rate("false") + SLACK),
        "2 not right probable": bool(tolerant[0].rate("not_right") <= today[0].rate("not_right") + SLACK),
        "3 right probable at shift 0": bool(tolerant[0].rate("right") >= today[0].rate("right") - SLACK),
        "4 right probable at shifts 2 and 4": all(tolerant[s].right > today[s].right for s in (2, 4)),
    }
    return rules, all(rules.values())


def tallies(rows, keep=lambda item: True):
    """{search: {shift: Tally}} over the rows (item, its answers) that are kept."""
    chosen = [answer for item, answer in rows if keep(item)]
    return {search: {shift: tally(a[search][shift] for a in chosen) for shift in SHIFTS} for search in SEARCHES}


def plain(counts):
    """{search: {shift: counts as a dict}} for the results file."""
    return {search: {str(shift): asdict(t) for shift, t in shifts.items()} for search, shifts in counts.items()}


def run(say=print):
    commit = locked()
    started = time.time()
    library = load_library()
    if len(library) != 16 or library.in_house:
        raise SystemExit("This step needs the 16 shipped references and nothing else.")
    items = read_items()
    say(f"{len(items)} spectra, {WORKERS} workers")
    done = []
    chunks = [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]
    with ProcessPoolExecutor(WORKERS, initializer=_start_worker) as pool:
        for i, part in enumerate(pool.map(_score_chunk, chunks)):
            done.extend(part)
            if i % 25 == 0:
                say(f"  {len(done)} of {len(items)}, {time.time() - started:.0f} s")
    rows = list(zip(items, done))
    overall = tallies(rows)
    rules, passed = verdict(overall[TODAY], overall[TOLERANT])
    results = {
        "protocol": "benchmark/PROTOCOL_SHIFT.md, version 4", "locked_commit": LOCKED_COMMIT, "ran_at_commit": commit,
        "ran_on": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"), "seconds": round(time.time() - started),
        "data_sha256": DATA_SHA256, "shifts_tried": list(config.SHIFT_TEST), "library": {"name": library.name, "sha256": library.sha256},
        "spectra": len(items), "rules": rules, "passed": passed, "overall": plain(overall),
        "per_material": {name: plain(tallies(rows, lambda i, n=name: i.polymer == n)) for name in TRUTH},
        "per_resolution": {name: plain(tallies(rows, lambda i, n=name: i.resolution == n)) for name in ("c4", "c8")},
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "shift_results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    say(f"Done in {results['seconds']} s. Rules: {rules}. Passed: {passed}")
    return results


# ---------------------------------------------------------------------------- the report
def share(counts, name):
    """'123 of 6000 (2.1%)'."""
    return f"{counts[name]:,} of {counts['spectra']:,} ({pct(counts[name] / counts['spectra'])})" if counts["spectra"] else "0"


def interval(counts, name):
    low, high = wilson(counts[name], counts["spectra"])
    return f"{pct(low)} to {pct(high)}"


def summary_table(r):
    o = r["overall"]
    rows = []
    for label, name, shift in (("Right probable", "right", "0"), ("Not right probable", "not_right", "0"), ("False probable", "false", "0"),
                               ("Right probable, bands shifted 2 cm⁻¹", "right", "2"), ("Not right probable, bands shifted 2 cm⁻¹", "not_right", "2"),
                               ("Right probable, bands shifted 4 cm⁻¹", "right", "4"), ("Not right probable, bands shifted 4 cm⁻¹", "not_right", "4")):
        rows.append(row([label, share(o[TODAY][shift], name), share(o[TOLERANT][shift], name), interval(o[TOLERANT][shift], name)]))
    return table(["Measure", "Today", "Tolerant", "Tolerant, 95% Wilson interval"], rows)


def rule_table(r):
    words = {"1 false probable": f"False probable: upper end at most {pct(FALSE_LIMIT, 0)}, and at most 1 point above today",
             "2 not right probable": "Not right probable: at most 1 point above today, at shift 0",
             "3 right probable at shift 0": "Right probable: at most 1 point below today, at shift 0",
             "4 right probable at shifts 2 and 4": "Right probable: above today at shifts of 2 and 4 cm⁻¹"}
    return table(["Rule", "Result"], [row([words[name], "Passed" if ok else "Failed"], ["", "good" if ok else "bad"])
                                      for name, ok in r["rules"].items()])


def split_table(parts):
    rows = []
    for name, part in parts.items():
        cells = [name]
        for search in (TODAY, TOLERANT):
            cells += [f"{part[search]['0']['right']:,}", f"{part[search]['0']['false']:,}", f"{part[search]['2']['right']:,}",
                      f"{part[search]['4']['right']:,}"]
        rows.append(row(cells))
    return table(["", "Today: right", "false", "right at 2", "right at 4", "Tolerant: right", "false", "right at 2", "right at 4"], rows)


def build(results_path, target):
    r = json.loads(Path(results_path).read_text(encoding="utf-8"))
    fonts = "".join(_font_face(name, family, weight) for name, family, weight in WEB_FONTS)
    style = (f"{fonts}:root{{{_tokens(LIGHT)}}}@media screen and (prefers-color-scheme:dark){{:root{{{_tokens(DARK)}}}"
             f"html{{color-scheme:dark}}}}{CSS}{EXTRA_CSS}")
    outcome = ("All four rules passed." if r["passed"] else
               "At least one rule failed, so the tolerant search stays switched off.")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FTIR Shift Test</title>
<style>{style}</style></head><body>
<header class="bar"><div class="bar-in"><span class="brand">{_logo_inline()}<span>FTIR Contamination Analyzer</span></span></div></header>
<main>
<div class="title"><h1>Shift-tolerant search</h1>
<p>{h(r['protocol'])}. Program locked at <code>{h(r['locked_commit'])}</code>, run at <code>{h(r['ran_at_commit'])}</code> on {h(r['ran_on'])}.</p></div>

<div class="panel" style="margin-top:24px"><p style="margin:0">{outcome}</p></div>

<div class="panel"><h4>Method</h4>
<p style="margin:0">{r['spectra']:,} spectra of six plastics from FTIR-Plastics (Villegas Camacho et al., 2024, CC BY 4.0), read as ATR. Today compares each spectrum at one position. Tolerant tries shifts of {r['shifts_tried'][0]} to +{r['shifts_tried'][-1]} cm⁻¹ and each reference keeps its best score. The verdict rule is the same. False probable is measured with every reference of the true material removed. HDPE and LDPE both count as PE.</p></div>

<div class="panel"><h4>Pass rules</h4>{rule_table(r)}</div>
<div class="panel"><h4>Results</h4>{summary_table(r)}</div>
<div class="panel"><h4>Per material</h4>{split_table(r['per_material'])}</div>
<div class="panel"><h4>Per resolution</h4>{split_table({'4 cm⁻¹': r['per_resolution']['c4'], '8 cm⁻¹': r['per_resolution']['c8']})}</div>

<div class="panel"><h4>Looked at after the results</h4>
<p>No rule or setting depends on these.</p><ul class="plain">{"".join(f"<li>{h(line)}</li>" for line in AFTER)}</ul></div>

<div class="panel"><h4>Limits</h4><ul class="plain">
<li>All spectra come from one instrument and six common plastics, so this says nothing about other materials or instruments.</li>
<li>The record does not say whether the 500 sample numbers are 500 physical pieces, and the numbers repeat across the two resolutions. The intervals treat the spectra as independent and may be too narrow.</li>
<li>The applied shifts are computed, not measured on an instrument that drifted. Shifts of 2 and 4 cm⁻¹ land exactly on positions the search tries, which flatters it: a shift between two tries would score a little lower.</li>
<li>False probable has one reference set removed at a time, so it tests these six plastics only.</li>
<li>These figures say nothing about real fab samples.</li></ul></div>
<p class="small">Rebuild: <code>python -m benchmark.shift --report-only</code></p>
</main></body></html>"""
    target = Path(target)
    target.write_text(page, encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description="Test the shift-tolerant search (benchmark/PROTOCOL_SHIFT.md).")
    parser.add_argument("--report-only", action="store_true", help="rebuild the report from the saved results")
    args = parser.parse_args()
    if not args.report_only:
        run()
    print("Written:", build(RESULTS / "shift_results.json", RESULTS / "shift_report.html"))


if __name__ == "__main__":
    main()
