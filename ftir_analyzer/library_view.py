"""
FTIR Contamination Analyzer - the Library page

Everything about the reference library, in one place:

    LibraryPage        an "album" of every reference: a category list on the left, a grid of cards
                       on the right (each with its spectrum as the cover), a search field, and the
                       library's validation status at the top
    MaterialCard       one reference: spectrum cover, name, category, where it came from
    SpectrumChart      a spectrum you can trace with the mouse (wavenumber, value and band name)
    MaterialDetail     the sheet that opens for one reference: its spectrum, key bands, where it can
                       come from in a fab, how far it is from its nearest neighbours, and its provenance
    SimilarityMap      every reference against every other one (Pearson r): which pairs could be confused
    AddReferencePanel  adds a reference the lab identified itself, and shows BEFORE saving what it
                       would do: is the library still validated, which existing reference is most
                       similar, and which of the spectra on screen would get a different answer

Short names used in this file:
    t = theme colours    p = the painter    y = a spectrum on the common grid    w = one band position
    r = a Pearson r (a score) or one Result    info = a MaterialInfo (what is known about a reference)

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

from pathlib import Path

import numpy as np
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate,
                               QToolTip, QVBoxLayout, QWidget)

from . import config
from .analysis import NO_MATCH
from .evidence import fab_sources, key_bands
from .inhouse import addition_preview, reference_notes
from .openspecy import CITATION, LICENCE
from .jobs import Job
from .library import reference_on_grid, similarity_matrix
from .motion import (EASE_OUT, MOTION, Card, Segmented, SmoothScrollArea, Spinner, alive, animate, fade_through,
                     make_opaque, snapshot, stop)
from .peaks import band_label, band_table
from .processing import GRID, absorbance
from .spectrum_io import SpectrumFileError, read_spectra
from .theme import CATEGORY_ICONS
from .widgets import Pill, ScoreBars, Theme, chip, clear_layout, font, icon, icon_pixmap, line_pen, polylines

ALL, IN_HOUSE, OPEN_SPECY = "All references", "In-house", "Open Specy"
ESSENTIALS, EXTENDED = "essentials", "extended"
TICKS = (4000, 3500, 3000, 2500, 2000, 1500, 1000)


def scaled(y):
    """0-1 over the points that have data (NaN stays NaN)."""
    y = np.asarray(y, float)
    low, high = np.nanmin(y), np.nanmax(y)
    return (y - low) / (high - low) if high > low else y * 0


def text_label(text="", name="Body", wrap=False):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def section(title, hint=""):
    """A card with a title (and a grey hint). Returns (card, layout for its content)."""
    card = Card()
    outer = QVBoxLayout(card)
    outer.setContentsMargins(18, 14, 18, 16)
    outer.setSpacing(8)
    head = QHBoxLayout()
    head.addWidget(text_label(title, "SectionTitle"))
    head.addStretch()
    if hint:
        head.addWidget(text_label(hint, "SectionHint"))
    outer.addLayout(head)
    body = QVBoxLayout()
    body.setSpacing(8)
    outer.addLayout(body)
    return card, body


# ---------------------------------------------------------------------------- a traceable spectrum
class SpectrumChart(QWidget):
    """A spectrum drawn with the painter, which draws itself in and can be traced with the mouse.

    main      the spectrum (on the common grid), drawn in the library blue
    other     an optional second spectrum (e.g. the selected sample), drawn in ink
    bands     key bands to mark: [(position, relative height)]
    """

    LEFT, RIGHT, TOP, BOTTOM = 14, 14, 22, 30

    def __init__(self, height=230, parent=None):
        super().__init__(parent)
        self.main = self.other = None
        self.main_label, self.other_label, self.bands = "", "", []
        self.progress, self.mouse_x, self._animation = 1.0, None, None
        table = band_table()
        self._table = (table["low"].to_numpy(float), table["high"].to_numpy(float), table["assignment"].tolist())
        self.setMinimumHeight(height)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, main, main_label="", bands=(), other=None, other_label="", animated=False):
        """New curves. animated=True: they start empty and draw themselves in when play() is called."""
        self.main = None if main is None else scaled(main)
        self.other = None if other is None else scaled(other)
        self.main_label, self.other_label, self.bands = main_label, other_label, list(bands)
        stop(self._animation)
        self._draw_in(0.0 if animated else 1.0)

    def play(self):
        """Draw the curves in, from left to right."""
        stop(self._animation)
        self._animation = animate(self, 0.0, 1.0, 800, self._draw_in, EASE_OUT)

    def _draw_in(self, value):
        self.progress = value
        self.update()

    def _plot_rect(self):
        return QRectF(self.LEFT, self.TOP, self.width() - self.LEFT - self.RIGHT,
                      self.height() - self.TOP - self.BOTTOM)

    def _x(self, w, rect):
        """Screen x of a wavenumber (high wavenumbers on the left, as in every FTIR plot)."""
        return rect.left() + (config.GRID_STOP - w) / (config.GRID_STOP - config.GRID_START) * rect.width()

    def _w(self, x, rect):
        return config.GRID_STOP - (x - rect.left()) / rect.width() * (config.GRID_STOP - config.GRID_START)

    def _path(self, y, rect):
        path, drawing = QPainterPath(), False
        limit = rect.left() + rect.width() * self.progress
        for w, v in zip(GRID, y):
            x = self._x(w, rect)
            if x > limit:
                break
            if not np.isfinite(v):
                drawing = False
                continue
            point = QPointF(x, rect.bottom() - v * rect.height() * 0.92)
            path.lineTo(point) if drawing else path.moveTo(point)
            drawing = True
        return path

    def mouseMoveEvent(self, event):
        self.mouse_x = event.position().x()
        self.update()

    def leaveEvent(self, _):
        self.mouse_x = None
        self.update()

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self._plot_rect()
        # axis and ticks
        p.setPen(QPen(QColor(t["chart_axis"]), 1))
        p.drawLine(QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.bottom()))
        p.setFont(font("caption"))
        for w in TICKS:
            x = self._x(w, rect)
            p.setPen(QPen(QColor(t["chart_axis"]), 1))
            p.drawLine(QPointF(x, rect.bottom()), QPointF(x, rect.bottom() + 4))
            p.setPen(QColor(t["muted"]))
            p.drawText(QRectF(x - 30, rect.bottom() + 6, 60, 16), Qt.AlignCenter, str(w))
        p.drawText(QRectF(rect.right() - 160, rect.bottom() + 6, 160, 16), Qt.AlignRight, "cm⁻¹")
        if self.main is None:
            return
        # the curves: a soft wash under the reference, then the lines
        main = self._path(self.main, rect)
        if self.other is None:
            wash = QColor(t["chart_reference"])                       # a faint, flat tint under the line
            wash.setAlphaF(0.07)
            fill = QPainterPath(main)
            fill.lineTo(main.currentPosition().x(), rect.bottom())
            fill.lineTo(rect.left(), rect.bottom())
            p.fillPath(fill, wash)
        p.setBrush(Qt.NoBrush)
        if self.other is not None:
            p.setPen(QPen(QColor(t["chart_sample"]), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(self._path(self.other, rect))
        p.setPen(QPen(QColor(t["chart_reference"]), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(main)
        # key bands: a small mark on the axis, the five tallest also labelled
        p.setFont(font("caption", QFont.Medium))
        for i, (w, _) in enumerate(self.bands):
            x = self._x(w, rect)
            if x > rect.left() + rect.width() * self.progress:
                continue
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["chart_found"]))
            p.drawPolygon([QPointF(x, rect.bottom() - 7), QPointF(x - 4, rect.bottom()), QPointF(x + 4, rect.bottom())])
            if i < 5:
                v = np.interp(w, GRID, np.nan_to_num(self.main))
                y = rect.bottom() - v * rect.height() * 0.92
                p.setPen(QColor(t["ink_2"]))
                p.drawText(QRectF(x - 24, y - 17, 48, 14), Qt.AlignCenter, f"{w:.0f}")
        # legend (only with two curves)
        if self.other is not None:
            x = rect.left() + 4
            for colour, label in ((t["chart_sample"], self.other_label), (t["chart_reference"], self.main_label)):
                p.setPen(QPen(QColor(colour), 2.4, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x, 8), QPointF(x + 16, 8))
                p.setPen(QColor(t["ink_2"]))
                p.setFont(font("small"))
                p.drawText(QRectF(x + 22, 0, 260, 16), Qt.AlignVCenter | Qt.AlignLeft, label)
                x += 30 + QFontMetrics(font("small")).horizontalAdvance(label)
        # tracing under the mouse: a cursor line, a dot on the curve, and a small label
        if self.mouse_x is not None and rect.left() <= self.mouse_x <= rect.right():
            w = self._w(self.mouse_x, rect)
            v = np.interp(w, GRID, self.main, left=np.nan, right=np.nan)
            p.setPen(QPen(QColor(t["muted"]), 1))
            p.drawLine(QPointF(self.mouse_x, rect.top()), QPointF(self.mouse_x, rect.bottom()))
            low, high, names = self._table
            hits = [names[i] for i in np.flatnonzero((low <= w) & (high >= w))]
            text = f"{w:.0f} cm⁻¹" + (f"   {v:.2f}" if np.isfinite(v) else "") + (f"   {hits[0]}" if hits else "")
            if np.isfinite(v):
                p.setPen(QPen(QColor(t["chart_surface"]), 1.5))
                p.setBrush(QColor(t["chart_reference"]))
                p.drawEllipse(QPointF(self.mouse_x, rect.bottom() - v * rect.height() * 0.92), 4, 4)
            fm = QFontMetrics(font("small"))
            box_w = min(fm.horizontalAdvance(text) + 18, rect.width())
            box_x = min(max(rect.left(), self.mouse_x - box_w / 2), rect.right() - box_w)
            box = QRectF(box_x, 0, box_w, 20)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["tooltip"]))
            p.drawRoundedRect(box, 6, 6)
            p.setPen(QColor(t["tooltip_ink"]))
            p.setFont(font("small"))
            p.drawText(box, Qt.AlignCenter, fm.elidedText(text, Qt.ElideRight, int(box_w - 12)))


# ---------------------------------------------------------------------------- one card of the album
class MaterialCard(Card):
    """One reference in the album: its spectrum as the cover, its name and where it came from.

    Lifts a little under the mouse; click (or Enter) opens the details.
    """

    opened = Signal(str)
    WIDTH, HEIGHT, COVER = 240, 240, 120

    def __init__(self, name, info, y, n_bands, parent=None):
        super().__init__(parent)
        self.name, self.info, self.n_bands = name, info, n_bands
        self.curve = scaled(y)
        self.glow, self._animation, self._glow_animation, self._picture = 0.0, None, None, None
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(self.WIDTH)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"{name}, {info.category}, {info.source}")
        self.setToolTip(f"{name}: open the details")

    # --- interaction
    def _lift_to(self, value):
        stop(self._animation)
        self._animation = animate(self, self.lift, value, MOTION["hover"], self._set_lift, EASE_OUT)

    def _set_lift(self, value):
        self.lift = value
        self.update()

    def enterEvent(self, _):
        self._lift_to(1.0)

    def leaveEvent(self, _):
        self._lift_to(0.0)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.opened.emit(self.name)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.opened.emit(self.name)
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._picture = None

    def retheme(self):
        self._picture = None
        self.update()

    def pulse(self):
        """A short accent glow, e.g. when this reference was just added."""
        stop(self._glow_animation)
        self._glow_animation = animate(self, 1.0, 0.0, 2200, self._set_glow, QEasingCurve.InQuad)

    def _set_glow(self, value):
        self.glow = value
        self.update()

    # --- drawing
    def _draw_picture(self, body):
        """Everything inside the card (cover, spectrum, text), drawn once into a picture."""
        t = Theme.t
        dpr = self.devicePixelRatioF() or 1.0
        picture = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        picture.setDevicePixelRatio(dpr)
        picture.fill(Qt.transparent)
        p = QPainter(picture)
        p.setRenderHint(QPainter.Antialiasing)
        in_house = self.info.origin == "in-house"

        # the cover: a quiet grey panel with the spectrum on it, clipped to the card's top corners
        cover = QRectF(body.left() + 1, body.top() + 1, body.width() - 2, self.COVER)
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(body.adjusted(1, 1, -1, -1), self.RADIUS - 1, self.RADIUS - 1)
        p.setClipPath(clip)
        p.fillRect(cover, QColor(t["surface_2"]))
        plot = cover.adjusted(16, 36, -16, -12)
        x = plot.left() + (config.GRID_STOP - GRID) / (config.GRID_STOP - config.GRID_START) * plot.width()
        p.setPen(line_pen(t["chart_reference"], 1.5))
        p.setBrush(Qt.NoBrush)                                           # a line, never a filled shape
        for line in polylines(x, plot.bottom() - self.curve * plot.height()):
            p.drawPolyline(line)
        p.restore()
        p.setPen(QPen(QColor(t["line"]), 1))
        p.drawLine(QPointF(body.left() + 1, cover.bottom()), QPointF(body.right() - 1, cover.bottom()))

        # category icon; an "In-house" tag on the right
        p.drawPixmap(int(body.left() + 16), int(body.top() + 14),
                     icon_pixmap(CATEGORY_ICONS.get(self.info.category, "flask-conical"), t["muted"], 16, dpr))
        if in_house:
            p.setFont(font("small", QFont.DemiBold))
            text = "In-house"
            badge_w = QFontMetrics(p.font()).horizontalAdvance(text) + 32
            badge = QRectF(body.right() - badge_w - 12, body.top() + 10, badge_w, 24)
            p.setPen(QPen(QColor(t["line"]), 1))
            p.setBrush(QColor(t["surface"]))
            p.drawRoundedRect(badge, 6, 6)
            p.drawPixmap(int(badge.left() + 8), int(badge.top() + 5), icon_pixmap("shield-plus", t["accent_ink"], 14, dpr))
            p.setPen(QColor(t["accent_ink"]))
            p.drawText(badge.adjusted(26, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

        # the text: name, category, then where it came from and how many key bands
        left, width = body.left() + 16, body.width() - 32
        name_font = font("title", QFont.DemiBold)
        p.setFont(name_font)
        p.setPen(QColor(t["ink"]))
        p.drawText(QRectF(left, cover.bottom() + 12, width, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(name_font).elidedText(self.name, Qt.ElideRight, int(width)))
        p.setFont(font("small"))
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(left, cover.bottom() + 36, width, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(font("small")).elidedText(self.info.category, Qt.ElideRight, int(width)))
        # the licence only when it fits, the detail sheet always has it in full
        metrics = QFontMetrics(font("small"))
        source = f"In-house · {self.info.added_by}" if in_house else f"{self.info.source} · {self.info.licence}"
        if not in_house and metrics.horizontalAdvance(source) > width * 0.6:
            source = self.info.source
        p.setPen(QColor(t["ink_2"]))
        p.drawText(QRectF(left, body.bottom() - 36, width * 0.6, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   metrics.elidedText(source, Qt.ElideRight, int(width * 0.6)))
        p.setPen(QColor(t["muted"]))
        p.drawText(QRectF(left, body.bottom() - 36, width, 24), Qt.AlignRight | Qt.AlignVCenter,
                   f"{self.n_bands} key bands")
        p.end()
        self._picture = picture

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        lift, self.lift = self.lift, 0.0
        resting = self.body()                                            # the picture is drawn resting ...
        self.lift = lift
        if self._picture is None or self._picture.size() != self.size() * (self.devicePixelRatioF() or 1.0):
            self._draw_picture(resting)
        body = self.body()
        self.paint_card(p, body)
        p.drawPixmap(QPointF(0, body.top() - resting.top()), self._picture)   # ... and moved with the card

        # keyboard focus ring, and the glow after it was added
        for strength, width_px in ((1.0 if self.hasFocus() else 0.0, 2.0), (self.glow, 3.0)):
            if strength > 0.01:
                ring = QColor(t["accent"])
                ring.setAlphaF(strength)
                p.setPen(QPen(ring, width_px))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(body.adjusted(1, 1, -1, -1), self.RADIUS, self.RADIUS)


class CardGrid(QWidget):
    """Places the visible cards in as many equal columns as fit the width."""

    GAP = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = []
        self.setObjectName("LibraryGrid")

    def set_cards(self, cards):
        for card in self.cards:
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self.cards = list(cards)
        for card in self.cards:
            card.setParent(self)
            card.show()
        self.relayout()

    def visible_cards(self):
        return [c for c in self.cards if not c.isHidden()]

    def relayout(self):
        cards, width = self.visible_cards(), max(1, self.width())
        columns = max(1, (width + self.GAP) // (MaterialCard.WIDTH + self.GAP))
        card_w = (width - self.GAP * (columns - 1)) // columns
        for i, card in enumerate(cards):
            row, column = divmod(i, columns)
            card.setGeometry(column * (card_w + self.GAP), row * (MaterialCard.HEIGHT + self.GAP),
                             card_w, MaterialCard.HEIGHT)
        rows = (len(cards) + columns - 1) // columns
        self.setMinimumHeight(max(0, rows * (MaterialCard.HEIGHT + self.GAP) - self.GAP))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout()


# ---------------------------------------------------------------------------- the category list
class CategoryDelegate(QStyledItemDelegate):
    """One row of the category list: icon, name and the number of references in it."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 40)

    def paint(self, p, option, index):
        t = Theme.t
        name, count = index.data(Qt.UserRole), index.data(Qt.UserRole + 1)
        rect = QRectF(option.rect.adjusted(6, 1, -6, -1))
        selected = bool(option.state & QStyle.State_Selected)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if selected:                                    # the same quiet selection as the list of spectra
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["accent_soft"]))
            p.drawRoundedRect(rect, 8, 8)
            p.setBrush(QColor(t["accent"]))
            p.drawRoundedRect(QRectF(rect.left() + 2, rect.center().y() - 10, 3, 20), 1.5, 1.5)
        elif option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["surface_2"]))
            p.drawRoundedRect(rect, 8, 8)
        p.drawPixmap(int(rect.left() + 14), int(rect.center().y() - 9),
                     icon_pixmap(CATEGORY_ICONS.get(name, "flask-conical"),
                                 t["accent_ink"] if selected else t["muted"], 18, p.device().devicePixelRatioF()))
        p.setFont(font("small", QFont.DemiBold if selected else QFont.Medium))
        p.setPen(QColor(t["ink"] if selected else t["ink_2"]))
        p.drawText(rect.adjusted(42, 0, -40, 0), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(p.font()).elidedText(name, Qt.ElideRight, int(rect.width() - 84)))
        p.setFont(font("small"))
        p.setPen(QColor(t["muted"]))
        p.drawText(rect.adjusted(0, 0, -14, 0), Qt.AlignVCenter | Qt.AlignRight, str(count))
        p.restore()


