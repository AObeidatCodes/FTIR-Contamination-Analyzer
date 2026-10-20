"""
FTIR Contamination Analyzer - motion and the pieces that move

How it stays smooth
    Moving real widgets is slow: every frame Qt would draw all of them again (cards, lists,
    the matplotlib figure). So every transition here works like a flip-book:
        1. take a picture of how it looks now (old snapshot)
        2. do all the slow work at once (fill the page, draw the figure) while nothing moves
        3. take a picture of the result (new snapshot)
        4. animate only those two pictures, on one opaque layer on top
    Painting two pictures per frame is cheap, so the animation runs at the screen's frame
    rate. When it ends, the layer disappears and the real, live widgets are underneath.

How it moves (the rules come from Material Design, Fluent, Emil Kowalski and Rauno Freiberg)
    - short: 150-340 ms; things you do often (clicking through samples) get the shortest
    - ease-out: fast start, gentle stop; no bounce
    - fade-through: the old content fades out quickly, then the new one fades in and rises
      a few pixels; only one picture is blended at a time
    - the slow work happens before the motion, never during it
    - View > Reduce motion (or Windows' "Show animations" switched off) turns it all off

    Motion           the switch for reduced motion and the animation times (theme.MOTION)
    curves           the easing curves (cubic Bezier, like CSS cubic-bezier())
    animate          moves any number from a start to an end value
    count_up         a number counts up to its value (0.00 -> 0.97)
    Overlay          the opaque layer that plays a transition from snapshots
    fade_through, rise_in, crossfade   the three transitions built on it
    SmoothScrollArea mouse-wheel scrolling that glides (each notch adds a short push)
    FadeStack        pages that fade through to each other (Analyze <-> Library)
    Card             a white card with a 1 px border (a soft shadow only while lifted)
    Tabs             text tabs with a sliding underline (the page switch in the toolbar)
    Segmented        a segmented control whose knob slides to the chosen segment
    Spinner          a thin arc that turns while something is working
    Toast            a small message that rises at the bottom of the window and fades away
    Sheet            a panel that slides in from the right over the dimmed window

Short names used in this file:
    p = the painter, or the progress of an animation (0 -> 1)    e = progress after easing
    t = theme colours    ms = milliseconds    dx, dy = how far something moves    pix = a snapshot

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import re
import sys

import shiboken6
from PySide6.QtCore import (QAbstractAnimation, QElapsedTimer, QEasingCurve, QEvent, QPoint, QPointF, QRect, QRectF,
                            QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from .theme import FONT_SANS, LIGHT, MOTION, RADIUS, SIZE


class Motion:
    """Whether animations run. Off = every change happens at once (View > Reduce motion)."""

    reduced = False

    @classmethod
    def ms(cls, key):
        """The duration of one kind of animation, or 0 when motion is reduced."""
        return 0 if cls.reduced else MOTION[key]

    @staticmethod
    def system_prefers_reduced():
        """True if Windows' "Show animations in Windows" is switched off (elsewhere: False)."""
        if not sys.platform.startswith("win"):
            return False
        try:
            import ctypes
            enabled = ctypes.c_bool(True)
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)   # SPI_GETCLIENTAREAANIMATION
            return not enabled.value
        except Exception:
            return False


class Look:
    """The theme in use right now (set by the window); painted widgets read their colours here."""

    t = LIGHT


def _font(size_key="body", weight=QFont.Normal):
    f = QFont(FONT_SANS)
    f.setPixelSize(SIZE[size_key])
    f.setWeight(weight)
    return f


def alive(obj):
    """True if the Qt object behind a Python object still exists."""
    return obj is not None and shiboken6.isValid(obj)


# ---------------------------------------------------------------------------- easing curves
def bezier(x1, y1, x2, y2):
    """An easing curve from a cubic Bezier, exactly like CSS cubic-bezier(x1, y1, x2, y2)."""
    curve = QEasingCurve(QEasingCurve.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1, 1))
    return curve


EASE_OUT = bezier(0.23, 1, 0.32, 1)        # things that appear or leave: fast start, long gentle stop
EASE_IN_OUT = bezier(0.77, 0, 0.175, 1)    # things that move from one place to another on screen
DRAWER = bezier(0.32, 0.72, 0, 1)          # sheets that slide in from the side


