"""
FTIR Contamination Analyzer - reference library, search and validation

The library has up to three parts:
    shipped     validated reference spectra that come with the program (data/library_index.csv)
    in-house    references the lab adds itself, measured on its own instrument (records/inhouse_library)
    Open Specy  optional: fab-relevant FTIR spectra from the Open Specy library, downloaded or imported
                on the lab's computer (records/openspecy, see openspecy.py); used in "extended" mode

Every reference belongs to a material GROUP (PE, PET, silicone, ...). Two references of the
same material (for example PE from OpenFTIR and polyethylene from Open Specy) are not rivals:
the impostor test and the verdict's "lead over the next material" look at the next DIFFERENT
material.

Every reference is put into the library's measuring mode (ATR) when it is loaded, exactly
like a sample, and then onto the common 5 cm-1 grid.

This file also holds the search (Pearson r on the derivative fingerprints) and the
validation tools:
    impostor_test        the best score a WRONG material can reach; must stay below 'probable'
    validation_impact    what adding a new reference would do to that, BEFORE it is added
    similarity_matrix    how similar every pair of references is (which ones could be confused)

Short names used in this file:
    wn = wavenumbers    a = absorbance    y = a spectrum on the common grid    a, b (in pearson) = two fingerprints
    ok = True where both have data    r = Pearson r (the score)    k, v = key and value of a dict

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config
from .processing import CO2_MASK, fingerprint, on_grid, to_library_mode
from .spectrum_io import checksum, read_mode_note, read_table


@dataclass(frozen=True)
class MaterialInfo:
    """Everything known about one reference: what it is, where it came from, how it was measured."""

    name: str
    category: str = "Uncategorised"
    source: str = ""             # "OpenFTIR", or "In-house"
    licence: str = ""
    contributor: str = ""        # who measured or published it
    mode: str = "ATR"            # how the reference was measured
    original_name: str = ""      # its name in the original source (or the file it was made from)
    origin: str = "shipped"      # "shipped" or "in-house"
    added_by: str = ""           # in-house only: who added it ...
    added_at: str = ""           # ... and when
    confirmation: str = ""       # in-house only: how the identity was confirmed
    fab_sources: str = ""        # in-house only: where it can come from in the fab
    check_next: str = ""         # in-house only: what to check next
    notes: str = ""
    file: str = ""               # the file holding the spectrum
    sha256: str = ""             # checksum of that file
    group: str = ""              # the material it is (PE, PET, silicone ...); "" = its own name


@dataclass(frozen=True)
class Library:
    """A set of reference spectra, all on the common grid, plus where each one came from."""

    name: str        # e.g. "16 shipped references" or "16 shipped + 2 in-house references"
    mode: str        # how the library is measured ("ATR"); references are converted to this on loading
    spectra: dict    # {material name: spectrum on the grid}
    sha256: str      # one checksum over every file the library was read from (in every report)
    path: Path
    info: dict = field(default_factory=dict)                        # {material name: MaterialInfo}
    _fingerprints: dict = field(default_factory=dict, compare=False, repr=False)   # filled on first use

    def __len__(self):
        return len(self.spectra)

    def fingerprint_of(self, name):
        """The fingerprint of one reference, calculated once and then kept."""
        if name not in self._fingerprints:
            self._fingerprints[name] = fingerprint(self.spectra[name])
        return self._fingerprints[name]

    def info_of(self, name):
        return self.info.get(name, MaterialInfo(name))

    def group_of(self, name):
        """The material a reference belongs to; references of one material are not rivals."""
        return self.info_of(name).group or name

    def rival(self, ranking):
        """The position in a ranking of the best material that is DIFFERENT from the winner's."""
        best = self.group_of(ranking[0][0])
        return next((i for i, (name, _) in enumerate(ranking) if i and self.group_of(name) != best),
                    min(1, len(ranking) - 1))

    @property
    def open_specy(self):
        """Names of the Open Specy references (extended mode)."""
        return [n for n in self.spectra if self.info_of(n).origin == "open specy"]

    @property
    def in_house(self):
        """Names of the references the lab added itself."""
        return [n for n in self.spectra if self.info_of(n).origin == "in-house"]


