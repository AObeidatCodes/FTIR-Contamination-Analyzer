"""
FTIR Contamination Analyzer - runs the benchmark (PROTOCOL.md) and writes the results

    python -m benchmark --data benchmark/data         the whole benchmark, then the report
    python -m benchmark --report-only                 only the report, from the saved results

The data folder needs feature_matrix_raw_transmittance.csv, medoid_nobaseline.rds and Sample_Spectra.csv. The tool
checks each one's SHA-256 against the protocol, and refuses to run if ftir_analyzer/ is not the locked commit. It
does not write to the program, the records or the data folder. Spectra are never copied into the results.

Short names used in this file:
    item = one spectrum to test    out = the stored outcome of one item

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")              # one thread per worker: the work is split by spectrum
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if "FTIR_ANALYZER_RECORDS" not in os.environ:              # a lab's own references must not change the benchmark
    os.environ["FTIR_ANALYZER_RECORDS"] = tempfile.mkdtemp(prefix="ftir_benchmark_")

import numpy as np                                                                   # noqa: E402
import pandas as pd                                                                  # noqa: E402

from ftir_analyzer.analysis import PROBABLE, WEAK, analyse                           # noqa: E402
from ftir_analyzer import config                                                     # noqa: E402
from ftir_analyzer.library import load_library, pearson                              # noqa: E402
from ftir_analyzer.openspecy import PACK_DIR, OpenSpecyLibrary, install_pack         # noqa: E402
from ftir_analyzer.processing import absorbance, on_grid                             # noqa: E402
from ftir_analyzer.spectrum_io import Spectrum, SpectrumFileError                    # noqa: E402

from . import scoring                                                                # noqa: E402
from .sets import FIBRES, IN, OPEN_SPECY, OPENFTIR, OUT, RELATIVE                    # noqa: E402
from .sets import first_by_hash, read_fibres, read_open_specy, read_openftir, split_locked   # noqa: E402
from .stress import LEVELS, UNITS, perturb                                           # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RESULTS = HERE / "results"
LOCKED_COMMIT = "c432cee"
FILES = {"feature_matrix_raw_transmittance.csv": "2739d901529a0fd97e693068d82cee5b7eee2a616f5e8d6e797a84ad859fa26f",
         "medoid_nobaseline.rds": "3591eb4b7be780ac12585631216bce5050cb543e9a61b8b482c91d1b4c821ab3",
         "Sample_Spectra.csv": "edb70bc53378e1c408e9bb29757f1f3a39b9c149a4c2a9dfad161dfb145918c3"}
STRESS_OPEN_SPECY = 500
COPY_R = 0.9999
CHUNK = 24
WORKERS = max(1, min(10, (os.cpu_count() or 2) - 4))       # leaves the computer usable while it runs

_library = None


# ---------------------------------------------------------------------------- guards
def check_program():
    """The locked program, or stop. An uncommitted change counts as a change."""
    changed = subprocess.run(["git", "diff", "--quiet", LOCKED_COMMIT, "--", "ftir_analyzer"], cwd=REPO).returncode
    if changed:
        raise SystemExit(f"ftir_analyzer/ differs from the locked commit {LOCKED_COMMIT}: the benchmark will not run.")
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()


def check_data(folder):
    """The three files named in the protocol, byte for byte, or stop."""
    for name, expected in FILES.items():
        path = Path(folder) / name
        if not path.exists():
            raise SystemExit(f"Missing data file: {path}")
        found = hashlib.sha256(path.read_bytes()).hexdigest()
        if found != expected:
            raise SystemExit(f"{name} is not the file the protocol names:\n  expected {expected}\n  found    {found}")


# ---------------------------------------------------------------------------- scoring one spectrum
def _start_worker(extended_dir):
    global _library
    _library = load_library(extended=bool(extended_dir), openspecy_dir=extended_dir or None)


def answer_of(item, library, wn=None, y=None, unit=None):
    """Run the program's own analysis on an item and keep what the benchmark needs. Spectra stay out of it."""
    if item.locked:
        raise ValueError("The locked set must not be scored")
    spectrum = Spectrum(item.key, item.wn if wn is None else wn, item.y if y is None else y,
                        unit or item.unit, "benchmark", Path("benchmark"), "")
    try:
        r = analyse(spectrum, library, mode=item.mode, mode_source="benchmark")
    except SpectrumFileError:
        return {"verdict": "could not be read", "best": "", "second": "", "tied": False, "r": 0.0, "gap": 0.0,
                "reading": "", "best_material": ""}
    return {"verdict": r.verdict, "best": library.group_of(r.best), "second": library.group_of(r.runner_up),
            "tied": r.gap < config.MIN_GAP, "r": round(r.r, 4), "gap": round(r.gap, 4), "reading": r.reading,
            "best_material": r.best}


