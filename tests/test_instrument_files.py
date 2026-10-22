"""
Tests for reading instrument files: JCAMP-DX and Bruker OPUS.

The JCAMP-DX files are written from the demo spectra with the jcamp package's own writer. No
real OPUS file with a licence that allows it in this repository was available, so the OPUS
files are written here in the OPUS binary layout (header, directory, parameter blocks, data
block) and read back with the brukeropus package: the same path a real file takes.

Run with:  python -m pytest

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import struct
from pathlib import Path

import numpy as np
import pytest

from ftir_analyzer import config
from ftir_analyzer.analysis import analyse
from ftir_analyzer.library import load_library
from ftir_analyzer.spectrum_io import (SpectrumFileError, find_spectrum_files, read_mode_note, read_spectra)

EXAMPLES = config.EXAMPLES_DIR


@pytest.fixture(scope="module")
def library():
    return load_library()


def demo(name):
    return read_spectra(EXAMPLES / name)[0]


# ---------------------------------------------------------------------------- JCAMP-DX
def write_jcamp(path, spectrum, yunits, sampling="", fraction=False):
    jcamp = pytest.importorskip("jcamp")
    y = np.asarray(spectrum.raw, float)
    if fraction:
        y = y / 100.0
    header = {"title": "particle 07", "data type": "INFRARED SPECTRUM", "xunits": "1/CM", "yunits": yunits}
    if sampling:
        header["sampling procedure"] = sampling
    jcamp.writefile(str(path), dict(header, x=np.asarray(spectrum.wn, float), y=y))
    return path


def test_jcamp_absorbance_with_atr_note(tmp_path, library):
    original = demo("07_particle_on_filter.csv")
    path = write_jcamp(tmp_path / "particle.jdx", original, "ABSORBANCE", "ATR")
    spectrum = read_spectra(path)[0]
    assert spectrum.unit == "A" and "JCAMP" in spectrum.unit_source
    assert np.allclose(spectrum.raw, original.raw, atol=1e-4) and not spectrum.raw.flags.writeable
    assert read_mode_note(path) == "ATR"                               # the file says how it was measured
    result = analyse(spectrum, library, "ATR", "file note")
    assert result.best == "PE (high density)" and result.r == pytest.approx(0.97, abs=0.01)


def test_jcamp_transmittance_as_fraction(tmp_path):
    original = demo("06_PS_calibration_film_transmission.csv")          # %T in the file
    path = write_jcamp(tmp_path / "film.dx", original, "TRANSMITTANCE", "TRANSMISSION", fraction=True)
    spectrum = read_spectra(path)[0]
    assert spectrum.unit == "%T" and "× 100" in spectrum.unit_source   # said in the report
    assert np.allclose(spectrum.raw, original.raw, atol=1e-2)
    assert read_mode_note(path) == "transmission"


def test_jcamp_other_values_are_refused(tmp_path):
    path = write_jcamp(tmp_path / "raman.jdx", demo("01_wipe_area_particle_ATR.csv"), "ARBITRARY UNITS")
    with pytest.raises(SpectrumFileError, match="only absorbance or transmittance"):
        read_spectra(path)


# ---------------------------------------------------------------------------- Bruker OPUS
def _block_type(*codes):
    """The six type codes packed into one 32-bit number, as OPUS stores them."""
    shifts = (0, 2, 4, 10, 17, 19)
    return sum(code << shift for code, shift in zip(codes, shifts))


def _params(items):
    """A parameter block: 3-letter key, type (0 int, 1 float, 2 text), size in 2-byte words, value; then END."""
    out = b""
    for key, value in items:
        if isinstance(value, int):
            out += key.encode() + b"\0" + struct.pack("<2h", 0, 2) + struct.pack("<i", value)
        elif isinstance(value, float):
            out += key.encode() + b"\0" + struct.pack("<2h", 1, 4) + struct.pack("<d", value)
        else:
            text = value.encode("latin-1") + b"\0"
            text += b"\0" * (-len(text) % 4)
            out += key.encode() + b"\0" + struct.pack("<2h", 2, len(text) // 2) + text
    return out + b"END\0" + struct.pack("<2h", 0, 0)


def write_opus(path, wn, y, kind=4, sample_name="particle 07", accessory=""):
    """A minimal OPUS file with one processed spectrum. kind 4 = absorbance, 5 = transmittance."""
    y = np.asarray(y, np.float32)
    status = _params([("DPF", 1), ("NPT", len(y)), ("FXV", float(wn[0])), ("LXV", float(wn[-1])),
                      ("CSF", 1.0), ("MXY", float(y.max())), ("MNY", float(y.min())), ("DXU", "WN")])
    sample = _params([("SNM", sample_name)] + ([("ACC", accessory)] if accessory else []))
    blocks = [(_block_type(0, 0, 10, 0, 0, 0), sample),               # sample parameters (name, accessory)
              (_block_type(3, 3, 1, kind, 0, 0), status),             # data status: x range, number of points
              (_block_type(3, 3, 0, kind, 0, 0), y.tobytes())]        # the values
    directory_start, entries = 24, len(blocks) + 1
    position = directory_start + entries * 12
    directory, body = b"", b""
    directory += struct.pack("<3i", _block_type(0, 0, 0, 13, 0, 0), entries * 3, directory_start)
    for type_code, data in blocks:
        directory += struct.pack("<3i", type_code, len(data) // 4, position + len(body))
        body += data
    header = b"\n\n\xfe\xfe" + struct.pack("<d", 920622.0) + struct.pack("<3i", directory_start, entries, entries)
    Path(path).write_bytes(header + directory + body)
    return path


def test_opus_absorbance(tmp_path, library):
    pytest.importorskip("brukeropus")
    original = demo("07_particle_on_filter.csv")
    wn, a = np.asarray(original.wn)[::-1], np.asarray(original.raw)[::-1]   # OPUS stores high -> low
    path = write_opus(tmp_path / "particle.0", wn, a, accessory="Platinum ATR")
    assert path in find_spectrum_files(tmp_path)                        # found by the folder scan
    spectrum = read_spectra(path)[0]
    assert spectrum.unit == "A" and "OPUS" in spectrum.unit_source and spectrum.name == "particle"
    assert np.allclose(spectrum.raw, original.raw, atol=1e-5) and np.allclose(spectrum.wn, original.wn, atol=1e-3)
    assert read_mode_note(path) == "ATR"                               # the accessory names ATR
    assert analyse(spectrum, library, "ATR", "file note").best == "PE (high density)"


def test_opus_transmittance_fraction(tmp_path):
    pytest.importorskip("brukeropus")
    original = demo("06_PS_calibration_film_transmission.csv")
    path = write_opus(tmp_path / "film.1", np.asarray(original.wn), np.asarray(original.raw) / 100, kind=5)
    spectrum = read_spectra(path)[0]
    assert spectrum.unit == "%T" and np.allclose(spectrum.raw, original.raw, atol=1e-2)
    assert read_mode_note(path) is None                                # nothing in the file: the program asks


def test_a_number_extension_alone_is_not_opus(tmp_path):
    (tmp_path / "notes.1").write_text("not a spectrum")
    (tmp_path / "particle.csv").write_bytes((EXAMPLES / "07_particle_on_filter.csv").read_bytes())
    assert [p.name for p in find_spectrum_files(tmp_path)] == ["particle.csv"]
