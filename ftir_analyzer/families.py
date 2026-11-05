"""
FTIR Contamination Analyzer - material families, and how to tell two close materials apart

A family is chemistry (data/families.csv): PET and PBT are both polyesters. The verdict never uses it, so nothing
here can turn a result into a "probable".

    family_of     the family of a material
    relatives     the other members of its family in this library
    close_call    for a weak result: the two materials it lies between, the family if both are in one, the bonds
                  they share, and where their reference spectra differ most, with what the sample does there

The family line needs two things, both tested on the 148 Open Specy references with their own material hidden.
Only two close references of one family count: a single high score named the wrong family 3 times in 12 at r >= 0.85.
And both scores must be high: two references agreeing named the wrong family 10 times in 16 at r >= 0.60, and it did
not happen at r >= 0.80, so the limit is config.FAMILY_R (0.85), with a margin. It is a family, not an identification.

Where two references differ is a fact about the two references, so it is shown whenever a result lies between them.
The sample's height there is given to be read; the program does not draw a conclusion from it.

Short names used in this file:
    r = one Result    w = a wavenumber (cm-1)

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from . import config
from .analysis import WEAK
from .evidence import relative_spectrum
from .structures import model_of

FAMILIES_FILE = config.DATA_DIR / "families.csv"
PLAIN = {"CH₃ bend", "CH₂ rock", "CH₂/CH₃ bend", "Aliphatic C–H", "Aromatic C–H"}   # nearly every polymer has these


@lru_cache(maxsize=1)
def _table():
    """{member: family}; {} if the file is missing."""
    try:
        table = pd.read_csv(FAMILIES_FILE, comment="#")
    except (OSError, ValueError):
        return {}
    return {member.strip(): row.family for row in table.itertuples() for member in row.members.split(";")}


def family_of(name, library=None):
    """The family of a material, by its name, then its material group; "" if it is in none."""
    table = _table()
    return table.get(name) or (table.get(library.group_of(name), "") if library is not None else "")


def relatives(name, library):
    """The other materials of a family in this library: the group's name once, whatever its number of references."""
    family = family_of(name, library)
    if not family:
        return []
    own = library.group_of(name)
    seen = {}
    for other in library.spectra:
        group = library.group_of(other)
        if group != own and family_of(other, library) == family:
            seen.setdefault(group, other)
    return list(seen.values())


@dataclass(frozen=True)
class CloseCall:
    """A weak result that lies between two materials."""

    first: str          # the best match
    second: str         # the next different material
    family: str         # their family, if both are in one and both score high enough; else ""
    shared: tuple       # the band groups both have, plain C-H left out
    w: float            # where their reference spectra differ most (cm-1)
    sample: float       # the height of the sample's band there, as a share of its tallest band
    height_1: float     # the same for the best match
    height_2: float     # the same for the next material

    def title(self):
        return self.family or "Too close to call"

    def text(self):
        """One or two short sentences, the same in the window, the web report and the PDF."""
        both = f"{self.first} and {self.second}"
        if self.family:
            share = f" and share {' and '.join(self.shared[:2])}" if self.shared else ""
            head = f"{both} are both {self.family.lower()}{share}, and the sample is close to both."
        else:
            head = f"The sample lies between {both}."
        return (f"{head} They differ most near {self.w:.0f} cm⁻¹: {self.first} {self.height_1:.0%}, "
                f"{self.second} {self.height_2:.0%}, this sample {self.sample:.0%}.")


def _height(spectrum, w):
    wn, rel = spectrum
    return float(np.interp(w, wn, rel))


def where_they_differ(library, first, second):
    """The wavenumber where two references differ most, each scaled to its own tallest band."""
    wn, a = relative_spectrum(library.spectra[first])
    wn2, b = relative_spectrum(library.spectra[second])
    # the O-H / N-H region is left out: a broad water band there says little about which polymer it is
    keep = wn <= 3100
    difference = np.abs(a - np.interp(wn, wn2, b))[keep]
    return float(wn[keep][int(np.argmax(difference))])


def close_call(r, library):
    """What can be said about a weak result that lies between two materials; None if it does not."""
    if r.verdict != WEAK or library is None or r.best not in library.spectra or r.runner_up not in library.spectra:
        return None
    other_r = r.r - r.gap
    family_1, family_2 = family_of(r.best, library), family_of(r.runner_up, library)
    family = family_1 if family_1 and family_1 == family_2 and other_r >= config.FAMILY_R else ""
    if not family and (r.gap >= config.MIN_GAP or r.r < config.FAMILY_R):      # a low score is not "between" anything
        return None
    w = where_they_differ(library, r.best, r.runner_up)
    one, two = model_of(r.best, library), model_of(r.runner_up, library)
    shared = tuple(g for g in one["groups"] if g in two["groups"] and g not in PLAIN) if one and two else ()
    spectra = (relative_spectrum(r.compared), relative_spectrum(library.spectra[r.best]),
               relative_spectrum(library.spectra[r.runner_up]))
    sample, first, second = (_height(s, w) for s in spectra)
    return CloseCall(r.best, r.runner_up, family, shared, w, sample, first, second)