@dataclass(frozen=True)
class Validation:
    """Result of the impostor test: the best score a WRONG material reaches in this library."""

    material: str    # the material that was taken out of the library
    impostor: str    # the wrong material that matched it best
    score: float     # that wrong match's Pearson r

    @property
    def passed(self):
        """True if no wrong material can reach 'probable' with this library."""
        return self.score < config.PROBABLE_R


@dataclass(frozen=True)
class Impact:
    """What adding one new reference would do to the library (worked out before it is added)."""

    before: Validation       # the impostor test now
    after: Validation        # the impostor test with the new reference in the library
    nearest: tuple           # (existing material, r): the one most similar to the new reference

    @property
    def passed(self):
        """True if the library stays valid with the new reference."""
        return self.after.passed

    @property
    def distinct(self):
        """True if the new reference is clearly different from every existing one."""
        return self.nearest[1] < config.PROBABLE_R


# ---------------------------------------------------------------------------- material groups
# (group, words that identify it). Checked in this order, so the specific names come first.
# Short abbreviations only count as whole words (PE matches "PE (high density)", not "PET").
GROUP_RULES = [
    ("ABS", ["ACRYLONITRILE BUTADIENE STYRENE", r"\bABS\b"]),
    ("SAN", ["STYRENE.ACRYLONITRILE", r"\bSAN\b"]),
    ("EVOH", ["ETHYLENE.VINYL ALCOHOL", r"\bEVOH\b"]),
    ("EVA", ["ETHYLENE.VINYL ACETATE", r"\bEVA\b"]),
    ("PET", ["ETHYLENE TEREPHTHALATE", r"\bPET\b"]),
    ("PBT", ["BUTYLENE TEREPHTHALATE", r"\bPBT\b"]),
    ("PEEK", ["ETHER ETHER KETONE", r"\bPEEK\b"]),
    ("PK", ["POLYKETONE", r"\bPK\b"]),
    ("PS", ["POLYSTYRENE", r"POLY\(STYRENE\)", r"\bPS\b"]),
    ("PP", ["POLYPROPYLENE", r"POLY\(PROPYLENE\)", r"\bPP\b"]),
    ("PE", ["POLYETHYLENE", r"POLY\(ETHYLENE\)", r"\b[HL]?DPE\b", r"\bPE\b"]),
    ("PMMA", ["METHYL METHACRYLATE", r"\bPMMA\b"]),
    ("PC", ["POLYCARBONATE", r"\bPC\b"]),
    ("PA", ["POLYAMIDE", "NYLON", r"\bPA\s?\d"]),
    ("PVOH", ["VINYL ALCOHOL", r"\bPVOH\b", r"\bPVA\b"]),
    ("PVAc", [r"POLY\(?VINYL ACETATE", r"\bPVAC\b"]),
    ("PAN", ["POLYACRYLONITRILE", r"\bPAN\b"]),
    ("PLA", ["LACTIC ACID", r"\bPLA\b"]),
    ("PVC", ["VINYL CHLORIDE", r"\bPVC\b"]),
    ("PU", ["URETHANE", r"\bT?PU\b"]),
    ("silicone", ["SILOXANE", "SILICONE", r"\bPDMS\b"]),
    ("fluoropolymer", ["FLUORO", r"\bPTFE\b", r"\bPVDF\b", r"\bFEP\b", r"\bPFA\b"]),
    ("POM", ["OXYMETHYLENE", "POLYACETAL", r"\bPOM\b"]),
    ("polyimide", ["POLYIMIDE", "KAPTON", r"\bPI\b"]),
    ("epoxy", ["EPOXY", "EPOXIDE", "PHENOXY"]),
    ("cellulose acetate", ["CELLULOSE ACETATE"]),
    ("cellulose", ["CELLULOSE", "COTTON", "PAPER"]),
    ("protein", ["PROTEIN", "KERATIN", "WOOL", "SILK", "HAIR"]),
    ("nitrile rubber", ["NITRILE", r"\bNBR\b"]),
    ("natural rubber", ["ISOPRENE", "LATEX", "NATURAL RUBBER"]),
    ("silica", ["QUARTZ", "SILICA", r"SILICON DIOXIDE"]),
]


