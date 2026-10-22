"""
FTIR Contamination Analyzer - instrument files

Reads spectra straight from the files the instruments write, so they need not be exported
to CSV first:

    JCAMP-DX   .jdx / .dx   the open exchange format every FTIR software can write (read with
                            the "jcamp" package, MIT licence). The file says its units and often
                            how it was measured ("##SAMPLING PROCEDURE=ATR").
    OPUS       .0, .1, ...  Bruker's own binary format (read with the "brukeropus" package, MIT
                            licence). A file with a number as its extension is only accepted if it
                            starts with the OPUS signature, so e.g. "notes.1" is never mistaken
                            for a spectrum. Of the spectra inside, absorbance is taken first, then
                            transmittance, then ATR.

As with every other file, the values are kept as they are in the file. One exception, said in
the report: transmittance stored as a fraction (0-1) is multiplied by 100, because the
program works in percent.

Short names used in this file:
    wn = wavenumbers (cm-1)    y = the values in the file    d = what the JCAMP reader returned
    opus = what the OPUS reader returned

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

JCAMP_TYPES = (".jdx", ".dx")
OPUS_SIGNATURE = b"\n\n\xfe\xfe"                 # the first four bytes of every OPUS file


@dataclass
class InstrumentSpectrum:
    """One spectrum read from an instrument file, before it becomes a Spectrum (spectrum_io.py)."""

    name: str            # the sample name stored in the file, or the file name
    wn: np.ndarray       # wavenumbers in cm-1
    y: np.ndarray        # the values (percent transmittance or absorbance)
    unit: str            # "%T" or "A"
    unit_source: str     # how the unit was known, for the report
    mode: str = None     # "ATR" / "transmission" if the file says so, else None


class InstrumentFileError(ValueError):
    """A file that cannot be read. The message is written for the user."""


def is_opus(path):
    """A number as the extension (.0, .1, .12 ...) AND the OPUS signature at the start."""
    path = Path(path)
    if not (path.suffix[1:].isdigit() and path.is_file()):
        return False
    with open(path, "rb") as f:
        return f.read(4) == OPUS_SIGNATURE


def is_jcamp(path):
    return Path(path).suffix.lower() in JCAMP_TYPES


def is_instrument_file(path):
    return is_jcamp(path) or is_opus(path)


def _percent(y, label):
    """Transmittance as percent: a fraction (all values 1.5 or less) is multiplied by 100."""
    if np.nanmax(y) <= 1.5:
        return y * 100.0, f"{label}: transmittance stored as a fraction (0-1), shown × 100 as %T"
    return y, f"{label}: transmittance"


# ---------------------------------------------------------------------------- JCAMP-DX
def _mode_from_text(text):
    text = str(text or "").lower()
    if "atr" in text or "attenuated" in text:
        return "ATR"
    if "transmission" in text:
        return "transmission"
    return None


def _jcamp_block(d, name):
    """One JCAMP block (a dict from the reader) -> InstrumentSpectrum."""
    if "x" not in d or "y" not in d:
        raise InstrumentFileError(f"{name}: no spectrum data in the JCAMP-DX file.")
    x, y = np.asarray(d["x"], float), np.asarray(d["y"], float)
    xunits, yunits = str(d.get("xunits", "")).upper(), str(d.get("yunits", "")).upper()
    if "MICRO" in xunits:                                             # micrometres -> wavenumbers
        x = 1e4 / x
    elif xunits and "1/CM" not in xunits and "CM-1" not in xunits and "CM^-1" not in xunits:
        raise InstrumentFileError(f"{name}: x-axis in {xunits}; the program needs wavenumbers (1/CM).")
    if "TRANSMITTANCE" in yunits:
        y, source = _percent(y, "JCAMP-DX ##YUNITS")
        unit = "%T"
    elif "ABSORBANCE" in yunits:
        unit, source = "A", "JCAMP-DX ##YUNITS: absorbance"
    else:
        raise InstrumentFileError(f"{name}: the values are {yunits.lower() or 'of an unknown kind'}; "
                                  "only absorbance or transmittance spectra can be compared.")
    title = str(d.get("title", "")).strip() or name
    mode = _mode_from_text(d.get("sampling procedure")) or _mode_from_text(d.get("$sampling procedure"))
    return InstrumentSpectrum(title, x, y, unit, source, mode)


def read_jcamp(path):
    try:
        import jcamp                                                  # only needed for this file type
    except ImportError as error:
        raise InstrumentFileError("Reading JCAMP-DX files needs the 'jcamp' package: "
                                  "python -m pip install jcamp") from error
    path = Path(path)
    try:
        d = jcamp.readfile(str(path))
    except Exception as error:                                       # the reader's own error, kept for the user
        raise InstrumentFileError(f"{path.name}: not a readable JCAMP-DX file ({error}).") from error
    blocks = d.get("children") or [d]                                 # a compound file holds several spectra
    spectra = [_jcamp_block(block, path.stem) for block in blocks if "x" in block]
    if not spectra:
        raise InstrumentFileError(f"{path.name}: no spectrum data in the JCAMP-DX file.")
    return spectra


# ---------------------------------------------------------------------------- Bruker OPUS
def _opus_mode(opus):
    """'ATR' if the measurement parameters name an ATR accessory, else None (then the program asks)."""
    for key in ("acc", "acn", "acs"):                                 # accessory code / name
        try:
            value = getattr(opus.params, key)
        except (AttributeError, KeyError):
            continue
        if "atr" in str(value).lower():
            return "ATR"
    return None


def read_opus(path):
    try:
        from brukeropus import read_opus as read                      # only needed for this file type
    except ImportError as error:
        raise InstrumentFileError("Reading Bruker OPUS files needs the 'brukeropus' package: "
                                  "python -m pip install brukeropus") from error
    path = Path(path)
    try:
        opus = read(str(path))
    except Exception as error:
        raise InstrumentFileError(f"{path.name}: not a readable OPUS file ({error}).") from error
    if not getattr(opus, "is_opus", False):
        raise InstrumentFileError(f"{path.name}: not an OPUS file.")
    for key, unit in (("a", "A"), ("t", "%T"), ("atr", "A")):         # the processed spectrum, best first
        if key in opus.data_keys:
            data = getattr(opus, key)
            wn, y = np.asarray(data.wn, float), np.asarray(data.y, float)
            if unit == "%T":
                y, source = _percent(y, "OPUS transmittance block")
            else:
                source = "OPUS absorbance block" if key == "a" else "OPUS ATR block (absorbance units)"
            try:
                name = str(opus.params.snm).strip() or path.stem      # SNM = the sample name typed in OPUS
            except (AttributeError, KeyError):
                name = path.stem
            mode = "ATR" if key == "atr" else _opus_mode(opus)
            return [InstrumentSpectrum(name, wn, y, unit, source, mode)]
    raise InstrumentFileError(f"{path.name}: no absorbance or transmittance spectrum in the OPUS file "
                              f"(it holds: {', '.join(opus.data_keys) or 'nothing readable'}).")


def read_instrument_file(path):
    """Every spectrum in a JCAMP-DX or OPUS file, as InstrumentSpectrum objects."""
    return read_opus(path) if is_opus(path) else read_jcamp(path)
