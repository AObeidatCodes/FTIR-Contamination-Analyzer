"""
FTIR Contamination Analyzer - settings

Every number the analysis depends on lives here, in one place, with the reason
it has its value. Changing a rule means changing one line in this file.

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------------------
# Where things are
# --------------------------------------------------------------------------------------
PACKAGE_DIR = Path(__file__).resolve().parent            # .../ftir_analyzer/ftir_analyzer
PROJECT_DIR = PACKAGE_DIR.parent                          # .../ftir_analyzer
DATA_DIR = PACKAGE_DIR / "data"                           # reference data shipped with the app
LIBRARY_INDEX = DATA_DIR / "library_index.csv"            # the shipped reference library: one row per material
LIBRARY_FILE = DATA_DIR / "library_openftir_atr.csv"      # its spectra (OpenFTIR, measured by ATR)
LIBRARY_MODE = "ATR"                                       # every reference is put into this mode when loaded
BAND_TABLE_FILE = DATA_DIR / "band_table.csv"             # band ranges and their assignments
FAB_SOURCES_FILE = DATA_DIR / "fab_sources.csv"           # where a material can come from in a fab
EXAMPLES_DIR = PROJECT_DIR / "examples"                   # demo spectra

# Records (sample log and audit log) are kept next to the app when it runs from its own
# folder, otherwise in the user's home folder. The environment variable FTIR_ANALYZER_RECORDS
# can point somewhere else (for example a shared lab drive).
_DEFAULT_RECORDS = (PROJECT_DIR / "records" if (PROJECT_DIR / "run_analyzer.py").exists()
                    else Path.home() / "FTIR Analyzer records")
RECORDS_DIR = Path(os.environ.get("FTIR_ANALYZER_RECORDS", _DEFAULT_RECORDS))
SAMPLE_LOG_FILE = RECORDS_DIR / "sample_log.csv"          # how each raw file was measured
INHOUSE_DIR = RECORDS_DIR / "inhouse_library"             # references the lab adds itself (append-only log)
AUDIT_LOG_FILE = RECORDS_DIR / "audit_log.csv"            # one row per spectrum per run, append-only

# File types the app reads: instrument exports with a wavenumber column and one or more
# intensity columns (comma, semicolon, tab or space separated, with or without a header).
SPECTRUM_FILE_TYPES = (".csv", ".txt", ".dpt")

# Categories of the library album, in the order they are shown (where a material comes from in a fab)
CATEGORIES = ("CMP & cleaning", "Cleanroom consumables", "People & clothing", "Carriers & handling",
              "Packaging", "Adhesives, seals & lubricants", "Litho & process residues", "Equipment & fixtures")

# --------------------------------------------------------------------------------------
# The common ruler: every spectrum is read off at the same wavenumbers before comparing
# --------------------------------------------------------------------------------------
GRID_START, GRID_STOP, GRID_STEP = 650.0, 4000.0, 5.0     # cm-1: a point every 5 cm-1, 671 points
CO2_RANGE = (2280.0, 2400.0)                              # atmospheric CO2: never part of a comparison
HOLE = 20.0              # cm-1: a wider step between two measured points is a cut-out region, never bridged

# --------------------------------------------------------------------------------------
# Derivative fingerprint (used for matching)
# --------------------------------------------------------------------------------------
SAVGOL_WINDOW = 11      # Savitzky-Golay window: the slope is fitted over 11 neighbouring points
SAVGOL_ORDER = 3        # ... with a 3rd-order polynomial, which smooths while it differentiates

# --------------------------------------------------------------------------------------
# Baseline (asymmetric least squares) - used for pictures and checks, never for matching
# --------------------------------------------------------------------------------------
DISPLAY_STIFFNESS = 1e7   # stiff enough to keep broad bands such as the O-H hill (1e5 erases it)
PEAK_WEIGHT = 0.01        # points above the curve (probably peaks) barely count
BASELINE_ROUNDS = 10      # re-weighting rounds until the curve has slid under the peaks

# --------------------------------------------------------------------------------------
# Peak finding
# --------------------------------------------------------------------------------------
PEAK_SHARE = 0.08         # a peak must stick out by 8 % of the spectrum's height (2 % = noise, 30 % = too few)
PEAK_DISTANCE_CM = 15.0   # two peaks closer than 15 cm-1 count as one (jagged, saturated tops)

# --------------------------------------------------------------------------------------
# Verdict rule
# --------------------------------------------------------------------------------------
PROBABLE_R = 0.95   # impostor test: a WRONG material reaches 0.90 (PET <-> PBT); true matches 0.96-0.99
MIN_GAP = 0.08      # the winner must lead the next material by 0.08, or the two are too close to call
WEAK_R = 0.60       # below this nothing in the library is similar enough (CO2 gas scores 0.58)

# --------------------------------------------------------------------------------------
# Checks on the raw spectrum
# --------------------------------------------------------------------------------------
SATURATED_A = 2.0     # above A = 2 less than 1 % of the light gets through: band tops are unreliable
CH_MIN_SHARE = 0.01   # C-H counts from 1 % of the tallest band (pure CO2 gas: 0.53 %, weakest real C-H: 2.7 %)
MIN_SN = 3.0          # detection limit as in ICH Q2: a band counts only if it is 3x the noise
MAJOR = 1 / 3         # a loud band (O-H) at >= 1/3 of the tallest band is part of the material
MINOR = 1 / 10        # ... between 1/10 and 1/3 it is minor, below 1/10 a trace
CO2_WARNING = 0.5     # a CO2 artefact half as tall as the tallest band means: probably no sample

# Quiet windows (no sample bands) where the noise is measured. The worst one counts:
# 3750-3950 is where water-vapour lines appear, and they are noise for our purposes.
NOISE_WINDOWS = ((2000.0, 2250.0), (2450.0, 2750.0), (3750.0, 3950.0))

# Ruler method: (left foot, right foot, band). A band's height is measured above a
# straight line drawn between the median levels of its two feet.
CO2_ZONE = ((2200.0, 2250.0), (2420.0, 2470.0), (2280.0, 2400.0))
CH_ZONE = ((2700.0, 2760.0), (3120.0, 3180.0), (2840.0, 2990.0))
OH_ZONE = ((2500.0, 2700.0), (3700.0, 3900.0), (3200.0, 3500.0))

# --------------------------------------------------------------------------------------
# Band evidence
# --------------------------------------------------------------------------------------
KEY_SHARE = 0.10      # a reference band is "key" if it reaches 10 % of the reference's tallest band
EXTRA_SHARE = 0.15    # a sample band must reach 15 % of its tallest band to be called unexplained
TOLERANCE_CM = 15.0   # two bands are the same band if they are at most 15 cm-1 apart
EVIDENCE_SHARE = 0.03 # bands are listed from 3 % of the tallest band (small bands still count as evidence)

# --------------------------------------------------------------------------------------
# Measuring mode and ATR correction
# --------------------------------------------------------------------------------------
MODES = ("ATR", "transmission", "unknown")
REFERENCE_WN = 1000.0   # at this wavenumber the ATR correction changes nothing (factor 1)