def ease(curve, progress):
    """The eased value of a progress between 0 and 1."""
    return curve.valueForProgress(max(0.0, min(1.0, progress)))


# ---------------------------------------------------------------------------- the basic animation
def animate(owner, start, end, duration, on_value, easing=EASE_OUT, on_done=None, delay=0):
    """Animate from start to end over `duration` ms, calling on_value(value) on every frame.

    The animation belongs to `owner`: if the owner is deleted, the animation stops with it.
    With reduced motion (or duration 0) the end value is applied at once.
    """
    if Motion.reduced or duration <= 0:
        on_value(end)
        if on_done:
            on_done()
        return None
    animation = QVariantAnimation(owner)
    animation.setStartValue(float(start) if isinstance(start, int) else start)   # floats move smoothly
    animation.setEndValue(float(end) if isinstance(end, int) else end)
    animation.setDuration(duration)
    animation.setEasingCurve(easing if isinstance(easing, QEasingCurve) else QEasingCurve(easing))
    animation.valueChanged.connect(on_value)
    if on_done:
        animation.finished.connect(on_done)
    if delay:
        on_value(start)
        QTimer.singleShot(delay, animation, lambda: animation.start(QAbstractAnimation.DeleteWhenStopped))
    else:
        animation.start(QAbstractAnimation.DeleteWhenStopped)
    return animation


def stop(animation):
    """Stop an animation if it is still running."""
    if alive(animation) and animation.state() == QAbstractAnimation.Running:
        animation.stop()


NUMBER = re.compile(r"^(-?)(\d+)(?:\.(\d+))?(.*)$", re.S)


def count_up(label, text, duration=None):
    """Show `text` in a label, counting its leading number up from 0, e.g. '0.97' or '4 of 4'."""
    stop(getattr(label, "_counter", None))
    match = NUMBER.match(text)
    if Motion.reduced or not match or duration == 0:
        label.setText(text)
        return
    sign, whole, decimals, rest = match.groups()
    value = float(f"{whole}.{decimals}" if decimals else whole)
    places = len(decimals or "")
    label._counter = animate(label, 0.0, value, duration or MOTION["count"],
                             lambda v: label.setText(f"{sign}{v:.{places}f}{rest}"), EASE_OUT,
                             lambda: label.setText(text))


def zero_like(text):
    """'0.97' -> '0.00', '4 of 4' -> '0 of 4': the first frame of count_up."""
    match = NUMBER.match(text)
    if not match:
        return text
    sign, _, decimals, rest = match.groups()
    return f"{0:.{len(decimals or '')}f}{rest}"


# ---------------------------------------------------------------------------- the transition layer
def snapshot(widget):
    """A picture of a widget as it looks now, with every pending layout change applied first."""
    QApplication.sendPostedEvents(None, QEvent.LayoutRequest)
    return widget.grab()


