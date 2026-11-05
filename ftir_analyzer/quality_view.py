"""
FTIR Contamination Analyzer - the Quality page

The instrument check and the second-person review. The page reads the records again each time it is shown.

    DriftChart    the mean band shift of each instrument check, between the limits
    ReviewPanel   the sheet where a second person records a review
    QualityPage   the page

Short names used in this file:
    t = theme colours    p = the painter    c = one instrument check

Author : Ali Obeidat
Version: 2.0.0
License: MIT (see LICENSE)
"""

from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QBoxLayout, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QToolTip, QVBoxLayout, QWidget)

from . import config
from .export_view import ClickLabel
from .instrument_check import FAILED, append_check, check_file, movement, read_checks
from .library_view import section, text_label
from .motion import FlowLayout, Segmented, SmoothScrollArea
from .records import DECISIONS, current_user, make_signoff, readable_time
from .review import CHANGED, MISSING, REVIEWED, WAITING, read_reports, reviewer_problem
from .widgets import Pill, Theme, clear_layout, font, icon, icon_pixmap

SHOWN = (("Waiting", WAITING), ("All", "all"))
REVIEW_CHOICES = (("Accept", "accept"), ("With changes", "accept with changes"), ("Re-measure", "re-measure"))
STATEMENT = "I did not make this analysis. I have read the report and looked at the raw spectra."
DECISION_KINDS = {"accept": "good", "accept with changes": "warn", "re-measure": "bad"}


def day_text(moment):
    return f"{moment.day} {moment:%b %Y}"


def later(stamp, days):
    """A recorded time, moved by some days."""
    return (datetime.fromisoformat(stamp) + days).isoformat()


def spectra_text(report):
    number = report.spectra
    return f"{number} spectr{'um' if number == 1 else 'a'}"


class DriftChart(QWidget):
    """Each check as a point: the mean shift, between the limits. A failed check is a red point."""

    LEFT, RIGHT, TOP, BOTTOM = 44, 12, 22, 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self.checks = []
        self.setFixedHeight(170)
        self.setMouseTracking(True)
        self.setAccessibleName("Mean band shift of each instrument check")

    def set_checks(self, checks):
        self.checks = list(checks)[-30:]
        self.update()

    def _span(self):
        return max([1.5 * config.FILM_LIMIT] + [1.15 * abs(c.mean) for c in self.checks])

    def _x(self, i):
        width = self.width() - self.LEFT - self.RIGHT
        return self.LEFT + (width * i / (len(self.checks) - 1) if len(self.checks) > 1 else width / 2)

    def _y(self, value):
        height = self.height() - self.TOP - self.BOTTOM
        return self.TOP + height * (self._span() - value) / (2 * self._span())

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(font("small"))
        right = self.width() - self.RIGHT
        limit = config.FILM_LIMIT
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["good_bg"]))
        p.drawRect(QRectF(self.LEFT, self._y(limit), right - self.LEFT, self._y(-limit) - self._y(limit)))
        p.setPen(QPen(QColor(t["line_strong"]), 1))
        p.drawLine(QPointF(self.LEFT, self._y(0)), QPointF(right, self._y(0)))
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(0, 0, 240, 16), Qt.AlignLeft | Qt.AlignVCenter, "Mean shift (cm⁻¹)")
        for value, text in ((limit, f"+{limit:g}"), (0, "0"), (-limit, f"−{limit:g}")):
            p.drawText(QRectF(0, self._y(value) - 9, self.LEFT - 8, 18), Qt.AlignRight | Qt.AlignVCenter, text)
        if not self.checks:
            return
        floor = self.height() - self.BOTTOM + 4
        p.drawText(QRectF(self.LEFT, floor, 120, 18), Qt.AlignLeft | Qt.AlignVCenter, day_text(self.checks[0].time))
        if len(self.checks) > 1:
            p.drawText(QRectF(right - 120, floor, 120, 18), Qt.AlignRight | Qt.AlignVCenter, day_text(self.checks[-1].time))
        line = QPainterPath(QPointF(self._x(0), self._y(self.checks[0].mean)))
        for i, c in enumerate(self.checks[1:], start=1):
            line.lineTo(self._x(i), self._y(c.mean))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(t["accent"]), 1.5))
        p.drawPath(line)
        for i, c in enumerate(self.checks):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["bad"] if c.result == FAILED else t["accent"]))
            p.drawEllipse(QPointF(self._x(i), self._y(c.mean)), 4, 4)

    def mouseMoveEvent(self, event):
        if not self.checks:
            return
        x = event.position().x()
        i = min(range(len(self.checks)), key=lambda n: abs(self._x(n) - x))
        c = self.checks[i]
        QToolTip.showText(self.mapToGlobal(QPoint(int(x), int(event.position().y()))),
                          f"{day_text(c.time)}: {c.result}. Mean shift {c.mean:+.2f} cm⁻¹, largest {c.largest:.2f} cm⁻¹")


