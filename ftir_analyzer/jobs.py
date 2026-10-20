"""
FTIR Contamination Analyzer - background work

Slow work (loading the library, analysing, validating a new reference, writing the report)
runs in a background thread, so the window never freezes. A Job runs one function there
and reports back with Qt signals: Qt's safe way to hand results from a background thread
to the window.

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal


class Job(QRunnable):
    """Runs function(*args, progress=...) in a background thread and reports back with signals."""

    class Signals(QObject):
        progress = Signal(int, int, str)       # step, of how many, what
        done = Signal(object, object)          # the job, the function's return value
        failed = Signal(object, str)           # the job, an error message

    def __init__(self, function, *args):
        super().__init__()
        self.function, self.args = function, args
        self.signals = Job.Signals()
        self.on_done, self.failure_title, self.details = None, "", ""
        self.setAutoDelete(False)              # the owner keeps it until it has reported back

    def run(self):
        try:
            result = self.function(*self.args, progress=self.signals.progress.emit)
        except Exception as error:             # report it, never crash the window
            self.details = traceback.format_exc()  # the full story, for the error log
            print(self.details)
            self.signals.failed.emit(self, f"{type(error).__name__}: {error}")
        else:
            self.signals.done.emit(self, result)