def blank(widget, colour):
    """A picture of an empty page (just the background colour), the size of `widget`."""
    dpr = widget.devicePixelRatioF() or 1.0
    pix = QPixmap(int(widget.width() * dpr), int(widget.height() * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(QColor(colour))
    return pix


class Overlay(QWidget):
    """An opaque layer over a widget that paints the frames of a transition from snapshots.

    Because it is opaque, Qt does not repaint anything underneath while it plays: each frame
    is only a few picture copies. `paint_frame(p, e)` draws one frame (e = eased progress).
    """

    active = {}                      # {id(host): the overlay playing on it}

    def __init__(self, host, paint_frame, duration, easing=EASE_OUT, on_done=None):
        super().__init__(host)
        Overlay.finish(host)                                       # one transition at a time per widget
        Overlay.active[id(host)] = self
        self.host, self.paint_frame, self.on_done, self.progress = host, paint_frame, on_done, 0.0
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(host.rect())
        self.show()
        self.raise_()
        self.repaint()                                             # the first frame, at once
        self.animation = animate(self, 0.0, 1.0, duration, self._frame, QEasingCurve.Linear, self._done)

    @classmethod
    def finish(cls, host):
        """Jump a transition that is still playing on `host` to its end."""
        overlay = cls.active.get(id(host))
        if alive(overlay):
            stop(overlay.animation)
            overlay._done()

    def _frame(self, value):
        self.progress = value
        self.update()

    def _done(self):
        if Overlay.active.get(id(self.host)) is self:
            del Overlay.active[id(self.host)]
        self.hide()
        self.deleteLater()
        if self.on_done:
            callback, self.on_done = self.on_done, None
            callback()

    def paintEvent(self, _):
        p = QPainter(self)
        self.paint_frame(p, self.progress)


def fade_through(host, old, new, dy=8, duration=None, on_done=None):
    """The old picture fades out quickly, then the new one fades in while rising `dy` pixels.

    One picture is blended per frame (old first, then new), which keeps it light.
    """
    duration = MOTION["page"] if duration is None else duration
    if Motion.reduced or duration <= 0 or not host.isVisible():
        if on_done:
            on_done()
        return None
    paper = QColor(Look.t["paper"])
    split = 0.3                                                    # the first 30 % of the time: the old one leaves

    def frame(p, progress):
        p.fillRect(QRect(QPoint(0, 0), host.size()), paper)
        if progress < split:
            p.setOpacity(1 - ease(EASE_OUT, progress / split))
            p.drawPixmap(0, 0, old)
        else:
            e = ease(EASE_OUT, (progress - split) / (1 - split))
            p.setOpacity(e)
            p.drawPixmap(0, round(dy * (1 - e)), new)

    return Overlay(host, frame, duration, on_done=on_done)


def rise_in(host, old, new, bands, dy=10, duration=None, on_done=None):
    """Fade-through where the new content arrives in bands (sections), each a little after the last.

    bands: rectangles of `host` (top to bottom) that rise in one after the other.
    """
    duration = MOTION["content"] if duration is None else duration
    if Motion.reduced or duration <= 0 or not host.isVisible():
        if on_done:
            on_done()
        return None
    paper = QColor(Look.t["paper"])
    split = 0.22
    stagger = MOTION["stagger"] / duration                         # each band starts this much later
    each = max(0.3, 1 - split - stagger * max(0, len(bands) - 1))

    def frame(p, progress):
        p.fillRect(QRect(QPoint(0, 0), host.size()), paper)
        if progress < split:
            p.setOpacity(1 - ease(EASE_OUT, progress / split))
            p.drawPixmap(0, 0, old)
            return
        dpr = new.devicePixelRatio()
        for i, band in enumerate(bands):
            local = (progress - split - i * stagger) / each
            if local <= 0:
                continue
            e = ease(EASE_OUT, local)
            p.setOpacity(e)
            source = QRectF(band.x() * dpr, band.y() * dpr, band.width() * dpr, band.height() * dpr)
            p.drawPixmap(QRectF(band).translated(0, round(dy * (1 - e))), new, source)

    return Overlay(host, frame, duration, on_done=on_done)


def crossfade(widget, change, duration=180):
    """Run change() (for example: switch the theme) and let the old picture fade into the new one."""
    if Motion.reduced or not widget.isVisible():
        change()
        return
    old = snapshot(widget)
    change()
    new = snapshot(widget)

    def frame(p, progress):
        p.drawPixmap(0, 0, old)
        p.setOpacity(ease(EASE_OUT, progress))
        p.drawPixmap(0, 0, new)

    Overlay(widget, frame, duration)


# ---------------------------------------------------------------------------- smooth scrolling
class SmoothScrollArea(QScrollArea):
    """A scroll area where every mouse-wheel notch adds a short, decelerating push.

    Notches that follow quickly add up, so a fast spin travels further and a single click
    moves calmly. Touchpads already send smooth pixel steps: those are passed straight on.
    The content is opaque, so Qt can move the picture instead of drawing it again.
    """

    STEP, DURATION = 110, 380                                      # pixels per notch, ms per push

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.pushes = []                                           # [(distance, start time ms)]
        self.applied, self.clock = 0.0, QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self._tick)
        self.recent = []                                           # times of the last wheel notches

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if Motion.reduced or not event.pixelDelta().isNull() or event.modifiers() or not delta or delta % 120:
            super().wheelEvent(event)                              # touchpad, Ctrl / Shift + wheel: as usual
            return
        now = self.clock.elapsed()
        self.recent = [stamp for stamp in self.recent if now - stamp < 500] + [now]
        boost = 1 + min(1.0, (len(self.recent) - 1) / 8)           # a fast spin travels further
        self.pushes.append((-delta / 120 * self.STEP * boost, now, 0.0))
        if not self.timer.isActive():
            self.timer.start()
        event.accept()

    def _tick(self):
        """One frame: every push hands over the distance it covered since the last frame."""
        bar, now, moved, kept = self.verticalScrollBar(), self.clock.elapsed(), 0.0, []
        for distance, start, used in self.pushes:
            share = ease(EASE_OUT, (now - start) / self.DURATION)
            moved += distance * (share - used)
            if share < 1:
                kept.append((distance, start, share))
        self.pushes = kept
        self.applied += moved
        whole = int(self.applied)                                  # move by whole pixels, keep the rest
        if whole:
            self.applied -= whole
            bar.setValue(bar.value() + whole)
        at_end = (moved < 0 and bar.value() <= bar.minimum()) or (moved > 0 and bar.value() >= bar.maximum())
        if not self.pushes or at_end:
            self.pushes, self.applied = [], 0.0
            self.timer.stop()

    def scroll_to_top(self):
        self.pushes, self.applied = [], 0.0
        self.timer.stop()
        self.verticalScrollBar().setValue(0)


def make_opaque(widget, colour):
    """Paint a widget's whole background itself, so Qt can scroll and move it by copying pixels."""
    widget.setAutoFillBackground(True)
    palette = widget.palette()
    palette.setColor(widget.backgroundRole(), QColor(colour))
    widget.setPalette(palette)


# ---------------------------------------------------------------------------- pages
class FadeStack(QStackedWidget):
    """A stack of pages; switching fades through from the old page to the new one."""

    def slide_to(self, page, direction=1):
        old = self.currentWidget()
        if page is old:
            return
        if Motion.reduced or not self.isVisible() or old is None:
            self.setCurrentWidget(page)
            return
        Overlay.finish(self)
        before = snapshot(self)
        self.setCurrentWidget(page)
        after = snapshot(self)
        fade_through(self, before, after, dy=8, duration=MOTION["page"])


# ---------------------------------------------------------------------------- cards
class Card(QFrame):
    """A white card with rounded corners and a 1 px border. While lifted it gains a soft shadow
    instead of the border (a border or a shadow, never both).

    The shadow is drawn inside the widget's own rectangle, so the card keeps a small margin
    around its visible body (MARGIN); the content goes inside that.
    """

    RADIUS, MARGIN = RADIUS["card"], 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
        self.lift = 0.0                                            # 0 = resting, 1 = lifted (hover)

    def body(self):
        """The visible card (without the margin), moved up a little when lifted."""
        m = self.MARGIN
        return QRectF(self.rect()).adjusted(m, m, -m, -m).translated(0, -2 * self.lift)

    def paint_card(self, p, rect=None):
        """Draw the card's body (and its shadow while lifted); used by subclasses that paint their content."""
        t = Look.t
        rect = rect or self.body()
        p.setRenderHint(QPainter.Antialiasing)
        if self.lift > 0.01:                                       # lifted: two soft layers below the card
            p.setPen(Qt.NoPen)
            for spread, strength in ((3, 0.35), (1.5, 0.65)):
                shadow = QColor(t["shadow"])
                shadow.setAlphaF(t["shadow_alpha"] * strength * self.lift)
                p.setBrush(shadow)
                p.drawRoundedRect(rect.adjusted(-spread, -spread + 3, spread, spread + 3),
                                  self.RADIUS + spread, self.RADIUS + spread)
        edge = QColor(t["line_strong"] if self.lift > 0.5 else t["line"])
        p.setPen(QPen(edge, 1))
        p.setBrush(QColor(t["surface"]))
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS, self.RADIUS)

    def paintEvent(self, _):
        p = QPainter(self)
        self.paint_card(p)


