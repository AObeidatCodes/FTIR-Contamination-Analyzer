# %%
"""
FTIR Contamination Analyzer - run it as code

The same analysis as the app, as one script. Open it in VS Code, Spyder or Jupyter and run it
cell by cell (each "# %%" is a cell) or all at once. No app window needed:

    1. the reference library is loaded and validated (impostor test)
    2. a file dialog asks which spectrum files to analyse
    3. files that do not say how they were measured: you are asked once (ATR / transmission)
    4. every spectrum is analysed and the results table is printed
    5. interactive figures: hover to read every value and the band name, zoom, pan, save as PNG
       (switch on "show_analytical_view" to see every step: raw -> absorbance -> fingerprint -> checks)
    6. the report (report.html + report.csv) is written and opened in the browser
    7. (optional) a reference is added to the in-house library: first you see what it would do
       (most similar reference, impostor test before -> after, which results would change)

How to run it:
    VS Code    open this file and click "Run Cell" above each # %%  (or "Run Python File")
    Spyder     open this file and press F5
    Terminal   python FTIR_Analyzer.py

Needs numpy, pandas, scipy, matplotlib and plotly:   pip install -r requirements.txt

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

# %%
# =========================================================================
# SETTINGS: change these, then run the script again
# =========================================================================
SETTINGS = {
    "files": [],                      # leave empty to choose with a file dialog, or list them,
                                      # e.g. ["examples/01_wipe_area_particle_ATR.csv"]
    "use_demo_spectra": False,        # True = analyse the twelve demo spectra in the examples folder
    "default_mode": None,             # for files that do not say how they were measured:
                                      # "ATR", "transmission", "unknown", or None = ask me
    "show_figures": True,             # one interactive figure per spectrum
    "show_analytical_view": False,    # True = also show every processing step for each spectrum
    "write_report": True,             # report.html + report.csv (+ a row in the audit log)
    "open_report": True,              # open the report in the browser when it is written
    "report_folder": "reports",       # where the reports go (next to this script)
    "library": "essentials",          # "essentials" = the shipped library; "extended" = also the Open Specy
                                      # references, if they were added in the app (Library > Open Specy...)
    "add_reference": None,            # a spectrum file to add to the in-house library, e.g.
                                      # "examples/library_demo/ABS_reference_known_part.csv"
    "really_add": False,              # False = only show what adding it would do; True = add it (if it is safe)
}

# %%
# =========================================================================
# IMPORTS
# =========================================================================
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    HERE = Path(__file__).resolve().parent          # the folder this script is in
except NameError:                                   # Jupyter / interactive window: there is no __file__
    HERE = Path.cwd()
sys.path.insert(0, str(HERE))                       # so Python finds the ftir_analyzer folder next to this file

import plotly.io as pio  # noqa: E402

from ftir_analyzer import __author__, __title__, __version__, config  # noqa: E402
from ftir_analyzer.analysis import analyse  # noqa: E402
from ftir_analyzer.analytical import analytical_steps  # noqa: E402
from ftir_analyzer.interactive import CONFIG as FIGURE_CONFIG  # noqa: E402
from ftir_analyzer.interactive import analytical_figure, result_figure  # noqa: E402
from ftir_analyzer.inhouse import InHouseLibrary, addition_preview, reference_notes  # noqa: E402
from ftir_analyzer.library import impostor_test, load_library, reference_on_grid  # noqa: E402
from ftir_analyzer.processing import absorbance  # noqa: E402
from ftir_analyzer.records import SampleLog, resolve_modes, run_info  # noqa: E402
from ftir_analyzer.report import results_table, write_report  # noqa: E402
from ftir_analyzer.spectrum_io import SpectrumFileError, find_spectrum_files, read_spectra  # noqa: E402


def in_notebook():
    """True in Jupyter, the VS Code interactive window or an IPython console (figures appear inline)."""
    try:
        from IPython import get_ipython
        return get_ipython() is not None
    except ImportError:
        return False


def show(fig):
    """Show an interactive figure inline (Jupyter / VS Code), or in the browser; if neither works, say so."""
    try:
        try:
            fig.show(config=FIGURE_CONFIG)
        except ValueError:                          # inline figures need the 'nbformat' package
            print("  (inline figures need:  pip install nbformat   -> opening the figure in the browser instead)")
            fig.show(config=FIGURE_CONFIG, renderer="browser")
    except Exception as error:                      # e.g. no browser on this computer: carry on without it
        print(f"  (the figure could not be shown here: {error}. The report contains every figure.)")


INTERACTIVE = in_notebook()
if not INTERACTIVE:
    pio.renderers.default = "browser"               # plain terminal: figures open in the browser

print(f"{__title__} {__version__}, by {__author__}")

# %%
# =========================================================================
# 1. LOAD AND VALIDATE THE REFERENCE LIBRARY
# =========================================================================
library = load_library(extended=SETTINGS["library"] == "extended")
validation = impostor_test(library)
print(f"\n--- 1. Library: {library.name}, compared in {library.mode} mode")
print(f"  -> Impostor test: the best WRONG match scores {validation.score:.2f} "
      f"({validation.material} -> {validation.impostor}). "
      + ("Below 0.95: the verdict rule is valid." if validation.passed else "WARNING: re-validate the thresholds!"))

# %%
# =========================================================================
# 2. CHOOSE THE SPECTRUM FILES
# =========================================================================


def choose_files():
    """Open a file dialog (tkinter) and return the chosen files."""
    import tkinter as tk
    from tkinter import filedialog
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)     # sharp dialog on high-resolution Windows screens
    except Exception:
        pass                                        # not Windows: nothing to do
    root = tk.Tk()
    root.withdraw()                                 # no empty main window, only the dialog
    root.attributes("-topmost", True)               # the dialog comes to the front
    chosen = filedialog.askopenfilenames(
        title="Choose one or more FTIR spectrum files", initialdir=str(config.EXAMPLES_DIR),
        filetypes=[("Spectrum files", "*.csv *.txt *.dpt *.jdx *.dx *.0 *.1 *.2 *.3 *.4 *.5 *.6 *.7 *.8 *.9"),
                   ("All files", "*.*")])
    root.destroy()
    return [Path(p) for p in chosen]


if SETTINGS["use_demo_spectra"]:
    files = find_spectrum_files(config.EXAMPLES_DIR)
elif SETTINGS["files"]:
    files = [Path(f) if Path(f).is_absolute() else HERE / f for f in SETTINGS["files"]]
else:
    print("\n--- 2. Opening the file dialog ...")
    files = choose_files()

print(f"\n--- 2. {len(files)} file(s) chosen")
for f in files:
    print(f"  -> {f.name}")
if not files:
    raise SystemExit("No files chosen. Run the script again, or set SETTINGS['use_demo_spectra'] = True.")

# %%
# =========================================================================
# 3. HOW WERE THEY MEASURED? (asked only for files that do not say it)
# =========================================================================


def ask_mode(paths):
    """Ask once in the console for every file without a mode. Answers are saved in the sample log."""
    if SETTINGS["default_mode"]:
        return {p: SETTINGS["default_mode"] for p in paths}
    if not (INTERACTIVE or sys.stdin.isatty()):     # nobody to ask (e.g. run by another program)
        return {}
    print(f"\n  {len(paths)} file(s) do not say how they were measured:")
    for p in paths:
        print(f"     {p.name}")
    choices = {"1": "ATR", "2": "transmission", "3": "unknown"}
    while True:                                     # keep asking until the answer is valid
        answer = input("  All of them were measured by: 1 = ATR, 2 = transmission, 3 = don't know: ").strip()
        if answer in choices:
            return {p: choices[answer] for p in paths}


modes = resolve_modes(files, SampleLog(), ask=ask_mode)
print("\n--- 3. Measuring mode")
for f in files:
    print(f"  -> {f.name}: {modes[f].mode} ({modes[f].source})")

# %%
# =========================================================================
# 4. ANALYSE
# =========================================================================
results, problems = [], []
for n, path in enumerate(files, start=1):
    info = modes[path]
    try:
        for spectrum in read_spectra(path):
            results.append(analyse(spectrum, library, info.mode, info.source, info.conflict))
        print(f"  [{n}/{len(files)}] {path.name}: analysed")
    except SpectrumFileError as error:
        problems.append(str(error))
        print(f"  [{n}/{len(files)}] skipped: {error}")

print(f"\n--- 4. {len(results)} spectra analysed" + (f", {len(problems)} file(s) skipped" if problems else ""))

# %%
# =========================================================================
# 5. RESULTS TABLE
# =========================================================================
table = results_table(results)
summary = table[["sample", "verdict", "match", "r", "gap", "mode", "flags"]].round({"r": 2, "gap": 2})
print("\n--- 5. Results\n")
print(summary.to_string(index=False))
for r in results:
    print(f"\n  {r.name}: {r.verdict.upper()} {r.match if r.has_match else ''}")
    print(f"     why:       {r.reason}")
    print(f"     next step: {r.next_step}")

# %%
# =========================================================================
# 6. INTERACTIVE FIGURES
#    hover = every value + the band name; drag = zoom; double-click = reset;
#    camera button (top right) = save a PNG at 4x resolution
# =========================================================================
if SETTINGS["show_figures"] and (INTERACTIVE or not SETTINGS["write_report"]):
    for r in results:
        show(result_figure(r, library).update_layout(title=f"{r.name}: {r.verdict} {r.match if r.has_match else ''}"))
        if SETTINGS["show_analytical_view"]:
            print(f"\n  Analytical view of {r.name}:")
            for step in analytical_steps(r, library):
                print(f"   {step.number}. {step.title}: {step.explanation}")
            show(analytical_figure(r, library))
elif SETTINGS["show_figures"]:
    print("\n--- 6. The interactive figures (and the analytical view of every spectrum) are in the report.")

# %%
# =========================================================================
# 7. REPORT
# =========================================================================
if SETTINGS["write_report"] and results:
    out_dir = HERE / SETTINGS["report_folder"] / f"FTIR_report_{datetime.now():%Y-%m-%d_%H%M%S}"
    report = write_report(results, library, run_info(library, validation), out_dir)
    print(f"\n--- 7. Report written: {report}")
    print("  -> The run was added to the audit log:", config.AUDIT_LOG_FILE)
    if SETTINGS["open_report"]:
        webbrowser.open(report.as_uri())

# %%
# =========================================================================
# 8. ADD A REFERENCE TO THE IN-HOUSE LIBRARY (only if SETTINGS["add_reference"] is set)
#    Use it for a material identified by other means (a known part, a data sheet, SEM-EDX).
#    First the program shows what adding it would do; it is only added if the library stays valid.
# =========================================================================
if SETTINGS["add_reference"]:
    ref_path = Path(SETTINGS["add_reference"])
    ref_path = ref_path if ref_path.is_absolute() else HERE / ref_path
    notes = reference_notes(ref_path)                       # details the file carries in its header, if any
    reference = read_spectra(ref_path)[0]
    name = notes.get("reference", reference.name)
    mode = notes.get("mode", "unknown")
    y = reference_on_grid(reference.wn, absorbance(reference), mode)
    impact, changes = addition_preview(library, name, y, results, before=validation)
    safe = impact.passed and impact.distinct

    print(f"\n--- 8. Adding '{name}' ({ref_path.name}, measured by {mode})")
    print(f"  -> Most similar existing reference: {impact.nearest[0]} (r = {impact.nearest[1]:.2f})")
    print(f"  -> Impostor test: now {impact.before.score:.2f}, with it {impact.after.score:.2f} "
          f"({impact.after.material} -> {impact.after.impostor})")
    print(f"  -> {len(changes)} of {len(results)} results would change:")
    for change in changes:
        print(f"       {change.sample}: {change}")
    print("  -> " + ("Safe to add: the library stays validated." if safe else
                     f"NOT safe to add: {name} and {impact.nearest[0]} could not be told apart."))
    if safe and SETTINGS["really_add"]:
        saved = InHouseLibrary().add(name, reference.wn, absorbance(reference), mode,
                                     category=notes.get("category", "In-house"),
                                     fab_sources=notes.get("fab sources", ""), check_next=notes.get("check next", ""),
                                     confirmation=notes.get("confirmation", ""), source_path=ref_path,
                                     existing=library.spectra)
        print(f"  -> Added: {saved}\n     Run the script again to analyse with it.")
    elif safe:
        print('  -> Nothing saved. Set SETTINGS["really_add"] = True to add it.')

print("\nDone.")
