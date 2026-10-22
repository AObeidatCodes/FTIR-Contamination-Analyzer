"""
FTIR Contamination Analyzer - records (data integrity)

Three append-only records, kept as plain CSV files (the Records menu opens them as formatted
Excel sheets, see log_views.py):

    sample log   how each raw file was measured (ATR or transmission). Each row belongs to
                 one exact file, identified by its SHA-256 checksum, so the mode is never
                 written into the raw file itself (that would change the raw data).
    audit log    one row per analysed spectrum per report: which file, which result,
                 when, who, which program version, which library.
    signatures   one row per signed report: who signed, when, the decision and the comment,
                 and the SHA-256 of the report file they signed.

Rows are only ever added, never changed or deleted (ALCOA: attributable, legible,
contemporaneous, original, accurate).

Short names used in this file:
    sha = SHA-256 checksum    who = login name of the person    r = one Result

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import getpass
import hashlib
import platform
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import scipy

from . import __version__, config
from .spectrum_io import checksum, read_mode_note, read_table

SAMPLE_LOG_HEADER = (
    "# Sample log: how each raw file was measured. Written when the sample is measured (or\n"
    "# later by the person running the analysis), never inside the raw file itself. Each row\n"
    "# belongs to one exact file, identified by its SHA-256 checksum. Rows are only added.\n"
)
SAMPLE_LOG_COLUMNS = ["file", "sha256", "mode", "recorded_by", "recorded_at", "note"]
SIGNATURE_HEADER = (
    "# Signatures: one row per signed report. The person states that they looked at the raw spectra\n"
    "# and agree with the conclusions, or noted their changes. report_sha256 identifies the exact\n"
    "# report file that was signed. Rows are only added.\n"
)
SIGNATURE_COLUMNS = ["signed_at", "signed_by", "login", "decision", "comment", "report", "report_sha256", "spectra"]
DECISIONS = {"accept": "Accepted", "accept with changes": "Accepted with changes", "re-measure": "Re-measure"}


@dataclass(frozen=True)
class ModeInfo:
    """How one file was measured, and how we know."""

    mode: str            # "ATR", "transmission" or "unknown"
    source: str          # where the answer came from, shown in the report
    conflict: str = ""   # "" or a description of a disagreement between the file and the log


def readable_time(stamp, with_zone=False):
    """A recorded time as people write it: '2026-10-20T16:50:00+02:00' -> '20 Oct 2026, 16:50'.

    Only for showing; the records keep the exact original. with_zone=True adds '(UTC+02:00)'.
    A date alone gives '20 Oct 2026'; anything that is not a time is returned as it is.
    """
    text = str(stamp or "").strip()
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return text
    if len(text) <= 10:                                                 # a date without a time
        return f"{moment.day} {moment:%b %Y}"
    shown = f"{moment.day} {moment:%b %Y, %H:%M}"
    if with_zone and moment.utcoffset() is not None:
        minutes = int(moment.utcoffset().total_seconds() // 60)
        sign = "+" if minutes >= 0 else "-"
        shown += f" (UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d})"
    return shown


def current_user():
    """The login name of the person running the program (for 'recorded by' and 'run by')."""
    try:
        return getpass.getuser()
    except Exception:                       # some systems have no login name available
        return "unknown user"


class SampleLog:
    """The sample log file: look up a file's mode by checksum, or record a new answer."""

    def __init__(self, path=config.SAMPLE_LOG_FILE):
        self.path = Path(path)

    def entries(self):
        """{sha256: (mode, recorded_by, recorded_at)}. If a file was recorded twice, the latest row counts."""
        if not self.path.exists():
            return {}
        table = read_table(self.path, dtype=str).fillna("")     # everything as text
        return {row.sha256: (row.mode, row.recorded_by, row.recorded_at) for row in table.itertuples()}

    def record(self, file_path, mode, who=None, note=""):
        """Add one row; earlier rows are never changed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = pd.DataFrame([{"file": Path(file_path).name, "sha256": checksum(file_path), "mode": mode,
                             "recorded_by": who or current_user(), "recorded_at": date.today().isoformat(),
                             "note": note}], columns=SAMPLE_LOG_COLUMNS)
        new_file = not self.path.exists()
        if new_file:
            self.path.write_text(SAMPLE_LOG_HEADER, encoding="utf-8")         # a new log starts with its explanation
        row.to_csv(self.path, mode="a", index=False, header=new_file)          # mode="a": append, never overwrite


def known_mode(file_path, sample_log):
    """The mode of one file if it is already known (file note, then sample log), else None.

    The instrument's own note in the file wins. If the file and the log disagree, the
    file is used and the disagreement is reported as a conflict for a person to check.
    """
    note = read_mode_note(file_path)
    entry = sample_log.entries().get(checksum(file_path))                     # None if the file is not logged
    if note:
        conflict = ""
        if entry and entry[0] != note:
            conflict = f"file says {note}, sample log says {entry[0]}: check which is right"
        return ModeInfo(note, "file note", conflict)
    if entry:
        return ModeInfo(entry[0], f"sample log, recorded by {entry[1]} on {entry[2]}")
    return None


def resolve_modes(file_paths, sample_log, ask=None):
    """{path: ModeInfo} for every file, before any analysis starts.

    `ask` is a function that receives the list of files with no known mode and returns
    {path: mode} (the window shows a dialog, the command line asks in the terminal).
    Every real answer is saved in the sample log with who and when, so each file is asked
    once. "Don't know" is not saved, so the question comes back next time.
    Without `ask`, or for files left unanswered, the mode is "unknown".
    """
    result, missing = {}, []
    for path in file_paths:
        info = known_mode(path, sample_log)
        if info:
            result[path] = info
        else:
            missing.append(path)                                               # ask later, all at once

    answers = ask(missing) if (missing and ask) else {}
    who = current_user()
    for path in missing:
        mode = answers.get(path)
        if mode in ("ATR", "transmission"):                                    # a real answer: save it
            sample_log.record(path, mode, who, note="entered when running the analysis")
            result[path] = ModeInfo(mode, f"entered by {who}, saved in the sample log")
        elif mode == "unknown":                                                # "don't know": not saved
            result[path] = ModeInfo("unknown", f"{who} did not know; not saved, so asked again next time")
        else:
            result[path] = ModeInfo("unknown", "not in the file or the sample log")
    return result


def code_fingerprint():
    """SHA-256 over all program files: proves exactly which code made a report (works without git)."""
    digest = hashlib.sha256()
    for path in sorted(config.PACKAGE_DIR.glob("*.py")):                       # every module, in a fixed order
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_info(library, validation, name=""):
    """The facts at the top of every report: when, who, which program, which library, validation.

    name: the full name of the person ("Ali Obeidat"); the login name is always recorded too.
    """
    return {
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_by": current_user(),
        "run_by_name": " ".join(str(name).split()),
        "program": f"FTIR Contamination Analyzer {__version__}",
        "code_sha256": code_fingerprint(),
        "software": (f"Python {platform.python_version()}, numpy {np.__version__}, "
                     f"pandas {pd.__version__}, scipy {scipy.__version__}"),
        "library": f"{library.name}, all compared in {library.mode} mode",
        "library_sha256": library.sha256,
        "validation": validation,
    }


def append_audit_log(results, info, path=config.AUDIT_LOG_FILE):
    """Add one row per analysed spectrum to the audit log. Earlier rows are never changed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = pd.DataFrame([{
        "run_at": info["run_at"], "run_by": info["run_by"], "program": info["program"],
        "code_sha256": info["code_sha256"][:16], "library_sha256": info["library_sha256"][:16],
        "file": r.spectrum.path.name, "file_sha256": r.spectrum.sha256, "sample": r.name,
        "mode": r.mode if r.mode == r.compared_as else f"{r.mode} (compared as {r.compared_as})",
        "verdict": r.verdict, "match": r.match, "r": round(r.r, 3),
        "flags": "; ".join(label for label, _ in r.flags),
    } for r in results])
    rows.to_csv(path, mode="a", index=False, header=not path.exists())        # append; header only for a new log
    return path


