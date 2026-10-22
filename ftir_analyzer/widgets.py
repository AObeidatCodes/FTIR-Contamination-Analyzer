"""
FTIR Contamination Analyzer - building blocks of the window

Small, reusable pieces the main window is made of. Most of them paint themselves
(QPainter), which gives full control over the look, crisp on any screen resolution:

    icon / icon_pixmap   Lucide line icons, recoloured to the theme and drawn sharp at any size
    Pill                 the coloured verdict / flag label: icon + word, never colour alone
    ScoreBars            the ranking as horizontal bars that grow into place, with the weak /
                         probable thresholds marked
    FlowLayout           lays chips (and library cards) out in rows that wrap, like words in a sentence
    SpectrumListModel    the analysed spectra, as a list Qt can display and filter
    SpectrumDelegate     how one row of the list is drawn (status icon, name, match, score, flags);
                         rows whose result changed after a library change glow for a moment
    PlotPanel            the figure, with a Result / Analytical view switch, "compare with ...",
                         zoom / pan / reset / save, and live tracing: under the mouse, every
                         curve's value and the name of the band at that wavenumber
    EmptyState           the welcome screen: what the program does and the ways to start
    ModeDialog           asks how files were measured (ATR / transmission / don't know)

Short names used in this file:
    t = the current theme colours    p = the painter (draws on the widget)    r = one Result
    w = one band position    rect = a rectangle on screen    dpr = device pixel ratio (2 on a "retina" screen)

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import os

os.environ.setdefault("QT_API", "pyside6")              # tell matplotlib which Qt binding to use

import matplotlib  # noqa: E402

matplotlib.use("QtAgg")                                  # draw matplotlib figures inside Qt widgets
import numpy as np  # noqa: E402
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from PySide6.QtCore import (QAbstractListModel, QByteArray, QEasingCurve, QEvent, QModelIndex, QPoint, QPointF,  # noqa: E402
                            QRect, QRectF, QSize, Qt, Signal)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QCursor, QFont, QFontMetrics, QIcon,  # noqa: E402
                           QPainter, QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea,  # noqa: E402
                               QSizePolicy, QStyle, QStyledItemDelegate, QToolButton, QToolTip, QVBoxLayout,
                               QWidget)

from . import config  # noqa: E402
from .analysis import NO_MATCH  # noqa: E402
from .analytical import analytical_steps  # noqa: E402
from .motion import (EASE_OUT, Card, FlowLayout, Look, Motion, Segmented, SmoothScrollArea, animate,  # noqa: E402
                     blank, make_opaque, rise_in, snapshot, stop)
from .peaks import band_table  # noqa: E402
from .plots import draw_analytical, draw_result  # noqa: E402
from .theme import FONT_SANS, ICONS, LOGO_SVG, SIZE, VERDICT_LOOK  # noqa: E402

Theme = Look        # the theme in use right now; painted widgets read their colours from Theme.t

# ---------------------------------------------------------------------------- icons and fonts
def _render_svg(svg_text, size, dpr=1.0):
    """Draw SVG text into a transparent pixmap of `size` logical pixels (sharp on high-DPI screens)."""
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def icon_pixmap(name, color, size=18, dpr=2.0):
    """A Lucide icon as a pixmap in the given colour."""
    svg = (ICONS / f"{name}.svg").read_text(encoding="utf-8").replace("currentColor", color)
    svg = svg.replace('stroke-width="2"', 'stroke-width="1.75"')          # a finer line, like SF Symbols
    return _render_svg(svg, size, dpr)


def icon(name, color, size=18):
    """A Lucide icon as a QIcon, with versions for normal, 2x and 3x screens."""
    result = QIcon()
    for dpr in (1.0, 2.0, 3.0):
        result.addPixmap(icon_pixmap(name, color, size, dpr))
    return result


def logo_pixmap(size, dpr=2.0):
    """The app logo at any size."""
    return _render_svg(LOGO_SVG.read_text(encoding="utf-8"), size, dpr)


def polylines(x, y):
    """Screen points -> one QPolygonF per unbroken stretch (NaN breaks the line).

    Drawn with drawPolyline and a bevel join, a long spectrum is stroked about twice as fast
    as a QPainterPath with round joins, and looks the same at these line widths.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    edges = np.flatnonzero(np.diff(np.concatenate([[0], ok.astype(int), [0]])))
    return [QPolygonF([QPointF(a, b) for a, b in zip(x[i:j], y[i:j])]) for i, j in zip(edges[::2], edges[1::2])]


def line_pen(colour, width):
    """The pen for a data line: solid, flat ends, bevel joins (fast to draw)."""
    return QPen(QColor(colour), width, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin)


def font(size_key="body", weight=QFont.Normal):
    """The app font at one of the sizes of the type scale."""
    f = QFont(FONT_SANS)
    f.setPixelSize(SIZE[size_key])
    f.setWeight(weight)
    return f


def status_of(verdict):
    """(status key, word, icon) for a verdict, e.g. ('good', 'Probable', 'circle-check')."""
    return VERDICT_LOOK[verdict]


