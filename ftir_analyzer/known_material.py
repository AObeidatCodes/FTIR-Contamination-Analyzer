"""
FTIR Contamination Analyzer - a contaminant in a known material

The bands of a main material can hide a small contaminant. If the lab has a clean spectrum of that material, it can be
taken out of the sample, and what is left is searched in the library:

    sample  ≈  a × clean spectrum  +  c  +  d × wavenumber

a, c and d are found so that the clean spectrum slides under the sample: points where the sample stands above the fit
barely count, as they are probably the contaminant (the same idea as the baseline in processing.py).

The clean spectrum must be the lab's own measurement. A library reference of the same material does not take out
cleanly: in a test on mixes made from separately measured spectra, wrong names then outnumbered right ones below a
30 % share. A material is named only when it is clearly ahead (config.KNOWN_R, config.KNOWN_LEAD), and it stays a hint:
the verdict rule was not tested on what is left after a subtraction.

Short names used in this file:
    y = the sample (as compared, on the grid)    m = the clean spectrum    ok = the points used for the fit
    left = what is left    r1, r2 = the best score and the best score of a different material

Author : Ali Obeidat
Version: 2.0.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass

import numpy as np

from . import config
from .library import search
from .processing import CO2_MASK, GRID, baseline_als


@dataclass(frozen=True)
class Remainder:
    """What is left of a spectrum after a clean spectrum of its main material was taken out."""

    known: str            # the clean spectrum that was taken out
    left: np.ndarray      # what is left, on the grid
    height: float         # the tallest band left, as a share of the sample's tallest band
    ranking: list         # [(material, r), ...] for what is left, the main material itself left out
    rival: int = 1        # position in the ranking of the best DIFFERENT material

    @property
    def lead(self):
        return self.ranking[0][1] - self.ranking[self.rival][1] if len(self.ranking) > 1 else 1.0

    @property
    def found(self):
        """The material named for what is left, or None if none is clearly ahead."""
        if not self.ranking or self.ranking[0][1] < config.KNOWN_R or self.lead < config.KNOWN_LEAD:
            return None
        return self.ranking[0][0]

    def text(self):
        """One sentence for the window and the report."""
        size = f"After taking out {self.known}, the tallest band left is {self.height:.0%} of the sample's tallest band"
        if not self.ranking:
            return f"{size}. There are no other references to compare it with."
        best, r1 = self.ranking[0]
        if self.found:
            return (f"{size}. It looks most like {best} (r {r1:.2f}, next {self.ranking[self.rival][0]} "
                    f"{self.ranking[self.rival][1]:.2f}). A hint, to be confirmed.")
        return f"{size}. Nothing in the library clearly matches it (closest {best}, r {r1:.2f})."


def slide_under(y, m, ok):
    """(a, background): the amount of m and the straight background that fit y from below."""
    x = (GRID - GRID[ok].mean()) / np.ptp(GRID[ok])
    columns = np.column_stack([np.nan_to_num(m), np.ones(len(y)), x])
    weights = np.ones(int(ok.sum()))
    coef = np.zeros(3)
    for _ in range(config.KNOWN_ROUNDS):
        root = np.sqrt(weights)[:, None]
        coef = np.linalg.lstsq(columns[ok] * root, y[ok] * root[:, 0], rcond=None)[0]
        coef[0] = max(coef[0], 0.0)
        weights = np.where(y[ok] - columns[ok] @ coef > 0, config.PEAK_WEIGHT, 1.0)
    return float(coef[0]), coef[1] + coef[2] * x


def take_out(result, known, clean, library):
    """A Remainder: the clean spectrum (on the grid, named `known`) taken out of a result, and what is left searched."""
    y = np.asarray(result.compared, float)
    m = np.asarray(clean, float)
    finite = np.isfinite(y) & np.isfinite(m)
    ok = finite & ~CO2_MASK
    if ok.sum() < config.KNOWN_MIN_POINTS:
        raise ValueError(f"{known} and this sample hardly cover the same range, so one cannot be taken out of the other.")
    a, background = slide_under(y, m, ok)
    left = np.where(finite, y - a * m - background, np.nan)
    above = left[finite] - baseline_als(left[finite])
    height = float(above[~CO2_MASK[finite]].max() / np.ptp(y[ok]))
    best, r = search(m, library)[0]                                     # the main material is no contaminant of itself
    main = library.group_of(best) if r >= config.PROBABLE_R else None
    ranking = [(name, score) for name, score in search(left, library) if library.group_of(name) != main]
    return Remainder(known, left, height, ranking, library.rival(ranking) if len(ranking) > 1 else 0)