def who_text(name, login):
    """'Ali Obeidat (aliio)', or just the login name when no full name was given."""
    return f"{name} ({login})" if name and name != login else login


def append_signature(signoff, report_path, n_spectra, path=config.SIGNATURE_LOG_FILE):
    """Record that a report was signed. Earlier rows are never changed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([{
        "signed_at": signoff["signed_at"], "signed_by": signoff["name"], "login": signoff["login"],
        "decision": signoff["decision"], "comment": signoff.get("comment", ""), "report": str(report_path),
        "report_sha256": checksum(report_path), "spectra": n_spectra,
    }], columns=SIGNATURE_COLUMNS)
    new_file = not path.exists()
    if new_file:
        path.write_text(SIGNATURE_HEADER, encoding="utf-8")
    row.to_csv(path, mode="a", index=False, header=new_file)
    return path


def make_signoff(name, decision, comment=""):
    """A sign-off, ready for the report: who (full name and login), when, the decision and the comment."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {', '.join(DECISIONS)}")
    name = " ".join(str(name).split())
    if not name:
        raise ValueError("A report is signed with a name.")
    return {"name": name, "login": current_user(), "decision": decision, "comment": " ".join(str(comment).split()),
            "signed_at": datetime.now().astimezone().isoformat(timespec="seconds")}