def _score_chunk(chunk):
    return [answer_of(item, _library) for item in chunk]


def _stress_chunk(chunk):
    done = []
    for item, test, level in chunk:
        a = absorbance(Spectrum(item.key, item.wn, item.y, item.unit, "", Path("."), ""))
        wn, changed = perturb(item.wn, a, test, level, item.key)
        done.append(answer_of(item, _library, wn, changed, "A"))
    return done


def _in_chunks(items):
    return [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]


def run_all(work, function, extended_dir, say):
    """Every job in parallel, in order. Each worker loads its own copy of the library once."""
    results, started = [], time.time()
    chunks = _in_chunks(work)
    with ProcessPoolExecutor(WORKERS, initializer=_start_worker, initargs=(extended_dir,)) as pool:
        for i, part in enumerate(pool.map(function, chunks)):
            results.extend(part)
            if i % 25 == 0:
                say(f"  {len(results)} of {len(work)}, {time.time() - started:.0f} s")
    return results


def is_copy(item, library):
    """True if a test spectrum is a copy of a reference: r >= COPY_R on the grid, with no fingerprint step."""
    a = absorbance(Spectrum(item.key, item.wn, item.y, item.unit, "", Path("."), ""))
    y = on_grid(item.wn, a)
    return any(pearson(y, reference) >= COPY_R for reference in library.spectra.values())


# ---------------------------------------------------------------------------- turning answers into results
def outcome(item, answer, library_groups=None):
    """One row of the results. library_groups: a run with another library, where more materials may be in it."""
    kind = item.kind
    if library_groups is not None and kind == OUT and item.truth in library_groups:
        kind = IN
    return {"id": hashlib.sha256(item.key.encode("utf-8")).hexdigest()[:12], "dataset": item.dataset, "truth": item.truth,
            "kind": kind, "relative": item.relative, "cluster": item.cluster, "contributor": item.contributor,
            "label": item.label, "doubtful": item.doubtful, "replica": item.replica, **answer,
            "bucket": scoring.bucket(kind, answer["verdict"], answer["best"], item.truth, item.relative)}


def share(k, n, interval):
    return {"k": int(k), "n": int(n), "share": (k / n if n else None), "low": interval[0], "high": interval[1]}


def headline(rows, dataset):
    """The numbers the report leads with, for one data set. rows: a DataFrame of outcomes."""
    rows = rows[rows.dataset == dataset]
    out, inside = rows[rows.kind == OUT], rows[rows.kind == IN]
    answered = inside[inside.verdict == PROBABLE]
    false = (out.verdict == PROBABLE).to_numpy()
    right = (answered.bucket == scoring.RIGHT).to_numpy()
    family = (answered.bucket != scoring.WRONG).to_numpy()
    probable = (inside.verdict == PROBABLE).to_numpy()
    top = (inside.best == inside.truth).to_numpy()
    return {"false_probable": share(false.sum(), len(out), scoring.margin(false, out.cluster, dataset)),
            "false_probable_same_family": int(sum(scoring.same_family(b, t) for b, t in
                                                  zip(out.best[false], out.truth[false]))),
            "strict_right": share(right.sum(), len(answered), scoring.margin(right, answered.cluster, dataset)),
            "family_right": share(family.sum(), len(answered), scoring.margin(family, answered.cluster, dataset)),
            "coverage": share(probable.sum(), len(inside), scoring.margin(probable, inside.cluster, dataset)),
            "best_match": share(top.sum(), len(inside), scoring.margin(top, inside.cluster, dataset)),
            "buckets": {str(k): int(v) for k, v in inside.bucket.value_counts().items()},
            "no_answer": no_answer_split(inside)}


def no_answer_split(inside):
    """Weak pointing at the truth, weak pointing elsewhere, and no reliable match."""
    silent = inside[inside.verdict != PROBABLE]
    weak = silent[silent.verdict == WEAK]
    pointing = ((weak.best == weak.truth) | (weak.tied & (weak.second == weak.truth))).sum()
    return {"weak_at_truth": int(pointing), "weak_elsewhere": int(len(weak) - pointing),
            "no_reliable_match": int(len(silent) - len(weak))}


