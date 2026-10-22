"""
FTIR Contamination Analyzer - checks on the raw spectrum

Independent of the library match, these checks describe what was actually measured:
    saturation   are the strongest bands too dark to trust?
    CO2          is the CO2 artefact as big as the sample? (then there is probably no sample)
    C-H          is there an organic C-H stretch?
    O-H / N-H    is there an O-H or N-H band, and how big is it?
    noise        how big is the scatter, so small bands can be judged fairly?

Band heights use the ruler method: a straight line is drawn between the median levels
of the band's two feet, and the band is measured from that line, so a sloping
background does not distort the height.

Why a CO2 band can point DOWN in absorbance: absorbance is always relative to the
background measurement, A = -log10(I_sample / I_background). If there was less CO2 in
the air during the sample scan than during the background scan, more light reaches the
detector at 2350 cm-1 and the band comes out negative. A band that depends on the air,
not on the sample, is exactly what an artefact looks like.

Short names used in this file:
    wn = wavenumbers    a = absorbance    lo, hi = low and high end of a range
    x1, x2 / y1, y2 = position / height of the left and right foot
    tall = height of the tallest band    ch / oh / co2 = height of that band

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import savgol_filter

from . import config
from .peaks import band_label, find_real_peaks
from .processing import baseline_als


@dataclass(frozen=True)
class Checks:
    """The results of the checks on one raw spectrum."""

    max_a: float            # highest absorbance in the spectrum
    co2_share: float        # CO2 artefact height as a share of the tallest band
    ch: str                 # "present", "not detected" or "not measured"
    ch_share: float         # C-H height as a share of the tallest band
    oh: str                 # "major", "minor", "none or trace" or "not measured"
    oh_share: float         # O-H / N-H height as a share of the tallest band
    noise: float            # robust noise level (absorbance units)
    co2_signed: float       # CO2 artefact height with its sign: < 0 = points down (less CO2 than in the background)
    tallest_bands: list = field(default_factory=list)   # labels of the 3 tallest bands

    @property
    def saturated(self):
        """True if the strongest bands are above A = 2 (less than 1 % of the light got through)."""
        return self.max_a > config.SATURATED_A

    @property
    def no_sample(self):
        """True if the CO2 artefact is at least half as tall as the tallest band."""
        return self.co2_share >= config.CO2_WARNING

    @property
    def co2_direction(self):
        """'down' = less CO2 in the air than during the background scan, 'up' = more."""
        return "down" if self.co2_signed < 0 else "up"

    @property
    def below_zero(self):
        """True if the whole spectrum is below zero: more light came through than in the background."""
        return self.max_a < 0


def describe_co2(c):
    """The CO2 check in words; says which way the band points when the artefact is noticeable."""
    text = f"{c.co2_share:.2f} of the tallest band"
    if c.co2_share >= 0.1:
        text += (", pointing down: less CO₂ in the air than during the background scan" if c.co2_direction == "down"
                 else ", pointing up: more CO₂ in the air than during the background scan")
    return text


BELOW_ZERO_TEXT = ("The whole spectrum is below zero: more light came through than in the background measurement, "
                   "so the background was probably not taken on a comparable spot.")


def noise_level(wn, a):
    """Robust scatter around a smooth curve, in the WORST of the band-free windows.

    The robust standard deviation (1.4826 x median absolute deviation) is used because
    one spike cannot inflate it. The worst window counts, because a small band must be
    judged against the noise where the noise is largest (e.g. water-vapour lines).
    """
    if len(a) < 15:                                                    # too few points for the smooth copy
        return float(np.std(a)) if len(a) else 0.0
    wiggle = a - savgol_filter(a, 15, 2)                               # the spectrum minus a smooth copy
    scatter = []
    for lo, hi in config.NOISE_WINDOWS:
        part = wiggle[(wn >= lo) & (wn <= hi)]                         # the wiggle inside this window
        if len(part) > 5:                                              # skip windows the file doesn't cover
            scatter.append(1.4826 * np.median(np.abs(part - np.median(part))))
    return max(scatter) if scatter else float(np.std(wiggle))


@dataclass(frozen=True)
class Ruler:
    """Where and how one band was measured: the straight line between its feet, and the band's top."""

    x1: float        # centre of the left foot (cm-1)
    y1: float        # median level of the left foot
    x2: float        # centre of the right foot
    y2: float        # median level of the right foot
    x: float         # where inside the band the height was measured
    curve: float     # the spectrum there
    line: float      # the ruler line there

    @property
    def height(self):
        """Height of the band above the line; negative if the band points down."""
        return self.curve - self.line


