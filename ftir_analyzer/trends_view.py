"""
FTIR Contamination Analyzer - the Trends page

What keeps coming back: repeats of one material on one tool, and the most common materials and tools. The page only
reads the records, and it reads them again each time it is shown.

    RankChart    a ranking as rows of bars, coloured by verdict, with a cumulative share
    TrendsPage   the page

Short names used in this file:
    t = theme colours    p = the painter

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (QBoxLayout, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout,
                               QWidget)

from . import config
from .library_view import section, text_label
from .motion import FlowLayout, Segmented, SmoothScrollArea
from .trends import NOT_RECORDED, demo_samples, in_period, ranked, read_samples, repeats
from .widgets import Theme, clear_layout, font, icon, icon_pixmap

ALL_TOOLS = "All tools"
PERIODS = (("30 days", "30"), ("90 days", "90"), ("All", "0"))
COUNTS, DAYS = (2, 3, 5), (7, 30, 90)
KEYS = (("Probable", "good"), ("Weak", "warn"), ("No reliable match", "none"))


def short_date(day):
    return f"{day.day} {day:%b}"


class RankChart(QWidget):
    """A ranking: each row a name, a bar split by verdict, the number of samples, and the cumulative share."""

    ROW, HEAD = 30, 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.setMouseTracking(True)
        self.setMinimumWidth(280)
        self.setFixedHeight(self.HEAD)

    def set_rows(self, rows):
        self.rows = rows
        self.setFixedHeight(self.HEAD + self.ROW * len(rows))
        self.update()

    def _columns(self):
        """(width for names, left of the bars, width of the bars, width of each number column)."""
        names, numbers = min(self.width() * 0.34, 190), 80
        return names, names + 12, max(40, self.width() - names - 12 - 2 * numbers), numbers

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(font("small"))
        metrics = QFontMetrics(p.font())
        names, left, bars, numbers = self._columns()

        x = 0
        for text, colour in KEYS:                                       # the key, and the headings of the numbers
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t[colour]))
            p.drawRoundedRect(QRectF(x, 7, 10, 10), 3, 3)
            p.setPen(QColor(t["ink_2"]))
            p.drawText(QRectF(x + 16, 0, 200, 24), Qt.AlignVCenter, text)
            x += 16 + metrics.horizontalAdvance(text) + 14
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(left + bars, 0, numbers, 24), Qt.AlignRight | Qt.AlignVCenter, "Samples")
        p.drawText(QRectF(left + bars + numbers, 0, numbers, 24), Qt.AlignRight | Qt.AlignVCenter, "Cumulative")

        most = max((row.total for row in self.rows), default=1)
        for i, row in enumerate(self.rows):
            top = self.HEAD + i * self.ROW
            middle = top + self.ROW / 2
            p.setPen(QColor(t["ink"]))
            p.drawText(QRectF(0, top, names, self.ROW), Qt.AlignVCenter, metrics.elidedText(row.name, Qt.ElideRight, int(names)))
            x = left
            for value, (_, colour) in zip((row.probable, row.weak, row.none), KEYS):
                if value:
                    width = bars * value / most
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(t[colour]))
                    p.drawRoundedRect(QRectF(x, middle - 5, max(width - 2, 3), 10), 3, 3)
                    x += width
            p.setPen(QColor(t["ink"]))
            p.drawText(QRectF(left + bars, top, numbers, self.ROW), Qt.AlignRight | Qt.AlignVCenter, str(row.total))
            p.setPen(QColor(t["muted"]))
            p.drawText(QRectF(left + bars + numbers, top, numbers, self.ROW), Qt.AlignRight | Qt.AlignVCenter,
                       f"{100 * row.running:.0f}%")

    def mouseMoveEvent(self, event):
        i = int((event.position().y() - self.HEAD) // self.ROW)
        if 0 <= i < len(self.rows):
            row = self.rows[i]
            QToolTip.showText(self.mapToGlobal(QPoint(int(event.position().x()), int(event.position().y()))),
                              f"{row.name}: {row.probable} probable, {row.weak} weak, {row.none} no reliable match")
        else:
            QToolTip.hideText()


class TrendsPage(QWidget):
    """Repeats, then the most common materials and tools, for a period and a tool."""

    repeat_rule_changed = Signal(int, int)        # samples, days

    def __init__(self, audit_log, tool_log, count=config.REPEAT_COUNT, days=config.REPEAT_DAYS, parent=None):
        super().__init__(parent)
        self.setObjectName("LibraryPage")                               # the same background
        self.audit_log, self.tool_log = audit_log, tool_log
        self.samples, self.shown = [], []
        self.demo, self.problem = False, ""

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
        titles.addWidget(text_label("Trends", "PageTitle"))
        self.subtitle = text_label("", "Meta", wrap=True)
        titles.addWidget(self.subtitle)
        self.top.addLayout(titles, 1)
        self.period = Segmented("90", choices=PERIODS)
        self.period.changed.connect(lambda _: self.show_samples())
        self.tool = QComboBox()
        self.tool.setMinimumWidth(150)
        self.tool.setAccessibleName("Tool or area")
        self.tool.currentTextChanged.connect(lambda _: self.show_samples())
        self.demo_button = QPushButton(" Demo data")
        self.demo_button.setCheckable(True)
        self.demo_button.setCursor(Qt.PointingHandCursor)
        self.demo_button.setVisible(config.TRENDS_DEMO_DIR.is_dir())
        self.demo_button.toggled.connect(self._toggle_demo)
        self.actions = QWidget()
        actions = FlowLayout(self.actions, spacing=8, row_spacing=8, align="right")
        for widget in (self.period, self.tool, self.demo_button):
            actions.addWidget(widget)
        self.top.addWidget(self.actions, 0, Qt.AlignBottom)
        column.addLayout(self.top)

        self.demo_note = QFrame()
        self.demo_note.setObjectName("Callout")
        self.demo_note.setProperty("kind", "warn")
        note_row = QHBoxLayout(self.demo_note)
        note_row.setContentsMargins(16, 10, 16, 10)
        self.demo_icon = QLabel()
        note_row.addWidget(self.demo_icon)
        note_row.addWidget(text_label("Demo data: these samples are made up.", "Body", wrap=True), 1)
        self.demo_note.hide()
        column.addWidget(self.demo_note)

        self.empty = text_label("", "Body2", wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)
        column.addWidget(self.empty)

        self.repeat_card, repeat_body = section("Repeats")
        self.count_choice = Segmented(str(count), choices=[(str(n), str(n)) for n in COUNTS])
        self.days_choice = Segmented(str(days), choices=[(str(n), str(n)) for n in DAYS])
        for choice in (self.count_choice, self.days_choice):
            choice.changed.connect(self._rule_changed)
        rule = QWidget()
        rule_row = FlowLayout(rule, spacing=8, row_spacing=8)
        for widget in (text_label("Same material on the same tool", "Body2"), self.count_choice, text_label("times in", "Body2"),
                       self.days_choice, text_label("days", "Body2")):
            rule_row.addWidget(widget)
        repeat_body.addWidget(rule)
        self.repeat_rows = QVBoxLayout()
        self.repeat_rows.setSpacing(8)
        repeat_body.addLayout(self.repeat_rows)
        self.no_tool = text_label("", "SectionHint", wrap=True)
        repeat_body.addWidget(self.no_tool)
        column.addWidget(self.repeat_card)

        self.material_card, material_body = section("Materials")
        self.material_chart = RankChart()
        material_body.addWidget(self.material_chart)
        self.tool_card, tool_body = section("Tools")
        self.tool_chart = RankChart()
        tool_body.addWidget(self.tool_chart)
        self.charts = QBoxLayout(QBoxLayout.LeftToRight)
        self.charts.setSpacing(16)
        self.charts.addWidget(self.material_card, 1, Qt.AlignTop)
        self.charts.addWidget(self.tool_card, 1, Qt.AlignTop)
        column.addLayout(self.charts)
        column.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        self.retheme()

    # ------------------------------------------------------------------
    def resizeEvent(self, event):
        """A narrow window: the controls move under the title, and the two rankings under each other."""
        super().resizeEvent(event)
        room = self.width() - 64
        beside = room >= 320 + self.actions.layout().sizeHint().width()
        direction = QBoxLayout.LeftToRight if beside else QBoxLayout.TopToBottom
        if self.top.direction() != direction:
            self.top.setDirection(direction)
            self.actions.layout().side = "right" if beside else "left"
            self.actions.layout().invalidate()
        self.charts.setDirection(QBoxLayout.LeftToRight if room >= 960 else QBoxLayout.TopToBottom)

    def retheme(self):
        self.demo_button.setIcon(icon("flask-conical", Theme.t["ink_2"]))
        self.demo_icon.setPixmap(icon_pixmap("triangle-alert", Theme.t["warn"], 18, self.devicePixelRatioF()))
        self.demo_note.style().unpolish(self.demo_note)
        self.demo_note.style().polish(self.demo_note)
        if self.shown:
            self._show_repeats(self.shown)                              # their icons take the new colour
        for chart in (self.material_chart, self.tool_chart):
            chart.update()

    # ------------------------------------------------------------------
    def refresh(self):
        """Read the records again."""
        self.problem = ""
        try:
            self.samples = demo_samples() if self.demo else read_samples(self.audit_log, self.tool_log)
        except (OSError, ValueError, AttributeError):                  # a damaged log must not stop the window
            self.samples, self.problem = [], "The audit log could not be read."
        self._fill_tools()
        self.show_samples()

    def _fill_tools(self):
        current = self.tool.currentText()
        names = sorted({s.tool for s in self.samples if s.tool != NOT_RECORDED}, key=str.casefold)
        self.tool.blockSignals(True)
        self.tool.clear()
        self.tool.addItems([ALL_TOOLS, *names])
        self.tool.setCurrentText(current if current in names else ALL_TOOLS)
        self.tool.blockSignals(False)

    def _toggle_demo(self, on):
        self.demo = on
        self.demo_note.setVisible(on)
        self.refresh()

    def _rule_changed(self, _):
        self.repeat_rule_changed.emit(int(self.count_choice.value()), int(self.days_choice.value()))
        self.show_samples()

    def show_samples(self):
        """Everything below the title, for the chosen period and tool."""
        samples = in_period(self.samples, int(self.period.value()))
        if self.tool.currentText() not in ("", ALL_TOOLS):
            samples = [s for s in samples if s.tool == self.tool.currentText()]
        self.shown = samples
        number = len(samples)
        self.subtitle.setText(f"{number} sample{'' if number == 1 else 's'}. An exported sample counts once.")
        for widget in (self.repeat_card, self.material_card, self.tool_card):
            widget.setVisible(bool(samples))
        self.empty.setVisible(not samples)
        self.empty.setText(self.problem or ("No samples in this period." if self.samples
                                            else "No samples yet. They appear here once a report is exported."))
        if not samples:
            return
        self.material_chart.set_rows(ranked(samples, "material"))
        self.tool_chart.set_rows(ranked(samples, "tool"))
        self._show_repeats(samples)

    def _show_repeats(self, samples):
        clear_layout(self.repeat_rows)
        found = repeats(samples, int(self.count_choice.value()), int(self.days_choice.value()))
        for repeat in found:
            row = QFrame()
            row.setObjectName("Callout")
            row.setProperty("kind", "warn")
            line = QHBoxLayout(row)
            line.setContentsMargins(12, 8, 12, 8)
            alert = QLabel()
            alert.setPixmap(icon_pixmap("triangle-alert", Theme.t["warn"], 16, self.devicePixelRatioF()))
            line.addWidget(alert)
            line.addWidget(text_label(f"{repeat.material} on {repeat.tool}: {repeat.samples} samples, "
                                      f"{short_date(repeat.first)} to {short_date(repeat.last)}", "Body", wrap=True), 1)
            self.repeat_rows.addWidget(row)
        if not found:
            self.repeat_rows.addWidget(text_label("No repeats in this period.", "Body2"))
        missing = sum(s.tool == NOT_RECORDED for s in samples)
        self.no_tool.setVisible(bool(missing))
        self.no_tool.setText(f"{missing} sample{'' if missing == 1 else 's'} with no tool recorded "
                             f"{'is' if missing == 1 else 'are'} not checked. Enter the tool when exporting a report.")
