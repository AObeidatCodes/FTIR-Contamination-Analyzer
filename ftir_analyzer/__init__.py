"""
FTIR Contamination Analyzer

Identifies the material behind a contamination (a particle, a film, a residue)
from its FTIR spectrum. The app compares the spectrum with a reference library,
gives a validated verdict, checks the raw spectrum for warning signs, explains
every match band by band, and writes a traceable report.

Modules, in the order the data flows through them:
    spectrum_io  read a spectrum file exactly as measured (read-only)
    processing   absorbance, common grid, baseline, derivative fingerprint, ATR correction
    peaks        find real peaks and name them from a band table
    library      reference library (shipped + in-house), Pearson score, search, impostor test,
                 validation of a new reference, similarity map
    inhouse      the lab's own references: add / remove with an append-only change log
    checks       checks on the raw spectrum: saturation, CO2, C-H, O-H/N-H
    evidence     which bands support a match, which bands it cannot explain
    analysis     the whole pipeline for one spectrum -> one Result
    analytical   every intermediate step of one analysis (the "analytical view")
    records      sample log (measuring mode per file) and audit log (every run)
    plots        the figures of the app and saved images (matplotlib)
    interactive  the interactive figures of the report and the script (Plotly)
    report       the HTML / CSV report
    theme        the design system: colours, fonts, sizes, animation times (light and dark)
    motion       animation and the pieces that move (cards, segmented control, sheets, toasts)
    widgets      the building blocks of the window (pills, score bars, list, plot, dialogs)
    library_view the Library page: album, details, similarity map, adding a reference
    jobs         background work, so the window never freezes
    gui          the desktop application

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

__title__ = "FTIR Contamination Analyzer"
__version__ = "1.0.0"
__author__ = "Ali Obeidat"
__license__ = "MIT"
