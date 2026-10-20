"""
FTIR Contamination Analyzer - processing

Turns a measured spectrum into the forms the analysis needs. Every function here
returns a NEW array; the measured values are never changed.

    absorbance        %T -> absorbance (Beer-Lambert: A = -log10 T)
    on_grid           read a spectrum off at the common 5 cm-1 ruler
    baseline_als      the smooth background under a spectrum (for pictures and checks)
    fingerprint       |first derivative| scaled 0-1 (for matching: offsets and thickness drop out)
    to_library_mode   ATR correction, so a sample can be compared with the library fairly

Short names used in this file:
    wn = wavenumbers    a = absorbance    y = a spectrum on the common grid
    ok = True where there is data (not NaN)    d = steepness (the derivative)

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import numpy as np
from scipy import sparse
from scipy.signal import savgol_filter
from scipy.sparse.linalg import spsolve

from . import config

# The common ruler: 650, 655, ... 4000 cm-1. Every spectrum is read off at these points,
# so two spectra can be compared point by point whatever their original spacing.
GRID = np.arange(config.GRID_START, config.GRID_STOP + config.GRID_STEP / 2, config.GRID_STEP)
# True for the grid points in the CO2 region, which never take part in a comparison.
CO2_MASK = (GRID >= config.CO2_RANGE[0]) & (GRID <= config.CO2_RANGE[1])


def transmittance_to_absorbance(percent_t):
    """A = -log10(T), with T as a fraction. Clipped at 1e-6 so a fully black band gives A = 6, not infinity."""
    fraction = np.clip(np.asarray(percent_t, float) / 100.0, 1e-6, None)
    return -np.log10(fraction)


def absorbance(spectrum):
    """The spectrum in absorbance, as a new array (converted from %T if needed)."""
    if spectrum.unit == "%T":
        return transmittance_to_absorbance(spectrum.raw)
    return np.array(spectrum.raw, dtype=float)                       # a writable copy of the measured values


def on_grid(wn, a):
    """Read a spectrum off at the grid points; NaN where it was not measured (never invent data)."""
    y = np.interp(GRID, wn, a)                                        # value on a straight line between neighbours
    y[(GRID < wn.min()) | (GRID > wn.max())] = np.nan                 # outside the measured range: no data
    steps = np.diff(wn)
    if len(steps):                                                    # a region cut out of the file (Open Specy
        hole = steps > max(config.HOLE, 4 * np.median(steps))         # leaves out 2200-2420) stays empty: no
        for low, high in zip(wn[:-1][hole], wn[1:][hole]):            # straight line is drawn across it
            y[(GRID > low) & (GRID < high)] = np.nan
    return y


def baseline_als(y, stiffness=config.DISPLAY_STIFFNESS, peak_weight=config.PEAK_WEIGHT,
                 rounds=config.BASELINE_ROUNDS):
    """Asymmetric least squares (Eilers & Boelens, 2005): a smooth curve that hugs the underside.

    Each round fits the smoothest curve that stays close to the weighted points. Points
    above the curve are probably peaks, so they get a tiny weight in the next round and
    the curve slides under them until only the background is left.
    """
    n = len(y)                                                                       # number of points
    bend = sparse.diags([1.0, -2.0, 1.0], [0, -1, -2], shape=(n, n - 2))             # curvature: y[i] - 2y[i+1] + y[i+2]
    penalty = stiffness * bend.dot(bend.transpose())                                 # the cost of bending
    weights = np.ones(n)                                                             # round 1: every point counts
    curve = y
    for _ in range(rounds):
        W = sparse.spdiags(weights, 0, n, n)                                         # weights on the diagonal
        curve = spsolve((W + penalty).tocsc(), weights * y)                          # best curve for these weights
        weights = np.where(y > curve, peak_weight, 1 - peak_weight)                  # above the curve -> barely counts
    return curve


def fingerprint(y):
    """|first derivative| scaled to 0-1: keeps the band shapes, drops offsets, slopes and sample thickness.

    The Savitzky-Golay filter fits a small polynomial over 11 neighbouring points and takes its
    slope, so it smooths the noise while it differentiates. abs() lets both sides of a band count.
    """
    y = np.asarray(y, float)
    ok = np.isfinite(y)                                               # only the points with data
    d = np.full_like(y, np.nan)                                       # the result starts as all NaN
    edges = np.flatnonzero(np.diff(np.concatenate(([0], ok.astype(int), [0]))))
    for start, stop in zip(edges[::2], edges[1::2]):                  # each unbroken stretch of data on its own,
        if stop - start >= config.SAVGOL_WINDOW:                      # so no slope is made up across a hole
            d[start:stop] = np.abs(savgol_filter(y[start:stop], window_length=config.SAVGOL_WINDOW,
                                                 polyorder=config.SAVGOL_ORDER, deriv=1))
    if not np.isfinite(d).any():                                      # too little data for a derivative:
        return d                                                      # all NaN, which never matches anything
    spread = np.nanmax(d) - np.nanmin(d)
    if spread == 0:                                                   # a flat line has no shape to compare
        return np.full_like(y, np.nan)
    return (d - np.nanmin(d)) / spread                                # scale to 0-1 (nanmin/nanmax skip NaN)


def to_library_mode(wn, a, mode, library_mode):
    """Make a spectrum look as if it had been measured the same way as the library.

    In ATR the light reaches less deep at high wavenumber (depth ~ 1/wavenumber), so ATR
    bands at high wavenumber look weaker than in transmission:
        transmission -> ATR look:  multiply by 1000 / wavenumber
        ATR -> transmission look:  multiply by wavenumber / 1000   (the classic ATR correction)
    Same mode, or unknown mode: unchanged. Always returns a new array, never the input itself.
    """
    if mode == "transmission" and library_mode == "ATR":
        return a * config.REFERENCE_WN / wn
    if mode == "ATR" and library_mode == "transmission":
        return a * wn / config.REFERENCE_WN
    return np.array(a, dtype=float)                                   # an unchanged copy