def material_group(text):
    """The material group a name belongs to (e.g. 'PE (high density)' -> 'PE'), or '' if unknown."""
    text = str(text).upper()
    for group, patterns in GROUP_RULES:
        if any(re.search(pattern, text) for pattern in patterns):
            return group
    return ""


# ---------------------------------------------------------------------------- loading
def reference_on_grid(wn, a, mode):
    """One reference: sorted, NaN removed, put into the library's mode, then onto the grid."""
    wn, a = np.asarray(wn, float), np.asarray(a, float)
    keep = np.isfinite(wn) & np.isfinite(a)
    order = np.argsort(wn[keep])
    wn, a = wn[keep][order], a[keep][order]
    return on_grid(wn, to_library_mode(wn, a, mode, config.LIBRARY_MODE))


def _load_shipped(index_path):
    """The shipped references listed in the index, with their information and the files they came from."""
    index = read_table(index_path, dtype=str).fillna("")
    spectra, info, files, tables = {}, {}, {index_path}, {}
    for row in index.itertuples():
        path = Path(index_path).parent / row.file
        if path not in tables:                                          # each file is read once
            tables[path] = read_table(path)
            files.add(path)
        table = tables[path]
        spectra[row.material] = reference_on_grid(table.iloc[:, 0], table[row.material], row.mode)
        info[row.material] = MaterialInfo(
            name=row.material, category=row.category, source=row.source, licence=row.licence,
            contributor=row.contributor, mode=row.mode, original_name=row.original_name,
            origin="shipped", file=row.file, sha256=checksum(path),
            group=material_group(row.material) or material_group(row.original_name))
    return spectra, info, files


def load_library(path=None, inhouse_dir=None, extended=False, openspecy_dir=None):
    """The reference library: the shipped references plus the lab's in-house references.

    path           the shipped library index (default: data/library_index.csv). An old-style
                   'wide' library file (one wavenumber column + one column per material) also works.
    inhouse_dir    the folder of in-house references (default: records/inhouse_library); missing = none.
    extended       True: also the Open Specy references, if they were downloaded or imported
    openspecy_dir  where those are kept (default: records/openspecy)
    """
    from .inhouse import InHouseLibrary                               # here, to avoid a circular import
    from .openspecy import OpenSpecyLibrary
    path = Path(path or config.LIBRARY_INDEX)
    header = read_table(path, nrows=0).columns
    if "material" not in header:                                       # an old-style wide file
        table = read_table(path)
        mode = read_mode_note(path) or "unknown"
        spectra = {str(c): on_grid(table.iloc[:, 0].to_numpy(float), table[c].to_numpy(float))
                   for c in table.columns[1:]}
        info = {n: MaterialInfo(n, mode=mode, source=path.name) for n in spectra}
        return Library(path.name, mode, spectra, checksum(path), path, info)

    spectra, info, files = _load_shipped(path)
    shipped = len(spectra)
    inhouse = InHouseLibrary(inhouse_dir or config.INHOUSE_DIR)
    for entry in inhouse.active():
        wn, a = inhouse.spectrum(entry)
        spectra[entry.name] = reference_on_grid(wn, a, entry.mode)
        info[entry.name] = entry
        files.add(inhouse.folder / entry.file)
    if inhouse.log.exists():
        files.add(inhouse.log)
    added = len(spectra) - shipped
    open_specy = 0
    if extended:
        extra = OpenSpecyLibrary(openspecy_dir)
        for entry, y in extra.entries():
            if entry.name not in spectra:
                spectra[entry.name], info[entry.name] = y, entry
                open_specy += 1
        files.update(extra.files())

    # one checksum over every file, so a report can prove exactly which library it used
    digest = hashlib.sha256()
    for file in sorted(files, key=lambda p: str(p.name)):
        digest.update(file.name.encode())
        digest.update(checksum(file).encode())
    name = (f"{shipped} shipped" + (f" + {added} in-house" if added else "")
            + (f" + {open_specy} Open Specy" if open_specy else "") + " references")
    return Library(name, config.LIBRARY_MODE, spectra, digest.hexdigest(), path, info)