# ---------------------------------------------------------------------------- tabs and segmented controls
class _Choice(QWidget):
    """What Tabs and Segmented share: a few choices, one chosen, an indicator that slides."""

    changed = Signal(str)

    def __init__(self, value, choices, size_key, padding, parent=None):
        super().__init__(parent)
        self.choices = list(choices)
        self._value = value if value in self.values() else self.choices[0][1]
        self.size_key, self.padding = size_key, padding
        self._indicator, self._animation, self.hover = None, None, -1
        self.keyboard_focus = False                                # the focus ring only for keyboard users
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAccessibleName("Choice: " + ", ".join(text for text, _ in self.choices))

    def values(self):
        return [v for _, v in self.choices]

    def value(self):
        return self._value

    def _widths(self):
        fm = QFontMetrics(_font(self.size_key, QFont.DemiBold))
        return [fm.horizontalAdvance(text) + 2 * self.padding for text, _ in self.choices]

    def _segment(self, index):
        widths = self._widths()
        return QRectF(2 + sum(widths[:index]), 2, widths[index], self.height() - 4)

    def _index_at(self, x):
        return next((i for i in range(len(self.choices))
                     if self._segment(i).left() <= x <= self._segment(i).right()), -1)

    def set_value(self, value, animated=True):
        if value not in self.values():
            return
        target = self._segment(self.values().index(value))
        start = self._indicator or target
        self._value = value
        stop(self._animation)
        if animated and self.isVisible():
            self._animation = animate(self, QRectF(start), target, MOTION["tab"], self._move, EASE_IN_OUT)
        else:
            self._move(target)

    def _move(self, rect):
        self._indicator = rect
        self.update()

    def _choose(self, index):
        if 0 <= index < len(self.choices) and self.choices[index][1] != self._value:
            self.set_value(self.choices[index][1])
            self.changed.emit(self._value)

    def mousePressEvent(self, event):
        self._choose(self._index_at(event.position().x()))

    def mouseMoveEvent(self, event):
        hover = self._index_at(event.position().x())
        if hover != self.hover:
            self.hover = hover
            self.update()

    def leaveEvent(self, _):
        self.hover = -1
        self.update()

    def focusInEvent(self, event):
        self.keyboard_focus = event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason)
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.keyboard_focus = False
        self.update()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        index = self.values().index(self._value)
        if event.key() in (Qt.Key_Left, Qt.Key_Up):
            self._choose(index - 1)
        elif event.key() in (Qt.Key_Right, Qt.Key_Down):
            self._choose(index + 1)
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._indicator = self._segment(self.values().index(self._value))