def ruler(wn, a, left_foot, right_foot, band, either_way=False):
    """Measure one band with the ruler method; None if the zone is not covered by the spectrum.

    either_way=True also looks for dips below the line (a CO2 artefact can point down).
    """
    def level(lo, hi):                                                 # typical (median) height of one foot
        part = (wn >= lo) & (wn <= hi)
        return np.median(a[part]) if part.any() else np.nan

    x1, x2 = np.mean(left_foot), np.mean(right_foot)                   # where each foot is
    y1, y2 = level(*left_foot), level(*right_foot)                     # how high each foot is
    inside = (wn >= band[0]) & (wn <= band[1])                         # the points inside the band zone
    if not inside.any():
        return None
    line = y1 + (y2 - y1) * (wn[inside] - x1) / (x2 - x1)              # y = y1 + slope x distance
    above = a[inside] - line
    i = int(np.argmax(np.abs(above) if either_way else above))         # the highest (or deepest) point
    return Ruler(float(x1), float(y1), float(x2), float(y2), float(wn[inside][i]),
                 float(a[inside][i]), float(line[i]))


def ruler_height(wn, a, left_foot, right_foot, band, either_way=False):
    """Height of a band above the straight line between its two feet (NaN if the zone is not covered).

    either_way=True returns the size of the largest step up OR down (always positive).
    """
    r = ruler(wn, a, left_foot, right_foot, band, either_way)
    if r is None:
        return np.nan
    return float(abs(r.height) if either_way else r.height)


def side_checks(wn, a):
    """Run every check on one spectrum (wavenumbers and absorbance on the common grid, no NaN)."""
    no_co2 = (wn < config.CO2_RANGE[0]) | (wn > config.CO2_RANGE[1])
    above = a - baseline_als(a)                                        # heights above the stiff baseline
    tall = above[no_co2].max()                                         # the tallest band, CO2 left out
    noise = noise_level(wn, a)
    co2_ruler = ruler(wn, a, *config.CO2_ZONE, either_way=True)
    co2_signed = co2_ruler.height if co2_ruler else np.nan        # < 0: the CO2 band points down
    co2 = abs(co2_signed)
    ch = ruler_height(wn, a, *config.CH_ZONE)
    oh = ruler_height(wn, a, *config.OH_ZONE)

    # C-H is a quiet band: any amount counts, as long as it is real (big enough AND above the noise).
    if np.isnan(ch):
        ch_says = "not measured"
    elif ch >= config.CH_MIN_SHARE * tall and ch >= config.MIN_SN * noise:
        ch_says = "present"
    else:
        ch_says = "not detected"

    # O-H / N-H is a loud band: its size decides what it means (part of the material, minor, trace).
    oh_share = oh / tall
    if np.isnan(oh):
        oh_says = "not measured"
    elif oh < config.MIN_SN * noise or oh_share < config.MINOR:
        oh_says = "none or trace"
    else:
        oh_says = "major" if oh_share >= config.MAJOR else "minor"

    # the three tallest bands, with names, for reading by hand
    peaks_wn, peaks_a = find_real_peaks(wn[no_co2], above[no_co2])
    tallest3 = [band_label(w) for w in peaks_wn[np.argsort(peaks_a)[::-1][:3]]]   # tallest first, keep 3

    return Checks(max_a=float(a.max()), co2_share=float(co2 / tall), ch=ch_says, ch_share=float(ch / tall),
                  oh=oh_says, oh_share=float(oh_share), noise=float(noise), co2_signed=float(co2_signed),
                  tallest_bands=tallest3)
