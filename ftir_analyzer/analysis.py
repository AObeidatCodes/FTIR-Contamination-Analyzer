"""
FTIR Contamination Analyzer - analysis of one spectrum

Puts every step together for one measured spectrum:

    1. absorbance        %T -> A if needed (a new array; the measured values stay as they are)
    2. mode correction   make the sample look as if it was measured like the library (ATR).
                         Mode unknown: it is read both ways (as ATR, as transmission) and the
                         reading that fits better is used and stated. Mode given: the other
                         reading is checked too, and a clearly better fit is flagged.
    3. library search    every reference material ranked by Pearson r, best first
    4. verdict           probable / weak / no reliable match, with the reason in numbers
    5. checks            saturation, CO2, C-H, O-H on the raw absorbance
    6. band evidence     key bands found / missing, unexplained bands (second component?)
    7. next step         one sentence a person can act on, in the order of the method card

The program suggests; a person reviews the raw spectrum and decides.

Short names used in this file:
    wn = wavenumbers    a = absorbance    a_grid = absorbance on the common grid
    ok = True where there is data    r1, r2 = best and second-best score    v = verdict word
    reading = the measuring mode the comparison used ("ATR", "transmission", or "unknown" = as measured)

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass, field

import numpy as np

from . import config
from .checks import Checks, side_checks
from .evidence import Evidence, band_evidence
from .library import search
from .processing import GRID, absorbance, on_grid, to_library_mode
from .spectrum_io import Spectrum, SpectrumFileError

# The three possible verdicts, best first.
PROBABLE, WEAK, NO_MATCH = "probable", "weak", "no reliable match"

# A spectrum must cover at least this many points of the 650-4000 cm-1 grid to be compared.
MIN_GRID_POINTS = 50

# The two ways a spectrum can have been measured; each can be put into the library's mode.
MODES = ("ATR", "transmission")


@dataclass(frozen=True)
class Result:
    """Everything the program concludes about one spectrum."""

    spectrum: Spectrum       # the measured spectrum, untouched
    mode: str                # how it was measured: "ATR", "transmission" or "unknown"
    mode_source: str         # where the mode came from (file note, sample log, the user)
    conflict: str            # "" or a description of a mode conflict
    verdict: str             # PROBABLE, WEAK or NO_MATCH
    match: str               # the material(s) named by the verdict, "-" if none
    ranking: list            # [(material, r), ...] for the whole library, best first
    reason: str              # the verdict in one sentence, with the numbers that decided it
    checks: Checks           # saturation, CO2, C-H, O-H, noise
    evidence: Evidence       # band evidence for the best match (None if there is no match)
    next_step: str           # what a person should do next
    flags: list = field(default_factory=list)   # [(label, kind)]; kind "bad" = not trustworthy, "warn" = look closer
    compared: np.ndarray = None                 # the copy that was compared with the library (on the grid)
    rival: int = 1                              # position in the ranking of the best DIFFERENT material
    reading: str = "unknown"                    # the mode the comparison used ("unknown": as measured)
    other: tuple = ()                           # (the other mode, its best r), for the mode check

    # Short-cuts used by the window and the report
    @property
    def name(self):
        return self.spectrum.name

    @property
    def best(self):
        """The best-scoring material (also when the verdict is 'no reliable match')."""
        return self.ranking[0][0]

    @property
    def r(self):
        """The best score (Pearson r)."""
        return self.ranking[0][1]

    @property
    def gap(self):
        """How far the best material is ahead of the next different material."""
        return self.ranking[0][1] - self.ranking[self.rival][1]

    @property
    def runner_up(self):
        """The best material that is different from the winner."""
        return self.ranking[self.rival][0]

    @property
    def has_match(self):
        return self.verdict != NO_MATCH

    @property
    def compared_as(self):
        """How the sample was compared, in a few words: 'ATR', 'transmission' or 'as measured'."""
        return self.reading if self.reading in MODES else "as measured"

    @property
    def mode_text(self):
        """The measuring mode and where it came from, plus how it was compared if that was worked out."""
        text = f"{self.mode} ({self.mode_source})"
        if self.mode not in MODES and self.reading in MODES:
            text += f", compared as {self.reading}: the better fit"
        return text


def decide(ranking, rival=1):
    """The verdict rule, from the best score and the best score of a DIFFERENT material: (verdict, material(s)).

    rival: where that different material is in the ranking (1 unless references of the same
    material, e.g. from another source, come second).
    """
    (best, r1), (second, r2) = ranking[0], ranking[rival]    # the two (name, score) pairs that decide
    clear = r1 - r2 >= config.MIN_GAP                        # is the winner clearly ahead?
    if r1 >= config.PROBABLE_R and clear:                    # high score AND a clear winner
        return PROBABLE, best
    if r1 >= config.WEAK_R:                                  # similar, not proven; two too close -> name both
        return WEAK, best if clear else f"{best} or {second}"
    return NO_MATCH, "-"                                     # nothing in the library is similar enough


def explain(ranking, verdict, rival=1):
    """The verdict in one sentence, with the numbers that decided it."""
    r1, gap = ranking[0][1], ranking[0][1] - ranking[rival][1]
    if verdict == PROBABLE:
        return f"r = {r1:.2f} ≥ {config.PROBABLE_R} and the gap to the next material ({gap:.2f}) ≥ {config.MIN_GAP}."
    if verdict == WEAK and r1 >= config.PROBABLE_R:
        return (f"r = {r1:.2f} is high, but the gap ({gap:.2f}) is below {config.MIN_GAP}: "
                "two materials are too close to call.")
    if verdict == WEAK:
        return f"r = {r1:.2f} is between {config.WEAK_R} and {config.PROBABLE_R}: similar, but not shown to be the same."
    return f"Best r = {r1:.2f} is below {config.WEAK_R}: nothing in the library is similar enough."


def advise(verdict, match, checks):
    """One sentence a person can act on, in the order of the method card."""
    if checks.no_sample:                                     # method card step 1: is there a sample at all?
        text = ("CO2 artefact as big as the sample bands: probably no sample here. "
                "Check the microscope image, take a fresh background.")
    elif verdict == PROBABLE:
        text = f"Probable {match}. Check the raw spectrum, then sign."
    elif verdict == WEAK:
        text = f"Possibly {match}. Confirm by reading the bands (method card)."
    elif checks.ch == "present":                             # no match, but C-H: an organic not in the library
        text = "Organic, but not in the library: read the bands by hand, consider adding a reference."
    elif checks.oh in ("major", "minor"):                    # no C-H, but O-H
        text = "O-H but no C-H: water, silicate or another inorganic. Read the bands, consider SEM-EDX."
    else:                                                    # nothing organic at all
        text = "No C-H, no O-H: not an ordinary organic (metal, inorganic, fluorinated?). Read the bands, SEM-EDX."
    if checks.saturated:                                     # added to any of the sentences above
        text += f" WARNING: bands saturated (A up to {checks.max_a:.1f}): measure thinner or use ATR."
    return text


def choose_reading(mode, best):
    """The mode the comparison uses. best = {mode: best r when read that way}.

    A known mode is used as it is. An unknown one: the reading that fits better, if it fits
    at all (r >= WEAK_R); if neither does, none (the spectrum is compared as measured).
    """
    if mode in best:
        return mode
    fit = max(best, key=best.get)
    return fit if best[fit] >= config.WEAK_R else "unknown"


def analyse(spectrum, library, mode="unknown", mode_source="not given", conflict=""):
    """Run the whole analysis on one spectrum and return a Result. The spectrum is never changed."""
    wn = spectrum.wn
    a = absorbance(spectrum)                                                    # 1. a new array, in absorbance
    readings = {m: on_grid(wn, to_library_mode(wn, a, m, library.mode)) for m in MODES}   # 2. read as ATR and
    if np.isfinite(readings[library.mode]).sum() < MIN_GRID_POINTS:                       #    as transmission
        raise SpectrumFileError(f"{spectrum.name}: the spectrum hardly covers the mid-IR range "
                                f"{config.GRID_START:.0f}-{config.GRID_STOP:.0f} cm-1, so it cannot be compared.")

    rankings = {m: search(y, library) for m, y in readings.items()}           # 3. every material, best first
    best = {m: ranking[0][1] for m, ranking in rankings.items()}
    reading = choose_reading(mode, best)
    used = reading if reading in MODES else library.mode                        #    'as measured' = no correction
    compared, ranking = readings[used], rankings[used]
    other = next(m for m in MODES if m != used)
    rival = library.rival(ranking)                                              #    the best DIFFERENT material
    verdict, match = decide(ranking, rival)                                     # 4. the rule

    a_grid = on_grid(wn, a)                                                     # 5. checks on the raw absorbance
    ok = np.isfinite(a_grid)
    checks = side_checks(GRID[ok], a_grid[ok])

    evidence = band_evidence(compared, library.spectra[ranking[0][0]]) if verdict != NO_MATCH else None   # 6.
    step = advise(verdict, match, checks)                                       # 7.

    # Flags: short labels for the list and the report, each with a severity
    flags = []
    if checks.no_sample:
        flags.append(("CO2 artefact: probably no sample", "bad"))
    if checks.saturated:
        flags.append(("saturated bands", "bad"))
    if evidence and evidence.unexplained:
        flags.append(("second component?", "warn"))
        step += (" Unexplained band(s) at " + ", ".join(f"{w:.0f}" for w in evidence.unexplained)
                 + " cm-1: possible second component. Read them with the method card.")
    if mode not in MODES:
        flags.append(("mode unknown", "warn"))
        if reading in MODES:
            step += (f" Measuring mode unknown: read both ways, it fits better as {reading} "
                     f"(r {best[reading]:.2f} against {best[other]:.2f}), so it is compared that way. "
                     "Record the mode to be sure.")
        else:
            step += " Measuring mode unknown, and neither reading matches anything, so it is compared as measured."
    elif best[other] - best[mode] >= config.MODE_DOUBT and best[other] >= config.WEAK_R:
        flags.append(("mode doubt", "warn"))
        step += (f" Mode check: it fits clearly better as {other} (r {best[other]:.2f} against "
                 f"{best[mode]:.2f}). Check how it was measured.")
    if conflict:
        flags.append(("mode conflict", "bad"))
        step += f" Mode conflict: {conflict}."

    return Result(spectrum, mode, mode_source, conflict, verdict, match, ranking, explain(ranking, verdict, rival),
                  checks, evidence, step, flags, compared, rival, reading, (other, best[other]))