# ---------------------------------------------------------------------------- the page
class LibraryPage(QWidget):
    """The album of every reference, with categories, search and the library's validation status."""

    open_material = Signal(str)
    add_requested = Signal()
    similarity_requested = Signal()
    mode_changed = Signal(str)            # "essentials" or "extended"
    openspecy_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LibraryPage")
        self.library = self.validation = None
        self.cards = {}

        # left: the categories
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(272)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(8, 24, 8, 16)
        side_layout.setSpacing(8)
        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 8, 0)
        head.addWidget(text_label("Library", "SidebarTitle"))
        head.addStretch()
        self.count = text_label("", "Count")
        head.addWidget(self.count)
        side_layout.addLayout(head)
        self.categories = QListWidget()
        self.categories.setItemDelegate(CategoryDelegate(self.categories))
        self.categories.setMouseTracking(True)
        self.categories.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.categories.currentRowChanged.connect(lambda _: self._filter(animated=True))
        side_layout.addWidget(self.categories, 1)
        self.change_log_hint = text_label("Every addition and removal is kept in records/inhouse_library/"
                                          "library_changes.csv (append-only).", "SectionHint", wrap=True)
        self.change_log_hint.setContentsMargins(8, 0, 8, 0)
        side_layout.addWidget(self.change_log_hint)

        # right: header, validation, search, the grid of cards
        self.scroll = SmoothScrollArea()
        content = QWidget()
        content.setObjectName("LibraryGrid")
        self.scroll.setWidget(content)
        column = QVBoxLayout(content)
        column.setContentsMargins(30, 26, 30, 30)
        column.setSpacing(14)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(text_label("REFERENCE LIBRARY", "Eyebrow"))
        self.title = text_label(ALL, "PageTitle")
        titles.addWidget(self.title)
        self.subtitle = text_label("", "Meta", wrap=True)
        titles.addWidget(self.subtitle)
        top.addLayout(titles, 1)
        self.mode = Segmented(ESSENTIALS, choices=(("Fab essentials", ESSENTIALS), ("Extended", EXTENDED)))
        self.mode.setToolTip("Extended: also the Open Specy references (downloaded or imported on this computer)")
        self.mode.changed.connect(self.mode_changed.emit)
        self.openspecy_button = QPushButton(" Open Specy…")
        self.openspecy_button.setToolTip("Get more references from the Open Specy library (download or import)")
        self.map_button = QPushButton(" Similarity map")
        self.map_button.setToolTip("Every reference against every other: which ones could be confused")
        self.add_button = QPushButton(" Add a reference…")
        self.add_button.setObjectName("Primary")
        self.add_button.setToolTip("Add a material the lab identified itself (validated before it is saved)")
        top.addWidget(self.mode, 0, Qt.AlignBottom)
        top.addSpacing(8)
        for button in (self.openspecy_button, self.map_button, self.add_button):
            button.setCursor(Qt.PointingHandCursor)
            top.addWidget(button, 0, Qt.AlignBottom)
        self.openspecy_button.clicked.connect(self.openspecy_requested.emit)
        self.map_button.clicked.connect(self.similarity_requested.emit)
        self.add_button.clicked.connect(self.add_requested.emit)
        column.addLayout(top)

        self.banner = QFrame()
        self.banner.setObjectName("Callout")
        banner_row = QHBoxLayout(self.banner)
        banner_row.setContentsMargins(14, 10, 14, 10)
        self.banner_icon = QLabel()
        self.banner_text = text_label("", "Body", wrap=True)
        self.banner_text.setTextFormat(Qt.RichText)
        banner_row.addWidget(self.banner_icon, 0, Qt.AlignTop)
        banner_row.addSpacing(4)
        banner_row.addWidget(self.banner_text, 1)
        column.addWidget(self.banner)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by material, category or source")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self._filter(animated=False))
        column.addWidget(self.search)
        self.grid = CardGrid()
        column.addWidget(self.grid)
        self.nothing = text_label("No reference matches the search.", "Body2")
        self.nothing.setAlignment(Qt.AlignCenter)
        self.nothing.hide()
        column.addWidget(self.nothing)
        column.addStretch()

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(side)
        row.addWidget(self.scroll, 1)
        self.retheme()

    # ------------------------------------------------------------------
    def retheme(self):
        t = Theme.t
        self.map_button.setIcon(icon("grid-3x3", t["ink_2"]))
        self.openspecy_button.setIcon(icon("layers", t["ink_2"]))
        self.add_button.setIcon(icon("plus", t["on_accent"]))
        if not self.search.actions():
            self.search.addAction(icon("search", t["muted"], 16), QLineEdit.LeadingPosition)
        self.search.actions()[0].setIcon(icon("search", t["muted"], 16))
        self._update_banner()
        for card in self.cards.values():
            card.retheme()
        make_opaque(self.scroll.widget(), t["paper"])
        self.categories.viewport().update()

    def set_mode(self, mode, available):
        """Which library is in use; the switch is only offered once Open Specy references exist."""
        self.mode.set_value(mode, animated=False)
        self.mode.setVisible(available)

    def set_library(self, library, validation):
        """Show a (new) library: rebuild the cards and the category counts."""
        self.library, self.validation = library, validation
        self.cards = {}
        cards = []
        for name, y in library.spectra.items():
            card = MaterialCard(name, library.info_of(name), y, len(key_bands(y)))
            card.opened.connect(self.open_material.emit)
            self.cards[name] = card
            cards.append(card)
        self.grid.set_cards(cards)
        self._fill_categories()
        self._update_banner()
        self._filter(animated=False)

    def _fill_categories(self):
        current = self.categories.currentItem().data(Qt.UserRole) if self.categories.currentItem() else ALL
        infos = [self.library.info_of(n) for n in self.library.spectra]
        counts = {ALL: len(infos), IN_HOUSE: sum(i.origin == "in-house" for i in infos),
                  OPEN_SPECY: sum(i.origin == "open specy" for i in infos)}
        for category in config.CATEGORIES:
            counts[category] = sum(i.category == category for i in infos)
        for info in infos:                                            # categories typed in for in-house references
            counts.setdefault(info.category, sum(i.category == info.category for i in infos))
        self.categories.blockSignals(True)
        self.categories.clear()
        for name, count in counts.items():
            if count or name in (ALL, IN_HOUSE):
                if name == OPEN_SPECY and not count:
                    continue
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, name)
                item.setData(Qt.UserRole + 1, count)
                item.setToolTip(f"{count} reference{'s' if count != 1 else ''}")
                self.categories.addItem(item)
                if name == current:
                    self.categories.setCurrentItem(item)
        if self.categories.currentRow() < 0:
            self.categories.setCurrentRow(0)
        self.categories.blockSignals(False)
        shipped = len(infos) - counts[IN_HOUSE] - counts[OPEN_SPECY]
        self.count.setText(f"{len(infos)}")
        self.subtitle_base = (f"{shipped} shipped" + (f" + {counts[IN_HOUSE]} in-house" if counts[IN_HOUSE] else "")
                              + (f" + {counts[OPEN_SPECY]} Open Specy" if counts[OPEN_SPECY] else "")
                              + f" references, all compared in {self.library.mode} mode")

    def _update_banner(self):
        v, t = self.validation, Theme.t
        if v is None:
            return
        kind = "good" if v.passed else "bad"
        self.banner.setProperty("kind", kind)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner_icon.setPixmap(icon_pixmap("shield-check" if v.passed else "shield-alert", t[kind], 20,
                                               self.devicePixelRatioF() or 2.0))
        verdict = "Validated." if v.passed else "NOT validated."
        self.banner_text.setText(
            f"<b style='color:{t[kind]}'>{verdict}</b> Impostor test: each reference is searched for with itself "
            f"removed. The best <i>wrong</i> match is {v.material} → {v.impostor} at r = {v.score:.2f}, "
            + (f"below the 'probable' threshold {config.PROBABLE_R}." if v.passed else
               f"which reaches 'probable' ({config.PROBABLE_R}): two references cannot be told apart."))

    def _filter(self, animated=True):
        if self.library is None:
            return
        item = self.categories.currentItem()
        category = item.data(Qt.UserRole) if item else ALL
        words = self.search.text().lower().split()
        shown = []
        for name, card in self.cards.items():
            info = card.info
            in_category = (category == ALL or (category == IN_HOUSE and info.origin == "in-house")
                           or (category == OPEN_SPECY and info.origin == "open specy") or info.category == category)
            text = f"{name} {info.category} {info.source} {info.original_name} {info.origin}".lower()
            visible = in_category and all(word in text for word in words)
            card.setVisible(visible)
            if visible:
                shown.append(card)
        viewport = self.scroll.viewport()
        before = snapshot(viewport) if animated and self.isVisible() else None
        self.grid.relayout()
        self.nothing.setVisible(not shown)
        self.title.setText(category)
        self.subtitle.setText(self.subtitle_base if category == ALL
                              else f"{len(shown)} of {len(self.cards)} references · {self.subtitle_base}")
        if before is not None:                                          # a quick fade-through to the new set
            self.scroll.scroll_to_top()
            fade_through(viewport, before, snapshot(viewport), dy=8, duration=MOTION["content"] - 60)

    def highlight(self, name):
        """Show one reference: select its category, scroll to its card and let it glow."""
        card = self.cards.get(name)
        if card is None:
            return
        self.search.clear()
        self.categories.setCurrentRow(0)

        def show():
            if alive(card):
                self.scroll.ensureWidgetVisible(card, 40, 80)
                card.pulse()

        QTimer.singleShot(60, self, show)


