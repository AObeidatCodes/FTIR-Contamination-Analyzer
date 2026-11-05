"""
FTIR Contamination Analyzer - the benchmark's stress tests

Each test changes a copy of a spectrum in one way a real measurement can go wrong. Everything is in absorbance, and
the random part is fixed by the seed, the spectrum and the level, so a run can be repeated exactly.

    perturb    one spectrum with one change

Short names used in this file:
    wn = wavenumbers (cm-1)    a = absorbance

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import zlib

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .scoring import SEED

NOISE, DRIFT, SHIFT, BLUR = "noise", "baseline drift", "shifted bands", "lower resolution"
LEVELS = {NOISE: (0.005, 0.01, 0.02, 0.05), DRIFT: (0.05, 0.10, 0.25, 0.50), SHIFT: (1, 2, 4, 8), BLUR: (8, 16, 32)}
UNITS = {NOISE: "share", DRIFT: "share", SHIFT: "cm-1", BLUR: "cm-1"}
FWHM_TO_SIGMA = 1 / 2.3548200450309493


def _stretches(wn):
    """The unbroken stretches of a wavenumber axis: Open Specy has a hole, which must stay a hole."""
    steps = np.diff(wn)
    breaks = np.flatnonzero(steps > 4 * np.median(steps)) + 1
    return np.split(np.arange(len(wn)), breaks)


def _blur(wn, a, fwhm):
    """A lower-resolution measurement: smoothed to the given width and sampled at half of it."""
    out_wn, out_a = [], []
    for part in _stretches(wn):
        fine = np.arange(wn[part[0]], wn[part[-1]] + 0.5, 1.0)
        smooth = gaussian_filter1d(np.interp(fine, wn[part], a[part]), fwhm * FWHM_TO_SIGMA, mode="nearest")
        coarse = np.arange(fine[0], fine[-1] + 0.5, fwhm / 2)
        out_wn.append(coarse)
        out_a.append(np.interp(coarse, fine, smooth))
    return np.concatenate(out_wn), np.concatenate(out_a)


def perturb(wn, a, test, level, key=""):
    """(wn, a) changed by one stress test. The input is not touched."""
    rng = np.random.default_rng([SEED, zlib.crc32(str(key).encode("utf-8")), zlib.crc32(test.encode()), int(level * 1000)])
    wn, a = np.asarray(wn, float), np.asarray(a, float)
    span = np.nanmax(a) - np.nanmin(a)
    if test == NOISE:
        return wn.copy(), a + rng.normal(0, level * span, len(a))
    if test == DRIFT:
        x = (wn - wn.min()) / (wn.max() - wn.min())
        shape = rng.uniform(-1, 1) * (2 * x - 1) + np.sin(np.pi * x + rng.uniform(0, np.pi))
        return wn.copy(), a + level * span * shape / np.max(np.abs(shape))
    if test == SHIFT:
        return wn + level * rng.choice((-1, 1)), a.copy()
    if test == BLUR:
        return _blur(wn, a, level)
    raise ValueError(f"Unknown stress test {test!r}")
