"""
FTIR Contamination Analyzer - instrument check

A polystyrene film is measured in transmission, and the positions of its bands are compared with their published
values. Every check is added to a log, so that a slow movement of the wavenumber scale shows up over time.

    measure_film   the positions of the film's bands in one spectrum
    check_file     the same for a file, refused if the file cannot be a film in transmission
    append_check   add a check to the log
    read_checks    every check in the log, oldest first
    movement       how far the bands moved over the last checks, if they moved steadily one way

The top of a band is found on the file's own points: the highest point near the published value, then a parabola
through it and its two neighbours, which places the top between two points. A band that is too dark, or that has no
top near the published value, is not measured.

Short names used in this file:
    wn = wavenumbers    a = absorbance    i = the highest point    y = three heights around it
    x = a band's published position    top = where it was found    shift = top - x

Author : Ali Obeidat
Version: 2.0.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .processing import absorbance
from .records import current_user
from .spectrum_io import SpectrumFileError, checksum, read_mode_note, read_spectra, read_table

CHECK_HEADER = (
    "# Instrument checks: one row per measured polystyrene film. Each band's shift is the position found minus the "
    "published position, in cm-1.\n"
    "# Rows are only added.\n"
)
SHIFT_COLUMNS = [f"shift_{x:.0f}" for x in config.FILM_BANDS]
CHECK_COLUMNS = ["checked_at", "checked_by", "instrument", "result", "bands_measured", "mean_shift", "largest_shift",
                 *SHIFT_COLUMNS, "file", "file_sha256"]
PASSED, FAILED = "passed", "failed"


@dataclass(frozen=True)
class FilmCheck:
    """The band positions of one measured film."""

    tops: tuple         # where each band of config.FILM_BANDS was found (NaN: not measured)

    @property
    def shifts(self):
        return tuple(top - x for top, x in zip(self.tops, config.FILM_BANDS))

    @property
    def measured(self):
        return [s for s in self.shifts if np.isfinite(s)]

    @property
    def mean(self):
        """The average shift, with its sign: the whole scale moving shows up here."""
        return float(np.mean(self.measured))

    @property
    def largest(self):
        """The largest shift, without its sign."""
        return float(np.max(np.abs(self.measured)))

    @property
    def result(self):
        return PASSED if self.largest <= config.FILM_LIMIT else FAILED


@dataclass(frozen=True)
class LoggedCheck:
    """One row of the log."""

    time: datetime
    instrument: str
    result: str
    measured: int
    mean: float
    largest: float
    shifts: tuple       # one per band of config.FILM_BANDS (NaN: not measured)
    file: str


def band_top(wn, a, x):
    """Where the band published at x has its top (NaN if it has none near x, or if it is too dark to place)."""
    near = np.flatnonzero(np.abs(wn - x) <= config.FILM_WINDOW)
    if len(near) < 5:
        return float("nan")
    i = near[np.argmax(a[near])]
    if i in (near[0], near[-1]) or a[i] > config.SATURATED_A:           # no top inside the window, or a flat dark one
        return float("nan")
    if a[i] - a[near].min() < config.FILM_MIN_HEIGHT * np.ptp(a):       # a wiggle, not a band
        return float("nan")
    y = a[i - 1: i + 2]
    bend = y[0] - 2 * y[1] + y[2]
    if bend >= 0:
        return float(wn[i])
    # three points may be unevenly spaced in a file, but neighbours in a spectrum are not: one step is enough
    step = (wn[i + 1] - wn[i - 1]) / 2
    return float(wn[i] + step * (y[0] - y[2]) / (2 * bend))


def measure_film(wn, a):
    """A FilmCheck, or None if the spectrum does not look like a polystyrene film."""
    order = np.argsort(wn)
    wn, a = np.asarray(wn, float)[order], np.asarray(a, float)[order]
    ok = np.isfinite(a)
    wn, a = wn[ok], a[ok]
    check = FilmCheck(tuple(band_top(wn, a, x) for x in config.FILM_BANDS))
    return check if len(check.measured) >= config.FILM_MIN_BANDS else None


def check_file(path):
    """(FilmCheck, the file's spectrum). A file that cannot be used stops with a SpectrumFileError that says why."""
    path = Path(path)
    if read_mode_note(path) == "ATR":
        raise SpectrumFileError("This file was measured by ATR. The published positions are for a film in transmission.")
    spectra = read_spectra(path)
    if len(spectra) != 1:
        raise SpectrumFileError(f"This file holds {len(spectra)} spectra. Choose a file with one measured film.")
    spectrum = spectra[0]
    step = float(np.median(np.abs(np.diff(spectrum.wn))))
    if step > config.FILM_MAX_STEP:
        raise SpectrumFileError(f"The data points are {step:.0f} cm⁻¹ apart. The check needs {config.FILM_MAX_STEP:.0f} "
                                "cm⁻¹ or closer.")
    check = measure_film(spectrum.wn, absorbance(spectrum))
    if check is None:
        raise SpectrumFileError("Too few polystyrene bands were found. Check that this is a polystyrene film, and "
                                "that its bands are not too dark.")
    return check, spectrum


def append_check(check, instrument, file_path, path=config.INSTRUMENT_LOG_FILE, who=None, when=None):
    """Add one check to the log. Earlier rows are never changed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = when or datetime.now().astimezone().isoformat(timespec="seconds")
    row = {"checked_at": stamp, "checked_by": who or current_user(), "instrument": " ".join(str(instrument).split()),
           "result": check.result, "bands_measured": len(check.measured), "mean_shift": round(check.mean, 3),
           "largest_shift": round(check.largest, 3), "file": Path(file_path).name, "file_sha256": checksum(file_path)}
    row.update({name: round(s, 3) if np.isfinite(s) else "" for name, s in zip(SHIFT_COLUMNS, check.shifts)})
    new_file = not path.exists()
    if new_file:
        path.write_text(CHECK_HEADER, encoding="utf-8")
    pd.DataFrame([row], columns=CHECK_COLUMNS).to_csv(path, mode="a", index=False, header=new_file)
    return path


def _number(text):
    try:
        return float(text)
    except ValueError:
        return float("nan")


def read_checks(path):
    """Every check in the log, oldest first. Rows without a time are left out."""
    if not Path(path).exists():
        return []
    checks = []
    for row in read_table(path, dtype=str).fillna("").to_dict("records"):
        try:
            time = datetime.fromisoformat(row["checked_at"])
        except ValueError:
            continue
        checks.append(LoggedCheck(time, row["instrument"], row["result"], int(_number(row["bands_measured"]) or 0),
                                  _number(row["mean_shift"]), _number(row["largest_shift"]),
                                  tuple(_number(row[name]) for name in SHIFT_COLUMNS), row["file"]))
    return sorted(checks, key=lambda c: c.time.timestamp())


def movement(checks):
    """How far the mean shift moved over the last checks of one instrument, if it moved steadily one way and far
    enough to matter, else 0."""
    if len(checks) < config.DRIFT_CHECKS:
        return 0.0
    means = [c.mean for c in checks[-config.DRIFT_CHECKS:]]
    steps = np.diff(means)
    moved = means[-1] - means[0]
    return float(moved) if ((steps > 0).all() or (steps < 0).all()) and abs(moved) >= config.DRIFT_MOVE else 0.0
