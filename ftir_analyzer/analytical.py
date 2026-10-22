"""
FTIR Contamination Analyzer - analytical view

Re-creates every intermediate step of the analysis for one spectrum, so a person can
check each one with their own eyes ("show your work"):

    1  Raw data            the file exactly as measured (%T or absorbance)
    2  Absorbance          A = -log10(T / 100), or unchanged if the file is already absorbance
    3  Mode correction     transmission -> ATR look (x 1000 / wavenumber), then the common 5 cm-1 grid
    4  Fingerprint         |first derivative| scaled 0-1, sample against the best library material:
                           exactly the two curves the Pearson r is calculated from
    5  Checks              the raw absorbance with its baseline and the ruler line of every check zone

Both the window (matplotlib) and the interactive figures (Plotly) draw from these steps,
so every view shows the same numbers. The steps are re-computed with the same functions
the analysis uses, and step 4 is checked against the score in the Result.

Short names used in this file:
    s = the spectrum    a = absorbance    y = a spectrum on the grid    ok = True where there is data
    fp = fingerprint    r = Pearson r    t = tallest band height    lo, hi = ends of a range

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass, field

import numpy as np

from . import config
from .checks import noise_level, ruler
from .library import pearson
from .processing import GRID, absorbance, baseline_als, fingerprint, on_grid

# Each curve has a role, which decides how it is drawn (colour, width, dash)
SAMPLE, REFERENCE, BEFORE, BASELINE = "sample", "reference", "before", "baseline"


@dataclass(frozen=True)
class Curve:
    label: str           # legend text
    x: np.ndarray        # wavenumbers, low -> high
    y: np.ndarray        # values
    role: str            # SAMPLE, REFERENCE, BEFORE or BASELINE


@dataclass(frozen=True)
class Step:
    number: int
    title: str           # short title for the panel
    y_label: str         # unit of the y axis
    explanation: str     # one or two sentences: what was done here and why
    curves: list = field(default_factory=list)
    spans: list = field(default_factory=list)     # [(lo, hi, label)] shaded regions
    rulers: list = field(default_factory=list)    # [(name, Ruler)] for the checks step


def _mode_text(result, library_mode):
    mode = result.reading
    if result.mode == "unknown" and mode != "unknown":
        other, r_other = result.other
        how = ("like the library, so no correction is needed" if mode == library_mode else
               "so it is multiplied by " + ("1000 / wavenumber" if mode == "transmission" else "wavenumber / 1000")
               + f" to look like {library_mode}")
        return (f"Measuring mode unknown, so the sample was read both ways. It fits better as {mode} "
                f"(r {result.r:.2f} against {r_other:.2f} as {other}), {how}.")
    if result.mode == "unknown":
        return ("Measuring mode unknown, and neither reading (ATR, transmission) matches anything, so no "
                "correction was made (the result is flagged).")
    return _mode_text_known(mode, library_mode)


def _mode_text_known(mode, library_mode):
    if mode == "transmission" and library_mode == "ATR":
        return ("Measured in transmission, the library by ATR: multiplied by 1000 / wavenumber, because ATR "
                "light reaches less deep at high wavenumber, so ATR bands there look weaker.")
    if mode == "ATR" and library_mode == "transmission":
        return "Measured by ATR, the library in transmission: multiplied by wavenumber / 1000 (ATR correction)."
    return f"Measured by {mode}, like the library: no correction needed."


def analytical_steps(result, library):
    """Every step for one Result, as a list of Step objects (see the module text above)."""
    s = result.spectrum
    steps = []

    # 1. Raw data
    unit = "transmittance (%)" if s.unit == "%T" else "absorbance"
    steps.append(Step(1, "Raw data, exactly as measured", unit,
                      f"{len(s.wn)} points from {s.wn.min():.0f} to {s.wn.max():.0f} cm⁻¹, read from "
                      f"{s.path.name}. Unit: {s.unit} (recognised from the {s.unit_source}). Never changed.",
                      [Curve("raw data", s.wn, s.raw, SAMPLE)]))

    # 2. Absorbance
    a = absorbance(s)
    text = ("A = −log₁₀(T / 100). Bands now point up and their height is proportional to the amount of "
            "material (Beer–Lambert law)." if s.unit == "%T" else
            "The file is already in absorbance, so nothing is converted.")
    steps.append(Step(2, "Absorbance", "absorbance", text, [Curve("absorbance", s.wn, a, SAMPLE)]))

    # 3. Mode correction, on the common grid
    before = on_grid(s.wn, a)
    after = result.compared
    curves = [Curve("absorbance on the grid", GRID, before, BEFORE),
              Curve("as compared with the library", GRID, after, SAMPLE)]
    steps.append(Step(3, "Measuring-mode correction, on the common grid", "absorbance",
                      _mode_text(result, library.mode) + " Then read off every 5 cm⁻¹ from 650 to 4000 cm⁻¹ "
                      "(671 points); where the file has no data, nothing is invented.", curves))

    # 4. Fingerprints: exactly what the score compares
    fp_sample = fingerprint(after)
    fp_reference = fingerprint(library.spectra[result.best])
    r = pearson(fp_sample, fp_reference)
    assert abs(r - result.r) < 1e-9, "the analytical view must reproduce the score exactly"
    steps.append(Step(4, f"Derivative fingerprint against {result.best}", "fingerprint (0–1)",
                      f"|first derivative| (Savitzky–Golay, 11 points, cubic), scaled 0–1, so offsets, sloping "
                      f"baselines and thickness drop out. The Pearson r of these two curves is the score: "
                      f"r = {r:.3f}. The CO₂ region is left out.",
                      [Curve("sample fingerprint", GRID, fp_sample, SAMPLE),
                       Curve(f"{result.best} fingerprint", GRID, fp_reference, REFERENCE)],
                      spans=[(*config.CO2_RANGE, "left out")]))

    # 5. Checks: raw absorbance on the grid, its baseline and the ruler of each zone
    ok = np.isfinite(before)
    wn, y = GRID[ok], before[ok]
    base = baseline_als(y)
    no_co2 = (wn < config.CO2_RANGE[0]) | (wn > config.CO2_RANGE[1])
    t = (y - base)[no_co2].max()
    rulers = []
    for name, zone, either in [("C–H", config.CH_ZONE, False), ("O–H / N–H", config.OH_ZONE, False),
                               ("CO₂", config.CO2_ZONE, True)]:
        measured = ruler(wn, y, *zone, either_way=either)
        if measured is not None and np.isfinite(measured.height):
            rulers.append((name, measured))
    heights = "; ".join(f"{name} {m.height:+.4f}" for name, m in rulers)
    c = result.checks
    co2_note = ""
    if c.co2_share >= 0.1:
        co2_note = (" The CO₂ band points " + ("down: there was less CO₂ in the air than during the background "
                    "scan." if c.co2_direction == "down" else "up: there was more CO₂ in the air than during the "
                    "background scan.") + " It comes from the air, not from the sample.")
    steps.append(Step(5, "Checks on the raw absorbance", "absorbance",
                      f"Each band is measured from a straight line between its two feet (the ruler): {heights}. "
                      f"Tallest band above the baseline: {t:.4f}. Noise: {noise_level(wn, y):.4f}; a band must be "
                      f"at least 3× the noise to count.{co2_note}",
                      [Curve("raw absorbance on the grid", wn, y, SAMPLE),
                       Curve("baseline (asymmetric least squares)", wn, base, BASELINE)],
                      rulers=rulers))
    return steps