class ReviewPanel(QWidget):
    """The content of the review sheet."""

    submitted = Signal(object, dict)      # the report, the sign-off (records.make_signoff)
    open_requested = Signal(object)       # the report
    cancelled = Signal()

    def __init__(self, report, name=""):
        super().__init__()
        t = Theme.t
        self.report = report
        column = QVBoxLayout(self)
        column.setContentsMargins(22, 16, 22, 22)
        column.setSpacing(14)
        who = report.analysed_by or f"login {report.login}"
        tool = f", {report.tool}" if report.tool else ""
        facts = text_label(f"Analysed by {who} on {readable_time(report.time)}{tool}. {spectra_text(report)}: "
                           f"{report.probable} probable, {report.weak} weak, {report.no_match} with no reliable match.",
                           "Body2", wrap=True)
        column.addWidget(facts)
        opening = QPushButton(" Open the report")
        opening.setIcon(icon("file-down", t["ink_2"]))
        opening.setCursor(Qt.PointingHandCursor)
        opening.clicked.connect(lambda: self.open_requested.emit(report))
        column.addWidget(opening, 0, Qt.AlignLeft)

        card, body = section("Your review")
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        self.name = QLineEdit(name)
        self.name.setPlaceholderText("your full name")
        self.name.textChanged.connect(lambda _: self._update())
        form.addWidget(text_label("Your name", "FactLabel"), 0, 0, Qt.AlignVCenter)
        form.addWidget(self.name, 0, 1)
        self.decision = Segmented("accept", choices=REVIEW_CHOICES)
        self.decision.changed.connect(lambda _: self._update())
        form.addWidget(text_label("Decision", "FactLabel"), 1, 0, Qt.AlignVCenter)
        form.addWidget(self.decision, 1, 1, Qt.AlignLeft)
        self.comment = QLineEdit()
        self.comment.setPlaceholderText("Comment (needed for 'with changes' and 're-measure')")
        self.comment.textChanged.connect(lambda _: self._update())
        form.addWidget(text_label("Comment", "FactLabel"), 2, 0, Qt.AlignVCenter)
        form.addWidget(self.comment, 2, 1)
        form.setColumnStretch(1, 1)
        body.addLayout(form)
        self.statement = QCheckBox()
        self.statement.setCursor(Qt.PointingHandCursor)
        self.statement.setAccessibleName(STATEMENT)
        self.statement.toggled.connect(lambda _: self._update())
        row = QHBoxLayout()
        row.addWidget(self.statement, 0, Qt.AlignTop)
        row.addWidget(ClickLabel(STATEMENT, self.statement.toggle), 1)
        body.addLayout(row)
        self.same_login = text_label("", "SectionHint", wrap=True)
        body.addWidget(self.same_login)
        column.addWidget(card)
        column.addStretch()

        self.footer = QFrame()
        self.footer.setObjectName("SheetHeader")
        foot = QHBoxLayout(self.footer)
        foot.setContentsMargins(22, 12, 22, 14)
        self.problem = text_label("", "SectionHint", wrap=True)
        foot.addWidget(self.problem, 1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancelled.emit)
        self.record_button = QPushButton(" Record review")
        self.record_button.setObjectName("Primary")
        self.record_button.setIcon(icon("circle-check", t["on_primary"]))
        self.record_button.clicked.connect(self._submit)
        for button in (cancel, self.record_button):
            button.setCursor(Qt.PointingHandCursor)
            foot.addWidget(button)
        self._update()

    def problems(self):
        """What still stops the review (an empty list = ready)."""
        missing = []
        who = reviewer_problem(self.report, self.name.text(), current_user())
        if who:
            missing.append(who)
        if not self.statement.isChecked():
            missing.append("the statement ticked")
        if self.decision.value() != "accept" and not self.comment.text().strip():
            missing.append("a comment")
        return missing

    def _update(self):
        missing = self.problems()
        self.record_button.setEnabled(not missing)
        self.problem.setText("Needs " + ", ".join(missing) + "." if missing else "")
        shared = current_user().casefold() == self.report.login.casefold()
        self.same_login.setVisible(shared)
        self.same_login.setText(f"You are on the analyst's login ({current_user()}). The review records this.")

    def _submit(self):
        if not self.problems():
            self.submitted.emit(self.report, make_signoff(self.name.text(), self.decision.value(), self.comment.text()))