class Tabs(_Choice):
    """Text tabs with a 2 px accent line under the chosen one; the line slides when the tab changes."""

    def __init__(self, value, choices, parent=None):
        super().__init__(value, choices, "body", 14, parent)

    def sizeHint(self):
        return QSize(sum(self._widths()) + 4, 44)

    def paintEvent(self, _):
        t = Look.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i, (text, value) in enumerate(self.choices):
            chosen = value == self._value
            p.setFont(_font("body", QFont.DemiBold if chosen else QFont.Medium))
            p.setPen(QColor(t["ink"] if chosen or i == self.hover else t["muted"]))
            p.drawText(self._segment(i), Qt.AlignCenter, text)
        line = self._indicator or self._segment(self.values().index(self._value))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["accent"]))
        p.drawRoundedRect(QRectF(line.left() + 10, self.height() - 3, line.width() - 20, 2), 1, 1)
        if self.hasFocus() and self.keyboard_focus:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(t["accent"]), 2))
            p.drawRoundedRect(self._segment(self.values().index(self._value)).adjusted(2, 6, -2, -6), 6, 6)


class Segmented(_Choice):
    """A segmented control: a quiet track and a white knob that slides to the chosen segment.

    choices: [(text, value), ...]. Click a segment, or use the arrow keys when it has focus.
    """

    MODES = (("ATR", "ATR"), ("Transmission", "transmission"), ("Don't know", "unknown"))

    def __init__(self, value="unknown", parent=None, choices=MODES, size_key="small", padding=14):
        super().__init__(value, choices, size_key, padding, parent)

    def sizeHint(self):
        return QSize(sum(self._widths()) + 4, 36)

    def paintEvent(self, _):
        t = Look.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(t["line"]), 1))
        p.setBrush(QColor(t["surface_2"]))
        p.drawRoundedRect(track, RADIUS["control"], RADIUS["control"])
        knob = self._indicator or self._segment(self.values().index(self._value))
        p.setPen(QPen(QColor(t["line_strong"]), 1))
        p.setBrush(QColor(t["surface"]))
        p.drawRoundedRect(knob.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        for i, (text, value) in enumerate(self.choices):
            chosen = value == self._value
            p.setFont(_font(self.size_key, QFont.DemiBold if chosen else QFont.Medium))
            p.setPen(QColor(t["ink"] if chosen or i == self.hover else t["muted"]))
            p.drawText(self._segment(i), Qt.AlignCenter, text)
        if self.hasFocus() and self.keyboard_focus:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(t["accent"]), 2))
            p.drawRoundedRect(track.adjusted(1, 1, -1, -1), RADIUS["control"], RADIUS["control"])


