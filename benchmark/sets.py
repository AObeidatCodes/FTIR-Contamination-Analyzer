"""
FTIR Contamination Analyzer - the benchmark's test sets

Reads the three data sets and says what each spectrum truly is, by the rules in PROTOCOL.md. Nothing here looks at
a score: the labels and the locked set are worked out from the labels alone.

    read_fibres        FasTEX-KCL: 137 physical samples, 160 spectra
    read_open_specy    Open Specy: every labelled spectrum, except NIST's
    read_openftir      OpenFTIR: the spectra that are not the library and have a stated material
    split_locked       which Open Specy clusters are kept back, unscored

Short names used in this file:
    wn = wavenumbers (cm-1)    y = intensities    item = one spectrum to test

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import hashlib
import re
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from ftir_analyzer import openspecy
from ftir_analyzer.library import GROUP_RULES, material_group

IN, OUT, RELATIVE = "in library", "not in library", "close relative"

FIBRES, OPEN_SPECY, OPENFTIR = "fibres", "open specy", "openftir"
SPLIT_SALT = "ftir-benchmark-v1|"
LOCKED_SHARE = 0.30

IN_LIBRARY = ("PE", "PS", "PP", "PA", "PVC", "PAN", "PET", "PU", "EVA", "PC", "PMMA", "PVOH", "PLA", "PBT", "EVOH")
NOT_IN_LIBRARY = ("cellulose", "cellulose acetate", "fluoropolymer", "silicone", "PVAc", "SAN", "ABS", "polyimide",
                  "natural rubber", "nitrile rubber", "epoxy", "PEEK", "POM", "protein", "silica", "aramid")
PA_OTHER = "polyamide (not 6,6)"
NIST = "nist chem web book"                                 # this project does not use NIST data

# A word that makes a label doubtful, and copolymers by nature, which "COPOLYMER" says nothing new about.
DOUBT_WORDS = r"GLYCOL|SULFON|WAX|BLEND|MIXTURE|COMPOSITE"
COPOLYMERS = ("EVA", "EVOH", "SAN", "ABS")
# Groups that only match because one name sits inside another: POLYACRYLONITRILE contains NITRILE.
NESTED = {"PAN": {"nitrile rubber"}, "EVA": {"PE"}, "cellulose acetate": {"cellulose"},
          "SAN": {"PS", "PAN", "nitrile rubber"}, "ABS": {"PS", "PAN", "nitrile rubber"},
          "EVOH": {"PE", "PVOH", "EVA"}}

# (Type, Subtype): (truth, how it is scored, its relative). An empty Subtype means every subtype of that Type.
FIBRE_TRUTH = {("Polyester", "PET"): ("PET", IN, ""), ("Polyolefin", "PP"): ("PP", IN, ""),
               ("Polyolefin", "PE"): ("PE", IN, ""), ("Polyamide", "PA 6,6"): ("PA", IN, ""),
               ("Polyamide", "PA 6"): (PA_OTHER, RELATIVE, "PA"),
               ("Polyamide", "Unspecified PA Copolymer"): (PA_OTHER, RELATIVE, "PA"),
               ("Acrylic", ""): ("acrylic fibre", RELATIVE, "PAN"), ("Modacrylic", ""): ("modacrylic fibre", RELATIVE, "PAN"),
               ("Aramid", ""): ("aramid", OUT, ""), ("Cellulose", ""): ("cellulose", OUT, ""),
               ("Regenerated cellulose", ""): ("cellulose", OUT, ""),
               ("Cellulose acetate", ""): ("cellulose acetate", OUT, ""), ("Protein", ""): ("protein", OUT, "")}


@dataclass(frozen=True, eq=False)
class Item:
    """One spectrum to test, with what it truly is."""

    key: str             # unique within its data set
    dataset: str         # FIBRES, OPEN_SPECY or OPENFTIR
    truth: str           # the material it is
    kind: str            # IN, OUT or RELATIVE
    relative: str        # the reference it is a close relative of, or ""
    cluster: str         # spectra that may be from one source; for the fibres, the physical sample
    contributor: str     # who measured it
    label: str           # the text its truth came from
    doubtful: bool       # the label may be wrong or describe a mixture
    mode: str            # "ATR", "transmission" or "unknown"
    unit: str            # "%T" or "A"
    wn: np.ndarray
    y: np.ndarray
    replica: int = 1     # fibres: which repeat of the sample
    locked: bool = False # kept back: must never be scored here


def says_nylon_66(text):
    """True if a polyamide label says 6,6 and does not also name Nylon 6 on its own."""
    text = str(text).upper()
    six_six = re.search(r"(?<!\d)6\s*[,./-]?\s*6(?!\d)", text)
    six_alone = re.search(r"(?:NYLON|PA|POLYAMIDE)[\s_(-]*6(?![\d,./\s-]*6)", text)
    return bool(six_six) and not six_alone


def open_specy_truth(text):
    """The material a label names, by the protocol's rules; "" if it fits no material group."""
    upper = str(text).upper()
    if re.search("ARAMID|KEVLAR|NOMEX|PHENYLENE TEREPHTHALAMIDE", upper):
        return "aramid"
    group = material_group(text)
    if group == "PA":
        return "PA" if says_nylon_66(upper) else PA_OTHER
    return group


