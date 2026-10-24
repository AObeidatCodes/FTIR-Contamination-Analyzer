"""
FTIR Contamination Analyzer - the closest matches, side by side

A score says HOW similar two spectra are; this shows WHERE they differ. For the best
four library materials, one small chart each:

    ink line      the sample, as it was compared
    blue line     the library material
    peach wash    the area between the two lines: where the shapes do not agree

Two views (the switch at the top right):
    Spectrum      the absorbance, both scaled 0-1: what a person reads
    Fingerprint   the derivative fingerprints: exactly the two curves the score (Pearson r)
                  is calculated from; the CO2 region, which the score leaves out, is greyed

Move the mouse over a chart to read both values at that wavenumber; click a chart to show
that material in the big figure above ("compare with").

Each chart is drawn once into a picture and then only copied to the screen, so hovering
and scrolling stay smooth.

Short names used in this file:
    t = theme colours    p = the painter    y = a curve on the common grid    r = a Pearson r or one Result
    rect = a rectangle on screen    w = a wavenumber

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from . import config
from .motion import EASE_OUT, MOTION, Card, Look, Segmented, animate, stop, warm_up
from .processing import CO2_MASK, GRID, fingerprint
from .widgets import font, line_pen, polylines

SPECTRUM, FINGERPRINT = "spectrum", "fingerprint"


def scaled(y):
    """0-1 over the points that have data (NaN stays NaN)."""
    y = np.asarray(y, float)
    low, high = np.nanmin(y), np.nanmax(y)
    return (y - low) / (high - low) if high > low else y * 0


class MatchTile(Card):
    """One candidate: its rank, name and score, and a small chart of the sample against it."""

    chosen = Signal(str)
    HEIGHT, HEAD = 216, 52

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rank, self.name, self.r, self.lead = 0, "", 0.0, 0.0
        self.sample = self.reference = None
        self.mask = None                                    # True where the score leaves the data out (CO2)
        self.selected, self.hovered, self.mouse_x = False, False, None
        self._picture = None                                # the chart, drawn once
        self._lift_animation = None
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(240)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_data(self, rank, name, r, lead, sample, reference, mask=None, selected=False):
        self.rank, self.name, self.r, self.lead = rank, name, r, lead
        self.sample, self.reference, self.mask, self.selected = sample, reference, mask, selected
        self.setAccessibleName(f"Match {rank}: {name}, r = {r:.2f}")
        self.setToolTip(f"{name}: click to show it in the big figure")
        self._picture = None
        self.update()

    def set_selected(self, selected):
        if selected != self.selected:
            self.selected = selected
            self.update()

    # --- interaction
    def _lift_to(self, value):
        stop(self._lift_animation)
        self._lift_animation = animate(self, self.lift, value, MOTION["hover"], self._set_lift, EASE_OUT)

    def _set_lift(self, value):
        self.lift = value
        self.update()

    def enterEvent(self, _):
        self.hovered = True
        self._lift_to(1.0)

    def leaveEvent(self, _):
        self.hovered, self.mouse_x = False, None
        self._lift_to(0.0)

    def mouseMoveEvent(self, event):
        self.mouse_x = event.position().x()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.chosen.emit(self.name)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.chosen.emit(self.name)
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._picture = None

    # --- drawing
    def _plot_rect(self):
        body = self.body()
        return QRectF(body.left() + 16, body.top() + self.HEAD, body.width() - 32, body.height() - self.HEAD - 24)

    def _x(self, w, rect):
        return rect.left() + (config.GRID_STOP - w) / (config.GRID_STOP - config.GRID_START) * rect.width()

    def _y(self, v, rect):
        return rect.bottom() - v * rect.height()

    def _lines(self, y, rect):
        """The curve as polylines on screen (one per stretch with data)."""
        x = rect.left() + (config.GRID_STOP - GRID) / (config.GRID_STOP - config.GRID_START) * rect.width()
        return polylines(x, rect.bottom() - np.asarray(y, float) * rect.height())

    def _draw_picture(self):
        """Draw the chart (everything that does not change under the mouse) into a picture."""
        t = Look.t
        dpr = self.devicePixelRatioF() or 1.0
        picture = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        picture.setDevicePixelRatio(dpr)
        picture.fill(Qt.transparent)
        p = QPainter(picture)
        p.setRenderHint(QPainter.Antialiasing)
        lift, self.lift = self.lift, 0.0                            # the picture is drawn resting; moved when lifted
        rect = self._plot_rect()
        self.lift = lift
        if self.sample is not None and self.reference is not None:
            if self.mask is not None and self.mask.any():           # the region the score leaves out
                xs = GRID[self.mask]
                p.fillRect(QRectF(self._x(xs.max(), rect), rect.top(), self._x(xs.min(), rect) - self._x(xs.max(), rect),
                                  rect.height()), QColor(t["surface_2"]))
            # the peach wash: the area between the two curves, point by point
            both = np.isfinite(self.sample) & np.isfinite(self.reference)
            wash = QColor(t["chart_diff"])
            wash.setAlphaF(t["chart_diff_alpha"])
            p.setPen(Qt.NoPen)
            p.setBrush(wash)
            for first, last in _runs(both):
                upper = [QPointF(self._x(w, rect), self._y(v, rect)) for w, v in
                         zip(GRID[first:last], self.sample[first:last])]
                lower = [QPointF(self._x(w, rect), self._y(v, rect)) for w, v in
                         zip(GRID[first:last][::-1], self.reference[first:last][::-1])]
                p.drawPolygon(upper + lower)
            p.setBrush(Qt.NoBrush)
            p.setPen(line_pen(t["chart_reference"], 1.5))
            for line in self._lines(self.reference, rect):
                p.drawPolyline(line)
            p.setPen(line_pen(t["chart_sample"], 1.2))
            for line in self._lines(self.sample, rect):
                p.drawPolyline(line)
        # the axis: a hairline with three wavenumbers
        p.setPen(QPen(QColor(t["chart_axis"]), 1))
        p.drawLine(QPointF(rect.left(), rect.bottom() + 0.5), QPointF(rect.right(), rect.bottom() + 0.5))
        p.setFont(font("caption"))
        p.setPen(QColor(t["muted"]))
        for w in (3000, 2000, 1000):                                # 4000 would sit on the card's edge
            x = self._x(w, rect)
            p.drawText(QRectF(x - 24, rect.bottom() + 4, 48, 16), Qt.AlignCenter, str(w))
        p.end()
        self._picture = picture

    def prepare(self):
        """Draw the chart picture now, if it is missing (see motion.warm_up)."""
        if self._picture is None or self._picture.size() != self.size() * (self.devicePixelRatioF() or 1.0):
            self._draw_picture()

    def paintEvent(self, _):
        t = Look.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = self.body()
        self.paint_card(p, body)
        if self.selected:                                           # shown in the big figure: an accent edge
            p.setPen(QPen(QColor(t["accent"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(body.adjusted(1, 1, -1, -1), self.RADIUS, self.RADIUS)

        # the head: rank, name, score
        left = body.left() + 16
        badge = QRectF(left, body.top() + 16, 24, 24)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["primary"] if self.rank == 1 else t["surface_2"]))
        p.drawRoundedRect(badge, 6, 6)
        p.setFont(font("small", QFont.DemiBold))
        p.setPen(QColor(t["on_primary"] if self.rank == 1 else t["ink_2"]))
        p.drawText(badge, Qt.AlignCenter, str(self.rank))
        score = f"r {self.r:.2f}"
        p.setFont(font("body", QFont.DemiBold))
        score_w = QFontMetrics(p.font()).horizontalAdvance(score)
        p.setPen(QColor(t["ink"]))
        p.drawText(QRectF(body.right() - 16 - score_w, body.top() + 14, score_w, 28), Qt.AlignVCenter, score)
        name_w = body.width() - 32 - 32 - score_w - 12
        p.drawText(QRectF(left + 34, body.top() + 14, name_w, 28), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(p.font()).elidedText(self.name, Qt.ElideRight, int(name_w)))

        # the chart (drawn once), then what follows the mouse
        if self._picture is None or self._picture.size() != self.size() * (self.devicePixelRatioF() or 1.0):
            self._draw_picture()
        p.drawPixmap(QPointF(0, -2 * self.lift), self._picture)
        rect = self._plot_rect()
        if self.mouse_x is not None and rect.left() <= self.mouse_x <= rect.right() and self.sample is not None:
            w = config.GRID_STOP - (self.mouse_x - rect.left()) / rect.width() * (config.GRID_STOP - config.GRID_START)
            a = np.interp(w, GRID, self.sample, left=np.nan, right=np.nan)
            b = np.interp(w, GRID, self.reference, left=np.nan, right=np.nan)
            p.setPen(QPen(QColor(t["muted"]), 1))
            p.drawLine(QPointF(self.mouse_x, rect.top()), QPointF(self.mouse_x, rect.bottom()))
            text = f"{w:.0f} cm⁻¹   sample {a:.2f}   {self.name} {b:.2f}" if np.isfinite(a) and np.isfinite(b) \
                else f"{w:.0f} cm⁻¹"
            fm = QFontMetrics(font("small"))
            box_w = min(fm.horizontalAdvance(text) + 16, rect.width())
            box_x = min(max(rect.left(), self.mouse_x - box_w / 2), rect.right() - box_w)
            box = QRectF(box_x, rect.top() - 4, box_w, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["tooltip"]))
            p.drawRoundedRect(box, 6, 6)
            p.setPen(QColor(t["tooltip_ink"]))
            p.setFont(font("small"))
            p.drawText(box, Qt.AlignCenter, fm.elidedText(text, Qt.ElideRight, int(box_w - 10)))
        if self.hasFocus():
            p.setPen(QPen(QColor(t["accent"]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(body.adjusted(1, 1, -1, -1), self.RADIUS, self.RADIUS)

    def retheme(self):
        self._picture = None
        self.update()


def _runs(mask):
    """(start, stop) of every stretch where mask is True."""
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(int), [0]])))
    return list(zip(edges[::2], edges[1::2]))


class TopMatches(Card):
    """The best four library materials, each compared with the sample in a small chart."""

    chosen = Signal(object)          # the material to show in the big figure (None = the best match)
    COUNT = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = self.library = None
        self.view, self.current = SPECTRUM, None
        title = QLabel("Closest matches")
        title.setObjectName("SectionTitle")
        self.hint = QLabel("where the shapes differ is shaded peach · click one to show it above")
        self.hint.setObjectName("SectionHint")
        self.hint.setWordWrap(True)                                        # two lines on a narrow window
        self.switch = Segmented(SPECTRUM, choices=(("Spectrum", SPECTRUM), ("Fingerprint", FINGERPRINT)))
        self.switch.setToolTip("Fingerprint: the two curves the score (Pearson r) is calculated from")
        self.switch.changed.connect(self.set_view)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(title)
        titles.addWidget(self.hint)
        head.addLayout(titles, 1)
        head.addWidget(self.switch, 0, Qt.AlignTop)
        self.tiles = [MatchTile() for _ in range(self.COUNT)]
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        for i, tile in enumerate(self.tiles):
            tile.chosen.connect(self._choose)
            grid.addWidget(tile, i // 2, i % 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(16)
        layout.addLayout(head)
        layout.addLayout(grid)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(600, 2 * MatchTile.HEIGHT + 120)

    def show_result(self, result, library, current=None):
        self.result, self.library, self.current = result, library, current
        self._fill()

    def set_view(self, view):
        self.view = view
        self.switch.set_value(view)
        self._fill()

    def set_current(self, name):
        """Mark the tile whose material is shown in the big figure."""
        self.current = name
        best = self.result.best if self.result else None
        for tile in self.tiles:
            tile.set_selected(tile.name == (name or best))

    def _fill(self):
        r, library = self.result, self.library
        if r is None:
            return
        best_r = r.ranking[0][1]
        if self.view == FINGERPRINT:
            sample = fingerprint(r.compared)
            mask = CO2_MASK & np.isfinite(sample)
        else:
            sample, mask = scaled(r.compared), None
        for i, tile in enumerate(self.tiles):
            if i >= len(r.ranking):
                tile.hide()
                continue
            name, score = r.ranking[i]
            reference = library.fingerprint_of(name) if self.view == FINGERPRINT else scaled(library.spectra[name])
            tile.set_data(i + 1, name, score, score - best_r, sample, reference, mask,
                          selected=name == (self.current or r.best))
            tile.show()
        warm_up([t for t in self.tiles if not t.isHidden()])          # drawn before they scroll into view

    def _choose(self, name):
        best = self.result.best if self.result else None
        self.set_current(None if name == best else name)
        self.chosen.emit(None if name == best else name)

    def retheme(self):
        for tile in self.tiles:
            tile.retheme()
