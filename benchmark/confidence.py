"""
FTIR Contamination Analyzer - calibrated confidence (PROTOCOL_CONFIDENCE.md)

Sets a bar on spectra of known material, so that the true material clears it about 90% of the time, then tests that
promise on spectra that took no part in setting it. On a new sample, every material at or above the bar goes on a list.

    python -m benchmark.confidence --data benchmark/data     the whole step, then the report
    python -m benchmark.confidence --report-only             only the report, from the saved results

    bar_of       the bar for a set of true scores
    list_of      the materials that clear a bar
    measure      coverage and list lengths for a set of spectra

The app is not changed. Spectra are never copied into the results.

Short names used in this file:
    item = one spectrum to test    row = the stored outcome of one item    bar = the score a material must reach

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if "FTIR_ANALYZER_RECORDS" not in os.environ:              # a lab's own references must not change the result
    os.environ["FTIR_ANALYZER_RECORDS"] = tempfile.mkdtemp(prefix="ftir_confidence_")

import numpy as np                                                         # noqa: E402

from ftir_analyzer.analysis import MODES, PROBABLE, analyse                # noqa: E402
from ftir_analyzer.library import load_library                             # noqa: E402
from ftir_analyzer.spectrum_io import Spectrum, SpectrumFileError          # noqa: E402

from . import scoring                                                      # noqa: E402
from .sets import FIBRES, IN, OPEN_SPECY, OUT, RELATIVE, read_fibres, read_open_specy, split_locked   # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RESULTS = HERE / "results"
LOCKED_COMMIT = "6675e0c"
FIBRE_FILE = ("feature_matrix_raw_transmittance.csv", "2739d901529a0fd97e693068d82cee5b7eee2a616f5e8d6e797a84ad859fa26f")
SPECY_FILE = ("medoid_nobaseline.rds", "3591eb4b7be780ac12585631216bce5050cb543e9a61b8b482c91d1b4c821ab3")
SALT = "ftir-confidence-v2|"
CALIBRATION_SHARE = 0.5
COVERAGE = 0.90
SHORT_LIST = 3                                             # a list longer than this helps nobody
AS_MEASURED = "as measured"
ONE_BAR = "one bar"
NO_BAR = -1.0                                              # too few true scores: every material is on the list


# ---------------------------------------------------------------------------- the method
def bar_of(true_scores, coverage=COVERAGE):
    """The score that this share of the true scores clears, by the protocol's exact rule."""
    scores = sorted(true_scores, reverse=True)
    position = math.ceil((len(scores) + 1) * coverage - 1e-9)   # the small number only guards against rounding
    return scores[position - 1] if position <= len(scores) else NO_BAR


def list_of(scores, bar):
    """The materials that clear a bar, best first. scores: {material: r}."""
    return [name for name, r in sorted(scores.items(), key=lambda kv: -kv[1]) if r >= bar]


def group_of(reading):
    """The group of version B: how the spectrum ended up being compared. It depends on the spectrum alone."""
    return reading if reading in MODES else AS_MEASURED


def bars_for(rows):
    """{version: {group: bar}}, from calibration rows that have a true score."""
    groups = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row["true_r"])
    return {"A": {ONE_BAR: bar_of([row["true_r"] for row in rows])}, "B": {g: bar_of(s) for g, s in groups.items()}}


def bar_for(row, bars, version):
    if version == "A":
        return bars["A"][ONE_BAR]
    return bars["B"].get(row["group"], NO_BAR)


def share(k, n, interval):
    return {"k": int(k), "n": int(n), "share": (k / n if n else None), "low": interval[0], "high": interval[1]}


def lengths(values):
    """How long the lists are: the median, and the share of each kind."""
    values = np.asarray(values)
    n = len(values)
    return {"n": n, "median": float(np.median(values)) if n else None,
            "empty": int((values == 0).sum()), "one": int((values == 1).sum()),
            "two_three": int(((values >= 2) & (values <= 3)).sum()), "four_up": int((values >= 4).sum())}


def verdict_on(hits, clusters, list_lengths, dataset):
    """Coverage and list lengths for one group, and whether the protocol calls it useful."""
    coverage = share(np.sum(hits), len(hits), scoring.margin(hits, clusters, dataset))
    size = lengths(list_lengths)
    valid = bool(len(hits)) and coverage["high"] >= COVERAGE
    short = size["median"] is not None and size["median"] <= SHORT_LIST
    return {"coverage": coverage, "lengths": size, "valid": valid, "short": short, "useful": valid and short}


