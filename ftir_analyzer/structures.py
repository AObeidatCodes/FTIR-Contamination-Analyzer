"""
FTIR Contamination Analyzer - the 3D model of a material, and which of its bonds belong to a band

data/structures.json holds a short model chain of each material (made by tools/make_structures.py): its atoms,
its bonds, and its band groups, each with the wavenumber ranges of the band table and the bonds it belongs to.

A model is found by the material's name, then by its material group, so an Open Specy reference of PEEK shows
PEEK. A reference with neither (most in-house references) has no model, and no model is shown.

A lit bond says "this group absorbs in this range", as the band table does. It is not proof that the band in a
spectrum comes from that bond.

Short names used in this file:
    w = a wavenumber (cm-1)    group = a band group, e.g. "C=O"

Author : Ali Obeidat
Version: 2.0.0
License: MIT (see LICENSE)
"""

import json
import math
from functools import lru_cache

import numpy as np

from . import config

STRUCTURES_FILE = config.DATA_DIR / "structures.json"
NEAR = 10                                                               # cm-1 a band may lie outside a range
# element: (colour on a dark page, colour on a light page, radius compared with carbon)
ELEMENTS = {"C": ("#8E97A5", "#2F3743", 1.0), "H": ("#E9EBEF", "#9AA5B4", 0.56), "O": ("#F2555A", "#D21F2E", 0.96),
            "N": ("#5B97FF", "#1D5BD8", 0.96), "F": ("#7AD07F", "#23893F", 0.84), "S": ("#F0C24B", "#B98500", 1.2),
            "Si": ("#D9A066", "#A8652A", 1.25), "Cl": ("#3DB46D", "#14804A", 1.2)}
NAMES = {"C": "Carbon", "H": "Hydrogen", "O": "Oxygen", "N": "Nitrogen", "F": "Fluorine", "S": "Sulfur", "Si": "Silicon",
         "Cl": "Chlorine"}
GLOW = {"dark": "#FFB224", "light": "#E8860C"}                          # the colour of a lit bond
ALIASES = {"PE": "PE (high density)", "EVA": "EVA (25% VA)", "EVOH": "EVOH (44% ethylene)", "PK": "PK (polyketone)",
           "Nylon": "Nylon 6,6", "cellulose acetate": "Cellulose acetate"}


@lru_cache(maxsize=1)
def structures():
    """Every model, {name: {formula, smiles, note, atoms, bonds, groups}}; {} if the file is missing."""
    try:
        return json.loads(STRUCTURES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def key_of(name, library=None):
    """The name of the model of a material (by its name, then its material group), or None."""
    models = structures()
    for candidate in (name, library.group_of(name) if library is not None else None):
        candidate = ALIASES.get(candidate, candidate)
        if candidate in models:
            return candidate
    return None


def model_of(name, library=None):
    """The model of a material, or None."""
    key = key_of(name, library)
    return structures()[key] if key else None


def elements_of(model):
    """The kinds of atom in a model, in the order of ELEMENTS: ["C", "H", "O"]."""
    present = {atom[0] for atom in model["atoms"]}
    return [element for element in ELEMENTS if element in present]


def ranges_text(group):
    """A group's ranges in words: 1700–1765 cm⁻¹."""
    return ", ".join(f"{low}–{high}" for low, high in group["ranges"]) + " cm⁻¹"


def groups_at(model, w):
    """The groups of a model that absorb at wavenumber w: [group name]; [] if none does."""
    return [name for name, group in model["groups"].items()
            if any(low - NEAR <= w <= high + NEAR for low, high in group["ranges"])]


def bonds_at(model, w):
    """The bonds that belong to a band at wavenumber w, as a set of bond numbers."""
    return {bond for name in groups_at(model, w) for bond in model["groups"][name]["bonds"]}


def still_picture(model, width, height, angle=0.5, tilt=-0.24):
    """A model seen from one side, for a page: (x, y, depth from 0 far to 1 near) of each atom in this rectangle."""
    xyz = np.array([atom[1:] for atom in model["atoms"]], float)
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    y, z = y * math.cos(angle) - z * math.sin(angle), y * math.sin(angle) + z * math.cos(angle)
    x, z = x * math.cos(tilt) + z * math.sin(tilt), z * math.cos(tilt) - x * math.sin(tilt)
    scale = min(width / (2 * (np.abs(x).max() + 0.8)), height / (2 * (np.abs(y).max() + 0.8)))
    reach = max(np.abs(z).max(), 1e-6)
    return width / 2 + x * scale, height / 2 - y * scale, (z + reach) / (2 * reach), scale
