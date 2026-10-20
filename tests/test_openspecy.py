"""
FTIR Contamination Analyzer - tests of the Open Specy references (extended mode)

The test file tests/data/openspecy_sample.rds has the structure of an Open Specy library
file (wavenumber, spectra, metadata). Its spectra are OpenFTIR spectra (MIT), labelled the
way Open Specy labels its own, with one Raman spectrum and one soil spectrum among them.

Checked: only fab-relevant FTIR spectra are kept; a spectrum that could be confused with a
different material is left out (and reported); the extended library passes the impostor
test; a second reference of the SAME material does not weaken a verdict; the 'derivative'
library is refused; the download finds the 'nobaseline' library on OSF.

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import io
import json
from pathlib import Path

import pytest

from ftir_analyzer import config
from ftir_analyzer.analysis import PROBABLE, WEAK, analyse, decide
from ftir_analyzer.evidence import fab_sources
from ftir_analyzer.library import impostor_test, load_library, material_group
from ftir_analyzer.spectrum_io import read_spectra

pytest.importorskip("rdata")
from ftir_analyzer.openspecy import (choose_file, curate, download, import_library, list_osf_files,  # noqa: E402
                                     prepare, read_library_file)

FIXTURE = Path(__file__).parent / "data" / "openspecy_sample.rds"


@pytest.fixture
def base(tmp_path):
    return load_library(inhouse_dir=tmp_path / "inhouse")


def test_material_groups():
    assert material_group("PE (high density)") == "PE" and material_group("PET Biaxial Film") == "PET"
    assert material_group("POLY(ETHYLENE)") == "PE" and material_group("Nylon 6,6") == "PA"
    assert material_group("POLY(DIMETHYLSILOXANE) (PDMS)") == "silicone"
    assert material_group("something else") == ""


def test_only_fab_relevant_ftir_spectra_are_kept():
    wn, X, metadata = read_library_file(FIXTURE)
    assert X.shape == (len(wn), 10)
    entries, skipped = prepare(wn, X, metadata)
    assert skipped["Raman"] == 1 and skipped["not likely in a fab"] == 1          # the PET Raman and the soil
    assert len(entries) == 8 and all(e["name"].endswith("(Open Specy)") for e in entries)


def test_confusable_spectra_are_left_out(base):
    entries, _ = prepare(*read_library_file(FIXTURE))
    kept, dropped = curate(base, entries)
    confused = {name: other for name, other, r in dropped}
    assert confused == {"acrylic coating (Open Specy)": "PMMA", "polyolefin pellet (Open Specy)": "PP"}
    assert all(r >= config.PROBABLE_R for _, _, r in dropped)
    assert len(kept) == 6


def test_import_gives_a_valid_extended_library(base, tmp_path):
    folder = tmp_path / "openspecy"
    summary = import_library(FIXTURE, base, folder)
    assert summary.kept == 6 and "confused" in summary.text()
    assert (folder / "import_report.txt").exists()
    extended = load_library(inhouse_dir=tmp_path / "inhouse", extended=True, openspecy_dir=folder)
    assert len(extended) == 22 and "6 Open Specy" in extended.name and len(extended.open_specy) == 6
    assert impostor_test(extended).passed
    pe = "Poly(ethylene) (Open Specy)"
    assert extended.group_of(pe) == "PE" and extended.info_of(pe).licence == "CC BY 4.0"
    assert extended.info_of(pe).category == "Packaging"                       # the shipped PE's category
    assert fab_sources(pe, extended) == fab_sources("PE (high density)", extended)
    shipped_only = load_library(inhouse_dir=tmp_path / "inhouse", extended=False, openspecy_dir=folder)
    assert len(shipped_only) == 16


def test_a_second_reference_of_the_same_material_does_not_weaken_the_verdict(base, tmp_path):
    folder = tmp_path / "openspecy"
    import_library(FIXTURE, base, folder)
    extended = load_library(inhouse_dir=tmp_path / "inhouse", extended=True, openspecy_dir=folder)
    result = analyse(read_spectra(config.EXAMPLES_DIR / "02_wafer_box_particle_ATR.csv")[0], extended, "ATR")
    assert result.verdict == PROBABLE and extended.group_of(result.match) == "PE"
    assert extended.group_of(result.runner_up) != "PE" and result.gap >= config.MIN_GAP
    # the rule itself: the lead is measured to the next DIFFERENT material
    ranking = [("PE a", 0.97), ("PE b", 0.96), ("PP", 0.60)]
    assert decide(ranking, rival=2) == (PROBABLE, "PE a") and decide(ranking, rival=1)[0] == WEAK


def test_the_derivative_library_is_refused(tmp_path):
    copy = tmp_path / "derivative.rds"
    copy.write_bytes(FIXTURE.read_bytes())
    with pytest.raises(ValueError, match="nobaseline"):
        read_library_file(copy)


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_download_finds_the_nobaseline_library(tmp_path):
    root = {"data": [{"attributes": {"kind": "file", "name": "derivative.rds", "size": 10},
                      "links": {"download": "https://osf.example/derivative"}},
                     {"attributes": {"kind": "folder", "name": "medoids"},
                      "relationships": {"files": {"links": {"related": {"href": "https://api.example/medoids"}}}}}],
            "links": {"next": None}}
    folder = {"data": [{"attributes": {"kind": "file", "name": "mediod_nobaseline.rds", "size": 4},
                        "links": {"download": "https://osf.example/mediod_nobaseline"}}], "links": {}}
    payload = FIXTURE.read_bytes()

    def opener(url, timeout=0):
        if url.startswith("https://api.osf.io/") and "x7dpz" in url:
            return FakeResponse(json.dumps(root).encode())
        if url == "https://api.example/medoids":
            return FakeResponse(json.dumps(folder).encode())
        if url == "https://osf.example/mediod_nobaseline":
            return FakeResponse(payload, {"Content-Length": str(len(payload))})
        raise AssertionError(url)

    files = list_osf_files(opener=opener)
    name, _, link = choose_file(files)
    assert name == "mediod_nobaseline.rds"                                    # not the derivative library
    steps = []
    target = download(link, tmp_path / name, lambda *a: steps.append(a), opener)
    assert target.read_bytes() == payload and steps
    with pytest.raises(FileNotFoundError):
        choose_file([("derivative.rds", 1, "x")])
