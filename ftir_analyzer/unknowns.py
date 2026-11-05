"""
FTIR Contamination Analyzer - unknown groups

Samples without a probable verdict have no name, so they cannot be counted as a material. This finds the ones that
look alike, using the same fingerprint and score as the library search. A group does not say what the material is,
and nothing here changes a verdict.

    save_fingerprints   at export: the fingerprint of each sample without a probable verdict
    read_fingerprints   those fingerprints, the latest for each sample
    similarity          every fingerprint against every other, as a table of r
    link_groups         samples joined through links of r >= the limit
    unknown_groups      the groups among a list of samples
    usable_file         a group's file, if a reference can safely be made from it

Short names used in this file:
    r = a Pearson r    s = one Sample    n = how many    y = a fingerprint on the common grid

Author : Ali Obeidat
Version: 2.0.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .analysis import PROBABLE
from .processing import CO2_MASK, GRID, fingerprint
from .spectrum_io import SpectrumFileError, checksum, read_spectra, read_table
from .trends import NOT_RECORDED

LOG_HEADER = (
    "# Unknown fingerprints: the fingerprint of each exported sample without a probable verdict, used to find samples\n"
    "# that look alike. Each row belongs to one spectrum of one exact file. Rows are only added.\n"
)
COLUMNS = ["file_sha256", "sample", "path", "recorded_at"]


@dataclass(frozen=True)
class UnknownGroup:
    """Samples that look alike."""

    samples: tuple      # the Samples, oldest first
    typical: object     # the Sample most like the others
    path: str           # the file of that sample, as it was when exported ("" if not known)

    @property
    def tools(self):
        return sorted({s.tool for s in self.samples if s.tool != NOT_RECORDED}, key=str.casefold)

    @property
    def first(self):
        return min(s.day for s in self.samples)

    @property
    def last(self):
        return max(s.day for s in self.samples)


def save_fingerprints(results, path=config.UNKNOWN_LOG_FILE):
    """Keep the fingerprint of each result without a probable verdict. Earlier rows are never changed."""
    rows = [{"file_sha256": r.spectrum.sha256, "sample": r.name, "path": str(r.spectrum.path),
             "recorded_at": date.today().isoformat(), **dict(zip(_grid_names(), np.round(fingerprint(r.compared), 4)))}
            for r in results if r.verdict != PROBABLE]
    if not rows:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    if new_file:
        path.write_text(LOG_HEADER, encoding="utf-8")
    pd.DataFrame(rows, columns=COLUMNS + _grid_names()).to_csv(path, mode="a", index=False, header=new_file)
    return path


def _grid_names():
    return [f"{value:g}" for value in GRID]


def read_fingerprints(path):
    """{(sha, sample): (fingerprint, file path)}. If a sample was saved twice, the latest row counts."""
    if not Path(path).exists():
        return {}
    table = read_table(path, dtype={"file_sha256": str, "sample": str, "path": str})
    table[["path"]] = table[["path"]].fillna("")
    values = table[_grid_names()].to_numpy(float)
    return {(sha, sample): (y, where) for sha, sample, where, y in zip(table.file_sha256, table["sample"], table.path, values)}


def similarity(prints):
    """Every fingerprint against every other: the library's r, on the points each pair has, the CO2 region left out.

    The sums for each pair are matrix products, so a few thousand samples take moments. A pair with too little in
    common, or a flat one, gets 0, as in the library search.
    """
    y = np.asarray(prints, float)
    known = np.isfinite(y) & ~CO2_MASK
    y = np.where(known, y, 0.0)
    known = known.astype(float)
    points = known @ known.T
    sums = y @ known.T                                                  # the sum of row i over the points it shares with j
    squares = (y * y) @ known.T
    products = y @ y.T
    upper = points * products - sums * sums.T
    below = (points * squares - sums * sums) * (points * squares - sums * sums).T
    with np.errstate(invalid="ignore", divide="ignore"):
        scores = upper / np.sqrt(below)
    scores[~np.isfinite(scores) | (points < config.SAVGOL_WINDOW)] = 0.0
    return scores


def link_groups(scores, link=config.UNKNOWN_LINK_R, size=config.UNKNOWN_GROUP_SIZE):
    """[[indexes]], largest first: samples joined through links of r >= link. Smaller groups than `size` are left out."""
    n = len(scores)
    parent = list(range(n))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in zip(*np.nonzero(np.triu(np.asarray(scores) >= link, 1))):
        parent[root(int(a))] = root(int(b))
    groups = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(i)
    return sorted((g for g in groups.values() if len(g) >= size), key=lambda g: (-len(g), g[0]))


def unknown_groups(samples, saved, link=config.UNKNOWN_LINK_R, size=config.UNKNOWN_GROUP_SIZE):
    """(the groups among these samples, how many unnamed samples have no saved fingerprint). saved: read_fingerprints."""
    unnamed = [s for s in samples if s.verdict != PROBABLE]
    found = [s for s in unnamed if (s.sha, s.name) in saved]
    if len(found) < size:
        return [], len(unnamed) - len(found)
    scores = similarity([saved[s.sha, s.name][0] for s in found])
    groups = []
    for indexes in link_groups(scores, link, size):
        inner = scores[np.ix_(indexes, indexes)]
        typical = found[indexes[int(inner.mean(axis=1).argmax())]]
        groups.append(UnknownGroup(tuple(sorted((found[i] for i in indexes), key=lambda s: s.day)), typical,
                                   saved[typical.sha, typical.name][1]))
    return groups, len(unnamed) - len(found)


def usable_file(group):
    """The group's file, if it is still the same file and holds that one spectrum; else None.

    A file with several spectra is left out, because the sheet for adding a reference reads the first one.
    """
    path = Path(group.path) if group.path else None
    if path is None or not path.is_file() or checksum(path) != group.typical.sha:
        return None
    try:
        return path if len(read_spectra(path)) == 1 else None
    except SpectrumFileError:
        return None
