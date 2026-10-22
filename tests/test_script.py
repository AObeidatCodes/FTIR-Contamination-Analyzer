"""
FTIR Contamination Analyzer - test of the run-as-code script (FTIR_Analyzer.py)

The script is run exactly as a user would run it from a terminal, with its settings
changed to: the demo spectra, ATR for files without a mode note, no browser.

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import os
import subprocess
import sys

import pytest

from ftir_analyzer import config

pytest.importorskip("plotly")
SCRIPT = config.PROJECT_DIR / "FTIR_Analyzer.py"


def run_script(tmp_path, extra=()):
    """Run a copy of the script with changed settings, the way a user runs it from a terminal."""
    text = SCRIPT.read_text(encoding="utf-8")
    for old, new in [('"use_demo_spectra": False', '"use_demo_spectra": True'),
                     ('"default_mode": None', '"default_mode": "ATR"'),
                     ('"open_report": True', '"open_report": False'),
                     ('"report_folder": "reports"', f'"report_folder": {str(tmp_path / "reports")!r}'), *extra]:
        assert old in text, f"setting not found: {old}"
        text = text.replace(old, new)
    copy = tmp_path / "FTIR_Analyzer.py"
    copy.write_text(text, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(config.PROJECT_DIR), FTIR_ANALYZER_RECORDS=str(tmp_path / "records"))
    run = subprocess.run([sys.executable, str(copy)], capture_output=True, text=True, env=env, timeout=300,
                         cwd=tmp_path, stdin=subprocess.DEVNULL)
    assert run.returncode == 0, run.stderr
    return run


def test_script_runs_from_start_to_end(tmp_path):
    run = run_script(tmp_path)
    assert "12 spectra analysed" in run.stdout
    assert "07_particle_on_filter: PROBABLE PE (high density)" in run.stdout
    assert list((tmp_path / "reports").glob("*/report.html"))


def test_script_shows_what_adding_a_reference_would_do(tmp_path):
    demo = config.EXAMPLES_DIR / "library_demo" / "ABS_reference_known_part.csv"
    run = run_script(tmp_path, [('"add_reference": None', f'"add_reference": {str(demo)!r}'),
                                ('"write_report": True', '"write_report": False'),
                                ('"show_figures": True', '"show_figures": False')])
    assert "Adding 'ABS'" in run.stdout and "Safe to add" in run.stdout
    assert "10_tool_cover_fragment_ATR: Weak: PS" in run.stdout and "Probable: ABS" in run.stdout
    assert not (tmp_path / "records" / "inhouse_library").exists()      # really_add is False: nothing saved
