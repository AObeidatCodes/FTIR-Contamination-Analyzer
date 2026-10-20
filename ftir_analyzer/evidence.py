"""
FTIR Contamination Analyzer - band evidence

A score is one number. A reviewer wants to see WHY a material was chosen:
    found        the key bands of the reference that the sample also has
    missing      the key bands of the reference that the sample lacks
    unexplained  clear bands of the sample that the reference cannot explain:
                 the first hint of a second component (a mixture)
It also looks up where a material can come from in a fab, as a starting point for
the root-cause analysis.

Short names used in this file:
    y = a spectrum on the grid    ok = True where there is data    wn = wavenumbers    a = absorbance
    rel = band heights relative to the tallest band (tallest = 1)
    u_ / r_ = the unknown sample / the reference    pos, h = band positions, band heights    w = one position

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from . import config
from .peaks import find_real_peaks
from .processing import GRID, baseline_als


@dataclass(frozen=True)
class Evidence:
    """Which bands support a match, which are missing, and which the match cannot explain."""

    found: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    unexplained: list = field(default_factory=list)

    @property
    def n_key(self):
        """How many key bands the reference has."""
        return len(self.found) + len(self.missing)


def relative_spectrum(y):
    """Wavenumbers and band heights above the baseline, scaled so the tallest band (CO2 left out) = 1.

    Scaling to the tallest band makes a sample and a reference comparable even if one
    absorbs ten times more strongly than the other.
    """
    ok = np.isfinite(y)
    wn, a = GRID[ok], y[ok]
    above = a - baseline_als(a)
    no_co2 = (wn < config.CO2_RANGE[0]) | (wn > config.CO2_RANGE[1])
    return wn[no_co2], above[no_co2] / above[no_co2].max()


def band_evidence(unknown, reference):
    """Compare the band lists of an unknown and a reference (both on the common grid)."""
    u_wn, u_rel = relative_spectrum(unknown)
    r_wn, r_rel = relative_spectrum(reference)
    u_pos, u_h = find_real_peaks(u_wn, u_rel, config.EVIDENCE_SHARE)   # the unknown's bands
    r_pos, r_h = find_real_peaks(r_wn, r_rel, config.EVIDENCE_SHARE)   # the reference's bands
    key = r_pos[r_h >= config.KEY_SHARE]                               # the reference's key bands

    def unknown_has_band_at(w):
        """Does the unknown have a band within the tolerance (15 cm-1) of w?"""
        return len(u_pos) > 0 and np.min(np.abs(u_pos - w)) <= config.TOLERANCE_CM

    def reference_height_at(w):
        """How strongly the reference absorbs within 10 cm-1 of w (0 if it absorbs nothing there)."""
        return r_rel[np.abs(r_wn - w) <= 10].max(initial=0.0)

    return Evidence(
        found=[float(w) for w in key if unknown_has_band_at(w)],
        missing=[float(w) for w in key if not unknown_has_band_at(w)],
        # a clear band of the unknown (>= 15 %) where the reference absorbs less than a third as strongly
        unexplained=[float(w) for w, h in zip(u_pos, u_h)
                     if h >= config.EXTRA_SHARE and reference_height_at(w) < h / 3],
    )


def key_bands(y):
    """The key bands of a reference (on the grid): [(position, height relative to the tallest)], tallest first.

    The same bands the band evidence looks for in a sample (height >= KEY_SHARE of the tallest).
    """
    wn, rel = relative_spectrum(y)
    pos, h = find_real_peaks(wn, rel, config.EVIDENCE_SHARE)
    keep = h >= config.KEY_SHARE
    return sorted(zip(pos[keep].tolist(), h[keep].tolist()), key=lambda band: -band[1])


@lru_cache(maxsize=1)
def _fab_sources_table():
    """The fab-sources table, indexed by material name. Read once, then kept in memory."""
    return pd.read_csv(config.FAB_SOURCES_FILE, comment="#").set_index("material")


def fab_sources(material, library=None):
    """(possible sources, what to check next) for a library material, or None if nothing is known.

    In-house references carry their own sources (entered when they were added); shipped
    references are looked up in data/fab_sources.csv.
    """
    if library is not None:
        info = library.info_of(material)
        if info.origin == "in-house" and info.fab_sources:
            return info.fab_sources, info.check_next or "the process history"
    table = _fab_sources_table()
    key = material
    if key not in table.index and library is not None:                 # e.g. an Open Specy reference:
        key = library.group_of(material)                                # look up the material it is
        if key not in table.index:                                      # or a shipped reference of that material
            key = next((n for n in library.spectra if library.info_of(n).origin == "shipped"
                        and library.group_of(n) == key), key)
    if key not in table.index:
        return None
    row = table.loc[key]
    return row["possible sources"], row["check next"]
