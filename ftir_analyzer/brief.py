"""
FTIR Contamination Analyzer - short wording

The same facts in the same few words for the PDF, the web report and the window, so every fact fits
on one line: a check is "none · A 0.40", a flag is "Saturated".

Short names used in this file:
    c = the Checks of one spectrum    r = one Result

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import numpy as np

from . import config
from .evidence import relative_spectrum
from .peaks import band_names

# The flags of analysis.py, in one or two words (the long label is the tooltip)
FLAG_SHORT = {"CO2 artefact: probably no sample": "CO₂ artefact", "saturated bands": "Saturated",
              "water-vapour lines": "Water vapour", "second component?": "2nd component",
              "mode unknown": "Mode unknown", "mode doubt": "Mode doubt", "mode conflict": "Mode conflict"}


def short_flag(label):
    """A flag in one or two words."""
    return FLAG_SHORT.get(label, label[:1].upper() + label[1:])


def clean_name(name):
    """A sample's name as words: underscores become spaces."""
    return " ".join(str(name).replace("_", " ").split())


def check_rows(c):
    """The checks on the raw spectrum as [(label, value)], each value short enough for one line."""
    co2 = f"{c.co2_share:.2f}"
    if c.co2_share >= 0.1:
        co2 += " · points " + ("down" if c.co2_direction == "down" else "up")
    if c.no_sample:
        co2 += " · probably no sample"
    if not np.isfinite(c.vapour):
        vapour = "not measured"
    else:
        vapour = ("lines" if c.vapour_lines else "none") + f" · {c.vapour:.1f}×"
    return [("Saturation", ("saturated" if c.saturated else "none") + f" · A {c.max_a:.2f}"),
            ("CO₂ artefact", co2),
            ("C–H", c.ch if c.ch == "not measured" else f"{c.ch} · {max(c.ch_share, 0):.2f}"),
            ("O–H / N–H", c.oh if c.oh == "not measured" else f"{c.oh} · {max(c.oh_share, 0):.2f}"),
            ("Noise", f"{c.noise:.4f} A"), ("Water vapour", vapour)]


def band_name(w):
    """What a band usually is: the first assignment of the band table, or a plain note."""
    return band_names(w).split(";")[0].strip() or "not in the band table"


def band_height_fn(r, library):
    """A function w -> (height in the sample, height in the match), each as a share of its own tallest band,
    or None where a spectrum has no data (the match is None without a library or a match)."""
    sample = relative_spectrum(r.compared)
    match = relative_spectrum(library.spectra[r.best]) if library is not None and r.has_match else None

    def near(spectrum, w, tolerance):
        wn, rel = spectrum
        close = rel[np.abs(wn - w) <= tolerance]
        return float(close.max()) if len(close) else None

    return lambda w: (near(sample, w, config.TOLERANCE_CM), near(match, w, 10) if match else None)


def check_kinds(c):
    """The colour of each of the six checks (good, warn, bad, none), in the order of check_rows."""
    return ["bad" if c.saturated else "good", "bad" if c.no_sample else "good", "good" if c.ch == "present" else "none",
            "warn" if c.oh in ("major", "minor") else "none", "none", "warn" if c.vapour_lines else "none"]
