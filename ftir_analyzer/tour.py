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
        self.under = None                                               # the widget that stays on top of the outline
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
        if self.under is not None:
            self.under.raise_()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(Theme.t["accent"]), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)


class TourCard(QFrame):
    """The card in a bottom corner: left, over the list; right on a page with no list. It stays off what a step shows."""

    WIDTH, MARGIN = 340, 14

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("TourCard")
        self.setFixedWidth(self.WIDTH)
        self.on_right = False
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
        """The card's height follows its words at its real width: adjustSize() would measure them at another width."""
        for label in (self.title, self.text):
            label.ensurePolished()                                      # the style sheet decides the font size
        self.setFixedHeight(self.layout().totalHeightForWidth(self.WIDTH))
        parent = self.parentWidget()
        x = parent.width() - self.WIDTH - self.MARGIN - 12 if self.on_right else self.MARGIN
        self.move(x, parent.height() - self.height() - self.MARGIN - 28)
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
    """Walks through the app in a window of its own. analyze, library, trends: the window's page names."""

    def __init__(self, window, analyze, library, trends):
        super().__init__(window)
        self.w, self.rv = window, window.result_view
        self.analyze, self.library, self.trends = analyze, library, trends
        self.card = TourCard(window)
        self.ring = Ring(window)
        self.ring.under = self.card
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
                      Step(self._go_to_verdicts, lambda: True, self._verdicts_said),
                      Step(self._go_to_figure, lambda: True, self._figure_said),
                      Step(self._pin_band, lambda: True, self._band_said),
                      Step(self._go_to_matches, lambda: True, self._matches_said),
                      Step(self._go_to_evidence, lambda: True, self._evidence_said),
                      Step(self._open_library, self._on_library, self._library_said),
                      Step(self._open_add, self._add_checked, self._add_said),
                      Step(self._add_it, self._reference_added, self._added_said),
                      Step(self._open_trends, self._on_trends, self._trends_said),
                      Step(self._go_to_groups, lambda: True, self._groups_said),
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

    def _go_to_verdicts(self):
        self.rv.ensureWidgetVisible(self.rv.strip, 0, 40)

    def _verdicts_said(self):
        return ("Three possible verdicts",
                f"Probable: a score of {config.PROBABLE_R:.2f} or more, clearly ahead of the next material. Weak: similar, "
                "so read the bands yourself. No reliable match: nothing in the library fits. The score measures similarity; "
                "it is not a percentage.", self.rv.strip)

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

    def _go_to_matches(self):
        if self.band is not None:                                       # let go of the band
            self.rv._pin_band(self.band)
        self.rv.ensureWidgetVisible(self.rv.top, 0, 40)

    def _matches_said(self):
        return ("The closest matches", "The best references side by side. The shaded area shows where the shapes disagree. "
                "Click one to draw it in the big figure.", self.rv.top)

    def _go_to_evidence(self):
        self.rv.ensureWidgetVisible(self.rv.evidence_panel, 0, 40)

    def _evidence_said(self):
        return ("What backs the verdict", "Here are the key bands that were found. Beside them are the checks on the raw "
                "spectrum and where the material can come from in a fab.", self.rv.evidence_panel)

    def _open_library(self):
        self.w.show_page(self.library)

    def _on_library(self):
        return self.w.pages.currentWidget() is self.w.library_page

    def _library_said(self):
        return ("Your library", f"{len(self.w.library)} references, each with its source, spectrum and key bands. Click one to "
                "open it. The similarity map shows which ones could be confused.", self.w.library_page.grid)

    def _open_add(self):
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

    def _open_trends(self):
        self.card.on_right = True                                       # this page has no list to sit over
        self.w.show_page(self.trends)
        self.w.trends_page.demo_button.setChecked(True)

    def _on_trends(self):
        return self.w.pages.currentWidget() is self.w.trends_page

    def _trends_said(self):
        return ("Trends", "What keeps coming back. These samples are made up. When one material keeps returning on one tool, "
                "it shows here, so you can look at the tool and not just one sample.", self.w.trends_page.repeat_card)

    def _go_to_groups(self):
        page = self.w.trends_page
        page.scroll.ensureWidgetVisible(page.group_card, 0, 40)

    def _groups_said(self):
        return ("Unknown groups", "Samples with no name that look alike, so an unknown material can be seen coming back before "
                "anyone knows what it is. Once you know, add it as a reference.", self.w.trends_page.group_card)

    def _open_export(self):
        self.card.on_right = False
        self.w.show_page(self.analyze)
        panel = self.w.export_report()
        if panel is not None:
            panel.set_folder(self.w.tour_folder)
            self.export = panel

    def _export_said(self):
        return ("Sign and export", "Write the report as a PDF or a web page, enter the tool or area for Trends, and sign it "
                "if you like. Try it: in the tour it goes to a folder that is deleted at the end.", self.export.export_button)

    def _close_sheet(self):
        if self.w.sheet is not None:
            self.w.sheet.close_sheet()

    def _done(self):
        return ("That is the app", "Open your own spectra in the main window, or drop them anywhere on it. Every export is "
                "kept in the audit log, which this menu opens. Close this window to delete everything the tour made.",
                self.w.menu_button)
