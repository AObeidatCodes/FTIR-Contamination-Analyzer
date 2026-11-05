"""
FTIR Contamination Analyzer - tests of the material families and of telling two close materials apart

A family is chemistry and never changes a verdict. It is only named when two close references agree, and where two
references differ is read from the references themselves.

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import pytest

from ftir_analyzer import config
from ftir_analyzer.analysis import analyse
from ftir_analyzer.families import close_call, family_of, relatives, where_they_differ
from ftir_analyzer.library import load_library
from ftir_analyzer.spectrum_io import read_mode_note, read_spectra
from ftir_analyzer.structures import structures


@pytest.fixture(scope="module")
def library():
    return load_library()


def result(name, library):
    path = config.EXAMPLES_DIR / name
    return analyse(read_spectra(path)[0], library, read_mode_note(path) or "unknown", "file note")


def test_a_family_is_chemistry(library):
    assert family_of("PET", library) == family_of("PBT", library) == "Polyesters"
    assert family_of("PE (high density)", library) == family_of("PP", library) == "Polyolefins"
    assert family_of("PK (polyketone)", library) == ""                           # stands alone
    assert relatives("PET", library) == ["PBT", "PLA"]
    assert relatives("PC", library) == []


def test_every_model_with_a_family_is_spelled_as_in_the_table():
    from ftir_analyzer.families import _table
    assert {"PEEK", "silicone", "epoxy", "Cotton", "Wool", "Nylon 6"} <= set(_table())
    assert sum(1 for name in structures() if family_of(name)) >= 25


def test_two_close_references_of_one_family_are_named(library):
    call = close_call(result("13_clear_film_on_tool_ATR.csv", library), library)
    assert call.family == "Polyesters" and (call.first, call.second) == ("PET", "PBT")
    assert "C=O" in call.shared and "Aliphatic C–H" not in call.shared
    assert "are both polyesters" in call.text() and f"{call.w:.0f} cm⁻¹" in call.text()
    assert call.height_1 > call.height_2                                         # PET has the taller band there
    assert 650 <= call.w <= 3100 and 0 <= call.sample <= 1


@pytest.mark.parametrize("name", ["05_fibre_on_wafer_ATR.csv", "10_tool_cover_fragment_ATR.csv",    # one high score
                                  "17_biopolymer_fragment_ATR.csv", "20_fibre_from_a_sweater_ATR.csv"])  # or a low one
def test_a_single_score_never_names_a_family(library, name):
    assert close_call(result(name, library), library) is None


def test_a_probable_or_no_match_has_no_close_call(library):
    assert close_call(result("01_wipe_area_particle_ATR.csv", library), library) is None   # PET 0.97, PBT 0.87
    assert close_call(result("19_lint_on_a_wafer_ATR.csv", library), library) is None


def test_a_close_call_changes_no_verdict(library):
    r = result("13_clear_film_on_tool_ATR.csv", library)
    before = r.verdict, r.match, r.r
    close_call(r, library)
    assert (r.verdict, r.match, r.r) == before


def test_where_two_references_differ_is_the_same_both_ways(library):
    assert where_they_differ(library, "PET", "PBT") == where_they_differ(library, "PBT", "PET")
