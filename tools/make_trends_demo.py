"""
Writes examples/trends_demo/: a made-up audit log and tool log, so the Trends page can be seen without real lab data.

Every sample here is invented. The file checksums start with 'demo', and the same seed gives the same files.

    python tools/make_trends_demo.py

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ftir_analyzer.processing import GRID  # noqa: E402
from ftir_analyzer.unknowns import LOG_HEADER, save_fingerprints  # noqa: E402

FOLDER = ROOT / "examples" / "trends_demo"
NOTE = "# Demo data: every sample in this file is made up.\n"
TOOLS = ("Wet bench 2", "Etch 3", "CMP 1", "Litho track 1")
MATERIALS = ("PE (high density)", "PP", "PET", "PVC", "PU", "PMMA", "Nylon 6,6", "PS")
AUDIT = ("run_at", "run_by", "program", "code_sha256", "library_sha256", "file", "file_sha256", "sample", "mode", "verdict",
         "match", "r", "flags")
TOOL_LOG = ("file_sha256", "sample", "file", "tool", "recorded_by", "recorded_at")
START = datetime(2026, 1, 5, 9, 0)
# (days after START, tool, material, verdict): the events that make the repeats on the page
EVENTS = ((70, "Wet bench 2", "PET", "probable"), (74, "Wet bench 2", "PET", "probable"), (79, "Wet bench 2", "PET", "weak"),
          (83, "Wet bench 2", "PET", "probable"), (60, "Etch 3", "PU", "probable"), (66, "Etch 3", "PU", "probable"),
          (82, "Etch 3", "PU", "probable"))
# (days after START, tool, band centres of a made-up material): unknown samples that look alike
UNKNOWN = ((58, "Etch 3", (1110, 1735, 2920)), (63, "Etch 3", (1110, 1735, 2920)), (69, "Etch 3", (1110, 1735, 2920)),
           (75, "CMP 1", (1110, 1735, 2920)), (81, "Etch 3", (1110, 1735, 2920)), (64, "Wet bench 2", (880, 1450, 3300)),
           (72, "Wet bench 2", (880, 1450, 3300)), (80, "Wet bench 2", (880, 1450, 3300)))


def spectrum(centres, noise):
    """A made-up spectrum: bands at these places, and a little noise so that no two are the same."""
    return sum(np.exp(-((GRID - c) / 22) ** 2) for c in centres) + noise.normal(0, 0.002, GRID.size)


def main():
    rng = random.Random(20261105)
    noise = np.random.default_rng(20261105)
    rows = [(day, tool, material, verdict, tuple(rng.randrange(800, 3600) for _ in range(4)))
            for day, tool, material, verdict in EVENTS]
    rows += [(day, tool, "-", "no reliable match", centres) for day, tool, centres in UNKNOWN]
    for _ in range(46):
        verdict = rng.choices(("probable", "weak", "no reliable match"), (6, 3, 2))[0]
        material = rng.choices(MATERIALS, (9, 7, 2, 4, 2, 3, 2, 1))[0]
        tool = rng.choice(TOOLS) if rng.random() > 0.08 else ""
        centres = tuple(rng.randrange(800, 3600) for _ in range(4))     # a sample that looks like no other
        rows.append((rng.randrange(0, 84), tool, material, verdict, centres))
    rows.sort(key=lambda row: row[0])

    FOLDER.mkdir(parents=True, exist_ok=True)
    prints = FOLDER / "unknown_fingerprints.csv"
    prints.unlink(missing_ok=True)
    unknown = []
    with open(FOLDER / "audit_log.csv", "w", encoding="utf-8", newline="") as audit, \
            open(FOLDER / "tool_log.csv", "w", encoding="utf-8", newline="") as tools:
        audit.write(NOTE)
        tools.write(NOTE)
        audit_rows, tool_rows = csv.writer(audit), csv.writer(tools)
        audit_rows.writerow(AUDIT)
        tool_rows.writerow(TOOL_LOG)
        for i, (day, tool, material, verdict, centres) in enumerate(rows, start=1):
            when = (START + timedelta(days=day, minutes=7 * i)).isoformat() + "+00:00"
            sample, sha = f"Demo sample {i:03d}", f"demo{i:04d}"
            match = "-" if verdict == "no reliable match" else material
            r = {"probable": 0.97, "weak": 0.82, "no reliable match": 0.41}[verdict]
            audit_rows.writerow((when, "demo", "Demo data", "demo", "demo", f"{sample}.csv", sha, sample, "ATR", verdict, match, r, ""))
            if tool:
                tool_rows.writerow((sha, sample, f"{sample}.csv", tool, "demo", when[:10]))
            if verdict != "probable":
                unknown.append(SimpleNamespace(verdict=verdict, name=sample, compared=spectrum(centres, noise),
                                               spectrum=SimpleNamespace(sha256=sha, path=Path(""))))
    save_fingerprints(unknown, prints)
    prints.write_text(NOTE + prints.read_text(encoding="utf-8").removeprefix(LOG_HEADER), encoding="utf-8")
    print(len(rows), "made-up samples written to", FOLDER)


if __name__ == "__main__":
    main()