# ---------------------------------------------------------------------------- details of one reference
class MaterialDetail(QWidget):
    """The content of the sheet for one reference."""

    compare = Signal(str)
    remove = Signal(str)
    show_file = Signal(str)

    def __init__(self, library, name, similarity, current=None):
        super().__init__()
        t = Theme.t
        info = library.info_of(name)
        y = library.spectra[name]
        bands = key_bands(y)
        column = QVBoxLayout(self)
        column.setContentsMargins(24, 16, 24, 32)
        column.setSpacing(16)

        # what it is
        row = QHBoxLayout()
        row.setSpacing(8)
        tag = QLabel()
        tag.setPixmap(icon_pixmap(CATEGORY_ICONS.get(info.category, "flask-conical"), t["accent_ink"], 18,
                                  self.devicePixelRatioF() or 2.0))
        row.addWidget(tag)
        row.addWidget(text_label(info.category, "Body2"))
        row.addSpacing(6)
        row.addWidget(Pill("good", "In-house reference" if info.origin == "in-house" else "Validated reference",
                           "shield-plus" if info.origin == "in-house" else "badge-check"))
        row.addStretch()
        column.addLayout(row)

        # the spectrum (with the selected sample on top, if there is one)
        chart_card, chart_body = section("Reference spectrum", f"compared in {library.mode} mode, scaled 0–1")
        self.chart = SpectrumChart(240)
        if current is not None:
            self.chart.set_data(y, name, bands, current.compared, current.name, animated=True)
        else:
            self.chart.set_data(y, name, bands, animated=True)
        chart_body.addWidget(self.chart)
        chart_body.addWidget(text_label("Move the mouse over the spectrum to read the wavenumber, the value and "
                                        "the band. Green marks = key bands (≥ "
                                        f"{config.KEY_SHARE:.0%} of the tallest band).", "SectionHint", wrap=True))
        column.addWidget(chart_card)

        # key bands
        band_card, band_body = section("Key bands", "height relative to the tallest band")
        band_grid = QGridLayout()
        band_grid.setHorizontalSpacing(14)
        band_grid.setVerticalSpacing(5)
        for n, (w, h) in enumerate(sorted(bands, key=lambda band: -band[0])[:12]):
            names = band_label(w).split(" (", 1)[1].rstrip(")")
            band_grid.addWidget(chip(f"{w:.0f}"), n, 0)
            band_grid.addWidget(text_label(names, "Body2", wrap=True), n, 1)
            band_grid.addWidget(text_label(f"{h:.0%}", "Meta"), n, 2, Qt.AlignRight)
        band_grid.setColumnStretch(1, 1)
        band_body.addLayout(band_grid)
        column.addWidget(band_card)

        # where it can come from in a fab
        fab_card, fab_body = section("Where it can come from in a fab")
        sources = fab_sources(name, library)
        if sources:
            fab_body.addWidget(text_label(sources[0][:1].upper() + sources[0][1:] + ".", "Body", wrap=True))
            check = text_label(f"<b>Check next:</b> {sources[1]}.", "Body2", wrap=True)
            check.setTextFormat(Qt.RichText)
            fab_body.addWidget(check)
        else:
            fab_body.addWidget(text_label("Nothing recorded for this material yet.", "Body2", wrap=True))
        column.addWidget(fab_card)

        # how it stands out from the others
        names, matrix = similarity
        i = names.index(name)
        nearest = sorted(((names[j], float(matrix[i, j])) for j in range(len(names)) if j != i),
                         key=lambda pair: -pair[1])[:5]
        near_card, near_body = section("How it stands out", "the five most similar references")
        closest, score = nearest[0]
        fine = score < config.PROBABLE_R
        near_body.addWidget(text_label(
            f"The most similar other reference is {closest} at r = {score:.2f}: "
            + ("below 0.95, so the two can be told apart." if fine else
               "at or above 0.95, so the program cannot tell the two apart. Confirm such samples another way."),
            "Body2", wrap=True))
        bars = ScoreBars()
        bars.set_data(nearest, NO_MATCH)
        near_body.addWidget(bars)
        column.addWidget(near_card)

        # where it came from
        prov_card, prov_body = section("Where it came from", "provenance")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        facts = [("Source", info.source), ("Licence", info.licence), ("Measured by", info.mode),
                 ("Contributor", info.contributor), ("Name in the source", info.original_name)]
        if info.origin == "in-house":
            facts = [("Added by", info.added_by), ("Added on", info.added_at.replace("T", " ")),
                     ("Identity confirmed by", info.confirmation), ("Made from", info.original_name),
                     ("Measured by", info.mode), ("Notes", info.notes)]
        facts += [("File", info.file), ("File SHA-256", info.sha256)]
        for n, (key, value) in enumerate(f for f in facts if f[1]):
            grid.addWidget(text_label(key, "FactLabel"), n, 0, Qt.AlignTop)
            shown = f"{value[:20]}…{value[-12:]}" if key == "File SHA-256" else value   # fits the sheet
            value_label = text_label(shown, "Mono" if key in ("File", "File SHA-256") else "Body2", wrap=True)
            value_label.setToolTip(value)                                    # the full value
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(value_label, n, 1)
        grid.setColumnStretch(1, 1)
        prov_body.addLayout(grid)
        column.addWidget(prov_card)

        # actions
        actions = QHBoxLayout()
        if current is not None:
            compare = QPushButton(f" Compare with {current.name}")
            compare.setIcon(icon("git-compare-arrows", t["on_accent"]))
            compare.setObjectName("Primary")
            compare.clicked.connect(lambda: self.compare.emit(name))
            actions.addWidget(compare)
        show = QPushButton(" Show the file")
        show.setIcon(icon("external-link", t["ink_2"]))
        show.clicked.connect(lambda: self.show_file.emit(name))
        actions.addWidget(show)
        actions.addStretch()
        if info.origin == "in-house":
            remove = QPushButton(" Remove from the library…")
            remove.setObjectName("Danger")
            remove.setIcon(icon("trash-2", t["bad"]))
            remove.setToolTip("Takes it out of the library. The file and its history are kept.")
            remove.clicked.connect(lambda: self.remove.emit(name))
            actions.addWidget(remove)
        for button in (actions.itemAt(k).widget() for k in range(actions.count())):
            if button:
                button.setCursor(Qt.PointingHandCursor)
        column.addLayout(actions)
        column.addStretch()

    def play(self):
        """Called when the sheet has arrived: the spectrum draws itself in."""
        self.chart.play()