def kind_of(truth):
    """(how a material is scored, its relative). An unlisted group stops the run: the protocol must name it."""
    if truth == PA_OTHER:
        return RELATIVE, "PA"
    if truth in IN_LIBRARY:
        return IN, ""
    if truth in NOT_IN_LIBRARY:
        return OUT, ""
    raise ValueError(f"The protocol does not name the material {truth!r}")


def groups_in(text):
    """Every material group a label fits, not only the first."""
    upper = str(text).upper()
    return [group for group, patterns in GROUP_RULES if any(re.search(p, upper) for p in patterns)]


def is_doubtful(text):
    """True if a label may be wrong or describe a mixture (PROTOCOL.md, 'Doubtful labels')."""
    upper = str(text).upper()
    first = material_group(text)
    if re.search(DOUBT_WORDS, upper) or ("COPOLYMER" in upper and first not in COPOLYMERS):
        return True
    return bool(set(groups_in(text)) - {first} - NESTED.get(first, set()))


def fibre_truth(fibre_type, subtype):
    """(truth, kind, relative) of a fibre. An unlisted fibre stops the run."""
    found = FIBRE_TRUTH.get((fibre_type, subtype)) or FIBRE_TRUTH.get((fibre_type, ""))
    if found is None:
        raise ValueError(f"The protocol does not name the fibre {fibre_type!r} / {subtype!r}")
    return found


def read_fibres(path):
    """Every fibre spectrum. Replica 1 of each sample is the main test; the others are the repeatability check."""
    table = pd.read_csv(path)
    columns = [c for c in table.columns if c.replace(".", "").isdigit()]
    wn = np.array(columns, float)
    order = np.argsort(wn)
    wn = wn[order]
    values = table[columns].to_numpy(float)[:, order]
    items = []
    for row, y in zip(table.itertuples(), values):
        subtype = "" if pd.isna(row.Subtype) else str(row.Subtype)
        truth, kind, relative = fibre_truth(row.Type, subtype)
        items.append(Item(f"{row.Sample_ID}#{row.Replica}", FIBRES, truth, kind, relative, row.Sample_ID,
                          "FasTEX-KCL", f"{row.Type} / {subtype}", False, "ATR", "%T", wn, y, int(row.Replica)))
    return items


