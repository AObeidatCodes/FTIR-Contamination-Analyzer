"""
FTIR Contamination Analyzer - protocol v4: the shift-tolerant search

Compares the search of today with the one that tries small band shifts, on data no earlier step has read, and applies
the pass rules of benchmark/PROTOCOL_SHIFT.md. The rules are checked by this file, not by a person after the fact.

    without_material   the library with every reference of one material removed
    outcome            the three measures for one spectrum
    tally              the counts of many outcomes
    verdict            do the numbers pass the protocol's rules?

The tool will not run until the data file's SHA-256 and the locked commit are filled in below, before the first run.

Short names used in this file:
    wn = wavenumbers (cm-1)    y = one spectrum as measured

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ftir_analyzer import config
from ftir_analyzer.analysis import PROBABLE, analyse
from ftir_analyzer.library import Library
from ftir_analyzer.spectrum_io import Spectrum

from .scoring import SEED, wilson
from .sets import measured_points

REPO = Path(__file__).resolve().parent.parent
DATA_FILE = REPO / "benchmark" / "data" / "FTIR-PLASTIC.zip"
DATA_SHA256 = ""                  # entered before the first run, once the licence is confirmed
LOCKED_COMMIT = ""                # the commit the program is locked at, entered before the first run
SHIFTS = (0, 2, 4)
SLACK = 0.01                      # 1 percentage point
FALSE_LIMIT = 0.05


@dataclass
class Tally:
    """Counts for one search."""

    spectra: int = 0
    right: int = 0
    not_right: int = 0
    false: int = 0

    def rate(self, name):
        return getattr(self, name) / self.spectra if self.spectra else 0.0


def locked():
    """Stops unless the data and the program are exactly the ones the protocol names."""
    if not DATA_SHA256 or not LOCKED_COMMIT:
        raise SystemExit("The data file and the locked commit are not filled in: this step will not run.")
    if hashlib.sha256(DATA_FILE.read_bytes()).hexdigest() != DATA_SHA256:
        raise SystemExit("The data file is not the one the protocol names: this step will not run.")
    changed = subprocess.run(["git", "diff", "--quiet", LOCKED_COMMIT, "--", "ftir_analyzer"], cwd=REPO).returncode
    if changed:
        raise SystemExit(f"ftir_analyzer/ differs from the locked commit {LOCKED_COMMIT}: this step will not run.")


def without_material(library, material):
    """The same library with every reference of one material removed."""
    kept = {name: spectrum for name, spectrum in library.spectra.items() if library.group_of(name) != material}
    return Library(library.name, library.mode, kept, library.sha256, library.path, library.info)


def outcome(wn, y, unit, mode, truth, library, without, shifts, moved=0.0):
    """(right, not right, false) for one spectrum. moved: a band shift applied to the spectrum first."""
    wn, y = measured_points(wn + moved, y)
    spectrum = Spectrum("spectrum", wn, y, unit, "benchmark", Path("benchmark"), "")
    full = analyse(spectrum, library, mode=mode, mode_source="benchmark", shifts=shifts)
    right = full.verdict == PROBABLE and library.group_of(full.best) == truth
    not_right = full.verdict == PROBABLE and not right
    false = analyse(spectrum, without, mode=mode, mode_source="benchmark", shifts=shifts).verdict == PROBABLE
    return right, not_right, false


def tally(outcomes):
    counts = Tally()
    for right, not_right, false in outcomes:
        counts.spectra += 1
        counts.right += right
        counts.not_right += not_right
        counts.false += false
    return counts


def direction(key):
    """The direction of the applied shift for one spectrum: fixed by the seed and the spectrum."""
    return np.random.default_rng([SEED, sum(str(key).encode("utf-8"))]).choice((-1, 1))


def verdict(today, tolerant):
    """{rule: passed} from {shift: Tally} of each search, and whether all of them hold."""
    low, high = wilson(tolerant[0].false, tolerant[0].spectra)
    rules = {
        "1 false probable": (high <= FALSE_LIMIT and tolerant[0].rate("false") <= today[0].rate("false") + SLACK),
        "2 not right probable": tolerant[0].rate("not_right") <= today[0].rate("not_right") + SLACK,
        "3 right probable at shift 0": tolerant[0].rate("right") >= today[0].rate("right") - SLACK,
        "4 right probable at shifts 2 and 4": all(tolerant[s].right > today[s].right for s in (2, 4)),
    }
    return rules, all(rules.values())


def main():
    locked()
    raise SystemExit(f"The reader for {DATA_FILE.name} is written once the file's layout is known, before its results are.")


if __name__ == "__main__":
    print("Shifts tested:", config.SHIFT_TEST)
    main()
