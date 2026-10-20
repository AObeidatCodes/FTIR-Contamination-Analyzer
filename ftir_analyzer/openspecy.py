"""
FTIR Contamination Analyzer - the Open Specy library (optional, "extended" mode)

Open Specy (Cowger et al. 2021, CC BY 4.0) is a large open library of FTIR and Raman
spectra of plastics, natural materials and minerals. The program can use part of it as
extra references, so that more kinds of samples can be identified:

    1. get the library file
         download   from Open Specy's public storage (OSF, project x7dpz) on this computer, or
         import     a file downloaded by hand (an Open Specy .rds / .RData library file)
       The "nobaseline" library is used: baseline-corrected absorbance spectra, comparable
       with the program's own references. (The "derivative" library holds processed
       derivative spectra, which cannot be compared with absorbance, so it is refused.)
    2. keep only what a fab is likely to see: FTIR spectra (no Raman), in the material
       classes of fab contaminations (gloves, wipes, seals, fluoropolymers, silicones,
       resins, fibres, silica and other minerals ...), at most 3 per material
    3. validate: every reference is compared with every other one; a spectrum that could be
       confused with a DIFFERENT material (r >= 0.95) is left out, until none is left, so the
       extended library passes the impostor test. Each left-out spectrum is listed with why.
    4. save it in records/openspecy/ with a report; the window can then switch between the
       shipped library ("Fab essentials") and the extended one.

The original files are never changed. Every reference keeps its Open Specy identity and the
CC BY 4.0 licence, and the reports cite Open Specy.

Short names used in this file:
    wn = wavenumbers    X = spectra (one column per spectrum)    md = metadata (one row per spectrum)
    y = a spectrum on the common grid    r = a Pearson r    entry = one prepared reference (a dict)

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .processing import GRID, fingerprint, on_grid
from .spectrum_io import checksum

OSF_NODE = "x7dpz"                                       # Open Specy's library project on OSF
OSF_FILES = "https://api.osf.io/v2/nodes/{node}/files/osfstorage/"
PREFERRED = ["medoid_nobaseline", "mediod_nobaseline", "nobaseline"]   # small and representative first
LICENCE = "CC BY 4.0"
CITATION = ("Cowger, W., Steinmetz, Z., Gray, A., Munno, K., Lynch, J., Hapich, H., Primpke, S., De Frond, H., "
            "Rochman, C., Herodotou, O. (2021). Microplastic Spectral Classification Needs an Open Source "
            "Community: Open Specy to the Rescue! Analytical Chemistry 93(21), 7543-7548.")
PER_GROUP = 3                                            # at most this many spectra of one material

# Which fab category a material class belongs to (first match wins); classes that match none are left out.
CATEGORY_RULES = [
    ("Cleanroom consumables", [r"\bNITRILE\b", "LATEX", "ISOPRENE", "POLYESTER", "CELLULOSE", "PAPER",
                               "VINYL CHLORIDE"]),
    ("Equipment & fixtures", ["FLUORO", "PTFE", "KETONE", "PEEK", "ACETAL", "OXYMETHYLENE", "SULFONE", "SULFIDE",
                              "IMIDE", "ACRYLONITRILE BUTADIENE", "STYRENE.ACRYLONITRILE", "PHENYLENE",
                              "POLYCARBONATE"]),
    ("Adhesives, seals & lubricants", ["SILOXANE", "SILICONE", "EPOXY", "EPOXIDE", "PHENOXY", "ACRYLATE", "RUBBER",
                                       "BUTADIENE", "WAX", "PARAFFIN", "VINYL ACETATE"]),
    ("Litho & process residues", ["NOVOLAC", "PHENOL", "METHACRYLATE", "HYDROXYSTYRENE"]),
    ("CMP & cleaning", ["VINYL ALCOHOL", "SILICA", "PYRROLIDONE", "ACRYLAMIDE", "ACRYLIC ACID", "GLYCOL"]),
    ("People & clothing", ["COTTON", "WOOL", "SILK", "PROTEIN", "KERATIN", "HAIR", "ACRYLONITRILE", "AMIDE", "NYLON"]),
    ("Packaging", ["ETHYLENE", "PROPYLENE", "STYRENE", "TEREPHTHALATE", "OLEFIN", "ALKENE"]),
    ("Minerals & inorganics", ["QUARTZ", "SILICATE", "CALCITE", "CARBONATE", "GYPSUM", "SULFATE", "TALC", "KAOLIN",
                               "MICA", "CLAY", "OXIDE", "MINERAL"]),
]


def fab_category(text):
    """The fab category of a material class, or None if a fab is unlikely to see it."""
    text = str(text).upper()
    for category, words in CATEGORY_RULES:
        if any(re.search(word, text) for word in words):
            return category
    return None


# ---------------------------------------------------------------------------- getting the file
def _get_json(url, opener):
    with opener(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def list_osf_files(node=OSF_NODE, opener=urllib.request.urlopen, depth=2):
    """Every file in Open Specy's OSF project: [(name, size in bytes, download link)]."""
    files, pages = [], [OSF_FILES.format(node=node) + "?page%5Bsize%5D=100"]
    while pages:
        page = _get_json(pages.pop(0), opener)
        for item in page.get("data", []):
            attributes, links = item.get("attributes", {}), item.get("links", {})
            if attributes.get("kind") == "file":
                files.append((attributes.get("name", ""), attributes.get("size") or 0, links.get("download", "")))
            elif attributes.get("kind") == "folder" and depth > 0:
                related = item.get("relationships", {}).get("files", {}).get("links", {}).get("related", {})
                href = related.get("href") if isinstance(related, dict) else related
                if href:
                    pages.append(href)
        following = page.get("links", {}).get("next")
        if following:
            pages.append(following)
    return files