def read_open_specy(path):
    """Every labelled FTIR spectrum of the Open Specy file, NIST's left out. Returns (items, what was left out)."""
    wn, X, metadata = openspecy.read_library_file(path)
    column = lambda *names: openspecy._column(metadata, *names).tolist()
    kinds = column("spectrum_type", "SpectrumType")
    identities = column("spectrum_identity", "SpectrumIdentity")
    polymers = column("polymer", "material")
    classes = column("material_class", "polymer_class", "Polymer.Category")
    contributors = column("organization", "Organization", "library_name")
    names = column("sample_name", "SpectrumID", "file_id")
    modes = column("instrument_mode")
    accessories = column("instrument_accessories")
    items, left_out = [], {"NIST": 0, "no material": 0, "Raman": 0}
    for i in range(X.shape[1]):
        if "RAMAN" in kinds[i].upper():
            left_out["Raman"] += 1
            continue
        if contributors[i].strip().lower() == NIST:
            left_out["NIST"] += 1
            continue
        described = " ".join(t for t in (polymers[i], identities[i], classes[i]) if t)
        truth = open_specy_truth(described)
        if not truth:
            left_out["no material"] += 1
            continue
        kind, relative = kind_of(truth)
        cluster = f"{contributors[i]}|{identities[i]}|{truth}"
        points = measured_points(wn, X[:, i])
        items.append(Item(names[i], OPEN_SPECY, truth, kind, relative, cluster, contributors[i], described[:80],
                          is_doubtful(described), openspecy.measuring_mode(f"{modes[i]} {accessories[i]}"), "A", *points))
    return items, left_out


def measured_points(wn, y):
    """Only the points that have a value, as the program's file reader keeps them: analyse() never sees a gap."""
    wn, y = np.asarray(wn, float), np.asarray(y, float)
    keep = np.isfinite(wn) & np.isfinite(y)
    return wn[keep], y[keep]


def read_openftir(path, library_names):
    """The OpenFTIR spectra that are not the library and whose material is stated. Returns (items, left out)."""
    table = pd.read_csv(path)
    wn = np.array(table.columns[1:], float)
    order = np.argsort(wn)
    wn = wn[order]
    items, left_out = [], {"the library itself": 0, "no stated material": 0}
    for name, y in zip(table.iloc[:, 0].astype(str), table.iloc[:, 1:].to_numpy(float)[:, order]):
        if name in library_names:
            left_out["the library itself"] += 1
        elif re.fullmatch(r"Sample \d+|Acrylic \w+", name):
            left_out["no stated material"] += 1
        else:
            truth = open_specy_truth(name.replace("GF-PVC043", "PVC"))        # 'PVC043' is not a whole word
            kind, relative = kind_of(truth) if truth else (OUT, "")           # no group: a material with no reference
            items.append(Item(name, OPENFTIR, truth or name.split()[0], kind, relative, name, "OpenFTIR", name, False,
                              "ATR", "A", wn, y))
    return items, left_out


def cluster_hash(cluster):
    return hashlib.sha256((SPLIT_SALT + cluster).encode("utf-8")).hexdigest()


def split_locked(items, share=LOCKED_SHARE):
    """The same items, with the locked set marked. It reads labels only, never a spectrum.

    Within each material, clusters are taken in hash order; one goes to the locked set if that keeps the locked share
    at or below the limit. So a cluster stays on one side, and a material with one big cluster is not lost to the test.
    """
    groups = {}
    for item in items:
        groups.setdefault(item.truth, {}).setdefault(item.cluster, []).append(item)
    locked = set()
    for clusters in groups.values():
        limit, taken = share * sum(len(c) for c in clusters.values()), 0
        for cluster in sorted(clusters, key=cluster_hash):
            size = len(clusters[cluster])
            if taken + size <= limit:
                taken += size
                locked.add(cluster)
    return [replace(item, locked=item.cluster in locked) for item in items]


def first_by_hash(items, number):
    """The first items in hash order: a fixed choice that uses no score."""
    return sorted(items, key=lambda item: cluster_hash(item.key))[:number]
