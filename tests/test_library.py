"""
FTIR Contamination Analyzer - tests of the library: provenance, validation and the in-house workflow

The central promise: a material that is NOT in the library is not identified; after a
reference of it is added (and validated), a new measurement of it IS identified. And a
reference that would make two materials impossible to tell apart is caught before it is added.

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import numpy as np
import pytest

from ftir_analyzer import config
from ftir_analyzer.analysis import NO_MATCH, PROBABLE, WEAK, analyse
from ftir_analyzer.inhouse import InHouseLibrary, reference_notes
from ftir_analyzer.library import impostor_test, load_library, similarity_matrix, validation_impact
from ftir_analyzer.processing import absorbance, on_grid, to_library_mode
from ftir_analyzer.spectrum_io import read_spectra

EXAMPLES = config.EXAMPLES_DIR
DEMO = EXAMPLES / "library_demo"


def analyse_file(name, library, mode="ATR"):
    return analyse(read_spectra(EXAMPLES / name)[0], library, mode)


def add_from_file(inhouse, path, library):
    """Add a reference file the way the app does: details from the file's own notes."""
    spectrum, notes = read_spectra(path)[0], reference_notes(path)
    return inhouse.add(notes["reference"], spectrum.wn, absorbance(spectrum), notes.get("mode", "ATR"),
                       category=notes.get("category", "In-house"), fab_sources=notes.get("fab sources", ""),
                       check_next=notes.get("check next", ""), confirmation=notes.get("confirmation", ""),
                       source_path=path, existing=library.spectra)


def grid_of(path, mode="ATR"):
    s = read_spectra(path)[0]
    return on_grid(s.wn, to_library_mode(s.wn, absorbance(s), mode, config.LIBRARY_MODE))


@pytest.fixture
def empty_inhouse(tmp_path):
    return tmp_path / "inhouse_library"


def test_shipped_library_has_provenance(empty_inhouse):
    library = load_library(inhouse_dir=empty_inhouse)
    assert len(library) == 16 and library.in_house == []
    for name in library.spectra:
        info = library.info_of(name)
        assert info.source == "OpenFTIR" and info.licence == "MIT" and info.original_name
        assert info.category in config.CATEGORIES
    assert impostor_test(library).passed


def test_similarity_matrix(empty_inhouse):
    names, matrix = similarity_matrix(load_library(inhouse_dir=empty_inhouse))
    assert np.allclose(matrix, matrix.T) and np.allclose(np.diag(matrix), 1)
    off = matrix - np.eye(len(names))
    i, j = np.unravel_index(np.argmax(off), off.shape)
    assert {names[i], names[j]} == {"PET", "PBT"}                       # the closest pair, as the impostor test says


def test_adding_a_reference_catches_the_unknown(empty_inhouse):
    library = load_library(inhouse_dir=empty_inhouse)
    assert analyse_file("10_tool_cover_fragment_ATR.csv", library).verdict == WEAK      # before: weak PS

    impact = validation_impact(library, "ABS", grid_of(DEMO / "ABS_reference_known_part.csv"))
    assert impact.passed and impact.distinct                             # safe to add

    add_from_file(InHouseLibrary(empty_inhouse), DEMO / "ABS_reference_known_part.csv", library)
    library = load_library(inhouse_dir=empty_inhouse)
    assert library.in_house == ["ABS"] and impostor_test(library).passed
    result = analyse_file("10_tool_cover_fragment_ATR.csv", library)
    assert (result.verdict, result.match) == (PROBABLE, "ABS")          # after: caught
    from ftir_analyzer.evidence import fab_sources
    assert "equipment housings" in fab_sources("ABS", library)[0]       # its fab sources came along


def test_a_too_similar_reference_is_caught_before_adding(empty_inhouse):
    add_from_file(InHouseLibrary(empty_inhouse), DEMO / "ABS_reference_known_part.csv",
                  load_library(inhouse_dir=empty_inhouse))
    library = load_library(inhouse_dir=empty_inhouse)
    impact = validation_impact(library, "SAN", grid_of(DEMO / "SAN_reference_cover_sample.csv"))
    assert not impact.passed and not impact.distinct                    # SAN and ABS cannot be told apart
    assert impact.nearest[0] == "ABS" and impact.nearest[1] >= config.PROBABLE_R


def test_adding_a_result_as_reference(empty_inhouse):
    library = load_library(inhouse_dir=empty_inhouse)
    fibre = read_spectra(EXAMPLES / "08_fibre_on_filter.csv")[0]
    assert analyse_file("11_second_fibre_on_filter.csv", library, "unknown").verdict == NO_MATCH
    InHouseLibrary(empty_inhouse).add("Cellulose acetate (fibre)", fibre.wn, absorbance(fibre), "unknown",
                                      category="People & clothing", confirmation="band reading: acetate C=O 1740, C-O 1230",
                                      source_path=fibre.path, existing=library.spectra)
    library = load_library(inhouse_dir=empty_inhouse)
    result = analyse_file("11_second_fibre_on_filter.csv", library, "unknown")
    assert (result.verdict, result.match) == (PROBABLE, "Cellulose acetate (fibre)")


def test_removing_keeps_the_history(empty_inhouse):
    inhouse = InHouseLibrary(empty_inhouse)
    path = add_from_file(inhouse, DEMO / "ABS_reference_known_part.csv", load_library(inhouse_dir=empty_inhouse))
    inhouse.remove("ABS", reason="demo finished")
    assert inhouse.names() == [] and path.exists()                      # out of the library, file kept
    assert list(inhouse.changes()["action"]) == ["add", "remove"]       # both changes recorded
    library = load_library(inhouse_dir=empty_inhouse)
    assert analyse_file("10_tool_cover_fragment_ATR.csv", library).verdict == WEAK


def test_names_must_be_new(empty_inhouse):
    library = load_library(inhouse_dir=empty_inhouse)
    with pytest.raises(ValueError):
        add_from_file(InHouseLibrary(empty_inhouse), DEMO / "ABS_reference_known_part.csv", library) and \
            InHouseLibrary(empty_inhouse).add("PET", [1, 2], [1, 2], "ATR", existing=library.spectra)
    with pytest.raises(ValueError):
        InHouseLibrary(empty_inhouse).add("PET", np.arange(650, 4000.0), np.ones(3350), "ATR",
                                          existing=library.spectra)