# ---------------------------------------------------------------------------- the similarity map
class SimilarityMap(QWidget):
    """Every reference against every other (Pearson r of the fingerprints), as a grid of coloured cells.

    Light = different, dark = similar. A red frame marks a pair at or above 'probable' (0.95):
    two references the program could not tell apart. Hover a cell to read the pair.
    """

    CELL = 34

    def __init__(self, names, matrix, worst=None, parent=None):
        super().__init__(parent)
        self.names, self.matrix, self.worst = names, matrix, worst
        self.hover, self.progress = None, 0.0
        fm = QFontMetrics(font("small"))
        self.label_w = max(fm.horizontalAdvance(n) for n in names) + 14
        self.top = int(self.label_w * 0.72) + 10
        size = len(names) * self.CELL
        self.setFixedSize(self.label_w + size + int(self.label_w * 0.66), self.top + size + 8)
        self.setMouseTracking(True)

    def play(self):
        """Fill the cells in, from the top-left corner along the diagonal."""
        animate(self, 0.0, 1.0, 700, self._grow, EASE_OUT)

    def _grow(self, value):
        self.progress = value
        self.update()

    def _cell(self, i, j):
        return QRectF(self.label_w + j * self.CELL, self.top + i * self.CELL, self.CELL, self.CELL)

    def colour(self, r):
        steps = Theme.t["sequence"]
        return QColor(steps[int(round(max(0.0, min(1.0, r)) * (len(steps) - 1)))])

    def mouseMoveEvent(self, event):
        x, y = event.position().x() - self.label_w, event.position().y() - self.top
        n = len(self.names)
        cell = (int(y // self.CELL), int(x // self.CELL)) if 0 <= x < n * self.CELL and 0 <= y < n * self.CELL else None
        if cell != self.hover:
            self.hover = cell
            self.update()
        if cell and cell[0] != cell[1]:
            a, b = self.names[cell[0]], self.names[cell[1]]
            r = self.matrix[cell]
            verdict = ("below 0.95: can be told apart" if r < config.PROBABLE_R
                       else "at or above 0.95: could be confused")
            QToolTip.showText(event.globalPosition().toPoint(), f"<b>{a}</b> vs <b>{b}</b><br>r = {r:.2f}, {verdict}",
                              self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.names)
        hi, hj = self.hover if self.hover else (-1, -1)
        # labels: rows on the left, columns slanted on top
        for k, name in enumerate(self.names):
            strong = k in (hi, hj)
            p.setFont(font("small", QFont.DemiBold if strong else QFont.Normal))
            p.setPen(QColor(t["ink"] if strong else t["ink_2"]))
            p.drawText(QRectF(0, self.top + k * self.CELL, self.label_w - 8, self.CELL),
                       Qt.AlignVCenter | Qt.AlignRight, name)
            p.save()
            p.translate(self.label_w + k * self.CELL + self.CELL / 2 + 4, self.top - 6)
            p.rotate(-50)
            p.drawText(QRectF(0, -8, self.label_w, 16), Qt.AlignVCenter | Qt.AlignLeft, name)
            p.restore()
        # cells: they fill in from the top-left corner along the diagonal
        p.setFont(font("caption", QFont.Medium))
        for i in range(n):
            for j in range(n):
                share = min(1.0, max(0.0, self.progress * 2.2 - (i + j) / (2 * n)))
                if share <= 0:
                    continue
                rect = self._cell(i, j).adjusted(1, 1, -1, -1)
                if i == j:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(t["surface_2"]))
                    p.drawRoundedRect(rect, 4, 4)
                    continue
                r = float(self.matrix[i, j])
                colour = self.colour(r)
                colour.setAlphaF(share)
                p.setPen(Qt.NoPen)
                p.setBrush(colour)
                p.drawRoundedRect(rect, 4, 4)
                light = colour.lightnessF() > 0.62
                p.setPen(QColor(0x1D, 0x1D, 0x1F) if light else QColor("#FFFFFF"))
                text = f"{abs(r):.2f}"[1:]                                   # .90, and −.03 for a negative r
                p.drawText(rect, Qt.AlignCenter, ("−" if r < 0 else "") + text)
                if r >= config.PROBABLE_R:                                # could be confused: a red frame
                    p.setPen(QPen(QColor(t["bad"]), 2))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
                elif self.worst and {self.names[i], self.names[j]} == set(self.worst):
                    p.setPen(QPen(QColor(t["ink"]), 1.6, Qt.DashLine))     # the impostor test's record pair
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
        if self.hover:                                                    # the hovered row and column
            p.setPen(QPen(QColor(t["ink"]), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(self.label_w, self.top + hi * self.CELL, n * self.CELL, self.CELL))
            p.drawRect(QRectF(self.label_w + hj * self.CELL, self.top, self.CELL, n * self.CELL))


class ColourScale(QWidget):
    """The legend of the similarity map: the colour ramp from 0 to 1 with the two thresholds."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        self.setMinimumWidth(320)

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bar = QRectF(8, 6, self.width() - 16, 12)
        ramp = QLinearGradient(bar.topLeft(), bar.topRight())
        steps = t["sequence"]
        for k, colour in enumerate(steps):
            ramp.setColorAt(k / (len(steps) - 1), QColor(colour))
        p.setPen(Qt.NoPen)
        p.setBrush(ramp)
        p.drawRoundedRect(bar, 6, 6)
        p.setFont(font("caption"))
        for value, text in ((0.0, "0 different"), (config.WEAK_R, f"{config.WEAK_R} weak"),
                            (config.PROBABLE_R, f"{config.PROBABLE_R} probable"), (1.0, "1 identical")):
            x = bar.left() + value * bar.width()
            p.setPen(QPen(QColor(t["ink_2"]), 1))
            p.drawLine(QPointF(x, bar.bottom() + 2), QPointF(x, bar.bottom() + 7))
            align = Qt.AlignLeft if value == 0 else Qt.AlignRight if value >= 0.95 else Qt.AlignHCenter
            box = QRectF(x - (0 if value == 0 else 120 if value >= 0.95 else 60), bar.bottom() + 8, 120, 16)
            p.setPen(QColor(t["muted"]))
            p.drawText(box, align | Qt.AlignVCenter, text)


class SimilarityPanel(QWidget):
    """The content of the similarity-map sheet: the explanation, the map and the closest pairs as a table."""

    def __init__(self, library, validation, similarity):
        super().__init__()
        names, matrix = similarity
        column = QVBoxLayout(self)
        column.setContentsMargins(22, 16, 22, 26)
        column.setSpacing(14)
        column.addWidget(text_label(
            "Each cell is the score (Pearson r) one reference gets against another. The verdict 'probable' needs "
            f"r ≥ {config.PROBABLE_R}, so every pair must stay below it: then no material can be mistaken for "
            "another. A red frame would mark a pair that breaks this; the dashed frame marks the closest pair, the "
            "one the impostor test reports.", "Body2", wrap=True))
        card, body = section("Similarity map", f"{len(names)} references · hover a cell")
        holder = QHBoxLayout()
        self.map = SimilarityMap(names, matrix, (validation.material, validation.impostor))
        holder.addWidget(self.map)
        holder.addStretch()
        body.addLayout(holder)
        body.addWidget(ColourScale())
        column.addWidget(card)

        # the same information as a table: the closest pairs
        pairs = sorted(((names[i], names[j], float(matrix[i, j])) for i in range(len(names))
                        for j in range(i + 1, len(names))), key=lambda pair: -pair[2])[:8]
        table_card, table_body = section("The closest pairs", "the same data, as a table")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        for k, header in enumerate(("Pair", "r", "Can be told apart?")):
            grid.addWidget(text_label(header, "FactLabel"), 0, k)
        for row, (a, b, r) in enumerate(pairs, start=1):
            grid.addWidget(text_label(f"{a}  ↔  {b}", "Body"), row, 0)
            grid.addWidget(text_label(f"{r:.2f}", "Body"), row, 1)
            grid.addWidget(Pill("good", "Yes", "circle-check") if r < config.PROBABLE_R
                           else Pill("bad", "No", "triangle-alert"), row, 2)
        grid.setColumnStretch(0, 1)
        table_body.addLayout(grid)
        column.addWidget(table_card)
        column.addStretch()

    def play(self):
        """Called when the sheet has arrived."""
        self.map.play()


# ---------------------------------------------------------------------------- adding a reference
class AddReferencePanel(QWidget):
    """Adds a reference, and shows what it would do before anything is saved.

    1  the spectrum: the selected result, or a file (a reference file's own notes fill in the form)
    2  what it is: name, category, how it was measured, how its identity was confirmed, fab sources
    3  validation, worked out in the background as soon as there is a spectrum:
         - the most similar existing reference
         - the impostor test now -> with the new reference
         - which of the spectra on screen would get another answer
       'Add to library' is only possible when the library stays validated.
    """

    submitted = Signal(dict)
    cancelled = Signal()

    def __init__(self, library, validation, results, current=None, start_dir="", parent=None):
        super().__init__(parent)
        t = Theme.t
        self.library, self.validation, self.results, self.current = library, validation, list(results), current
        self.start_dir = str(start_dir)
        self.spectrum = self.source_path = None
        self.preview = None                 # (impact, changes) once worked out
        self.job, self.pending = None, False
        self.pool = QThreadPool.globalInstance()

        column = QVBoxLayout(self)
        column.setContentsMargins(22, 16, 22, 22)
        column.setSpacing(14)
        column.addWidget(text_label(
            "Use this for a material the lab has identified by other means (a known part, the supplier's data "
            "sheet, SEM-EDX). From then on it is recognised. Nothing is saved until you press 'Add to library', "
            "and the program first checks that the library stays validated.", "Body2", wrap=True))

        # 1. the spectrum
        spec_card, spec_body = section("1   The spectrum")
        choices = (("Selected result", "result"), ("A file", "file")) if current is not None else (("A file", "file"),)
        self.source = Segmented(choices[0][1], choices=choices)
        self.source.changed.connect(self._source_changed)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source)
        self.file_button = QPushButton(" Choose a file…")
        self.file_button.setIcon(icon("upload", t["ink_2"]))
        self.file_button.setCursor(Qt.PointingHandCursor)
        self.file_button.clicked.connect(self.choose_file)
        source_row.addSpacing(8)
        source_row.addWidget(self.file_button)
        source_row.addStretch()
        spec_body.addLayout(source_row)
        self.source_text = text_label("", "Meta", wrap=True)
        spec_body.addWidget(self.source_text)
        self.chart = SpectrumChart(190)
        spec_body.addWidget(self.chart)
        column.addWidget(spec_card)

        # 2. what it is
        form_card, form_body = section("2   What it is")
        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. ABS (tool cover)")
        self.name_error = text_label("", "SectionHint", wrap=True)
        self.name_error.hide()
        self.category = QComboBox()
        self.category.addItems(list(config.CATEGORIES) + ["In-house"])
        self.category.setCurrentText("In-house")
        self.category.setEditable(False)
        self.mode = Segmented("ATR")
        self.mode.changed.connect(lambda _: self._spectrum_changed())
        self.confirmation = QLineEdit()
        self.confirmation.setPlaceholderText("e.g. known part, supplier data sheet, SEM-EDX (required)")
        self.fab = QLineEdit()
        self.fab.setPlaceholderText("e.g. covers and housings of handling equipment")
        self.check_next = QLineEdit()
        self.check_next.setPlaceholderText("e.g. worn or cracked covers near the affected tool")
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("optional")
        rows = [("Name", self.name), ("", self.name_error), ("Category", self.category), ("Measured by", self.mode),
                ("Identity confirmed by", self.confirmation), ("Where it comes from in the fab", self.fab),
                ("What to check next", self.check_next), ("Notes", self.notes)]
        for n, (caption, widget) in enumerate(rows):
            if caption:
                form.addWidget(text_label(caption, "FactLabel"), n, 0, Qt.AlignVCenter)
            if widget is self.mode:
                form.addWidget(widget, n, 1, Qt.AlignLeft)
            else:
                form.addWidget(widget, n, 1)
        form.setColumnStretch(1, 1)
        form_body.addLayout(form)
        column.addWidget(form_card)
        for field in (self.name, self.confirmation):
            field.textChanged.connect(self._update_button)
        self.name.textChanged.connect(self._check_name)

        # 3. validation
        val_card, self.val_body = section("3   Validation before adding", "worked out automatically")
        self.val_status = QHBoxLayout()
        self.spinner = Spinner(16, colour_key="accent")
        self.val_text = text_label("Choose a spectrum first.", "Body2", wrap=True)
        self.val_status.addWidget(self.spinner)
        self.val_status.addWidget(self.val_text, 1)
        self.val_body.addLayout(self.val_status)
        self.val_rows = QVBoxLayout()
        self.val_rows.setSpacing(10)
        self.val_body.addLayout(self.val_rows)
        column.addWidget(val_card)
        column.addStretch()

        # the footer (placed by the sheet under the scrolling content)
        self.footer = QFrame()
        self.footer.setObjectName("SheetHeader")
        foot = QHBoxLayout(self.footer)
        foot.setContentsMargins(22, 12, 22, 14)
        foot.addWidget(text_label("Saved in records/inhouse_library with your name and the date.\n"
                                  "Nothing is ever overwritten; removals are recorded too.", "SectionHint"), 1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        self.add_button = QPushButton(" Add to library")
        self.add_button.setObjectName("Primary")
        self.add_button.setIcon(icon("plus", t["on_accent"]))
        self.add_button.clicked.connect(self._submit)
        for button in (self.cancel_button, self.add_button):
            button.setCursor(Qt.PointingHandCursor)
            foot.addWidget(button)

        self._source_changed(self.source.value())
        self.val_card = val_card

    # ------------------------------------------------------------------ the spectrum
    def _source_changed(self, value):
        self.file_button.setVisible(value == "file")
        if value == "result" and self.current is not None:
            r = self.current
            self.spectrum, self.source_path = r.spectrum, r.spectrum.path
            self.mode.set_value(r.mode if r.mode in ("ATR", "transmission") else "unknown", animated=False)
            self.source_text.setText(f"{r.spectrum.path.name}  ·  {r.verdict}"
                                     + (f" {r.match}" if r.has_match else "") + f"  ·  measured by {r.mode}")
            self._spectrum_changed()
        else:
            self.spectrum = self.source_path = None
            self.source_text.setText("Choose a spectrum file. A reference file can carry its details in its header "
                                     "(# reference: ..., # category: ..., # fab sources: ...).")
            self.chart.set_data(None)
            self.preview = None
            self._show_preview()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the reference spectrum", self.start_dir,
                                              "Spectrum files (*.csv *.txt *.dpt);;All files (*)")
        if path:
            self.load_file(Path(path))

    def load_file(self, path):
        """Use a spectrum file; its header notes (if any) fill in the form."""
        try:
            spectrum = read_spectra(path)[0]
        except SpectrumFileError as error:
            self.source_text.setText(str(error))
            return
        notes = reference_notes(path)
        self.spectrum, self.source_path = spectrum, Path(path)
        mode = notes.get("mode", "unknown")
        self.mode.set_value(mode if mode in ("ATR", "transmission") else "unknown", animated=False)
        for key, field in (("reference", self.name), ("confirmation", self.confirmation),
                           ("fab sources", self.fab), ("check next", self.check_next)):
            if notes.get(key):
                field.setText(notes[key])
                field.setCursorPosition(0)                                  # show the start of a long text
        if notes.get("category") in [self.category.itemText(i) for i in range(self.category.count())]:
            self.category.setCurrentText(notes["category"])
        self.source_text.setText(f"{Path(path).name}  ·  {len(spectrum.wn)} points, "
                                 f"{spectrum.wn.min():.0f}–{spectrum.wn.max():.0f} cm⁻¹, {spectrum.unit}"
                                 + ("  ·  details read from the file's notes" if notes.get("reference") else ""))
        self._spectrum_changed()

    def grid_spectrum(self):
        """The spectrum as it would be stored and compared: absorbance, library mode, common grid."""
        return reference_on_grid(self.spectrum.wn, absorbance(self.spectrum), self.mode.value())

    def _spectrum_changed(self):
        if self.spectrum is None:
            return
        y = self.grid_spectrum()
        self.chart.set_data(y, "the new reference", key_bands(y))
        self.preview = None
        self.pending = True
        QTimer.singleShot(150, self, self._run_preview)                     # wait for quick changes to settle
        self._show_preview()

    # ------------------------------------------------------------------ validation (in the background)
    def _run_preview(self):
        if not self.pending or self.spectrum is None:
            return
        if self.job is not None:                                            # one at a time; run again after it
            return
        self.pending = False
        y, name = self.grid_spectrum(), self.name.text().strip() or "the new reference"
        library, validation, results = self.library, self.validation, self.results

        def work(progress):
            progress(0, 1, "Validating")
            return addition_preview(library, name, y, results, before=validation)

        self.job = Job(work)
        self.job.signals.done.connect(self._preview_done)
        self.job.signals.failed.connect(self._preview_failed)
        self.spinner.start()
        self.val_text.setText("Testing the library with the new reference…")
        self.pool.start(self.job)

    def _preview_done(self, job, preview):
        self.job = None
        if self.pending:                                                    # the spectrum changed meanwhile
            self._run_preview()
            return
        self.preview = preview
        self._show_preview()

    def _preview_failed(self, job, message):
        self.job = None
        self.spinner.stop()
        self.val_text.setText(f"The validation could not be run: {message}")

    def _show_preview(self):
        t = Theme.t
        clear_layout(self.val_rows)
        if self.preview is None:
            if self.spectrum is None:
                self.spinner.stop()
                self.val_text.setText("Choose a spectrum first.")
            self._update_button()
            return
        self.spinner.stop()
        impact, changes = self.preview
        name = self.name.text().strip() or "the new reference"
        self.val_text.setText("Done. This is what adding it would do:")
        nearest, score = impact.nearest

        rows = []
        # most similar existing reference, on the same 0-1 scale with the thresholds
        similar = QWidget()
        similar_layout = QVBoxLayout(similar)
        similar_layout.setContentsMargins(0, 0, 0, 0)
        similar_layout.addWidget(text_label("Most similar existing reference", "SectionTitle"))
        bars = ScoreBars()
        bars.winner_colour = "chart_unexplained" if score >= config.PROBABLE_R else "chart_reference"
        bars.set_data([(nearest, score)], "probable")
        similar_layout.addWidget(bars)
        rows.append(similar)

        # impostor test before -> after
        before, after = impact.before, impact.after
        test = QWidget()
        test_layout = QHBoxLayout(test)
        test_layout.setContentsMargins(0, 0, 0, 0)
        test_layout.addWidget(text_label("Impostor test", "SectionTitle"))
        test_layout.addStretch()
        test_layout.addWidget(text_label(f"now {before.score:.2f}", "Body2"))
        arrow = QLabel()
        arrow.setPixmap(icon_pixmap("arrow-right", t["muted"], 16, self.devicePixelRatioF() or 2.0))
        test_layout.addWidget(arrow)
        test_layout.addWidget(Pill("good" if after.passed else "bad",
                                   f"with it {after.score:.2f} ({after.material} → {after.impostor})",
                                   "shield-check" if after.passed else "shield-alert"))
        rows.append(test)

        # the spectra on screen that would change
        effect = QWidget()
        effect_layout = QVBoxLayout(effect)
        effect_layout.setContentsMargins(0, 0, 0, 0)
        effect_layout.setSpacing(4)
        effect_layout.addWidget(text_label("Your spectra on screen", "SectionTitle"))
        if not self.results:
            effect_layout.addWidget(text_label("No spectra are open, so nothing on screen would change.", "Body2"))
        elif not changes:
            effect_layout.addWidget(text_label(f"None of the {len(self.results)} results would change.", "Body2"))
        else:
            effect_layout.addWidget(text_label(f"{len(changes)} of {len(self.results)} results would change:",
                                               "Body2"))
            for change in changes:
                line = text_label(f"<b>{change.sample}</b>&nbsp;&nbsp;{change.before} &nbsp;→&nbsp; "
                                  f"<span style='color:{t['accent_ink']}'><b>{change.after}</b></span>", "Body", True)
                line.setTextFormat(Qt.RichText)
                effect_layout.addWidget(line)
        rows.append(effect)

        # the conclusion
        verdict = QFrame()
        verdict.setObjectName("Callout")
        good = impact.passed and impact.distinct
        verdict.setProperty("kind", "good" if good else "bad")
        verdict_row = QHBoxLayout(verdict)
        verdict_row.setContentsMargins(14, 10, 14, 10)
        mark = QLabel()
        mark.setPixmap(icon_pixmap("circle-check" if good else "triangle-alert", t["good" if good else "bad"], 20,
                                   self.devicePixelRatioF() or 2.0))
        verdict_row.addWidget(mark, 0, Qt.AlignTop)
        if good:
            text = (f"<b>Safe to add.</b> {name} is clearly different from every reference (closest: {nearest}, "
                    f"r = {score:.2f}) and the library stays validated.")
        else:
            text = (f"<b>Not safe to add.</b> {name} and {nearest} are too similar (r = {score:.2f} ≥ "
                    f"{config.PROBABLE_R}): the program could not tell them apart, so a wrong 'probable' answer "
                    "would become possible. Keep only one of them, or confirm such samples with another method "
                    "(e.g. a known part, or the bands that differ).")
        message = text_label(text, "Body", wrap=True)
        message.setTextFormat(Qt.RichText)
        verdict_row.addWidget(message, 1)
        rows.append(verdict)

        card = self.val_card
        before = snapshot(card) if card.isVisible() else None
        for row in rows:
            self.val_rows.addWidget(row)
        if before is not None:                                          # the result fades in, in place
            fade_through(card, before, snapshot(card), dy=6, duration=MOTION["content"])
        self._update_button()

    # ------------------------------------------------------------------ the form
    def _check_name(self):
        name = " ".join(self.name.text().split())
        taken = name in self.library.spectra
        self.name.setProperty("invalid", taken)
        self.name.style().unpolish(self.name)
        self.name.style().polish(self.name)
        self.name_error.setText(f"'{name}' is already in the library: choose another name." if taken else "")
        self.name_error.setVisible(taken)
        self._update_button()

    def problems(self):
        """What still stops the reference from being added (an empty list = ready)."""
        name = " ".join(self.name.text().split())
        missing = []
        if self.spectrum is None:
            missing.append("a spectrum")
        if not name or name in self.library.spectra:
            missing.append("a new name")
        if not self.confirmation.text().strip():
            missing.append("how the identity was confirmed")
        if self.preview is None:
            missing.append("the validation")
        elif not (self.preview[0].passed and self.preview[0].distinct):
            missing.append("a reference that keeps the library valid")
        return missing

    def _update_button(self):
        missing = self.problems()
        self.add_button.setEnabled(not missing)
        self.add_button.setToolTip("Needs " + ", ".join(missing) if missing else "Add it to the in-house library")

    def _submit(self):
        if self.problems():
            return
        self.submitted.emit({
            "name": " ".join(self.name.text().split()), "wn": self.spectrum.wn, "a": absorbance(self.spectrum),
            "mode": self.mode.value(), "category": self.category.currentText(), "fab_sources": self.fab.text().strip(),
            "check_next": self.check_next.text().strip(), "confirmation": self.confirmation.text().strip(),
            "notes": self.notes.text().strip(), "source_path": self.source_path})

    def closing(self):
        """Called when the sheet closes: a running validation reports to nobody."""
        if self.job is not None:
            for signal in (self.job.signals.done, self.job.signals.failed):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass


class OpenSpecyPanel(QWidget):
    """The content of the Open Specy sheet: what it is, what is installed, download or import."""

    download_requested = Signal()
    import_requested = Signal(str)

    def __init__(self, store, start_dir=""):
        super().__init__()
        t = Theme.t
        self.start_dir = str(start_dir)
        column = QVBoxLayout(self)
        column.setContentsMargins(24, 16, 24, 32)
        column.setSpacing(16)
        column.addWidget(text_label(
            "Open Specy is a large open library of FTIR and Raman spectra (Cowger et al. 2021, CC BY 4.0). "
            "The program can add the part a fab is likely to see: FTIR spectra of gloves, wipes, seals, "
            "fluoropolymers, silicones, resins, fibres, silica and other minerals, at most three per material.",
            "Body2", wrap=True))
        steps, steps_body = section("What happens", "nothing is changed in the original file")
        for number, text in enumerate([
                "The 'medoid nobaseline' library (baseline-corrected absorbance) is downloaded from where "
                "Open Specy keeps it (AWS, or osf.io), or you choose a file you downloaded yourself (.rds).",
                "Only FTIR spectra in fab-relevant material classes are kept.",
                "Every spectrum is compared with every reference. One that could be confused with a different "
                "material (r ≥ 0.95) is left out, so the extended library still passes the impostor test.",
                "The result is saved in records/openspecy/ with a report. Switch between 'Fab essentials' and "
                "'Extended' on the Library page at any time."], start=1):
            line = text_label(f"<b>{number}</b>&nbsp;&nbsp;{text}", "Body", wrap=True)
            line.setTextFormat(Qt.RichText)
            steps_body.addWidget(line)
        column.addWidget(steps)
        status, status_body = section("On this computer")
        if store.installed:
            report = store.report_file.read_text(encoding="utf-8") if store.report_file.exists() else ""
            status_body.addWidget(text_label(report.split("\n\nCite:")[0] or "Installed.", "Mono", wrap=True))
        else:
            status_body.addWidget(text_label("Not installed yet.", "Body2"))
        column.addWidget(status)
        buttons = QHBoxLayout()
        self.download_button = QPushButton(" Download from Open Specy")
        self.download_button.setObjectName("Primary")
        self.download_button.setIcon(icon("file-down", t["on_accent"]))
        self.import_button = QPushButton(" Import a library file…")
        self.import_button.setIcon(icon("upload", t["ink_2"]))
        for button in (self.download_button, self.import_button):
            button.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch()
        column.addLayout(buttons)
        column.addWidget(text_label(f"Licence {LICENCE}. Please cite: {CITATION}", "SectionHint", wrap=True))
        column.addStretch()
        self.download_button.clicked.connect(self.download_requested.emit)
        self.import_button.clicked.connect(self._choose)

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose an Open Specy library file", self.start_dir,
                                              "Open Specy library (*.rds *.RData *.rda);;All files (*)")
        if path:
            self.import_requested.emit(path)


def similarity_for(library):
    """(names, matrix) for a library, worked out once per library object and then kept with it."""
    cached = getattr(library, "_similarity", None)
    if cached is None:
        cached = similarity_matrix(library)
        object.__setattr__(library, "_similarity", cached)       # the Library is frozen; this is only a cache
    return cached
