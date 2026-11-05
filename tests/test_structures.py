"""
FTIR Contamination Analyzer - tests of the 3D models and of the band groups they carry

Every shipped reference has a model, its formula fits its atoms, its bonds are real, and a bond can only light
up for a band that material's reference spectrum really has.

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import re

import numpy as np
import pytest

from ftir_analyzer.library import load_library
from ftir_analyzer.processing import GRID
from ftir_analyzer.report import structure_html
from ftir_analyzer.structures import (ELEMENTS, NAMES, bonds_at, elements_of, groups_at, key_of, model_of, still_picture,
                                      structures)


@pytest.fixture(scope="module")
def library():
    return load_library()


def test_every_shipped_reference_has_a_model(library):
    assert all(model_of(name, library) for name in library.spectra)


@pytest.mark.parametrize("name", sorted(structures()))
def test_a_model_is_sound(name):
    model = structures()[name]
    atoms = [atom[0] for atom in model["atoms"]]
    assert {k: int(n or 1) for k, n in re.findall(r"([A-Z][a-z]?)(\d*)", model["formula"])} == \
        {k: atoms.count(k) for k in set(atoms)}                         # the formula fits the atoms
    xyz = np.array([atom[1:] for atom in model["atoms"]])
    for i, j, order in model["bonds"]:
        assert 0.8 < np.linalg.norm(xyz[i] - xyz[j]) < 2.0              # angstrom: a real bond length
        assert order in (1, 1.5, 2, 3)
    for group in model["groups"].values():
        assert group["ranges"] and group["bonds"]
        assert max(group["bonds"]) < len(model["bonds"])


def test_a_bond_only_lights_up_for_a_band_the_reference_has(library):
    for name, spectrum in library.spectra.items():
        a = spectrum - np.nanmin(spectrum)
        tops = np.flatnonzero((a[1:-1] > a[:-2]) & (a[1:-1] >= a[2:])) + 1
        bands = GRID[tops[a[tops] >= 0.02 * np.nanmax(a)]]
        for group, data in model_of(name, library)["groups"].items():
            for low, high in data["ranges"]:
                assert any(low - 12 <= w <= high + 12 for w in bands), f"{name}: {group} at {low}-{high}"


def test_the_carbonyl_of_pet_is_found_by_its_band(library):
    model = model_of("PET", library)
    assert "C=O" in groups_at(model, 1715)
    double = {n for n, (_, _, order) in enumerate(model["bonds"]) if order == 2}
    assert bonds_at(model, 1715) >= double and groups_at(model, 2100) == []     # nothing absorbs there


def test_chain_end_caps_are_not_band_groups(library):
    assert "CH₃ bend" not in model_of("PET", library)["groups"]        # PET has no CH3: only the model's ends do
    assert "CH₃ bend" in model_of("PMMA", library)["groups"]


def test_a_reference_without_a_model_has_none(library):
    assert key_of("something the lab made up", library) is None
    assert model_of("something the lab made up", library) is None


def test_a_model_is_found_by_its_material_group():
    class Group:
        @staticmethod
        def group_of(_):
            return "PEEK"
    assert key_of("peek - poly(ether ether ketone) (Open Specy)", Group) == "PEEK"


def test_the_legend_names_only_the_atoms_of_a_model(library):
    assert elements_of(model_of("PET", library)) == ["C", "H", "O"]
    assert elements_of(model_of("Nylon 6,6", library)) == ["C", "H", "O", "N"]
    assert all(element in ELEMENTS and element in NAMES for model in structures().values() for element in elements_of(model))


def test_the_web_report_names_each_model_it_shows(library):
    class Result:
        has_match, best = True, "PET"
    page = structure_html(Result, 0, library)
    assert 'data-model="PET"' in page and "Oxygen" in page and "Nitrogen" not in page
    assert page.index("mol-key") < page.index("mol-side")                        # the legend is in the 3D space


def test_still_picture_fits_its_rectangle(library):
    x, y, depth, scale = still_picture(model_of("Nylon 6,6", library), 300, 70)
    assert x.min() >= 0 and x.max() <= 300 and y.min() >= 0 and y.max() <= 70
    assert 0 <= depth.min() and depth.max() <= 1 and scale > 0
