"""
FTIR Contamination Analyzer - the in-house library (references the lab adds itself)

A real lab finds contaminants that no published library has: its own gloves, pads,
greases, tapes, garments. When such a material has been identified by other means
(a known part, the supplier's material sheet, band reading, SEM-EDX), its spectrum can be
added here as an in-house reference. From then on, the program recognises it.

How it is stored (records/inhouse_library/):
    <name>_<code>.csv        the reference spectrum (absorbance as measured) with notes in its header
    library_changes.csv      append-only: every addition and removal, with who, when, why and the
                             checksums of the files. The current library is "replayed" from it, so
                             nothing is ever overwritten or deleted, and every change is traceable.

Adding is safe because the program first works out what the new reference would do to the
library (library.validation_impact): if it would make two materials impossible to tell
apart, the person is warned before anything is saved.

Short names used in this file:
    wn = wavenumbers    a = absorbance    who = login name of the person    row = one change
    y = a spectrum on the common grid    r = one Result

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .analysis import analyse
from .library import MaterialInfo, validation_impact, with_reference
from .records import current_user
from .spectrum_io import checksum, read_table

CHANGE_COLUMNS = ["time", "user", "action", "material", "file", "file_sha256", "mode", "category",
                  "fab_sources", "check_next", "confirmation", "notes", "source_file", "source_sha256", "reason"]
LOG_HEADER = ("# In-house library: every change, in order. Rows are only ever added; the current library\n"
              "# is the result of replaying them. action = add or remove.\n")


class InHouseLibrary:
    """The lab's own references, kept in one folder with an append-only change log."""

    def __init__(self, folder=None):
        self.folder = Path(folder or config.INHOUSE_DIR)
        self.log = self.folder / "library_changes.csv"

    # ------------------------------------------------------------------ reading
    def changes(self):
        """Every change ever made, oldest first (an empty table if there are none)."""
        if not self.log.exists():
            return pd.DataFrame(columns=CHANGE_COLUMNS)
        return read_table(self.log, dtype=str).fillna("")

    def active(self):
        """The references in the library now, as MaterialInfo (the last change per material decides)."""
        current = {}
        for row in self.changes().itertuples():
            if row.action == "add":
                current[row.material] = row
            elif row.action == "remove":
                current.pop(row.material, None)
        return [MaterialInfo(
            name=row.material, category=row.category or "In-house", source="In-house", licence="in-house data",
            contributor=row.user, mode=row.mode, original_name=row.source_file, origin="in-house",
            added_by=row.user, added_at=row.time, confirmation=row.confirmation, fab_sources=row.fab_sources,
            check_next=row.check_next, notes=row.notes, file=row.file, sha256=row.file_sha256)
            for row in current.values()]

    def names(self):
        return [entry.name for entry in self.active()]

    def spectrum(self, entry):
        """(wavenumbers, absorbance) of one in-house reference, as it was measured."""
        table = read_table(self.folder / entry.file)
        return table.iloc[:, 0].to_numpy(float), table.iloc[:, 1].to_numpy(float)

    # ------------------------------------------------------------------ changing
    def _append(self, row):
        self.folder.mkdir(parents=True, exist_ok=True)
        new = not self.log.exists()
        if new:
            self.log.write_text(LOG_HEADER, encoding="utf-8")
        pd.DataFrame([row], columns=CHANGE_COLUMNS).to_csv(self.log, mode="a", index=False, header=new)

    def add(self, name, wn, a, mode, category="In-house", fab_sources="", check_next="", confirmation="",
            notes="", source_path=None, who=None, existing=()):
        """Add one reference and return the file it was saved in.

        name must be new (not in `existing`, the names already in the whole library).
        wn, a: the spectrum as measured, in absorbance; mode: how it was measured.
        """
        name = " ".join(str(name).split())
        if not name:
            raise ValueError("Give the reference a name.")
        if name in existing or name in self.names():
            raise ValueError(f"'{name}' is already in the library. Choose another name.")
        wn, a = np.asarray(wn, float), np.asarray(a, float)
        keep = np.isfinite(wn) & np.isfinite(a)
        if keep.sum() < 50:
            raise ValueError("The spectrum has too few data points to be a reference.")
        who = who or current_user()
        now = datetime.now().astimezone().isoformat(timespec="seconds")

        # the spectrum file: a readable name plus a short code, so two similar names never collide
        slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:40] or "reference"
        code = hashlib.sha256(f"{name}{now}".encode()).hexdigest()[:6]
        path = self.folder / f"{slug}_{code}.csv"
        self.folder.mkdir(parents=True, exist_ok=True)
        order = np.argsort(wn[keep])
        notes_head = (f"# In-house reference: {name}\n# mode: {mode}\n# unit: absorbance\n"
                      f"# added by {who} on {now}\n"
                      + (f"# made from: {Path(source_path).name} (SHA-256 {checksum(source_path)})\n" if source_path else ""))
        body = pd.DataFrame({"wavenumber": wn[keep][order], "absorbance": a[keep][order]})
        path.write_text(notes_head + body.to_csv(index=False, float_format="%.6g"), encoding="utf-8")

        self._append({"time": now, "user": who, "action": "add", "material": name, "file": path.name,
                      "file_sha256": checksum(path), "mode": mode, "category": category,
                      "fab_sources": fab_sources, "check_next": check_next, "confirmation": confirmation,
                      "notes": notes, "source_file": Path(source_path).name if source_path else "",
                      "source_sha256": checksum(source_path) if source_path else "", "reason": ""})
        return path

    def remove(self, name, reason="", who=None):
        """Take a reference out of the library. Its file and its history stay (nothing is deleted)."""
        entry = next((e for e in self.active() if e.name == name), None)
        if entry is None:
            raise ValueError(f"'{name}' is not an in-house reference.")
        self._append({"time": datetime.now().astimezone().isoformat(timespec="seconds"), "user": who or current_user(),
                      "action": "remove", "material": name, "file": entry.file, "file_sha256": entry.sha256,
                      "mode": entry.mode, "category": entry.category, "fab_sources": "", "check_next": "",
                      "confirmation": "", "notes": "", "source_file": "", "source_sha256": "", "reason": reason})


