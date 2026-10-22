"""
FTIR Contamination Analyzer - reading spectrum files

Reads instrument exports (CSV, TXT, DPT) and instrument files (JCAMP-DX, Bruker OPUS; see
instrument_files.py) into Spectrum objects. The measured values
are kept exactly as they are in the file and are made read-only, so nothing later
in the program can change them by accident. Each file's SHA-256 checksum is recorded,
so anyone can prove later that a report was made from this exact file.

Short names used in this file:
    wn  = wavenumbers (the x-axis, cm-1)
    raw = the intensity values exactly as measured (%T or absorbance)

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .instrument_files import InstrumentFileError, is_instrument_file, is_jcamp, read_instrument_file


class SpectrumFileError(ValueError):
    """A file that cannot be read as a spectrum. The message is written for the user."""


@dataclass(frozen=True)
class Spectrum:
    """One measured spectrum, exactly as it is in the file.

    frozen=True: the fields cannot be reassigned, and the two arrays are read-only.
    """

    name: str          # sample name: the file name, or the column name in a multi-column file
    wn: np.ndarray     # wavenumbers in cm-1, sorted low -> high
    raw: np.ndarray    # values as measured, in the same row order as wn
    unit: str          # "%T" (transmittance) or "A" (absorbance)
    unit_source: str   # how the unit was recognised (shown in the report)
    path: Path         # the file it came from
    sha256: str        # checksum of that file


def checksum(path):
    """SHA-256 fingerprint of a file: change one byte and it is completely different."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_table(path, **options):
    """A CSV table that may have '# ...' note lines.

    Only whole note lines are left out. pandas' own comment="#" would also cut a line at a '#'
    inside a name, so 'Glove batch #2' would lose the rest of its line and shift every column
    after it.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    kept = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return pd.read_csv(io.StringIO(kept), **options)


def read_mode_note(path):
    """The measuring mode the file states: a '# mode: ...' note in a text file, the sampling procedure
    of a JCAMP-DX file or the accessory of an OPUS file. None if the file does not say."""
    if is_instrument_file(path):
        try:
            return read_instrument_file(path)[0].mode
        except InstrumentFileError:
            return None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("# mode:"):
            note = line.split(":", 1)[1].strip().lower()              # "# mode: ATR" -> "atr"
            # the matching known mode, or "unknown" for anything else (e.g. "reflection")
            return next((m for m in config.MODES if m.lower() == note), "unknown")
    return None


def _is_number(text):
    """True if the text is a number, e.g. '4000.0' (used to spot a file without a header line)."""
    try:
        float(str(text))
        return True
    except ValueError:
        return False


def _read_table(path):
    """Read the numeric table from a file, whatever the separator and with or without a header."""
    try:
        # sep=None + engine="python": pandas sniffs the separator (comma, semicolon, tab, space)
        table = read_table(path, sep=None, engine="python")
        if all(_is_number(c) for c in table.columns):              # the "header" is really the first data row
            table = read_table(path, sep=None, engine="python", header=None)
            table.columns = ["wavenumber"] + [f"column {i}" for i in range(1, table.shape[1])]
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as error:
        raise SpectrumFileError(f"{Path(path).name}: the file could not be read as a table ({error}).") from error
    return table


def _detect_unit(notes, column_names, values):
    """Decide whether the values are %T or absorbance, and say how it was decided."""
    unit_notes = [n for n in notes if n.lower().startswith("# unit")]
    labels = " ".join(unit_notes + [str(c) for c in column_names]).lower()
    if "transmittance" in labels or "%t" in labels:
        return "%T", "file note / column name"
    if "absorbance" in labels:
        return "A", "file note / column name"
    # No label: absorbance above 5 would mean 0.001 % of the light gets through, which an FTIR
    # cannot measure. Values that typically sit far above 5 are therefore percent transmittance.
    if np.nanmedian(values) > 5:
        return "%T", "value range (no unit label in the file)"
    return "A", "value range (no unit label in the file)"


def read_spectra(path):
    """All spectra in one file as a list of Spectrum objects.

    Two columns = one spectrum. More columns = one spectrum per column (a "wide" file).
    Raises SpectrumFileError with a readable message if the file is not a usable spectrum.
    """
    path = Path(path)
    if not path.is_file():
        raise SpectrumFileError(f"{path.name}: file not found.")
    if is_instrument_file(path):
        return _read_instrument(path)

    notes = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
             if line.lstrip().startswith("#")]                        # the "# ..." header lines
    table = _read_table(path)
    if table.shape[1] < 2:
        raise SpectrumFileError(f"{path.name}: needs a wavenumber column and at least one intensity column.")

    table = table.apply(pd.to_numeric, errors="coerce")                # text cells -> NaN, so they can be dropped
    table = table.dropna(subset=[table.columns[0]])                    # rows without a wavenumber are useless
    table = table.sort_values(table.columns[0])                        # low -> high; whole rows move, pairs stay together
    wn_all = table.iloc[:, 0].to_numpy(float)

    if len(wn_all) < 20:
        raise SpectrumFileError(f"{path.name}: only {len(wn_all)} data points; a spectrum needs many more.")
    if wn_all.min() < 200 or wn_all.max() > 8000:
        raise SpectrumFileError(f"{path.name}: the first column ({wn_all.min():.0f}-{wn_all.max():.0f}) "
                                "does not look like wavenumbers in cm-1.")

    file_checksum = checksum(path)
    columns = list(table.columns[1:])                                  # every column after the wavenumbers
    spectra = []
    for column in columns:
        values = table[column].to_numpy(float)
        keep = np.isfinite(values)                                     # skip empty cells in this column
        if keep.sum() < 20:
            continue                                                   # an empty or almost empty column
        wn, raw = wn_all[keep].copy(), values[keep].copy()
        wn.setflags(write=False)                                       # read-only: the measured data can't be changed
        raw.setflags(write=False)
        unit, unit_source = _detect_unit(notes, table.columns[1:], raw)
        name = path.stem if len(columns) == 1 else str(column)
        spectra.append(Spectrum(name, wn, raw, unit, unit_source, path, file_checksum))

    if not spectra:
        raise SpectrumFileError(f"{path.name}: no column with enough numeric values was found.")
    return spectra


def _read_instrument(path):
    """A JCAMP-DX or OPUS file -> Spectrum objects (sorted low -> high, read-only, with the file's checksum)."""
    try:
        found = read_instrument_file(path)
    except InstrumentFileError as error:
        raise SpectrumFileError(str(error)) from error
    file_checksum, spectra = checksum(path), []
    for item in found:
        keep = np.isfinite(item.wn) & np.isfinite(item.y)
        order = np.argsort(item.wn[keep])
        wn, raw = item.wn[keep][order].copy(), item.y[keep][order].copy()
        if len(wn) < 20 or wn.min() < 200 or wn.max() > 8000:
            raise SpectrumFileError(f"{path.name}: the data does not look like an FTIR spectrum in cm-1.")
        wn.setflags(write=False)                                       # read-only, as for every other file
        raw.setflags(write=False)
        name = item.name if len(found) > 1 else path.stem
        spectra.append(Spectrum(name, wn, raw, item.unit, item.unit_source, path, file_checksum))
    return spectra


def is_spectrum_file(path):
    """A file the program can read: a text export by its extension, or an instrument file."""
    path = Path(path)
    return path.suffix.lower() in config.SPECTRUM_FILE_TYPES or is_jcamp(path) or is_instrument_file(path)


def find_spectrum_files(folder):
    """Every spectrum file in a folder (not in sub-folders), sorted by name."""
    folder = Path(folder)
    return sorted(p for p in folder.iterdir() if p.is_file() and is_spectrum_file(p))