# ---------------------------------------------------------------------------- search
def pearson(a, b):
    """Shape similarity from -1 to 1, on the points both spectra have, CO2 region left out.

    Subtracting the averages removes offsets, dividing by the spreads removes scale:
    what is left asks "do the two go up and down together?".
    """
    ok = np.isfinite(a) & np.isfinite(b) & ~CO2_MASK                  # ~ means NOT
    if ok.sum() < config.SAVGOL_WINDOW or np.ptp(a[ok]) == 0 or np.ptp(b[ok]) == 0:
        return 0.0                                                     # nothing to compare: no similarity
    return float(np.corrcoef(a[ok], b[ok])[0, 1])                      # [0, 1] picks r out of the 2x2 table


def search(y, library):
    """Every library material with its score, best first: [("PET", 0.97), ("PBT", 0.87), ...]."""
    u = fingerprint(y)                                                 # the unknown's fingerprint, made once
    scores = {name: pearson(u, library.fingerprint_of(name)) for name in library.spectra}
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)  # sort by the score, highest first


def _without(library, name):
    """The same library with one material left out."""
    others = {k: v for k, v in library.spectra.items() if k != name}
    return Library(library.name, library.mode, others, library.sha256, library.path, library.info,
                   {k: v for k, v in library._fingerprints.items() if k != name})


def impostor_test(library):
    """Take each reference out of the library and search with its own spectrum.

    The best match that is a DIFFERENT material is a wrong answer (references of the same
    material, from another source, would be right). The highest of these scores is how high
    a wrong material can get, so 'probable' must start above it.
    """
    worst = Validation("", "", 0.0)
    for name, spectrum in library.spectra.items():
        group = library.group_of(name)
        ranking = search(spectrum, _without(library, name))
        impostor, r = next(((n, s) for n, s in ranking if library.group_of(n) != group), ("", 0.0))
        if r > worst.score:                                            # keep the record
            worst = Validation(name, impostor, r)
    return worst


# ---------------------------------------------------------------------------- validation of changes
def with_reference(library, name, y, info=None):
    """A copy of the library with one more reference (y = its spectrum on the grid)."""
    spectra = dict(library.spectra)
    spectra[name] = y
    infos = dict(library.info)
    infos[name] = info or MaterialInfo(name, origin="in-house")
    return Library(library.name, library.mode, spectra, library.sha256, library.path, infos,
                   dict(library._fingerprints))


def validation_impact(library, name, y, before=None):
    """What adding reference `name` (spectrum y on the grid) would do, worked out before adding it."""
    before = before or impostor_test(library)
    nearest = search(y, library)[0]                                    # the most similar existing material
    after = impostor_test(with_reference(library, name, y))
    return Impact(before, after, nearest)


def similarity_matrix(library):
    """(names, matrix): the Pearson r of every pair of references; the diagonal is 1."""
    names = list(library.spectra)
    prints = [library.fingerprint_of(n) for n in names]
    size = len(names)
    matrix = np.eye(size)
    for i in range(size):
        for j in range(i + 1, size):
            matrix[i, j] = matrix[j, i] = pearson(prints[i], prints[j])
    return names, matrix
