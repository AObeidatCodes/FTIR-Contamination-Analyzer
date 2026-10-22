"""
FTIR Contamination Analyzer - start-up

    python -m ftir_analyzer                          open the application (asks for spectrum files)
    python -m ftir_analyzer FILE_OR_FOLDER ...       open the application with these spectra
    python -m ftir_analyzer --report OUT FILES ...   no window: analyse and write the report into OUT
    python -m ftir_analyzer --version                show the version

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import argparse
import sys
from pathlib import Path

from . import __author__, __title__, __version__, config


def expand(items):
    """Turn a mix of files and folders into a list of spectrum files."""
    from .spectrum_io import find_spectrum_files
    paths = []
    for item in map(Path, items):
        paths.extend(find_spectrum_files(item) if item.is_dir() else [item])
    return paths


def ask_in_terminal(paths):
    """Ask in the terminal how files were measured (used by --report when a person is at the keyboard)."""
    print(f"{len(paths)} file(s) do not say how they were measured:")
    for path in paths:
        print(f"   {path.name}")
    choices = {"1": "ATR", "2": "transmission", "3": "unknown"}
    while True:                                                        # keep asking until the answer is valid
        answer = input("All of them were measured by: 1 = ATR, 2 = transmission, 3 = don't know: ").strip()
        if answer in choices:
            return {path: choices[answer] for path in paths}


def make_report(out_dir, items, mode=None):
    """Analyse spectra without a window and write the report. Returns the exit code (0 = fine)."""
    from .analysis import analyse
    from .library import impostor_test, load_library
    from .records import SampleLog, resolve_modes, run_info
    from .report import results_table, write_report
    from .spectrum_io import SpectrumFileError, read_spectra

    paths = expand(items)
    if not paths:
        print("No spectrum files given.", file=sys.stderr)
        return 2

    library = load_library()
    validation = impostor_test(library)
    if mode:                                                           # --mode answers for every file without a mode
        ask = lambda missing: {p: mode for p in missing}  # noqa: E731
    else:
        ask = ask_in_terminal if sys.stdin.isatty() else None          # nobody to ask -> "unknown"
    modes = resolve_modes(paths, SampleLog(), ask=ask)

    results = []
    for path in paths:
        info = modes[path]
        try:
            results.extend(analyse(s, library, info.mode, info.source, info.conflict) for s in read_spectra(path))
        except SpectrumFileError as error:
            print(f"skipped: {error}", file=sys.stderr)
    if not results:
        print("No spectrum could be analysed.", file=sys.stderr)
        return 1

    html_path = write_report(results, library, run_info(library, validation), out_dir)
    table = results_table(results)[["sample", "mode", "verdict", "match", "r", "flags"]]
    print(table.to_string(index=False, float_format="%.2f"))
    print(f"\nreport -> {html_path}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ftir_analyzer",
        description=f"{__title__}: identify contamination from FTIR spectra. By {__author__}.")
    parser.add_argument("files", nargs="*", help="spectrum files or folders to open")
    parser.add_argument("--report", metavar="OUT_DIR",
                        help="no window: analyse FILES and write report.html / report.csv into OUT_DIR")
    parser.add_argument("--mode", choices=config.MODES,
                        help="with --report: measuring mode for files that do not state it")
    parser.add_argument("--no-dialog", action="store_true",
                        help="do not open the file chooser when the application starts")
    parser.add_argument("--version", action="version", version=f"{__title__} {__version__} by {__author__}")
    args = parser.parse_args(argv)

    if args.report:
        return make_report(Path(args.report), args.files, args.mode)

    try:
        from .gui import run_app                                       # imported here: --report needs no window
    except ImportError as error:                                       # most likely PySide6 is not installed
        print(f"The window could not start ({error}).\n"
              "Install the required packages first:  python -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    return run_app(expand(args.files), ask_for_files=not args.no_dialog)


if __name__ == "__main__":
    sys.exit(main())
