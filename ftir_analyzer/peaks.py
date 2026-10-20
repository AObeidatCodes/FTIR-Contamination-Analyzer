"""
FTIR Contamination Analyzer - peaks and band names

Finds the real peaks of a spectrum (not the noise wiggles) and names each one from
a band table (for example 1730 -> "C=O (ester / ketone / acid)").

Short names used in this file:
    wn = wavenumbers    a = absorbance (or band heights)    w = one band position
    idx = row numbers of the peaks

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from . import config


@lru_cache(maxsize=1)
def band_table():
    """The band table (columns: low, high, assignment). Read once, then kept in memory."""
    return pd.read_csv(config.BAND_TABLE_FILE, comment="#")


def find_real_peaks(wn, a, min_share=config.PEAK_SHARE, min_distance_cm=config.PEAK_DISTANCE_CM):
    """Positions and heights of the peaks that stick out by at least `min_share` of the height range.

    "Stick out" is the prominence: how far a peak rises above the higher of its two
    neighbouring valleys, so a peak sitting on a slope is judged fairly. Two peaks closer
    than `min_distance_cm` count as one (the taller is kept).
    """
    height_range = np.nanmax(a) - np.nanmin(a)                       # lowest to highest point
    spacing = np.median(np.diff(wn))                                  # cm-1 between two data points
    distance = max(1, round(min_distance_cm / spacing)) if min_distance_cm else None   # scipy counts points
    idx, _ = find_peaks(a, prominence=min_share * height_range, distance=distance)     # _ = extra info, not needed
    return wn[idx], a[idx]


def band_names(w):
    """Every assignment in the band table whose range contains wavenumber w, or '' if none."""
    table = band_table()
    rows = table[(table["low"] <= w) & (table["high"] >= w)]          # rows whose range contains w
    return "; ".join(rows["assignment"])


def band_label(w):
    """A readable label, e.g. '1030 (C-O stretch ... or Si-O-Si)' or '1690 (not in the band table)'."""
    names = band_names(w)
    return f"{w:.0f} ({names if names else 'not in the band table'})"