def choose_file(files):
    """The library file to use: the small 'medoid' nobaseline library if there is one."""
    rds = [f for f in files if f[0].lower().endswith((".rds", ".rdata", ".rda"))]
    for wanted in PREFERRED:
        for name, size, link in rds:
            if Path(name).stem.lower() == wanted:
                return name, size, link
    for name, size, link in rds:
        if "nobaseline" in name.lower():
            return name, size, link
    raise FileNotFoundError("No Open Specy 'nobaseline' library was found in the OSF project.")


def download(link, target, progress=None, opener=urllib.request.urlopen):
    """Download a file in pieces (so the window can show progress) and return its path."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with opener(link, timeout=60) as response, open(partial, "wb") as handle:
        total, done = int(response.headers.get("Content-Length") or 0), 0
        while True:
            piece = response.read(1 << 20)
            if not piece:
                break
            handle.write(piece)
            done += len(piece)
            if progress:
                progress(done >> 20, max(2, total >> 20), "Downloading the Open Specy library (MB)")
    partial.replace(target)
    return target


# ---------------------------------------------------------------------------- reading it
def read_library_file(path):
    """An Open Specy library file -> (wavenumbers, spectra as columns, metadata as rows)."""
    path = Path(path)
    if "deriv" in path.name.lower():
        raise ValueError("This is Open Specy's 'derivative' library: processed derivative spectra cannot be "
                         "compared with absorbance. Use the 'nobaseline' library instead.")
    try:
        import rdata                                                    # only needed for this feature
    except ImportError as error:
        raise ImportError("Reading Open Specy files needs the 'rdata' package: python -m pip install rdata") \
            from error
    if path.suffix.lower() == ".rds":
        obj = rdata.read_rds(path)
    else:
        found = rdata.read_rda(path)
        obj = next(iter(found.values()))
    if not isinstance(obj, dict) or not {"wavenumber", "spectra"} <= set(obj):
        raise ValueError(f"{path.name} is not an Open Specy library (it has no 'wavenumber' and 'spectra').")
    wn = np.asarray(obj["wavenumber"], float)
    spectra = obj["spectra"]
    if isinstance(spectra, pd.DataFrame):
        X = spectra.to_numpy(float)
    else:
        X = np.asarray(spectra, float)
        if X.shape[0] != len(wn) and X.shape[1] == len(wn):
            X = X.T
    metadata = obj.get("metadata")
    metadata = metadata.reset_index(drop=True) if isinstance(metadata, pd.DataFrame) else pd.DataFrame(index=range(X.shape[1]))
    return wn, X, metadata


def _column(metadata, *names):
    """The first metadata column that exists, matched without regard to case or '_' / '.'."""
    simple = {re.sub(r"[^a-z]", "", c.lower()): c for c in metadata.columns}
    for name in names:
        key = re.sub(r"[^a-z]", "", name.lower())
        if key in simple:
            return metadata[simple[key]].astype("string").fillna("")
    return pd.Series([""] * len(metadata), dtype="string")


def _display_name(text):
    text = " ".join(str(text).replace("_", " ").split())
    if text.isupper() and len(text) > 5:                                # 'POLY(ETHYLENE)' -> 'Poly(ethylene)'
        text = text.capitalize()
    return text[:44]


# ---------------------------------------------------------------------------- choosing and validating
def prepare(wn, X, metadata):
    """Keep the fab-relevant FTIR spectra and give each a name, a material group and a category.

    Returns (entries, skipped) where skipped counts what was left out and why.
    """
    from .library import material_group
    kind = _column(metadata, "spectrum_type", "SpectrumType")
    identity = _column(metadata, "spectrum_identity", "SpectrumIdentity", "sample_name")
    polymer = _column(metadata, "polymer")
    material_class = _column(metadata, "material_class", "polymer_class", "Polymer.Category")
    organisation = _column(metadata, "organization", "Organization")
    sample_id = _column(metadata, "sample_name", "SpectrumID", "file_id")
    skipped = {"Raman": 0, "not likely in a fab": 0, "too little data": 0, "more than 3 of one material": 0}
    entries, per_group, names = [], {}, set()
    for i in range(X.shape[1]):
        if kind[i] and "RAMAN" in kind[i].upper():
            skipped["Raman"] += 1
            continue
        described = " ".join(str(v) for v in (polymer[i], identity[i], material_class[i]) if v)
        category = fab_category(described)
        if category is None:
            skipped["not likely in a fab"] += 1
            continue
        y = on_grid(wn, X[:, i])
        if np.isfinite(y).sum() < 200 or np.nanmax(y) <= np.nanmin(y):
            skipped["too little data"] += 1
            continue
        group = material_group(described) or _display_name(material_class[i] or identity[i]).lower()
        if per_group.get(group, 0) >= PER_GROUP:
            skipped["more than 3 of one material"] += 1
            continue
        per_group[group] = per_group.get(group, 0) + 1
        base = _display_name(polymer[i] or identity[i] or material_class[i]) or f"Spectrum {i + 1}"
        name, k = f"{base} (Open Specy)", 2
        while name in names:
            name, k = f"{base} {k} (Open Specy)", k + 1
        names.add(name)
        low, high = np.nanmin(y), np.nanmax(y)
        entries.append({"name": name, "group": group, "category": category, "y": (y - low) / (high - low),
                        "original_name": str(identity[i] or polymer[i] or material_class[i]),
                        "spectrum_id": str(sample_id[i]), "contributor": str(organisation[i])})
    return entries, skipped


def curate(base_library, entries):
    """Leave out every Open Specy spectrum that could be confused with a DIFFERENT material.

    Two references of different materials must score below 'probable' (0.95) against each
    other, or a wrong 'probable' answer would be possible. Greedy: the spectrum involved in
    most such pairs goes first, until no pair is left. Returns (kept, dropped) where dropped
    is [(name, the material it was confused with, r)].
    """
    from .library import pearson
    base_names = list(base_library.spectra)
    prints = [base_library.fingerprint_of(n) for n in base_names] + [fingerprint(e["y"]) for e in entries]
    groups = [base_library.group_of(n) for n in base_names] + [e["group"] for e in entries]
    labels = base_names + [e["name"] for e in entries]
    n_base, n = len(base_names), len(labels)
    conflicts = {}                                                      # {index: [(other index, r)]}
    for i in range(n_base, n):
        for j in range(n):
            if j >= i and j >= n_base:
                continue
            if groups[i] == groups[j]:
                continue
            r = pearson(prints[i], prints[j])
            if r >= config.PROBABLE_R:
                conflicts.setdefault(i, []).append((j, r))
                if j >= n_base:
                    conflicts.setdefault(j, []).append((i, r))
    removed, dropped = set(), []
    while True:
        live = {i: [(j, r) for j, r in pairs if j not in removed] for i, pairs in conflicts.items() if i not in removed}
        live = {i: pairs for i, pairs in live.items() if pairs}
        if not live:
            break
        worst = max(live, key=lambda i: (len(live[i]), max(r for _, r in live[i])))
        partner, r = max(live[worst], key=lambda pair: pair[1])
        removed.add(worst)
        dropped.append((labels[worst], labels[partner], r))
    kept = [e for k, e in enumerate(entries, start=n_base) if k not in removed]
    return kept, dropped


# ---------------------------------------------------------------------------- keeping it
@dataclass
class ImportSummary:
    """What an import did, for the window and the report file."""

    source: str
    kept: int
    by_category: dict = field(default_factory=dict)
    skipped: dict = field(default_factory=dict)
    dropped: list = field(default_factory=list)          # [(name, confused with, r)]

    def text(self):
        lines = [f"Open Specy library imported from {self.source}",
                 f"{self.kept} reference spectra kept (FTIR, fab-relevant, validated)."]
        lines += [f"  {category}: {count}" for category, count in sorted(self.by_category.items())]
        left_out = {k: v for k, v in self.skipped.items() if v}
        if left_out:
            lines.append("Left out: " + ", ".join(f"{v} {k}" for k, v in left_out.items()) + ".")
        if self.dropped:
            lines.append(f"{len(self.dropped)} left out because they could be confused with another material:")
            lines += [f"  {name}  ~  {other}  (r = {r:.2f})" for name, other, r in self.dropped]
        return "\n".join(lines)


class OpenSpecyLibrary:
    """The converted Open Specy references, kept in records/openspecy/."""

    def __init__(self, folder=None):
        self.folder = Path(folder or config.RECORDS_DIR / "openspecy")
        self.spectra_file = self.folder / "openspecy_library.csv"
        self.index_file = self.folder / "openspecy_index.csv"
        self.report_file = self.folder / "import_report.txt"

    @property
    def installed(self):
        return self.spectra_file.exists() and self.index_file.exists()

    def files(self):
        return [f for f in (self.spectra_file, self.index_file) if f.exists()]

    def entries(self):
        """[(MaterialInfo, spectrum on the grid)] for every kept reference ([] if nothing is installed)."""
        from .library import MaterialInfo
        if not self.installed:
            return []
        table = pd.read_csv(self.spectra_file, comment="#")
        index = pd.read_csv(self.index_file, comment="#", dtype=str).fillna("")
        wn, sha = table.iloc[:, 0].to_numpy(float), checksum(self.spectra_file)
        out = []
        for row in index.itertuples():
            if row.name not in table.columns:
                continue
            info = MaterialInfo(name=row.name, category=row.category, source="Open Specy", licence=LICENCE,
                                contributor=row.contributor, mode="unknown", original_name=row.original_name,
                                origin="open specy", notes=f"Open Specy id {row.spectrum_id}",
                                file=self.spectra_file.name, sha256=sha, group=row.group)
            out.append((info, on_grid(wn, table[row.name].to_numpy(float))))
        return out

    def save(self, entries, summary):
        """Write the kept references, their index and the import report."""
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        head = (f"# Open Specy reference spectra ({LICENCE}), kept for fab use on {stamp}.\n"
                f"# Source: {summary.source}. Cite: {CITATION}\n")
        table = pd.DataFrame({"wavenumber": GRID, **{e["name"]: np.round(e["y"], 5) for e in entries}})
        self.spectra_file.write_text(head + table.to_csv(index=False), encoding="utf-8")
        index = pd.DataFrame([{k: e[k] for k in ("name", "group", "category", "original_name", "spectrum_id",
                                                 "contributor")} for e in entries],
                             columns=["name", "group", "category", "original_name", "spectrum_id", "contributor"])
        self.index_file.write_text(head + index.to_csv(index=False), encoding="utf-8")
        self.report_file.write_text(summary.text() + f"\n\nCite: {CITATION}\n", encoding="utf-8")


def import_library(path, base_library, folder=None, progress=None):
    """Read an Open Specy library file, keep the fab-relevant validated FTIR spectra, save them."""
    say = progress or (lambda *_: None)
    say(0, 1, "Reading the Open Specy library")
    wn, X, metadata = read_library_file(path)
    say(0, 1, "Choosing the fab-relevant FTIR spectra")
    entries, skipped = prepare(wn, X, metadata)
    known = {}                                                          # a material the shipped library has
    for name in base_library.spectra:                                   # keeps that reference's category
        known.setdefault(base_library.group_of(name), base_library.info_of(name).category)
    for e in entries:
        e["category"] = known.get(e["group"], e["category"])
    say(0, 1, "Validating them against every other reference")
    kept, dropped = curate(base_library, entries)
    by_category = {}
    for e in kept:
        by_category[e["category"]] = by_category.get(e["category"], 0) + 1
    summary = ImportSummary(Path(path).name, len(kept), by_category, skipped, dropped)
    OpenSpecyLibrary(folder).save(kept, summary)
    return summary


def download_and_import(base_library, folder=None, progress=None, opener=urllib.request.urlopen):
    """Find the nobaseline library on Open Specy's OSF project, download it and import it."""
    say = progress or (lambda *_: None)
    say(0, 1, "Looking up the Open Specy library")
    name, _, link = choose_file(list_osf_files(opener=opener))
    target = Path(folder or config.RECORDS_DIR / "openspecy") / "downloads" / name
    download(link, target, progress, opener)
    return import_library(target, base_library, folder, progress)
