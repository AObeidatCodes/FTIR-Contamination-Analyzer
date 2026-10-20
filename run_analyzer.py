"""
FTIR Contamination Analyzer - start the application

    python run_analyzer.py                 open the application
    python run_analyzer.py --help          all options (batch report without a window, ...)

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import sys

from ftir_analyzer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
