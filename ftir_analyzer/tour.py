"""
FTIR Contamination Analyzer - the guided tour

A second window with its own, empty records: the tour does real work there, with the demo files, and the folder
is deleted when the window closes. Nothing reaches the lab's library, logs or signatures.

    Ring       a soft outline around the part of the window a step is about
    TourCard   the small card in the corner: what this step shows, and Next
    Tour       the steps, in order: each one does something real, waits until it is done, then explains it

The words of a step come from the result on the screen, so they stay true when the library changes.

Short names used in this file:
    w = the tour's window    rv = its result page

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import config
from .motion import Moving, alive
from .openspecy import PACK_DIR
from .structures import groups_at
from .widgets import Theme

SAMPLE = config.EXAMPLES_DIR / "05_fibre_on_wafer_ATR.csv"
REFERENCE = config.EXAMPLES_DIR / "library_demo" / "Nylon6_reference_fibre_collection.csv"


class Ring(QWidget):
    """A soft outline around a part of the window. It follows that part while the page moves."""

    PAD = 6

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.target = None
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._follow)

    def follow(self, target):
        self.target = target
        self._follow()
        self.timer.start()

    def stop(self):
        self.target = None
        self.timer.stop()
        self.hide()

    def _follow(self):
        if not alive(self.target) or not self.target.isVisible():
            self.hide()
            return
        place = QRect(self.target.mapTo(self.parentWidget(), QPoint(0, 0)), self.target.size())
        place = place.adjusted(-self.PAD, -self.PAD, self.PAD, self.PAD).intersected(self.parentWidget().rect())
        if place != self.geometry():
            self.setGeometry(place)
        self.show()
        self.raise_()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(Theme.t["accent"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)


class TourCard(QFrame):
    """The card in the bottom left corner, over the list, so it never covers what a step is about."""

    WIDTH, MARGIN = 340, 14

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("TourCard")
        self.setFixedWidth(self.WIDTH)
        self.title = QLabel()
        self.title.setObjectName("SectionTitle")
        self.title.setWordWrap(True)
        self.text = QLabel()
        self.text.setObjectName("Body")
        self.text.setWordWrap(True)
        self.count = QLabel()
        self.count.setObjectName("Meta")
        self.end_button = QPushButton("End tour")
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("Primary")
        for button in (self.end_button, self.next_button):
            button.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout()
        row.addWidget(self.count)
        row.addStretch()
        row.addWidget(self.end_button)
        row.addWidget(self.next_button)
        column = QVBoxLayout(self)
        column.setContentsMargins(18, 16, 18, 14)
        column.setSpacing(8)
        column.addWidget(self.title)
        column.addWidget(self.text)
        column.addSpacing(4)
        column.addLayout(row)
        parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self.place()
        return False

    def place(self):
        self.adjustSize()
        parent = self.parentWidget()
        self.move(self.MARGIN, parent.height() - self.height() - self.MARGIN - 28)
        self.raise_()

    def say(self, title, text, count, last=False):
        self.title.setText(title)
        self.text.setText(text)
        self.count.setText(count)
        self.next_button.setText("Close" if last else "Next")
        self.end_button.setVisible(not last)
        self.show()
        self.place()


@dataclass
class Step:
    """One step: do something, wait until it is done, then explain it."""

    prepare: Callable                    # does the real work of the step
    ready: Callable                      # True when that work is finished
    explain: Callable                    # -> (title, text, the part of the window it is about, or None)


class Tour(QObject):
    """Walks through the app in a window of its own. pages: the window's two page names (analyze, library)."""

    def __init__(self, window, analyze, library):
        super().__init__(window)
        self.w, self.rv, self.analyze, self.library = window, window.result_view, analyze, library
        self.card = TourCard(window)
        self.ring = Ring(window)
        self.card.hide()
        self.ring.hide()
        self.card.next_button.clicked.connect(self.next)
        self.card.end_button.clicked.connect(window.close)
        self.at, self.panel, self.band = -1, None, None
        self.clock = QTimer(self)
        self.clock.setInterval(60)
        self.clock.timeout.connect(self._check)
        self.waited = 0
        self.steps = [Step(lambda: None, lambda: True, self._welcome),
                      Step(self._open_sample, self._has_result, self._sample_said),
                      Step(self._go_to_figure, lambda: True, self._figure_said),
                      Step(self._pin_band, lambda: True, self._band_said),
                      Step(self._open_add, self._add_checked, self._add_said),
                      Step(self._add_it, self._reference_added, self._added_said),
                      Step(self._more_references, self._pack_added, self._more_said),
                      Step(self._open_export, lambda: self.w.sheet is not None, self._export_said),
                      Step(self._close_sheet, lambda: self.w.sheet is None, self._done)]

    def start(self):
        self.next()

    def next(self):
        if self.at == len(self.steps) - 1:
            self.w.close()
            return
        self.at += 1
        self.card.hide()
        self.ring.stop()
        self.steps[self.at].prepare()
        self.waited = 0
        self.clock.start()

    def _check(self):
        self.waited += 1
        settled = not self.w.busy and not Moving.count
        if not (settled and self.steps[self.at].ready()) and self.waited < 1000:   # one minute at the very most
            return
        self.clock.stop()
        title, text, target = self.steps[self.at].explain()
        self.card.say(title, text, f"{self.at + 1} of {len(self.steps)}", self.at == len(self.steps) - 1)
        if target is not None:
            self.ring.follow(target)
            self.card.raise_()

    # ---------------------------------------------------------------- the steps
    def _welcome(self):
        return ("A tour with real data",
                "This window has its own empty records, and they are deleted when it closes. Nothing here reaches "
                "your library, your logs or your signatures.", None)

    def _open_sample(self):
        self.w.analyse_paths([SAMPLE])

    def _has_result(self):
        return self.w.current_result() is not None and self.rv.isVisible()

    def _sample_said(self):
        r = self.w.current_result()
        return ("One sample",
                f"A fibre found on a wafer. The closest reference is {r.best} at r {r.r:.2f}: similar, not proven. "
                f"So the verdict is {r.verdict}, and the app says what to do next.", self.rv.facts)

    def _go_to_figure(self):
        self.rv.ensureWidgetVisible(self.rv.plot, 0, 40)

    def _figure_said(self):
        r = self.w.current_result()
        return ("Check it by eye", f"The sample against {r.best}, the raw data on top. Everything the app says can be "
                "seen here. Move the mouse over it to read any band.", self.rv.plot)

    def _pin_band(self):
        model = self.rv.structure.model
        bands = [b for b in self.rv.band_buttons if model and groups_at(model, b.w)]
        self.band = next((b for b in bands if "C=O (amide)" in groups_at(model, b.w)), bands[0] if bands else None)
        if self.band is not None:
            self.rv._pin_band(self.band)

    def _band_said(self):
        if self.band is None:
            return "Bands and bonds", "Click a band: the figure zooms to it and its bonds glow on the model.", self.rv.plot
        name = groups_at(self.rv.structure.model, self.band.w)[0]
        return ("A band is a bond", f"This is the band at {self.band.w:.0f} cm⁻¹, from the {name} group. Click any band: "
                "the figure zooms to it, and its bonds glow on a short model chain. Drag the model to turn it.",
                self.rv.structure)

    def _open_add(self):
        if self.band is not None:                                       # let go of the band
            self.rv._pin_band(self.band)
        self.panel = self.w.open_add_reference(use_current=False)
        self.panel.load_file(REFERENCE)

    def _add_checked(self):
        return self.panel is not None and self.panel.preview is not None and self.w.sheet is not None

    def _add_said(self):
        impact, changes = self.panel.preview
        near, score = impact.nearest
        return ("Add a reference from your lab",
                f"Your lab has a known Nylon 6 fibre. Its file fills in the form, and the app checks it before anything "
                f"is saved: the closest reference is {near} at r {score:.2f}, the library stays valid, and "
                f"{len(changes)} of your spectra would change.", self.panel.add_button)

    def _add_it(self):
        self.panel.add_button.click()

    def _reference_added(self):
        return "Nylon 6" in self.w.library.spectra

    def _added_said(self):
        self.w.show_page(self.analyze)
        self.rv.scroll_to_top()
        change = self.w.model.updated.get(self.w.current_result().name)
        text = f"{change.before} became {change.after}." if change else "The library was validated again."
        return ("The answer changed", f"{text} The library was validated again, every spectrum was analysed again, "
                "and the change is written down in the library's log.", self.rv.change_box)

    def _more_references(self):
        self.w.get_openspecy(PACK_DIR)

    def _pack_added(self):
        return self.w.extended

    def _more_said(self):
        self.w.show_page(self.library)
        v = self.w.validation
        return ("More references, one click", f"Open Specy's references come with the app. This library now has "
                f"{len(self.w.library)} references, and it still passes the impostor test: the best wrong match stays "
                f"at r {v.score:.2f}, below the {config.PROBABLE_R:.2f} that a probable needs.", None)

    def _open_export(self):
        self.w.show_page(self.analyze)
        panel = self.w.export_report()
        if panel is not None:
            panel.set_folder(self.w.tour_folder)
            self.export = panel

    def _export_said(self):
        return ("Sign and export", "Write the report as a PDF or a web page, and sign it if you like. Try it: in the "
                "tour it goes to a folder that is deleted at the end.", self.export.export_button)

    def _close_sheet(self):
        if self.w.sheet is not None:
            self.w.sheet.close_sheet()

    def _done(self):
        return ("That is the app", "Open your own spectra in the main window, or drop them anywhere on it. Close this "
                "window to delete everything the tour made.", None)