def per_material(rows):
    """One row per data set and material."""
    table = []
    for (dataset, kind, truth), part in rows.groupby(["dataset", "kind", "truth"]):
        answered = part[part.verdict == PROBABLE]
        counts = part.bucket.value_counts()
        table.append({"dataset": dataset, "kind": kind, "truth": truth, "n": len(part),
                      "probable": len(answered), "right": int(counts.get(scoring.RIGHT, 0)),
                      "family": int(counts.get(scoring.RIGHT_FAMILY, 0)), "wrong": int(counts.get(scoring.WRONG, 0)),
                      "false_probable": int(counts.get(scoring.FALSE_PROBABLE, 0)),
                      "relative_named": int(counts.get(scoring.RELATIVE_NAMED, 0)),
                      "weak": int((part.verdict == WEAK).sum()),
                      "none": int((part.verdict != PROBABLE).sum() - (part.verdict == WEAK).sum()),
                      "doubtful": int(part.doubtful.sum()), "median_r": round(float(part.r.median()), 3),
                      "named": {str(k): int(v) for k, v in answered.best.value_counts().items()}})
    return table


def per_contributor(rows):
    """Open Specy, one row per contributor: a single large source cannot hide behind the total."""
    table = []
    for name, part in rows[rows.dataset == OPEN_SPECY].groupby("contributor"):
        inside, out = part[part.kind == IN], part[part.kind == OUT]
        answered = inside[inside.verdict == PROBABLE]
        table.append({"contributor": name, "n": len(part), "in_library": len(inside),
                      "probable": len(answered), "right": int((answered.bucket == scoring.RIGHT).sum()),
                      "not_right": int((answered.bucket != scoring.RIGHT).sum()), "not_in_library": len(out),
                      "false_probable": int((out.verdict == PROBABLE).sum())})
    return sorted(table, key=lambda row: -row["n"])


def repeatability(rows):
    """Do the repeats of a fibre sample get the same verdict, and the same material?"""
    fibres = rows[rows.dataset == FIBRES]
    groups = [part for _, part in fibres.groupby("cluster") if len(part) > 1]
    same_verdict = sum(part.verdict.nunique() == 1 for part in groups)
    same_both = sum(part.verdict.nunique() == 1 and part.best.nunique() == 1 for part in groups)
    spread = [float(part.r.max() - part.r.min()) for part in groups]
    different = [{"sample": part.cluster.iloc[0], "truth": part.truth.iloc[0], "verdicts": part.verdict.tolist(),
                  "named": part.best.tolist(), "r": part.r.tolist()}
                 for part in groups if part.verdict.nunique() > 1 or part.best.nunique() > 1]
    return {"samples": len(groups), "spectra": int(sum(len(p) for p in groups)), "same_verdict": int(same_verdict),
            "same_verdict_and_material": int(same_both), "median_r_spread": float(np.median(spread)) if spread else 0.0,
            "largest_r_spread": max(spread, default=0.0), "different": different}


def relatives_table(rows):
    table = []
    for (dataset, truth), part in rows[rows.kind == RELATIVE].groupby(["dataset", "truth"]):
        counts = part.bucket.value_counts()
        table.append({"dataset": dataset, "truth": truth, "relative": part.relative.iloc[0], "n": len(part),
                      "relative_named": int(counts.get(scoring.RELATIVE_NAMED, 0)),
                      "wrong": int(counts.get(scoring.WRONG, 0)), "no_answer": int(counts.get(scoring.NO_ANSWER, 0)),
                      "named": {str(k): int(v) for k, v in part[part.verdict == PROBABLE].best.value_counts().items()}})
    return table


def lead_rule(rows, dataset):
    """What the lead rule is worth: the same answers with 'probable' decided by the score alone."""
    rows = rows[rows.dataset == dataset]
    kept = rows[rows.verdict == PROBABLE]
    extra = rows[(rows.verdict != PROBABLE) & rows.r.map(scoring.without_lead)]
    inside, out = extra[extra.kind == IN], extra[extra.kind == OUT]
    return {"held": {str(k): int(v) for k, v in inside.truth.value_counts().items()},
            "probable_with": len(kept), "probable_without": len(kept) + len(extra), "extra": len(extra),
            "extra_right": int((inside.best == inside.truth).sum()),
            "extra_wrong_material": int((inside.best != inside.truth).sum()),
            "extra_false_probable": len(out), "extra_relative": len(extra[extra.kind == RELATIVE]),
            "false_with": int(((rows.kind == OUT) & (rows.verdict == PROBABLE)).sum()),
            "out_total": int((rows.kind == OUT).sum())}


def without_doubtful(rows, dataset):
    return headline(rows[~rows.doubtful], dataset)


