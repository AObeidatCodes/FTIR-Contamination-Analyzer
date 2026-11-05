"""
FTIR Contamination Analyzer - second-person review

Every exported report is entered in a register. A different person then reads the report and records a decision.

    append_report   enter an exported report in the register
    append_review   record a review
    read_reports    every report with its review, newest first
    reviewer_problem    why this person may not review this report ("" if they may)

The names come from what people type and the login from the computer, so a review shows who it says it is from: it is
not an electronic signature. On a shared login the row says so.

Short names used in this file:
    r = one Result    sha = SHA-256 checksum of a file

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import config
from .analysis import NO_MATCH, PROBABLE, WEAK
from .records import tidy_tool
from .spectrum_io import checksum, read_table

REPORT_HEADER = (
    "# Report register: one row per exported report, with the SHA-256 of its report.html. Rows are only added.\n"
)
REPORT_COLUMNS = ["exported_at", "analysed_by", "login", "tool", "spectra", "probable", "weak", "no_match", "report",
                  "report_sha256"]
REVIEW_HEADER = (
    "# Reviews: one row per second-person review of a report, identified by the SHA-256 of its report.html. "
    "Rows are only added.\n"
)
REVIEW_COLUMNS = ["reviewed_at", "reviewed_by", "login", "decision", "comment", "analysed_by", "analysed_login",
                  "same_login", "report", "report_sha256"]
WAITING, REVIEWED, MISSING, CHANGED = "waiting", "reviewed", "file not found", "file changed"


@dataclass(frozen=True)
class Review:
    """One recorded review."""

    time: str
    name: str
    login: str
    decision: str
    comment: str
    same_login: bool


@dataclass(frozen=True)
class Report:
    """One exported report, with its review if it has one."""

    time: str
    analysed_by: str
    login: str
    tool: str
    spectra: int
    probable: int
    weak: int
    no_match: int
    path: Path
    sha: str
    review: Review = None

    @property
    def state(self):
        """WAITING, REVIEWED, or why it cannot be reviewed. A report that changed after export cannot be."""
        if self.review is not None:
            return REVIEWED
        if not self.path.exists():
            return MISSING
        return WAITING if checksum(self.path) == self.sha else CHANGED


def _append(path, header, columns, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    if new_file:
        path.write_text(header, encoding="utf-8")
    pd.DataFrame([row], columns=columns).to_csv(path, mode="a", index=False, header=new_file)
    return path


def append_report(results, info, html_path, tool="", path=config.REPORT_LOG_FILE):
    """Enter an exported report in the register."""
    count = {v: sum(r.verdict == v for r in results) for v in (PROBABLE, WEAK, NO_MATCH)}
    return _append(path, REPORT_HEADER, REPORT_COLUMNS, {
        "exported_at": info["run_at"], "analysed_by": info.get("run_by_name", ""), "login": info["run_by"],
        "tool": tidy_tool(tool), "spectra": len(results), "probable": count[PROBABLE], "weak": count[WEAK],
        "no_match": count[NO_MATCH], "report": str(html_path), "report_sha256": checksum(html_path)})


def same_person(report, name, login):
    """True if the name, or without a name to compare the login, is the analyst's."""
    if report.analysed_by:
        return " ".join(name.split()).casefold() == report.analysed_by.casefold()
    return login.casefold() == report.login.casefold()


def reviewer_problem(report, name, login):
    """Why this person may not review this report; "" if they may."""
    if not " ".join(name.split()):
        return "your name"
    if same_person(report, name, login):
        return "a different person from the analyst"
    return ""


def append_review(report, signoff, path=config.REVIEW_LOG_FILE):
    """Record a review (records.make_signoff). The same person, or a changed report file, is refused."""
    problem = reviewer_problem(report, signoff["name"], signoff["login"])
    if problem:
        raise ValueError(f"A review needs {problem}.")
    if report.state != WAITING:
        raise ValueError(f"This report cannot be reviewed: {report.state}.")
    return _append(path, REVIEW_HEADER, REVIEW_COLUMNS, {
        "reviewed_at": signoff["signed_at"], "reviewed_by": signoff["name"], "login": signoff["login"],
        "decision": signoff["decision"], "comment": signoff.get("comment", ""), "analysed_by": report.analysed_by,
        "analysed_login": report.login, "same_login": "yes" if signoff["login"].casefold() == report.login.casefold() else "no",
        "report": str(report.path), "report_sha256": report.sha})


def read_reports(report_log, review_log):
    """Every report in the register, newest first, each with its latest review."""
    if not Path(report_log).exists():
        return []
    reviews = {}
    if Path(review_log).exists():
        for row in read_table(review_log, dtype=str).fillna("").to_dict("records"):
            reviews[row["report_sha256"]] = Review(row["reviewed_at"], row["reviewed_by"], row["login"], row["decision"],
                                                   row["comment"], row["same_login"] == "yes")
    reports = [Report(row["exported_at"], row["analysed_by"], row["login"], row["tool"], int(row["spectra"]),
                      int(row["probable"]), int(row["weak"]), int(row["no_match"]), Path(row["report"]),
                      row["report_sha256"], reviews.get(row["report_sha256"]))
               for row in read_table(report_log, dtype=str).fillna("").to_dict("records")]
    return list(reversed(reports))