def measure(rows, bars, version, dataset=OPEN_SPECY):
    """Everything the protocol reports for one version on one set of rows with a true score, overall and by group."""
    made = [dict(row, bar=bar_for(row, bars, version)) for row in rows]
    for row in made:
        row["list"] = list_of(row["scores"], row["bar"])
        row["hit"] = row["truth"] in row["list"]
    out = {"all": verdict_on([r["hit"] for r in made], [r["cluster"] for r in made], [len(r["list"]) for r in made], dataset)}
    if version == "B":
        for key in sorted({row["group"] for row in made}):
            part = [r for r in made if r["group"] == key]
            out[key] = verdict_on([r["hit"] for r in part], [r["cluster"] for r in part], [len(r["list"]) for r in part], dataset)
    materials = {}
    for row in made:
        materials.setdefault(row["truth"], []).append(row)
    out["per_material"] = {name: {"n": len(part), "hits": int(sum(r["hit"] for r in part)),
                                  "median_list": float(np.median([len(r["list"]) for r in part]))}
                           for name, part in sorted(materials.items())}
    probable = [r for r in made if r["verdict"] == PROBABLE]
    out["probable"] = {"n": len(probable), "on_list": int(sum(r["best"] in r["list"] for r in probable)),
                       "alone": int(sum(r["list"] == [r["best"]] for r in probable))}
    return out


def on_unknowns(rows, bars, version):
    """Materials with no reference: an empty list is the right signal. Any material on it is a wrong candidate."""
    sizes = [len(list_of(r["scores"], bar_for(r, bars, version))) for r in rows]
    return lengths(sizes)


def on_relatives(rows, bars, version):
    hits = sum(r["relative"] in list_of(r["scores"], bar_for(r, bars, version)) for r in rows)
    sizes = [len(list_of(r["scores"], bar_for(r, bars, version))) for r in rows]
    return {"n": len(rows), "relative_on_list": int(hits), "median_list": float(np.median(sizes)) if rows else None}


# ---------------------------------------------------------------------------- scoring
def row_of(item, library):
    """Run the program's own analysis and keep the scores. Spectra stay out of it."""
    spectrum = Spectrum(item.key, item.wn, item.y, item.unit, "benchmark", Path("benchmark"), "")
    try:
        r = analyse(spectrum, library, mode=item.mode, mode_source="benchmark")
    except SpectrumFileError:
        return None
    scores = {}
    for name, value in r.ranking:                          # one number per material, the best of its references
        group = library.group_of(name)
        scores[group] = max(scores.get(group, -1.0), round(float(value), 4))
    return {"id": hashlib.sha256(item.key.encode("utf-8")).hexdigest()[:12], "dataset": item.dataset, "truth": item.truth,
            "kind": item.kind, "relative": item.relative, "cluster": item.cluster, "contributor": item.contributor,
            "doubtful": item.doubtful, "group": group_of(r.reading), "verdict": r.verdict,
            "best": library.group_of(r.best), "scores": scores, "true_r": scores.get(item.truth, -1.0)}


def score_all(items, library, say):
    rows, started = [], time.time()
    for i, item in enumerate(items, start=1):
        rows.append(row_of(item, library))
        if i % 300 == 0:
            say(f"  {i} of {len(items)}, {time.time() - started:.0f} s")
    return [row for row in rows if row is not None], len(items) - sum(row is not None for row in rows)


# ---------------------------------------------------------------------------- guards
def check_program():
    changed = subprocess.run(["git", "diff", "--quiet", LOCKED_COMMIT, "--", "ftir_analyzer"], cwd=REPO).returncode
    if changed:
        raise SystemExit(f"ftir_analyzer/ differs from the locked commit {LOCKED_COMMIT}: this step will not run.")
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()