# ---------------------------------------------------------------------------- activity indicator
class Spinner(QWidget):
    """A thin arc that turns while something is working."""

    def __init__(self, size=16, parent=None, colour_key="accent"):
        super().__init__(parent)
        self.angle, self.colour_key = 0.0, colour_key
        self.setFixedSize(size, size)
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.update)
        self.hide()

    def start(self):
        if not self.timer.isActive():
            self.clock.start()
            self.timer.start()
        self.show()

    def stop(self):
        self.timer.stop()
        self.hide()

    def paintEvent(self, _):
        t = Look.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        width = max(1.5, self.width() / 9)
        rect = QRectF(self.rect()).adjusted(width, width, -width, -width)
        p.setPen(QPen(QColor(t["line"]), width))
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(t[self.colour_key]), width, Qt.SolidLine, Qt.RoundCap))
        turn = (self.clock.elapsed() % 900) / 900 * 360                # one turn every 0.9 s
        p.drawArc(rect, int(-turn * 16), int(100 * 16))


# ---------------------------------------------------------------------------- toast
class Toast(QWidget):
    """A small message near the bottom of the window: it rises in, waits and fades away."""

    def __init__(self, host):
        super().__init__(host)
        self.host, self.text, self.icon, self.opacity, self.rise = host, "", None, 0.0, 0.0
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.dismiss)
        self._animation = None
        self.hide()

    def show_message(self, text, icon_pixmap=None):
        """Show a message (with an optional icon) for a few seconds."""
        self.text, self.icon = text, icon_pixmap
        fm = QFontMetrics(_font("body", QFont.Medium))
        width = min(self.host.width() - 48, fm.horizontalAdvance(text) + (64 if icon_pixmap else 40))
        self.resize(width, 44)
        self._place()
        self.show()
        self.raise_()
        stop(self._animation)
        self._animation = animate(self, self.opacity, 1.0, 220, self._frame, EASE_OUT)
        self.hide_timer.start(MOTION["toast"])

    def _place(self):
        self.move((self.host.width() - self.width()) // 2, self.host.height() - self.height() - 24 + round(self.rise))

    def _frame(self, value):
        self.opacity, self.rise = value, 8 * (1 - value)
        self._place()
        self.update()

    def dismiss(self):
        stop(self._animation)
        self._animation = animate(self, self.opacity, 0.0, 180, self._frame, EASE_OUT, self.hide)

    def mousePressEvent(self, _):
        self.dismiss()

    def paintEvent(self, _):
        t = Look.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self.opacity)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["tooltip"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS["control"], RADIUS["control"])
        x = 16
        if self.icon is not None:
            p.drawPixmap(int(x), int((self.height() - 18) / 2), self.icon)
            x += 28
        p.setPen(QColor(t["tooltip_ink"]))
        p.setFont(_font("body", QFont.Medium))
        p.drawText(QRectF(x, 0, self.width() - x - 16, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text)


# ---------------------------------------------------------------------------- sheet
class Sheet(QWidget):
    """A panel that slides in from the right over the dimmed window.

    Smooth because it is a flip-book: the window behind is photographed once, and while
    the sheet moves only that photo, a dim layer and a photo of the panel are painted.
    When it has arrived, the real (live) panel takes the photo's place. Closes with the
    close button, the Esc key or a click on the dimmed part.
    """

    closed = Signal()
    arrived = Signal()               # the sheet has slid in: its content may start its own animation

    def __init__(self, host, title, content, width=600, eyebrow="", footer=None):
        super().__init__(host)
        self.host, self.panel_width, self.progress, self.closing = host, width, 0.0, False
        self.has_arrived = False
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.background = host.grab()                             # the window behind, photographed once
        self.panel = QFrame(self)
        self.panel.setObjectName("SheetPanel")

        head = QFrame()
        head.setObjectName("SheetHeader")
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(24, 16, 16, 16)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        if eyebrow:
            small = QLabel(eyebrow)
            small.setObjectName("Eyebrow")
            titles.addWidget(small)
        self.title = QLabel(title)
        self.title.setObjectName("DialogTitle")
        self.title.setWordWrap(True)
        titles.addWidget(self.title)
        head_row.addLayout(titles, 1)
        self.close_button = QToolButton()
        self.close_button.setToolTip("Close (Esc)")
        self.close_button.setAccessibleName("Close")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.close_sheet)
        head_row.addWidget(self.close_button, 0, Qt.AlignTop)

        content.setObjectName(content.objectName() or "SheetContent")
        make_opaque(content, Look.t["paper"])
        self.scroll = SmoothScrollArea()
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   # the content follows the width
        self.scroll.setWidget(content)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(head)
        layout.addWidget(self.scroll, 1)
        if footer is not None:
            footer.setObjectName("SheetFooter")
            layout.addWidget(footer)

        host.installEventFilter(self)                              # follow the window when it is resized
        self.setGeometry(host.rect())
        self._place_panel()
        self.show()
        self.raise_()
        self.setFocus()
        self.panel_photo = snapshot(self.panel)                    # the panel, photographed once it is laid out
        self.panel.hide()
        self._animation = animate(self, 0.0, 1.0, Motion.ms("sheet"), self._frame, DRAWER, self._arrived)

    def set_close_icon(self, qicon):
        self.close_button.setIcon(qicon)

    def _panel_rect(self):
        width = min(self.panel_width, self.width() - 48)
        return QRect(self.width() - width, 0, width, self.height())

    def _place_panel(self):
        self.panel.setGeometry(self._panel_rect())

    def _frame(self, value):
        self.progress = value
        self.update()

    def _arrived(self):
        if not self.closing:
            self.panel.show()                                      # the live panel takes over
            self.update()
            self.has_arrived = True
            self.arrived.emit()

    def close_sheet(self):
        if self.closing:
            return
        self.closing = True
        stop(self._animation)
        self.host.removeEventFilter(self)
        if self.panel.isVisible():
            self.panel_photo = self.panel.grab()
            self.panel.hide()

        def finished():
            self.hide()
            self.closed.emit()
            self.deleteLater()

        self._animation = animate(self, self.progress, 0.0, Motion.ms("sheet_out"), self._frame, EASE_OUT, finished)

    def eventFilter(self, obj, event):
        if obj is self.host and event.type() == QEvent.Resize and not self.closing:
            self.hide()                                            # photograph the resized window without the sheet
            self.setGeometry(self.host.rect())
            self.background = self.host.grab()
            self._place_panel()
            self.show()
            self.raise_()
        return False

    def mousePressEvent(self, event):
        if not self._panel_rect().contains(event.position().toPoint()):
            self.close_sheet()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close_sheet()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _):
        t = Look.t
        p = QPainter(self)
        p.drawPixmap(0, 0, self.background)
        dim = QColor(0, 0, 0)
        dim.setAlphaF(t["backdrop_alpha"] * self.progress)
        p.fillRect(self.rect(), dim)
        if not self.panel.isVisible():                             # moving: paint the photo of the panel
            rect = self._panel_rect()
            x = self.width() - round(rect.width() * self.progress)
            p.drawPixmap(x, 0, self.panel_photo)


def rounded_path(rect, radius):
    """A rounded rectangle as a path (used to clip pictures to a card's corners)."""
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    return path