def clear_layout(layout):
    """Remove and delete every widget in a layout (used before filling it again)."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.hide()                    # gone from the screen at once ...
            widget.setParent(None)
            widget.deleteLater()             # ... and deleted by Qt a moment later
        elif item.layout():
            clear_layout(item.layout())


# ---------------------------------------------------------------------------- Pill
class Pill(QWidget):
    """A rounded label: status icon + word, in the status colours (good / warn / none / bad)."""

    def __init__(self, kind, text, icon_name, parent=None, size_key="small"):
        super().__init__(parent)
        self.kind, self.text, self.icon_name, self.size_key = kind, text, icon_name, size_key
        self.compact = False                                           # True: only the icon (tight spaces)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self):
        fm = QFontMetrics(font(self.size_key, QFont.DemiBold))
        h = fm.height() + 8
        if self.compact:
            return QSize(h, h)
        return QSize(8 + 14 + 6 + fm.horizontalAdvance(self.text) + 11, h)

    def set_compact(self, compact):
        if compact != self.compact:
            self.compact = compact
            self.updateGeometry()
            self.update()

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t[f"{self.kind}_bg"]))
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        pix = icon_pixmap(self.icon_name, t[self.kind], 14, self.devicePixelRatioF())
        if self.compact:
            p.drawPixmap(QPoint(int((rect.width() - 14) / 2), int((rect.height() - 14) / 2)), pix)
            return
        p.drawPixmap(QPoint(8, int((rect.height() - 14) / 2)), pix)
        p.setPen(QColor(t[self.kind]))
        p.setFont(font(self.size_key, QFont.DemiBold))
        p.drawText(rect.adjusted(8 + 14 + 6, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self.text)


def verdict_pill(verdict, parent=None, size_key="small"):
    kind, word, icon_name = status_of(verdict)
    return Pill(kind, word, icon_name, parent, size_key)


def flag_pill(label, severity, parent=None):
    """A flag: 'bad' = do not trust the result as it is, 'warn' = look closer."""
    return Pill(severity, label[:1].upper() + label[1:],
                "triangle-alert" if severity == "bad" else "circle-alert", parent)


# ---------------------------------------------------------------------------- ScoreBars
class ScoreBars(QWidget):
    """The best library matches as horizontal bars (0 to 1), with the two thresholds marked.

    The winner is drawn in the library colour (the same blue as in the figure), the others
    in grey. The value sits at the tip of each bar. When new data arrives the bars grow from
    the baseline, one after the other, so the eye follows the ranking from top to bottom.
    """

    ROW, BAR = 32, 8       # row height and bar thickness (pixels)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ranking, self.verdict, self.growth = [], NO_MATCH, 1.0
        self.winner_colour = "chart_reference"
        self._animation = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, ranking, verdict, animated=True):
        """New bars. animated=True: they start at zero and grow when grow() is called (after the
        page transition, so they move on a still page); False: drawn at full length at once."""
        self.ranking, self.verdict = ranking, verdict
        self.updateGeometry()
        stop(self._animation)
        self._grow(0.0 if animated and not Motion.reduced else 1.0)

    def grow(self):
        """Let the bars grow from the baseline, one a little after the other."""
        stop(self._animation)
        self._animation = animate(self, 0.0, 1.0, Motion.ms("bars"), self._grow, QEasingCurve.Linear)

    def _grow(self, value):
        self.growth = value
        self.update()

    def _share(self, i):
        """How far bar i has grown (0 to 1): each bar starts a little after the one above, and eases out."""
        n = max(1, len(self.ranking))
        lag = 0.09
        local = min(1.0, max(0.0, (self.growth - i * lag) / max(0.2, 1 - lag * (n - 1))))
        return 1 - (1 - local) ** 3

    def sizeHint(self):
        return QSize(320, 22 + self.ROW * max(1, len(self.ranking)))

    def _bar(self, x, y, width):
        """A bar shape: square on the left (the baseline), 4 px rounded on the right (the value)."""
        radius = min(4.0, width / 2)
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(x + width - radius, y)
        path.quadTo(x + width, y, x + width, y + radius)
        path.lineTo(x + width, y + self.BAR - radius)
        path.quadTo(x + width, y + self.BAR, x + width - radius, y + self.BAR)
        path.lineTo(x, y + self.BAR)
        path.closeSubpath()
        return path

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(font("small"))
        name_w = min(170, max((fm.horizontalAdvance(n) for n, _ in self.ranking), default=60) + 14)
        x0, x1 = name_w, self.width() - 44                          # where the 0 and the 1 of the scale are
        scale = lambda r: x0 + max(r, 0) * (x1 - x0)  # noqa: E731

        # Threshold marks at the top: weak (0.60) and probable (0.95)
        p.setFont(font("caption"))
        for value, label in [(config.WEAK_R, "weak"), (config.PROBABLE_R, "probable")]:
            x = scale(value)
            p.setPen(QPen(QColor(t["line_strong"]), 1, Qt.DashLine))
            p.drawLine(int(x), 16, int(x), self.height())
            p.setPen(QColor(t["muted"]))
            p.drawText(QRect(int(x) - 60, 0, 120, 14), Qt.AlignCenter, f"{label} {value:.2f}")

        for i, (name, r) in enumerate(self.ranking):
            y = 22 + i * self.ROW
            winner = i == 0 and self.verdict != NO_MATCH
            share = self._share(i)
            p.setFont(font("small", QFont.DemiBold if winner else QFont.Normal))
            p.setPen(QColor(t["ink"] if winner else t["ink_2"]))
            p.drawText(QRect(0, y, name_w - 10, self.ROW), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(name, Qt.ElideRight, name_w - 10))
            # the track, then the bar: square at the baseline, rounded at the data end
            top = y + (self.ROW - self.BAR) / 2
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["surface_2"]))
            p.drawPath(self._bar(x0, top, x1 - x0))
            end = scale(r * share)
            if end > x0 + 1:
                p.setBrush(QColor(t[self.winner_colour] if winner else t["line_strong"]))
                p.drawPath(self._bar(x0, top, end - x0))
            ink = QColor(t["ink"] if winner else t["ink_2"])
            ink.setAlphaF(share)
            p.setPen(ink)
            p.drawText(QRect(int(end) + 6, y, 44, self.ROW), Qt.AlignVCenter | Qt.AlignLeft, f"{r:.2f}")


def chip(text, kind="Chip"):
    """A small label for one band: 'Chip' = found, 'ChipMissing' = missing, 'ChipExtra' = unexplained."""
    label = QLabel(text)
    label.setObjectName(kind)
    label.setWordWrap(len(text) > 24)                                  # a long one may take two lines
    return label


class ElidedLabel(QLabel):
    """One line of text that is shortened with '…' when it does not fit; the full text is in the tooltip.

    mode Qt.ElideMiddle keeps both ends (a checksum, a file path); copyable=True adds 'Copy' to the
    right-click menu, which copies the full text.
    """

    def __init__(self, text="", name="Body", mode=Qt.ElideRight, copyable=False):
        super().__init__()
        self.setObjectName(name)
        self.mode, self.full = mode, ""
        if copyable:
            copy = QAction("Copy", self)
            copy.triggered.connect(lambda: QApplication.clipboard().setText(self.full))
            self.addAction(copy)
            self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.setText(text)

    def setText(self, text):
        self.full = str(text)
        self._elide()
        self.updateGeometry()                                          # the layout should know the new length

    def text(self):
        return self.full

    def _elide(self):
        width = self.contentsRect().width()
        shown = self.fontMetrics().elidedText(self.full, self.mode, width) if width > 0 else self.full
        QLabel.setText(self, shown)
        self.setToolTip(self.full if shown != self.full else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._elide()

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.full) + 4, super().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(min(64, self.sizeHint().width()), super().minimumSizeHint().height())


# ---------------------------------------------------------------------------- the list of spectra
class SpectrumListModel(QAbstractListModel):
    """The analysed spectra as a list. Row text = sample name; the Result rides along as data."""

    RESULT = Qt.UserRole + 1          # the Result object
    SEARCH = Qt.UserRole + 2          # text the filter box searches in (name + match)
    UPDATED = Qt.UserRole + 3         # True if the result changed with the last library change

    def __init__(self):
        super().__init__()
        self.results = []
        self.updated = {}             # {sample name: Change ("Weak: PS -> Probable: ABS")} after a library change
        self.reason = ""              # ... and which change it was ("ABS added to the library")
        self.glow = 0.0               # 1 -> 0: the changed rows glow for a moment

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.results)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.results[index.row()]
        if role == Qt.DisplayRole:
            return r.name
        if role == self.RESULT:
            return r
        if role == self.SEARCH:
            return f"{r.name} {r.match} {r.verdict}"
        if role == self.UPDATED:
            return r.name in self.updated
        if role == Qt.ToolTipRole:
            change = self.updated.get(r.name)
            return f"{r.spectrum.path.name}\n{r.reason}" + (f"\nChanged with the library: {change}" if change else "")
        return None

    def add(self, results):
        if results:
            start = len(self.results)
            self.beginInsertRows(QModelIndex(), start, start + len(results) - 1)
            self.results.extend(results)
            self.endInsertRows()

    def replace(self, results, updated, reason=""):
        """New results for the same spectra (after a library change); `updated` = what changed, and why."""
        self.results = list(results)
        self.updated, self.reason = dict(updated), reason
        self.dataChanged.emit(self.index(0), self.index(max(0, len(self.results) - 1)))

    def remove_rows(self, rows):
        for row in sorted(rows, reverse=True):              # from the bottom up, so row numbers stay valid
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.results[row]
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self.results, self.updated = [], {}
        self.endResetModel()


class SpectrumDelegate(QStyledItemDelegate):
    """Draws one row of the list: status icon, sample name, match and score, flag marker.

    The selected row is filled with the accent blue (like a Mac's sidebar or Mail), its text white.
    """

    HEIGHT = 64

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.HEIGHT)

    def paint(self, p, option, index):
        t = Theme.t
        r = index.data(SpectrumListModel.RESULT)
        model = index.model().sourceModel() if hasattr(index.model(), "sourceModel") else index.model()
        updated = bool(index.data(SpectrumListModel.UPDATED))
        rect = option.rect.adjusted(6, 2, -6, -2)
        dpr = p.device().devicePixelRatioF()
        selected = bool(option.state & QStyle.State_Selected)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)

        # background: the selected row gets a soft accent tint and a short accent bar, a hovered row a grey wash
        if selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["accent_soft"]))
            p.drawRoundedRect(QRectF(rect), 8, 8)
            p.setBrush(QColor(t["accent"]))
            p.drawRoundedRect(QRectF(rect.left() + 2, rect.center().y() - 12, 3, 24), 1.5, 1.5)
        elif option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["surface_2"]))
            p.drawRoundedRect(QRectF(rect), 8, 8)
        if updated and model.glow > 0.01:                       # changed with the library: a tint and a ring
            wash, ring = QColor(t["accent"]), QColor(t["accent"])  # that fade together
            wash.setAlphaF(0.22 * model.glow)
            ring.setAlphaF(model.glow)
            p.setPen(QPen(ring, 2))
            p.setBrush(wash)
            p.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 8, 8)

        # status icon in a soft circle
        kind, word, icon_name = status_of(r.verdict)
        circle = QRectF(rect.left() + 14, rect.center().y() - 16, 32, 32)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["surface"] if selected else t[f"{kind}_bg"]))
        p.drawEllipse(circle)
        p.drawPixmap(QPoint(int(circle.left() + 7), int(circle.top() + 7)), icon_pixmap(icon_name, t[kind], 18, dpr))

        # flag marker on the right (triangle = do not trust as it is, circle = look closer)
        severities = [kind_ for _, kind_ in r.flags]
        right = rect.right() - 10
        if severities:
            severity = "bad" if "bad" in severities else "warn"
            marker = "triangle-alert" if severity == "bad" else "circle-alert"
            colour = t[severity]
            p.drawPixmap(QPoint(right - 16, rect.center().y() - 8), icon_pixmap(marker, colour, 16, dpr))
            right -= 24
        if updated:                                             # a small blue dot: "changed with the library"
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t["accent"]))
            p.drawEllipse(QRectF(right - 8, rect.center().y() - 4, 8, 8))
            right -= 16

        # score at the right, name and match in the middle
        main, second = QColor(t["ink"]), QColor(t["muted"])
        p.setFont(font("small", QFont.Medium))
        p.setPen(QColor(t["ink_2"]))
        score = f"{r.r:.2f}"
        score_w = QFontMetrics(p.font()).horizontalAdvance(score)
        p.drawText(QRect(right - score_w, rect.top(), score_w, rect.height()), Qt.AlignVCenter | Qt.AlignRight, score)
        text_left = int(circle.right()) + 12
        text_w = right - score_w - 12 - text_left
        name_font = font("small", QFont.DemiBold)
        p.setFont(name_font)
        p.setPen(main)
        p.drawText(QRect(text_left, rect.top() + 9, text_w, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(name_font).elidedText(r.name, Qt.ElideRight, text_w))
        sub = f"{word}: {r.match}" if r.verdict != NO_MATCH else "No reliable match"
        p.setFont(font("small"))
        p.setPen(second)
        p.drawText(QRect(text_left, rect.top() + 31, text_w, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(font("small")).elidedText(sub, Qt.ElideRight, text_w))
        p.restore()


# ---------------------------------------------------------------------------- the plot
class TraceCanvas(FigureCanvasQTAgg):
    """The figure's canvas. The mouse wheel scrolls the page; Ctrl + wheel zooms the spectrum."""

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            super().wheelEvent(event)                                   # matplotlib turns it into a zoom
        else:
            event.ignore()                                              # let the page scroll


class PlotPanel(Card):
    """The spectrum figure with two views, its tools and a live trace of every curve under the mouse.

    Result view       raw data on top, the comparison with the library below
    Analytical view   every processing step, one panel each (raw -> absorbance -> mode correction
                      -> fingerprint -> checks), with the explanation of each step underneath
    Compare with      draw any other library material instead of the best match, to see by eye
                      why it scored lower (the menu lists every material with its score)
    Under the mouse   a cursor line across all panels, a dot on every curve of the panel, and the
                      values of those curves plus the band's name above the figure
    Ctrl + scroll zooms around the mouse, double-click resets, the buttons zoom / pan / save.
    """

    save_requested = Signal()
    compare_changed = Signal(object)                                    # the material drawn instead of the best
    RESULT, ANALYTICAL = "result", "analytical"
    HEIGHT = {RESULT: 470, ANALYTICAL: 1500}                            # canvas height of each view (pixels)
    HINT = "Move the mouse over the spectrum to trace every curve.  Ctrl + scroll to zoom, double-click to reset."

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = self.RESULT
        self.result = self.library = self.drawing = self.background = self.compare = None
        self.cursors, self.markers, self.home_limits = [], {}, []
        table = band_table()                                            # band ranges, for the readout
        self._bands = (table["low"].to_numpy(float), table["high"].to_numpy(float), table["assignment"].tolist())

        self.figure = Figure(figsize=(8, 4.6))
        self.canvas = TraceCanvas(self.figure)
        self.canvas.setFixedHeight(self.HEIGHT[self.RESULT])
        self.navigator = NavigationToolbar2QT(self.canvas, self)        # zoom/pan logic; its own bar stays hidden
        self.navigator.hide()

        # row 1: the view switch on the left, the tools on the right
        self.switch = Segmented(self.RESULT, choices=(("Result", self.RESULT), ("Analytical view", self.ANALYTICAL)))
        self.switch.setToolTip("Analytical view: every step from the raw file to the score, one panel each")
        self.switch.changed.connect(self.set_view)
        self.compare_button = QToolButton()
        self.compare_button.setText(" Compare with")
        self.compare_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.compare_button.setPopupMode(QToolButton.InstantPopup)
        self.compare_button.setToolTip("Draw another library material instead of the best match")
        self.compare_button.setCursor(Qt.PointingHandCursor)
        self.compare_menu = QMenu(self)
        self.compare_button.setMenu(self.compare_menu)
        self.tools = {}
        bar = QHBoxLayout()
        bar.setContentsMargins(16, 16, 12, 0)
        bar.addWidget(self.switch)
        bar.addSpacing(10)
        bar.addWidget(self.compare_button)
        bar.addStretch()
        for key, icon_name, tip, checkable in [("home", "rotate-ccw", "Reset the view (or double-click the figure)", False),
                                               ("zoom", "zoom-in", "Zoom: drag a rectangle", True),
                                               ("pan", "move", "Pan: drag the spectrum", True),
                                               ("save", "image-down", "Save this view: PNG 300 or 600 dpi, SVG or PDF",
                                                False)]:
            button = QToolButton()
            button.setToolTip(tip)
            button.setAccessibleName(tip.split(":")[0].split(" (")[0])
            button.setCheckable(checkable)
            button.setIconSize(QSize(18, 18))
            button.setCursor(Qt.PointingHandCursor)
            bar.addWidget(button)
            self.tools[key] = (button, icon_name)
        self.tools["home"][0].clicked.connect(self.reset_view)
        self.tools["zoom"][0].clicked.connect(self._toggle_zoom)
        self.tools["pan"][0].clicked.connect(self._toggle_pan)
        self.tools["save"][0].clicked.connect(self.save_requested.emit)

        # row 2: the readout; then the figure; then (analytical view only) what each step did
        self.readout = QLabel(self.HINT)
        self.readout.setObjectName("Readout")
        self.readout.setTextFormat(Qt.RichText)
        self.readout.setWordWrap(True)
        self.readout.setMinimumHeight(36)
        self.steps_text = QLabel()
        self.steps_text.setObjectName("Body2")
        self.steps_text.setTextFormat(Qt.RichText)
        self.steps_text.setWordWrap(True)
        self.steps_text.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 12)
        layout.addLayout(bar)
        readout_box = QHBoxLayout()
        readout_box.setContentsMargins(16, 8, 16, 0)
        readout_box.addWidget(self.readout)
        layout.addLayout(readout_box)
        layout.addWidget(self.canvas)
        steps_box = QHBoxLayout()
        steps_box.setContentsMargins(18, 4, 18, 6)
        steps_box.addWidget(self.steps_text)
        layout.addLayout(steps_box)

        self.canvas.mpl_connect("draw_event", self._on_draw)
        self.canvas.mpl_connect("motion_notify_event", self._on_move)
        self.canvas.mpl_connect("figure_leave_event", self._on_leave)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_click)
        self.retheme()


    def resizeEvent(self, event):
        """A narrow figure: 'Compare with' shows only its icon (the tooltip still says what it does)."""
        super().resizeEvent(event)
        narrow = self.width() < 640
        if self.compare_button.toolButtonStyle() != (Qt.ToolButtonIconOnly if narrow else Qt.ToolButtonTextBesideIcon):
            self.compare_button.setToolButtonStyle(Qt.ToolButtonIconOnly if narrow else Qt.ToolButtonTextBesideIcon)
    def retheme(self):
        """Recolour the tool icons and redraw the figure in the current theme."""
        for button, icon_name in self.tools.values():
            button.setIcon(icon(icon_name, Theme.t["ink_2"]))
        self.compare_button.setIcon(icon("git-compare-arrows", Theme.t["ink_2"]))
        if self.result is not None:
            self.show_result(self.result, self.library)

    def set_view(self, view):
        """Switch between the result view and the analytical view."""
        self.view = view
        self.switch.set_value(view)
        self.canvas.setFixedHeight(self.HEIGHT[view])
        self.steps_text.setVisible(view == self.ANALYTICAL)
        self.compare_button.setVisible(view == self.RESULT)
        if self.result is not None:
            self.show_result(self.result, self.library)

    def set_compare(self, name):
        """Draw library material `name` instead of the best match (None = back to the best match)."""
        self.compare = name
        if self.result is not None:
            self.show_result(self.result, self.library, keep_compare=True)
        self.compare_changed.emit(name)

    def _fill_compare_menu(self):
        """One entry per library material, with its score; the one drawn now is ticked."""
        self.compare_menu.clear()
        group = QActionGroup(self.compare_menu)
        r = self.result
        best = QAction(f"Best match ({r.best}, r = {r.r:.2f})", self.compare_menu, checkable=True)
        best.setChecked(self.compare in (None, r.best))
        best.triggered.connect(lambda: self.set_compare(None))
        group.addAction(best)
        self.compare_menu.addAction(best)
        self.compare_menu.addSeparator()
        for name, score in r.ranking[1:]:
            action = QAction(f"{name}   r = {score:.2f}", self.compare_menu, checkable=True)
            action.setChecked(self.compare == name)
            action.triggered.connect(lambda _=False, n=name: self.set_compare(n))
            group.addAction(action)
            self.compare_menu.addAction(action)
        shown = self.compare if self.compare and self.compare != r.best else None
        self.compare_button.setText(f" Compared with {shown}" if shown else " Compare with")

    def _toggle_zoom(self):
        self.tools["pan"][0].setChecked(False)
        self.navigator.zoom()

    def _toggle_pan(self):
        self.tools["zoom"][0].setChecked(False)
        self.navigator.pan()

    def show_result(self, result, library, keep_compare=False):
        """Draw a result in the current view; prepare the cursor lines and the dots for tracing."""
        if result is not self.result and not keep_compare:
            self.compare = None                                         # a new spectrum starts with its best match
        self.result, self.library = result, library
        if self.compare not in library.spectra:
            self.compare = None
        t = Theme.t
        if self.view == self.ANALYTICAL:
            self.drawing = draw_analytical(self.figure, result, library, t)
            self.steps_text.setText("<ol style='margin-left:-20px'>" + "".join(
                f"<li style='margin-bottom:6px'><b>{step.title}.</b> {step.explanation}</li>"
                for step in analytical_steps(result, library)) + "</ol>")
        else:
            self.drawing = draw_result(self.figure, result, library, t, self.compare)
        self._fill_compare_menu()
        axes = self.drawing.axes
        self.cursors = [ax.axvline(config.GRID_STOP, color=t["muted"], lw=0.8, animated=True, visible=False)
                        for ax in axes]
        self.markers = {ax: [ax.plot([], [], "o", ms=5.5, color=colour, mec=t["chart_surface"], mew=1.3,
                                     animated=True, zorder=10)[0]
                             for _, _, _, colour, _ in self.drawing.traces.get(ax, [])] for ax in axes}
        self.home_limits = [(ax, ax.get_xlim(), ax.get_ylim()) for ax in axes]
        self.navigator.update()                                         # new figure = new zoom history
        self.readout.setText(self.HINT)
        self.canvas.draw()                      # now, not later: the drawing must never land inside an animation

    def reset_view(self):
        """Back to the full spectrum, as first drawn."""
        for ax, x_limits, y_limits in self.home_limits:
            ax.set_xlim(x_limits)
            ax.set_ylim(y_limits)
        self.navigator.update()
        self.canvas.draw_idle()

    # --- zoom with Ctrl + scroll, reset with a double-click
    def _on_scroll(self, event):
        if event.inaxes is None or event.xdata is None:
            return
        factor = 0.8 if event.button == "up" else 1.25                 # scroll up = zoom in
        left, right = event.inaxes.get_xlim()
        x = event.xdata
        event.inaxes.set_xlim(x - (x - left) * factor, x + (right - x) * factor)   # the panels share the x axis
        self.canvas.draw_idle()

    def _on_click(self, event):
        if event.dblclick:
            self.reset_view()

    # --- tracing (blitting: only the cursor and the dots are redrawn, so it stays smooth)
    def _on_draw(self, _):
        self.background = self.canvas.copy_from_bbox(self.figure.bbox)

    def _on_move(self, event):
        if self.drawing is None or event.inaxes not in self.drawing.axes or event.xdata is None:
            self._on_leave(event)
            return
        x, hovered, t = float(event.xdata), event.inaxes, Theme.t
        parts, tip, dots = [f"<b>{x:.0f} cm⁻¹</b>"], [f"<b>{x:.0f} cm⁻¹</b>"], []
        for (label, xs, ys, colour, fmt), marker in zip(self.drawing.traces.get(hovered, []), self.markers[hovered]):
            y = np.interp(x, xs, ys, left=np.nan, right=np.nan)       # the curve's value at this wavenumber
            if np.isfinite(y):
                parts.append(f"<span style='color:{colour}'>●</span> {label} {y:{fmt}}")
                # the tooltip is dark: an ink-coloured dot would vanish there, so it is drawn light
                dot = t["tooltip_ink"] if colour == t["chart_sample"] else colour
                tip.append(f"<span style='color:{dot}'>●</span> {label}: {y:{fmt}}")
                marker.set_data([x], [y])
                dots.append(marker)
        low, high, names = self._bands
        hits = [names[i] for i in np.flatnonzero((low <= x) & (high >= x))]
        band = "; ".join(hits) if hits else "no assignment in the band table"
        self.readout.setText("&nbsp;&nbsp;&nbsp;".join(parts) +
                             f"<br><span style='color:{t['muted']}'>{band}</span>")
        if self.view == self.ANALYTICAL:                               # tall view: the values follow the mouse
            QToolTip.showText(QCursor.pos() + QPoint(18, 18), "<br>".join(tip) + f"<br><i>{band}</i>", self.canvas)
        if self.navigator.mode or self.background is None:             # zooming or panning: no cursor drawing
            return
        self.canvas.restore_region(self.background)
        for ax, line in zip(self.drawing.axes, self.cursors):
            line.set_xdata([x, x])
            line.set_visible(True)
            ax.draw_artist(line)
        for marker in dots:
            hovered.draw_artist(marker)
        self.canvas.blit(self.figure.bbox)

    def _on_leave(self, _):
        QToolTip.hideText()
        if self.background is not None and self.cursors and self.cursors[0].get_visible():
            for line in self.cursors:
                line.set_visible(False)
            self.canvas.restore_region(self.background)
            self.canvas.blit(self.figure.bbox)


