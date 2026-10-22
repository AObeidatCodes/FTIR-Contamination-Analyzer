"""
FTIR Contamination Analyzer - two-component fit

When the best match leaves clear bands unexplained ("second component?"), this asks: does the
spectrum look like a MIX of the match and one other reference?

How (for every other reference in turn):
    sample  ≈  a × match  +  b × other  +  c  +  d × wavenumber
a and b are how much of each reference is in the sample (never negative); c + d × wavenumber is a
straight background line, so a tilted or lifted baseline does not count as a component. It is
solved by least squares (scipy's lsq_linear) on the copy that was compared with the library,
CO2 region left out. The best "other" is the one that fits best. It is reported only when it
clearly helps:
    the fit r rises by at least MIX_GAIN over the match alone,
    the other reference makes up at least MIX_MIN_SHARE of the signal, and
    it has a band at most of the bands the match could not explain.

The shares compare band heights: each reference counts as tall as its tallest band, so "70 % PE +
30 % PET" means PE's bands make up 70 % of the height. That is not the mass: a strong absorber looks
bigger than it is. The fit is a hint for the person reading the spectrum, never a verdict; the verdict
itself (r, lead, thresholds) is not changed by it.

Short names used in this file:
    y = the sample (as compared, on the grid)    m = the match    o = the other reference
    X = the columns of the fit (match, other, 1, wavenumber)    coef = the fitted a, b, c, d
    ok = the points used (data present, CO2 region left out)

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import lsq_linear

from . import config
from .processing import CO2_MASK, GRID


@dataclass(frozen=True)
class Mixture:
    """A two-component fit that clearly beats the match alone."""

    match: str            # the best match
    other: str            # the second reference
    share_match: float    # share of the band height (0-1), each reference counted by its tallest band
    share_other: float
    r_alone: float        # how well the match alone (plus a background line) fits the spectrum
    r_fit: float          # how well the two together fit
    explains: list        # the unexplained bands the other reference has a band at

    def text(self):
        """One sentence for the window and the report."""
        return (f"Fits as about {self.share_match:.0%} {self.match} + {self.share_other:.0%} {self.other} "
                f"(fit r {self.r_fit:.3f}, against {self.r_alone:.3f} for {self.match} alone). "
                "Shares of the band height, not of the mass; a hint, to be confirmed.")


def _fit(y, columns, ok):
    """Least squares with the reference amounts kept >= 0; returns (coefficients, fitted curve, r)."""
    x = (GRID[ok] - GRID[ok].mean()) / np.ptp(GRID[ok])               # the background line's slope term, scaled
    X = np.column_stack([c[ok] for c in columns] + [np.ones(ok.sum()), x])
    n = len(columns)
    bounds = ([0.0] * n + [-np.inf, -np.inf], [np.inf] * n + [np.inf, np.inf])
    coef = lsq_linear(X, y[ok], bounds=bounds).x
    fitted = X @ coef
    r = float(np.corrcoef(fitted, y[ok])[0, 1]) if np.ptp(fitted) > 0 else 0.0
    return coef, r


def _has_band_at(reference, w):
    """Does a reference (scaled 0-1) rise to at least MIX_BAND_SHARE within ±TOLERANCE_CM of w?"""
    near = np.abs(GRID - w) <= config.TOLERANCE_CM
    part = reference[near]
    lo, hi = np.nanmin(reference), np.nanmax(reference)
    return bool(np.isfinite(part).any() and (np.nanmax(part) - lo) / (hi - lo) >= config.MIX_BAND_SHARE)


def two_component_fit(result, library):
    """The best two-component fit for a result with unexplained bands, or None if none clearly helps."""
    if not result.has_match or not result.evidence or not result.evidence.unexplained:
        return None
    y = np.asarray(result.compared, float)
    match = np.asarray(library.spectra[result.best], float)
    ok = np.isfinite(y) & np.isfinite(match) & ~CO2_MASK
    if ok.sum() < 50:
        return None
    (a, *_), r_alone = _fit(y, [match], ok)
    unexplained = result.evidence.unexplained
    best = None
    for name, spectrum in library.spectra.items():
        if name == result.best or library.group_of(name) == library.group_of(result.best):
            continue                                                     # the same material twice is no mix
        other = np.asarray(spectrum, float)
        use = ok & np.isfinite(other)
        if use.sum() < 50:
            continue
        (a, b, *_), r_fit = _fit(y, [match, other], use)
        if best is None or r_fit > best[0]:
            best = (r_fit, name, a, b, other)
    if best is None:
        return None
    r_fit, name, a, b, other = best
    signal_match, signal_other = a * np.ptp(match[ok]), b * np.ptp(other[ok][np.isfinite(other[ok])])   # band heights
    if signal_match + signal_other <= 0:
        return None
    share_other = signal_other / (signal_match + signal_other)
    explains = [w for w in unexplained if _has_band_at(other, w)]
    if (r_fit - r_alone < config.MIX_GAIN or share_other < config.MIX_MIN_SHARE
            or len(explains) < max(1, (len(unexplained) + 1) // 2)):
        return None
    return Mixture(result.best, name, 1 - share_other, share_other, r_alone, r_fit, explains)