class QualityPage(QWidget):
    """The instrument check, then the reports and their reviews."""

    review_requested = Signal(object)     # a Report
    open_requested = Signal(object)       # a Report
    instrument_changed = Signal(str)

    def __init__(self, instrument_log, report_log, review_log, instrument="", parent=None):
        super().__init__(parent)
        self.setObjectName("LibraryPage")                               # the same background
        self.instrument_log, self.report_log, self.review_log = instrument_log, report_log, review_log
        self.checks, self.reports = [], []
        self.demo, self.problem, self.real_instrument = False, "", instrument

        self.scroll = SmoothScrollArea()
        content = QWidget()
        content.setObjectName("LibraryGrid")
        self.scroll.setWidget(content)
        column = QVBoxLayout(content)
        column.setContentsMargins(32, 24, 32, 32)
        column.setSpacing(16)

        self.top = QBoxLayout(QBoxLayout.LeftToRight)
        self.top.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(text_label("Quality", "PageTitle"))
        self.subtitle = text_label("", "Meta", wrap=True)
        titles.addWidget(self.subtitle)
        self.top.addLayout(titles, 1)
        self.demo_button = QPushButton(" Demo data")
        self.demo_button.setCheckable(True)
        self.demo_button.setCursor(Qt.PointingHandCursor)
        self.demo_button.setVisible(config.TRENDS_DEMO_DIR.is_dir())
        self.demo_button.toggled.connect(self._toggle_demo)
        self.top.addWidget(self.demo_button, 0, Qt.AlignBottom)
        column.addLayout(self.top)

        self.demo_note = QFrame()
        self.demo_note.setObjectName("Callout")
        self.demo_note.setProperty("kind", "warn")
        note_row = QHBoxLayout(self.demo_note)
        note_row.setContentsMargins(16, 10, 16, 10)
        self.demo_icon = QLabel()
        note_row.addWidget(self.demo_icon)
        note_row.addWidget(text_label("Demo data: these checks and reports are made up.", "Body", wrap=True), 1)
        self.demo_note.hide()
        column.addWidget(self.demo_note)

        # the instrument check
        self.check_card, check_body = section("Instrument check")
        check_body.addWidget(text_label("Measure a polystyrene film in transmission, then choose the file. Each band "
                                        f"must be within {config.FILM_LIMIT:g} cm⁻¹ of its published position.",
                                        "Body2", wrap=True))
        self.instrument = QComboBox()
        self.instrument.setEditable(True)
        self.instrument.setMinimumWidth(190)
        self.instrument.setAccessibleName("Instrument")
        self.instrument.lineEdit().setPlaceholderText("Instrument, e.g. FTIR 1")
        self.instrument.setEditText(instrument)
        self.instrument.currentTextChanged.connect(self._instrument_chosen)
        self.check_button = QPushButton(" Check a film…")
        self.check_button.setCursor(Qt.PointingHandCursor)
        self.check_button.clicked.connect(self.choose_film)
        controls = QWidget()
        control_row = FlowLayout(controls, spacing=8, row_spacing=8)
        control_row.addWidget(self.instrument)
        control_row.addWidget(self.check_button)
        check_body.addWidget(controls)
        self.status = QFrame()
        self.status.setObjectName("Callout")
        status_row = QHBoxLayout(self.status)
        status_row.setContentsMargins(12, 8, 12, 8)
        self.status_icon = QLabel()
        self.status_text = text_label("", "Body", wrap=True)
        status_row.addWidget(self.status_icon, 0, Qt.AlignTop)
        status_row.addWidget(self.status_text, 1)
        check_body.addWidget(self.status)
        self.chart = DriftChart()
        check_body.addWidget(self.chart)
        self.band_grid = QGridLayout()
        self.band_grid.setHorizontalSpacing(12)
        self.band_grid.setVerticalSpacing(2)
        check_body.addLayout(self.band_grid)
        column.addWidget(self.check_card)

        # the reports
        self.review_card, review_body = section("Second-person review")
        review_body.addWidget(text_label("A different person from the analyst reads each exported report and records "
                                         "a decision.", "Body2", wrap=True))
        self.shown = Segmented(WAITING, choices=SHOWN)
        self.shown.changed.connect(lambda _: self.show_reports())
        review_body.addWidget(self.shown, 0, Qt.AlignLeft)
        self.report_rows = QVBoxLayout()
        self.report_rows.setSpacing(8)
        review_body.addLayout(self.report_rows)
        column.addWidget(self.review_card)
        column.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        self.retheme()

    # ------------------------------------------------------------------
    def retheme(self):
        t = Theme.t
        self.demo_button.setIcon(icon("flask-conical", t["ink_2"]))
        self.demo_icon.setPixmap(icon_pixmap("triangle-alert", t["warn"], 18, self.devicePixelRatioF()))
        self.check_button.setIcon(icon("folder-open", t["ink_2"]))
        for frame in (self.demo_note, self.status):
            frame.style().unpolish(frame)
            frame.style().polish(frame)
        self.show_checks()
        self.show_reports()

    def refresh(self):
        """Read the records again."""
        self.problem = ""
        folder = config.TRENDS_DEMO_DIR
        try:
            self.checks = read_checks(folder / "instrument_checks.csv" if self.demo else self.instrument_log)
            self.reports = read_reports(folder / "reports.csv" if self.demo else self.report_log,
                                        folder / "reviews.csv" if self.demo else self.review_log)
        except (OSError, ValueError, KeyError):                        # a damaged log must not stop the window
            self.checks, self.reports, self.problem = [], [], "The records could not be read."
        if self.demo:
            self._bring_up_to_date()
        self._fill_instruments()
        self.show_checks()
        self.show_reports()

    def _bring_up_to_date(self):
        """The made-up records moved so that the newest check is today: a demo must not look old."""
        if self.checks:
            days = timedelta(days=(datetime.now().astimezone() - self.checks[-1].time.astimezone()).days)
            self.checks = [replace(c, time=c.time + days) for c in self.checks]
            self.reports = [replace(r, time=later(r.time, days),
                                    review=r.review and replace(r.review, time=later(r.review.time, days)))
                            for r in self.reports]

    def _fill_instruments(self):
        text = self.instrument.currentText()
        names = sorted({c.instrument for c in self.checks if c.instrument}, key=str.casefold)
        if self.demo and names:
            text = names[0]
        self.instrument.blockSignals(True)
        self.instrument.clear()
        self.instrument.addItems(names)
        self.instrument.setEditText(text)
        self.instrument.blockSignals(False)

    def _toggle_demo(self, on):
        if on:
            self.real_instrument = self.instrument.currentText()
        self.demo = on
        self.demo_note.setVisible(on)
        self.check_button.setEnabled(not on)
        self.refresh()
        if not on:                                                     # the made-up name must not reach a real check
            self.instrument.setEditText(self.real_instrument)

    def _instrument_chosen(self, text):
        self.show_checks()
        if not self.demo:
            self.instrument_changed.emit(text)

    def checks_of_instrument(self):
        name = " ".join(self.instrument.currentText().split()).casefold()
        return [c for c in self.checks if c.instrument.casefold() == name]

    # ------------------------------------------------------------------
    def choose_film(self):
        path = QFileDialog.getOpenFileName(self, "Choose the measured polystyrene film")[0]
        if path:
            self.run_check(path)

    def run_check(self, path):
        """Check one file and add it to the log. A file that cannot be used changes nothing and says why."""
        try:
            check, _ = check_file(path)
            append_check(check, self.instrument.currentText(), path, self.instrument_log)
        except (OSError, ValueError) as problem:                       # SpectrumFileError is a ValueError
            self._set_status("bad", "triangle-alert", str(problem))
            return None
        self.refresh()
        return check

    def _set_status(self, kind, icon_name, text):
        self.status.setProperty("kind", kind)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status_icon.setPixmap(icon_pixmap(icon_name, Theme.t[kind if kind != "none" else "muted"], 16,
                                               self.devicePixelRatioF()))
        self.status_text.setText(text)

    def last_check_text(self):
        """The newest check in a few words, for the report ("" if there is none)."""
        checks = self.checks_of_instrument() or self.checks
        if not checks:
            return ""
        c = checks[-1]
        where = f"{c.instrument}: " if c.instrument else ""
        return (f"{where}{c.result} on {day_text(c.time)}, largest band shift {c.largest:.2f} cm⁻¹, "
                f"limit {config.FILM_LIMIT:g} cm⁻¹")

    def show_checks(self):
        checks = self.checks_of_instrument()
        self.chart.set_checks(checks)
        clear_layout(self.band_grid)
        limit = f"Limit {config.FILM_LIMIT:g} cm⁻¹."
        if not checks:
            self._set_status("none", "circle-minus", self.problem or "No check for this instrument yet.")
            return
        last = checks[-1]
        shift = f"Largest shift {last.largest:.2f} cm⁻¹. {limit}"
        moved = movement(checks)
        if last.result == FAILED:
            self._set_status("bad", "triangle-alert", f"Failed on {day_text(last.time)}. {shift} Have the instrument "
                                                      "calibrated, then check again.")
        elif moved:
            self._set_status("warn", "circle-alert", f"Passed on {day_text(last.time)}, but the bands moved {moved:+.2f} "
                                                     f"cm⁻¹ over the last {config.DRIFT_CHECKS} checks. Plan a calibration.")
        else:
            self._set_status("good", "circle-check", f"Passed on {day_text(last.time)}. {shift}")
        self.band_grid.addWidget(text_label("Published", "FactLabel"), 0, 0)
        self.band_grid.addWidget(text_label("Shift", "FactLabel"), 1, 0)
        for i, (x, s) in enumerate(zip(config.FILM_BANDS, last.shifts), start=1):
            self.band_grid.addWidget(text_label(f"{x:.1f}", "Body2"), 0, i)
            self.band_grid.addWidget(text_label(f"{s:+.2f}" if np.isfinite(s) else "–", "Body"), 1, i)
        self.band_grid.setColumnStretch(len(config.FILM_BANDS) + 1, 1)

    # ------------------------------------------------------------------
    def show_reports(self):
        clear_layout(self.report_rows)
        waiting = [r for r in self.reports if r.review is None]
        rows = waiting if self.shown.value() == WAITING else self.reports
        for report in rows:
            self.report_rows.addWidget(self._report_row(report))
        if not rows:
            self.report_rows.addWidget(text_label(self.problem or ("No reports are waiting." if self.reports else
                                                                   "No reports yet. They appear here once exported."),
                                                  "Body2", wrap=True))
        number = len(waiting)
        self.subtitle.setText(f"{number} report{'' if number == 1 else 's'} waiting for review." if self.reports else
                              "Instrument checks and second-person reviews.")

    def _report_row(self, report):
        t = Theme.t
        row = QFrame()
        row.setObjectName("Callout")
        line = QHBoxLayout(row)
        line.setContentsMargins(12, 8, 12, 8)
        words = QVBoxLayout()
        words.setSpacing(2)
        who = report.analysed_by or report.login
        tool = f", {report.tool}" if report.tool else ""
        words.addWidget(text_label(f"{readable_time(report.time)}: {spectra_text(report)}{tool}, analysed by {who}", "Body",
                                   wrap=True))
        state = WAITING if self.demo and report.review is None else report.state      # made-up reports have no file
        if state == REVIEWED:
            review = report.review
            text = f"{DECISIONS.get(review.decision, review.decision)} by {review.name} on {readable_time(review.time)}."
            if review.comment:
                text += f" {review.comment}"
            if review.same_login:
                text += " Same login as the analyst."
            words.addWidget(text_label(text, "Body2", wrap=True))
        line.addLayout(words, 1)
        if state == REVIEWED:
            kind = DECISION_KINDS.get(report.review.decision, "none")
            line.addWidget(Pill(kind, "Reviewed", "circle-check" if kind == "good" else "circle-alert"), 0, Qt.AlignVCenter)
        elif state in (MISSING, CHANGED):
            line.addWidget(Pill("bad", state[:1].upper() + state[1:], "triangle-alert"), 0, Qt.AlignVCenter)
        if self.demo:
            return row
        if state != MISSING:
            opening = QPushButton("Open")
            opening.setCursor(Qt.PointingHandCursor)
            opening.clicked.connect(lambda _=False, chosen=report: self.open_requested.emit(chosen))
            line.addWidget(opening)
        if state == WAITING:
            review = QPushButton(" Review…")
            review.setCursor(Qt.PointingHandCursor)
            review.setIcon(icon("circle-check", t["ink_2"]))
            review.clicked.connect(lambda _=False, chosen=report: self.review_requested.emit(chosen))
            line.addWidget(review)
        return row