# ---------------------------------------------------------------------------- the welcome screen
class SpectrumArt(QWidget):
    """A decorative absorbance spectrum that draws itself from left to right: the welcome illustration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 1.0
        self._animation = None
        self.setMinimumHeight(128)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def play(self):
        """Draw the line again, from nothing (1.6 s, slowing down at the end)."""
        stop(self._animation)
        self._animation = animate(self, 0.0, 1.0, 1400, self._step, EASE_OUT)

    def _step(self, value):
        self.progress = value
        self.update()

    def paintEvent(self, _):
        t = Theme.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        x = np.linspace(0, 1, 500)
        bands = [(0.10, 0.30, 0.060), (0.30, 0.95, 0.010), (0.33, 0.55, 0.009), (0.52, 0.25, 0.015),
                 (0.64, 0.80, 0.012), (0.70, 0.45, 0.010), (0.80, 0.60, 0.018), (0.90, 0.35, 0.008)]
        y = sum(a * np.exp(-((x - c) / s) ** 2) for c, a, s in bands)
        n = max(2, int(len(x) * self.progress))                        # how much of the line is drawn so far
        left, right, base, top = w * 0.12, w * 0.88, h - 18, 14
        points = [QPointF(left + xi * (right - left), base - yi * (base - top)) for xi, yi in zip(x[:n], y[:n])]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        fill = QPainterPath(path)
        fill.lineTo(points[-1].x(), base)
        fill.lineTo(left, base)
        fill.closeSubpath()
        wash = QColor(t["accent"])                                     # a faint, flat tint under the line
        wash.setAlphaF(0.06)
        p.fillPath(fill, wash)
        p.setPen(QPen(QColor(t["accent"]), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        if self.progress < 0.999:                                       # the pen's tip while it draws
            glow = QColor(t["accent"])
            glow.setAlphaF(0.25)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(points[-1], 7, 7)
            p.setBrush(QColor(t["accent"]))
            p.drawEllipse(points[-1], 3.2, 3.2)
        p.setPen(QPen(QColor(t["line_strong"]), 1))
        p.drawLine(int(left), int(base), int(right), int(base))


class FeatureTile(Card):
    """One small card on the welcome screen: an icon, a title and one sentence."""

    def __init__(self, icon_name, title, text):
        super().__init__()
        self.icon_name = icon_name
        self.mark = QLabel()
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        body = QLabel(text)
        body.setObjectName("Body2")
        body.setWordWrap(True)
        body.setFixedWidth(224)
        self.blurb = body
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        layout.addWidget(self.mark)
        layout.addSpacing(2)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addStretch()
        self.setFixedWidth(264)
        self.retheme()

    def retheme(self):
        self.mark.setPixmap(icon_pixmap(self.icon_name, Theme.t["accent_ink"], 24, self.devicePixelRatioF() or 2.0))


class EmptyState(QWidget):
    """Shown before any spectrum is opened: what the program does, and the ways to start.

    It fits any window: the page scrolls rather than squeezing anything; on a low window the
    decorative spectrum is left out and the headline gets smaller; on a narrow one the three
    tiles wrap onto more lines and the text narrows.
    """

    choose_files = Signal()
    open_demo = Signal()
    open_library = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyPage")
        self.page = QWidget()
        self.page.setObjectName("EmptyPage")
        self.logo = QLabel()
        self.eyebrow = QLabel("FTIR CONTAMINATION ANALYZER")
        self.eyebrow.setObjectName("Eyebrow")
        self.eyebrow.setAlignment(Qt.AlignCenter)
        self.title = QLabel("Identify a contamination\nfrom its FTIR spectrum.")
        self.title.setObjectName("HeroTitle")
        self.title.setAlignment(Qt.AlignCenter)
        self.text = QLabel("Choose one or more spectrum files, or drop them anywhere on this window. "
                           "Each spectrum is compared with a validated reference library, checked for "
                           "warning signs and explained band by band.")
        self.text.setObjectName("Body2")
        self.text.setWordWrap(True)
        self.text.setAlignment(Qt.AlignCenter)
        self.choose = QPushButton(" Choose spectrum files…")
        self.choose.setObjectName("Primary")
        self.demo = QPushButton(" Open the demo spectra")
        self.library_link = QPushButton("Browse the reference library  ›")
        self.library_link.setObjectName("Link")
        for button in (self.choose, self.demo, self.library_link):
            button.setCursor(Qt.PointingHandCursor)
        self.formats = QLabel("CSV, TXT or DPT exports in %T or absorbance, with or without a header line")
        self.formats.setObjectName("SectionHint")
        self.formats.setAlignment(Qt.AlignCenter)
        self.formats.setWordWrap(True)
        self.art = SpectrumArt()
        self.choose.clicked.connect(self.choose_files.emit)
        self.demo.clicked.connect(self.open_demo.emit)
        self.library_link.clicked.connect(self.open_library.emit)
        self.tiles = [
            FeatureTile("shield-check", "A validated library",
                        "Every reference is tested against all the others each time it loads."),
            FeatureTile("scan-search", "Checks you can see",
                        "Raw-spectrum checks, and every step from the file to the score."),
            FeatureTile("history", "Traceable by design",
                        "Checksums, a sample log and an append-only audit trail."),
        ]

        self.buttons = QWidget()
        buttons = FlowLayout(self.buttons, spacing=16, align="center")
        buttons.addWidget(self.choose)
        buttons.addWidget(self.demo)
        self.tile_row = QWidget()
        tiles = FlowLayout(self.tile_row, spacing=16, row_spacing=16, align="center", even=True)
        for tile in self.tiles:
            tiles.addWidget(tile)
        layout = QVBoxLayout(self.page)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(0)
        layout.addStretch(2)
        layout.addWidget(self.logo, 0, Qt.AlignCenter)
        layout.addSpacing(16)
        layout.addWidget(self.eyebrow)
        layout.addSpacing(8)
        layout.addWidget(self.title)
        layout.addSpacing(16)
        layout.addWidget(self.text, 0, Qt.AlignCenter)
        layout.addSpacing(24)
        layout.addWidget(self.buttons)
        layout.addSpacing(8)
        layout.addWidget(self.library_link, 0, Qt.AlignCenter)
        layout.addWidget(self.formats)
        self.art_gap = layout.count()
        layout.addSpacing(16)
        layout.addWidget(self.art)
        layout.addSpacing(16)
        layout.addWidget(self.tile_row)
        layout.addStretch(3)

        self.scroll = SmoothScrollArea()
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.page)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        self.retheme()

    # ---------------------------------------------------------- fitting the window
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _fit(self):
        """Narrow the text to the width; then, step by step, leave out what does not fit the height:
        first the decorative spectrum, then the logo (and the title gets smaller)."""
        self.text.setFixedWidth(max(280, min(600, self.width() - 96)))
        self._set_heights()
        width, height = max(1, self.width()), self.height()
        for art, roomy in ((True, True), (False, True), (False, False)):
            self.art.setVisible(art)
            self.logo.setVisible(roomy)
            if self.title.property("compact") != (not roomy):
                self.title.setProperty("compact", not roomy)
                self.title.style().unpolish(self.title)
                self.title.style().polish(self.title)
            layout = self.page.layout()
            layout.invalidate()
            if layout.totalHeightForWidth(width) <= height:
                break

    def _set_heights(self):
        for label in [self.text] + [tile.blurb for tile in self.tiles]:  # wrapped text: the height its lines need
            label.ensurePolished()
            label.setMinimumHeight(label.heightForWidth(min(label.maximumWidth(), 600)) + 4)

    def play(self):
        """The entrance: the parts rise in one after the other, then the spectrum draws itself."""
        if Motion.reduced or not self.isVisible():
            return
        self.art.progress = 0.0
        parts = [self.logo, self.eyebrow, self.title, self.text, self.buttons, self.library_link, self.art,
                 self.tile_row]
        bands = []
        for widget in parts:
            if not widget.isVisible():
                continue
            rect = QRect(widget.mapTo(self, QPoint(0, 0)), widget.size())
            if widget is self.library_link:
                formats = self.formats
                rect = rect.united(QRect(formats.mapTo(self, QPoint(0, 0)), formats.size()))
            bands.append(rect)
        rise_in(self, blank(self, Theme.t["paper"]), snapshot(self), bands, dy=16, duration=720,
                on_done=self.art.play)

    def retheme(self):
        self._set_heights()
        make_opaque(self.page, Theme.t["paper"])
        make_opaque(self.scroll.viewport(), Theme.t["paper"])
        self.logo.setPixmap(logo_pixmap(64, self.devicePixelRatioF() or 2.0))
        self.choose.setIcon(icon("files", Theme.t["on_primary"]))
        self.demo.setIcon(icon("flask-conical", Theme.t["ink_2"]))
        for tile in self.tiles:
            tile.retheme()
        self.art.update()


# ---------------------------------------------------------------------------- measuring-mode dialog
class ModeDialog(QDialog):
    """Asks how files were measured. OK returns {path: mode}; Cancel leaves every file 'unknown'."""

    def __init__(self, paths, library_mode, parent=None):
        super().__init__(parent)
        self.setWindowTitle("How were these spectra measured?")
        self.paths = list(paths)
        self.rows = {}
        t = Theme.t

        head_icon = QLabel()
        head_icon.setPixmap(icon_pixmap("circle-help", t["accent_ink"], 28, self.devicePixelRatioF() or 2.0))
        title = QLabel(f"How were these {len(self.paths)} file{'s' if len(self.paths) > 1 else ''} measured?")
        title.setObjectName("DialogTitle")
        text = QLabel(f"These files do not say it themselves. The reference library was measured by "
                      f"{library_mode}, so a spectrum measured another way is corrected before it is compared. "
                      "Don't know: both ways are tried and the better fit is used (and said). "
                      "Your answer is saved in the sample log with your name and today's date, so you are "
                      "asked only once per file. Nothing is written into the files.")
        text.setObjectName("Body2")
        text.setWordWrap(True)

        all_row = QHBoxLayout()
        all_label = QLabel("Set all files to")
        all_label.setObjectName("SectionHint")
        self.all_choice = Segmented("unknown")
        self.all_choice.changed.connect(self._set_all)
        all_row.addWidget(all_label)
        all_row.addStretch()
        all_row.addWidget(self.all_choice)

        # one row per file, inside a scroll area (in case there are many)
        list_widget = QWidget()
        list_widget.setObjectName("ListArea")
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        for path in self.paths:
            row = QFrame()
            row.setObjectName("FileRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 8, 10, 8)
            name = QLabel(path.name)
            name.setToolTip(str(path))
            choice = Segmented("unknown")
            row_layout.addWidget(name, 1)
            row_layout.addWidget(choice)
            list_layout.addWidget(row)
            self.rows[path] = choice
        scroll = QScrollArea()
        scroll.setObjectName("FileList")
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_widget)
        scroll.setMinimumHeight(min(320, 52 * len(self.paths) + 4))

        ok = QPushButton("Save and continue")
        ok.setObjectName("Primary")
        ok.setDefault(True)
        cancel = QPushButton("Skip")
        cancel.setToolTip("Continue without answering: the files are analysed as 'mode unknown'")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(cancel)
        footer.addWidget(ok)

        head = QHBoxLayout()
        head.addWidget(head_icon, 0, Qt.AlignTop)
        head.addSpacing(6)
        head.addWidget(title, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.addLayout(head)
        layout.addSpacing(6)
        layout.addWidget(text)
        layout.addSpacing(14)
        layout.addLayout(all_row)
        layout.addSpacing(6)
        layout.addWidget(scroll)
        layout.addSpacing(16)
        layout.addLayout(footer)
        self.resize(640, self.sizeHint().height())

    def _set_all(self, mode):
        for choice in self.rows.values():
            choice.set_value(mode)

    def answers(self):
        """{path: mode} for every file (only meaningful after OK)."""
        return {path: choice.value() for path, choice in self.rows.items()}