def by_reading(rows):
    """Open Specy, materials with a reference: answers by the way the spectrum ended up being compared."""
    inside = rows[(rows.dataset == OPEN_SPECY) & (rows.kind == IN)]
    return [{"reading": str(name), "n": len(part), "probable": int((part.verdict == PROBABLE).sum()),
             "right": int((part.bucket == scoring.RIGHT).sum()), "median_r": round(float(part.r.median()), 3)}
            for name, part in inside.groupby("reading")]


def stress_summary(clean, jobs, answers):
    """Per test and level, per data set: right on materials with a reference, false probable on those without.

    Level 0 is the clean spectrum: the same spectra, so each line starts from its own true starting point.
    """
    by_key = {}
    fixed = list(dict.fromkeys(item for item, _, _ in jobs))
    jobs = jobs + [(item, name, 0) for name in LEVELS for item in fixed]
    answers = answers + [clean[item.dataset, item.key] for _ in LEVELS for item in fixed]
    for (item, test, level), answer in zip(jobs, answers):
        by_key.setdefault((item.dataset, test, level), []).append((item, answer))
    summary = []
    for (dataset, test, level), pairs in by_key.items():
        rows = pd.DataFrame([outcome(i, a) for i, a in pairs])
        same = sum(clean[i.dataset, i.key]["verdict"] == a["verdict"] and clean[i.dataset, i.key]["best"] == a["best"]
                   for i, a in pairs)
        inside, out = rows[rows.kind == IN], rows[rows.kind == OUT]
        summary.append({"dataset": dataset, "test": test, "level": level, "unit": UNITS[test], "n": len(rows),
                        "same_answer": same, "n_in": len(inside), "right": int((inside.bucket == scoring.RIGHT).sum()),
                        "not_right": int(((inside.verdict == PROBABLE) & (inside.bucket != scoring.RIGHT)).sum()),
                        "n_out": len(out), "false_probable": int((out.verdict == PROBABLE).sum())})
    return summary


def to_csv_rows(rows):
    """The committed outcomes: no spectra. A material label is kept only where the answer was a failure."""
    keep = ["id", "dataset", "truth", "kind", "contributor", "doubtful", "replica", "verdict", "best_material", "r",
            "gap", "reading", "bucket"]
    table = rows[keep + ["label"]].copy()
    failed = table.bucket.isin([scoring.WRONG, scoring.FALSE_PROBABLE, scoring.RIGHT_FAMILY])
    table.loc[~failed, "label"] = ""
    return table


