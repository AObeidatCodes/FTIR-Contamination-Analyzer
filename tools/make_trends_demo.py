"""
Writes examples/trends_demo/: a made-up audit log and tool log, so the Trends page can be seen without real lab data.

Every sample here is invented. The file checksums start with 'demo', and the same seed gives the same files.

    python tools/make_trends_demo.py

Author : Ali Obeidat
License: MIT (see LICENSE)
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent / "examples" / "trends_demo"
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


def main():
    rng = random.Random(20261105)
    rows = [(day, tool, material, verdict) for day, tool, material, verdict in EVENTS]
    for _ in range(46):
        verdict = rng.choices(("probable", "weak", "no reliable match"), (6, 3, 2))[0]
        material = rng.choices(MATERIALS, (9, 7, 2, 4, 2, 3, 2, 1))[0]
        tool = rng.choice(TOOLS) if rng.random() > 0.08 else ""
        rows.append((rng.randrange(0, 84), tool, material, verdict))
    rows.sort(key=lambda row: row[0])

    FOLDER.mkdir(parents=True, exist_ok=True)
    with open(FOLDER / "audit_log.csv", "w", encoding="utf-8", newline="") as audit, \
            open(FOLDER / "tool_log.csv", "w", encoding="utf-8", newline="") as tools:
        audit.write(NOTE)
        tools.write(NOTE)
        audit_rows, tool_rows = csv.writer(audit), csv.writer(tools)
        audit_rows.writerow(AUDIT)
        tool_rows.writerow(TOOL_LOG)
        for i, (day, tool, material, verdict) in enumerate(rows, start=1):
            when = (START + timedelta(days=day, minutes=7 * i)).isoformat() + "+00:00"
            sample, sha = f"Demo sample {i:03d}", f"demo{i:04d}"
            match = "-" if verdict == "no reliable match" else material
            r = {"probable": 0.97, "weak": 0.82, "no reliable match": 0.41}[verdict]
            audit_rows.writerow((when, "demo", "Demo data", "demo", "demo", f"{sample}.csv", sha, sample, "ATR", verdict, match, r, ""))
            if tool:
                tool_rows.writerow((sha, sample, f"{sample}.csv", tool, "demo", when[:10]))
    print(len(rows), "made-up samples written to", FOLDER)


if __name__ == "__main__":
    main()