def check_data(folder):
    for name, expected in (FIBRE_FILE, SPECY_FILE):
        path = Path(folder) / name
        if not path.exists():
            raise SystemExit(f"Missing data file: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"{name} is not the file the protocol names.")


def split_halves(items):
    """(calibration, test) of the spectra with a reference: whole clusters, by labels alone, seeded with its own salt."""
    marked = split_locked([replace(item, locked=False) for item in items], CALIBRATION_SHARE, SALT)
    return ([replace(item, locked=False) for item in marked if item.locked], [item for item in marked if not item.locked])


def histogram(values, low=-0.2, high=1.0, width=0.05):
    """Counts of the true scores, for the report's picture. Only counts leave this function."""
    edges = np.arange(low, high + width / 2, width)
    counts, _ = np.histogram(np.clip(values, low, high), bins=edges)
    return {"edges": [round(float(e), 2) for e in edges], "counts": [int(c) for c in counts]}


# ---------------------------------------------------------------------------- the whole step
def run(data_folder, say=print):
    commit = check_program()
    check_data(data_folder)
    started = time.time()
    data_folder = Path(data_folder)
    library = load_library()
    if len(library) != 16 or library.in_house:
        raise SystemExit("This step needs the 16 shipped references and nothing else.")

    say("Reading the data")
    specy, _ = read_open_specy(data_folder / SPECY_FILE[0])
    locked = [item for item in split_locked(specy) if item.locked]
    calibration, test = split_halves([item for item in locked if item.kind == IN])
    unknown = [replace(item, locked=False) for item in locked if item.kind == OUT]
    relatives = [replace(item, locked=False) for item in locked if item.kind == RELATIVE]
    fibres = [item for item in read_fibres(data_folder / FIBRE_FILE[0]) if item.replica == 1]
    say(f"Locked set {len(locked)}: calibration {len(calibration)}, test {len(test)}, no reference {len(unknown)}, "
        f"relatives {len(relatives)}; fibres {len(fibres)}")

    say("Setting the bar")
    calibration_rows, missed_c = score_all(calibration, library, say)
    bars = bars_for(calibration_rows)
    say(f"Bars: {bars}")

    say("Testing it")
    test_rows, missed_t = score_all(test, library, say)
    unknown_rows, missed_u = score_all(unknown, library, say)
    relative_rows, missed_r = score_all(relatives, library, say)
    fibre_rows, missed_f = score_all(fibres, library, say)
    clean = [row for row in test_rows if not row["doubtful"]]
    fibre_in = [row for row in fibre_rows if row["kind"] == IN]
    fibre_out = [row for row in fibre_rows if row["kind"] == OUT]

    versions = {}
    for version in ("A", "B"):
        versions[version] = {
            "test": measure(test_rows, bars, version), "without_doubtful": measure(clean, bars, version),
            "calibration": measure(calibration_rows, bars, version),
            "no_reference": on_unknowns(unknown_rows, bars, version),
            "relatives": on_relatives(relative_rows, bars, version),
            "fibres": measure(fibre_in, bars, version, FIBRES),
            "fibres_no_reference": on_unknowns(fibre_out, bars, version)}

    groups = {g: {"calibration": sum(r["group"] == g for r in calibration_rows),
                  "test": sum(r["group"] == g for r in test_rows),
                  "picture": histogram([r["true_r"] for r in calibration_rows if r["group"] == g])}
              for g in sorted({r["group"] for r in calibration_rows})}
    results = {
        "protocol": "benchmark/PROTOCOL_CONFIDENCE.md, version 2", "locked_commit": LOCKED_COMMIT, "ran_at_commit": commit,
        "ran_on": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"), "seconds": round(time.time() - started),
        "coverage_target": COVERAGE, "short_list": SHORT_LIST, "library": {"name": library.name, "sha256": library.sha256},
        "counts": {"locked": len(locked), "calibration": len(calibration_rows), "test": len(test_rows),
                   "no_reference": len(unknown_rows), "relatives": len(relative_rows), "fibres_in": len(fibre_in),
                   "fibres_no_reference": len(fibre_out), "could_not_be_read": missed_c + missed_t + missed_u + missed_r + missed_f,
                   "calibration_clusters": len({r["cluster"] for r in calibration_rows}),
                   "test_clusters": len({r["cluster"] for r in test_rows}),
                   "doubtful_in_test": len(test_rows) - len(clean)},
        "bars": bars, "groups": groups, "picture": histogram([r["true_r"] for r in calibration_rows]),
        "versions": versions, "materials": sorted({m for r in calibration_rows + test_rows for m in r["scores"]}),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "confidence_results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    with open(RESULTS / "confidence_outcomes.csv", "w", encoding="utf-8", newline="") as out:
        out.write("id,part,dataset,truth,kind,contributor,doubtful,compared,verdict,best,true_r\n")
        for part, rows in (("calibration", calibration_rows), ("test", test_rows), ("no reference", unknown_rows),
                           ("relative", relative_rows), ("fibre", fibre_rows)):
            for r in rows:
                name = r["contributor"].replace(",", ";")
                out.write(f'{r["id"]},{part},{r["dataset"]},{r["truth"].replace(",", ";")},{r["kind"]},{name},{r["doubtful"]},'
                          f'{r["group"]},{r["verdict"]},{r["best"].replace(",", ";")},{r["true_r"]}\n')
    say(f"Done in {time.time() - started:.0f} s")
    return results


def main():
    parser = argparse.ArgumentParser(description="Set and test the confidence bar (benchmark/PROTOCOL_CONFIDENCE.md).")
    parser.add_argument("--data", default=str(HERE / "data"), help="the folder with the data files")
    parser.add_argument("--report-only", action="store_true", help="rebuild the report from the saved results")
    args = parser.parse_args()
    if not args.report_only:
        run(args.data, say=lambda text: print(text, flush=True))
    from .confidence_report import build
    print("Report:", build(RESULTS / "confidence_results.json", RESULTS / "confidence_report.html"))


if __name__ == "__main__":
    main()