# ---------------------------------------------------------------------------- the whole run
def run(data_folder, say=print):
    commit = check_program()
    check_data(data_folder)
    started = time.time()
    data_folder = Path(data_folder)
    library = load_library()
    if len(library) != 16 or library.in_house:
        raise SystemExit("The benchmark needs the 16 shipped references and nothing else.")

    say("Reading the data")
    fibres = read_fibres(data_folder / "feature_matrix_raw_transmittance.csv")
    open_specy, specy_left_out = read_open_specy(data_folder / "medoid_nobaseline.rds")
    open_specy = split_locked(open_specy)
    openftir, ftir_left_out = read_openftir(data_folder / "Sample_Spectra.csv",
                                            {library.info_of(n).original_name for n in library.spectra})
    test = [i for i in open_specy if not i.locked]
    say(f"Open Specy: {len(open_specy)} labelled, {len(test)} in the test set, {len(open_specy) - len(test)} locked")
    copies = [i.key for i in test + fibres + openftir if is_copy(i, library)]
    test = [i for i in test if i.key not in set(copies)]
    fibres = [i for i in fibres if i.key not in set(copies)]
    openftir = [i for i in openftir if i.key not in set(copies)]
    say(f"Copies of a reference left out: {len(copies)}")

    say(f"Default library: {len(fibres) + len(test) + len(openftir)} spectra, {WORKERS} workers")
    everything = fibres + test + openftir
    answers = run_all(everything, _score_chunk, "", say)
    rows = pd.DataFrame([outcome(i, a) for i, a in zip(everything, answers)])
    main = rows[(rows.replica == 1)]
    clean = {(i.dataset, i.key): a for i, a in zip(everything, answers)}

    say("Extended library")
    with tempfile.TemporaryDirectory() as folder:
        summary = install_pack(library, folder)
        extended = load_library(extended=True, openspecy_dir=folder)
        pack_keys = {info.notes.removeprefix("Open Specy id ") for info, _ in OpenSpecyLibrary(folder).entries()}
        pack_clusters = {i.cluster for i in open_specy if i.key in pack_keys}
        reduced = [i for i in test if i.cluster not in pack_clusters] + [i for i in fibres if i.replica == 1]
        groups = {extended.group_of(n) for n in extended.spectra}
        wide = run_all(reduced, _score_chunk, folder, say)
    ext_rows = pd.DataFrame([outcome(i, a, groups) for i, a in zip(reduced, wide)])
    base_rows = pd.DataFrame([outcome(i, clean[i.dataset, i.key]) for i in reduced])

    say("Stress tests")
    fixed = [i for i in fibres if i.replica == 1] + first_by_hash(test, STRESS_OPEN_SPECY)
    jobs = [(item, name, level) for name, levels in LEVELS.items() for level in levels for item in fixed]
    stressed = run_all(jobs, _stress_chunk, "", say)

    results = {
        "protocol": "benchmark/PROTOCOL.md, version 1", "locked_commit": LOCKED_COMMIT, "ran_at_commit": commit,
        "ran_on": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"), "seconds": round(time.time() - started),
        "library": {"name": library.name, "sha256": library.sha256, "references": len(library)},
        "data": FILES,
        "counts": {"fibre_samples": int((main.dataset == FIBRES).sum()), "fibre_spectra": len(fibres),
                   "open_specy_labelled": len(open_specy), "open_specy_test": len(test),
                   "open_specy_locked": int(sum(i.locked for i in open_specy)),
                   "open_specy_clusters_test": len({i.cluster for i in test}),
                   "openftir": len(openftir), "copies_left_out": len(copies),
                   "could_not_be_read": int((rows.verdict == "could not be read").sum()),
                   "kinds": {f"{d}|{k}": int(v) for (d, k), v in main.groupby(["dataset", "kind"]).size().items()}},
        "left_out": {"open_specy": specy_left_out, "openftir": ftir_left_out},
        "headline": {d: headline(main, d) for d in (FIBRES, OPEN_SPECY)},
        "without_doubtful": {OPEN_SPECY: without_doubtful(main, OPEN_SPECY),
                             "doubtful_spectra": int(main[main.dataset == OPEN_SPECY].doubtful.sum())},
        "per_material": per_material(main[main.dataset != OPENFTIR]),
        "per_contributor": per_contributor(main),
        "repeatability": repeatability(rows),
        "relatives": relatives_table(main[main.dataset != OPENFTIR]),
        "lead_rule": {d: lead_rule(main, d) for d in (FIBRES, OPEN_SPECY)},
        "by_reading": by_reading(main),
        "stress": stress_summary(clean, jobs, stressed),
        "extended": {"references": len(extended), "kept_from_pack": summary.kept, "pack_clusters_left_out": len(pack_clusters),
                     "spectra": len(reduced), "materials_added": sorted(groups - {library.group_of(n) for n in library.spectra}),
                     "lead_rule": {d: lead_rule(ext_rows, d) for d in (FIBRES, OPEN_SPECY)},
                     "extended": {d: headline(ext_rows, d) for d in (FIBRES, OPEN_SPECY)},
                     "default_same_spectra": {d: headline(base_rows, d) for d in (FIBRES, OPEN_SPECY)}},
        "openftir": {"headline": headline(main, OPENFTIR), "per_material": per_material(main[main.dataset == OPENFTIR])},
        "failures": main[main.bucket.isin([scoring.WRONG, scoring.FALSE_PROBABLE])][
            ["dataset", "truth", "kind", "best_material", "r", "gap", "contributor", "label", "doubtful"]
        ].sort_values("r", ascending=False).head(60).to_dict("records"),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "results.json").write_text(json.dumps(results, indent=1, default=_plain), encoding="utf-8")
    to_csv_rows(rows).to_csv(RESULTS / "outcomes.csv", index=False)
    to_csv_rows(ext_rows).to_csv(RESULTS / "outcomes_extended.csv", index=False)
    say(f"Done in {time.time() - started:.0f} s")
    return results


def _plain(value):
    """numpy numbers to plain numbers, for the results file."""
    return value.item() if hasattr(value, "item") else str(value)


def main():
    parser = argparse.ArgumentParser(description="Run the FTIR benchmark (benchmark/PROTOCOL.md).")
    parser.add_argument("--data", default=str(HERE / "data"), help="the folder with the three data files")
    parser.add_argument("--report-only", action="store_true", help="rebuild the report from the saved results")
    args = parser.parse_args()
    if not args.report_only:
        run(args.data, say=lambda text: print(text, flush=True))
    from .report import build
    print("Report:", build(RESULTS / "results.json", RESULTS / "benchmark_report.html"))


if __name__ == "__main__":
    sys.exit(main())