def reference_notes(path):
    """Details a reference file may carry in its header, e.g. '# reference: ABS', '# category: ...'."""
    notes = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("#"):
            break
        key, _, value = line[1:].partition(":")
        if value:
            notes[key.strip().lower()] = value.strip()
    return notes


# ---------------------------------------------------------------------------- what a change does to the results
@dataclass(frozen=True)
class Change:
    """One result that is different after a library change."""

    sample: str
    before: str      # e.g. "Weak: PS (r 0.88)"
    after: str       # e.g. "Probable: ABS (r 0.99)"

    def __str__(self):
        return f"{self.before} -> {self.after}"


def describe(r):
    """A result in a few words, e.g. 'Probable: ABS (r 0.99)'."""
    return (f"{r.verdict.capitalize()}: {r.match} (r {r.r:.2f})" if r.has_match
            else f"No reliable match (best {r.best}, r {r.r:.2f})")


def reanalyse(results, library):
    """The same spectra, analysed again with another library (mode and its source are kept)."""
    return [analyse(r.spectrum, library, r.mode, r.mode_source, r.conflict) for r in results]


def changes_between(old, new):
    """The results whose verdict or match is different, as Change objects (same order as the list)."""
    return [Change(a.name, describe(a), describe(b)) for a, b in zip(old, new)
            if (a.verdict, a.match) != (b.verdict, b.match)]


def addition_preview(library, name, y, results=(), before=None):
    """Everything adding reference `name` (spectrum y on the grid) would do, BEFORE anything is saved:

        impact    the impostor test now and with the new reference, and the most similar existing one
        changes   which of the results on screen would get another verdict or match
    """
    impact = validation_impact(library, name, y, before)
    trial = with_reference(library, name, y)
    return impact, changes_between(list(results), reanalyse(results, trial))
