"""
FTIR Contamination Analyzer - trends from the records

Reads the audit log and the tool log, and works out what keeps coming back. Nothing here writes to a record, and
nothing here changes a verdict.

    read_samples   every exported sample, once
    in_period      the samples of the last days
    ranked         materials or tools, most common first, with a running total
    repeats        the same material on the same tool, often enough in a short enough time

A sample is one spectrum of one exact file. Exporting it again adds a row to the audit log, but it stays one sample:
it keeps the day it first appeared and takes its latest result.

Short names used in this file:
    s = one Sample    sha = SHA-256 checksum of a file

Author : Ali Obeidat
Version: 2.0.0
License: MIT (see LICENSE)
"""

from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config
from .analysis import NO_MATCH, PROBABLE, WEAK
from .records import tidy_tool
from .spectrum_io import read_table

NOT_RECORDED = "Not recorded"
NO_MATCH_NAME = "No reliable match"
UNNAMED = (NOT_RECORDED, NO_MATCH_NAME)                    # these stay at the end of a ranking


@dataclass(frozen=True)
class Sample:
    """One exported sample."""

    sha: str            # checksum of the file
    name: str           # the sample (spectrum) name
    day: date           # the day it first appeared in the audit log
    verdict: str        # its latest verdict
    material: str       # its latest match, or NO_MATCH_NAME
    tool: str           # the tool or area, or NOT_RECORDED

    @property
    def one_material(self):
        """True if the verdict names one material: a tie and 'no reliable match' cannot make a repeat."""
        return self.verdict in (PROBABLE, WEAK) and " or " not in self.material


@dataclass(frozen=True)
class Rank:
    """One row of a ranking."""

    name: str
    probable: int
    weak: int
    none: int
    running: float      # the share of all samples, down to and including this row

    @property
    def total(self):
        return self.probable + self.weak + self.none


@dataclass(frozen=True)
class Repeat:
    """The same material on the same tool, often enough in a short enough time."""

    tool: str
    material: str
    samples: int
    first: date
    last: date


def read_tools(path):
    """{(sha, sample): tool}. If a sample was recorded twice, the latest row counts."""
    if not Path(path).exists():
        return {}
    table = read_table(path, dtype=str).fillna("")
    return {(row.file_sha256, row.sample): tidy_tool(row.tool) for row in table.itertuples()}


def known_tools(path):
    """Every tool or area recorded so far, one spelling of each, for the export sheet."""
    latest = {tool.casefold(): tool for tool in read_tools(path).values() if tool}
    return sorted(latest.values(), key=str.casefold)


def _day(text):
    try:
        return datetime.fromisoformat(str(text)).date()
    except ValueError:
        return None


def read_samples(audit_log, tool_log):
    """Every exported sample once, oldest first. Rows without a date or a checksum are left out."""
    if not Path(audit_log).exists():
        return []
    tools = read_tools(tool_log)
    spelling = {tool.casefold(): tool for tool in tools.values() if tool}   # 'etch 3' and 'Etch 3' are one tool
    first, latest = {}, {}
    for row in read_table(audit_log, dtype=str).fillna("").itertuples():
        day, key = _day(row.run_at), (row.file_sha256, row.sample)
        if day is None or not row.file_sha256:
            continue
        first[key] = min(day, first.get(key, day))
        latest[key] = row                                              # rows are in time order: the last one counts
    samples = []
    for key, row in latest.items():
        tool = tools.get(key, "")
        samples.append(Sample(key[0], key[1], first[key], row.verdict,
                              NO_MATCH_NAME if row.verdict == NO_MATCH else row.match,
                              spelling.get(tool.casefold(), NOT_RECORDED)))
    return sorted(samples, key=lambda s: s.day)


def demo_samples(folder=config.TRENDS_DEMO_DIR, today=None):
    """The made-up samples, moved so that the newest one is today: a demo must not age out of 'the last 30 days'."""
    samples = read_samples(Path(folder) / "audit_log.csv", Path(folder) / "tool_log.csv")
    if not samples:
        return []
    shift = (today or date.today()) - samples[-1].day
    return [replace(s, day=s.day + shift) for s in samples]


def in_period(samples, days, today=None):
    """The samples of the last `days` days, today included; days 0 or None: all of them."""
    if not days:
        return list(samples)
    start = (today or date.today()) - timedelta(days=days - 1)
    return [s for s in samples if s.day >= start]


def ranked(samples, attribute):
    """[Rank], most common first, by 'material' or 'tool'. Rows with no name stay last, as they are not a finding."""
    counts = {}
    for s in samples:
        row = counts.setdefault(getattr(s, attribute), [0, 0, 0])
        row[0 if s.verdict == PROBABLE else 1 if s.verdict == WEAK else 2] += 1
    order = sorted(counts, key=lambda name: (name in UNNAMED, -sum(counts[name]), name.casefold()))
    ranks, seen = [], 0
    for name in order:
        seen += sum(counts[name])
        ranks.append(Rank(name, *counts[name], seen / len(samples)))
    return ranks


def repeats(samples, count=config.REPEAT_COUNT, days=config.REPEAT_DAYS):
    """[Repeat], newest first: at least `count` samples of one material on one tool within `days` days."""
    groups = {}
    for s in samples:
        if s.tool != NOT_RECORDED and s.one_material:
            groups.setdefault((s.tool, s.material), []).append(s.day)
    found = []
    for (tool, material), seen in groups.items():
        seen.sort()
        worst = None                                                    # the fullest stretch of `days` days
        for start, day in enumerate(seen):
            stop = bisect_right(seen, day + timedelta(days=days - 1))
            if stop - start >= count and (worst is None or stop - start >= worst[0]):
                worst = (stop - start, day, seen[stop - 1])
        if worst:
            found.append(Repeat(tool, material, *worst))
    return sorted(found, key=lambda r: (r.last, r.samples), reverse=True)
