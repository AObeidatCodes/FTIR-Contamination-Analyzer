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
    - short: 150-280 ms; things you do often (clicking through samples) get the shortest
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
    Sheet            a card in the middle of the dimmed window (fades in, rises 16 px)
    FlowLayout       a row of widgets that wraps onto the next line when it runs out of room

Short names used in this file:
    p = the painter, or the progress of an animation (0 -> 1)    e = progress after easing
    t = theme colours    ms = milliseconds    dx, dy = how far something moves    pix = a snapshot

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import gc
import math
import re
import sys

import shiboken6
from PySide6.QtCore import (QAbstractAnimation, QElapsedTimer, QEasingCurve, QEvent, QPoint, QPointF, QRect, QRectF,
                            QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLayout, QScrollArea, QSizePolicy,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

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


def _precise_timers():
    """Windows ticks its timers every 15.6 ms by default, so frames come 13 and 25 ms apart: the motion
    stutters. Asking for 1 ms ticks while the program runs makes every frame come when it should."""
    if not sys.platform.startswith("win"):
        return
    try:
        import atexit
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
        atexit.register(ctypes.windll.winmm.timeEndPeriod, 1)
    except Exception:
        pass


_precise_timers()


class Look:
    """The theme in use right now (set by the window); painted widgets read their colours here."""

    t = LIGHT


def _font(size_key="body", weight=QFont.Normal):
    f = QFont(FONT_SANS)
    f.setPixelSize(SIZE[size_key])
    f.setWeight(weight)
    return f


POP, POP_BAND = 0.94, 0.975             # how small a page / a section starts before it grows to full size


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
EASE_POP = bezier(0.16, 1, 0.3, 1)          # the report's "expo out": a quick start and a very long, soft stop
EASE_IN_OUT = bezier(0.77, 0, 0.175, 1)    # things that move from one place to another on screen


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


# ---------------------------------------------------------------------------- no pauses while things move
class Moving:
    """While anything moves, Python's garbage collector waits: a collection can take tens of
    milliseconds, which is two or three frames. It catches up as soon as the motion ends."""

    count = 0

    @classmethod
    def start(cls):
        cls.count += 1
        if cls.count == 1 and gc.isenabled():
            gc.disable()
            cls.paused = True

    @classmethod
    def end(cls):
        cls.count = max(0, cls.count - 1)
        if cls.count == 0 and getattr(cls, "paused", False):
            cls.paused = False
            gc.enable()


def warm_up(widgets, delay=350):
    """Draw these widgets' cached pictures ahead of time (their prepare()), one per quiet moment and
    never while something moves. Without it a picture is drawn the first time its widget scrolls
    into view, and that one slow frame (5-20 ms) is felt as a hitch in the scrolling."""
    queue = [w for w in widgets if hasattr(w, "prepare")]

    def step():
        if not queue:
            return
        if Moving.count:                                           # something is moving: later
            QTimer.singleShot(60, step)
            return
        widget = queue.pop(0)
        if alive(widget) and widget.width() > 0:
            widget.prepare()
        QTimer.singleShot(0, step)                                 # the next one after the next events

    QTimer.singleShot(delay, step)


# ---------------------------------------------------------------------------- the transition layer
def snapshot(widget):
    """A picture of a widget as it looks now, with every pending layout change applied first.

    Qt shows a widget that was just put into a layout a moment later (a queued call), gives
    new widgets their style (font, colours) a moment after that, and a layout pass can ask for
    another one (a label shortened to its new width, a row that wraps). All of it is done
    now, until things settle: otherwise the picture would miss the new badges (they would
    pop in when the transition ends) and the work would make its first frame late.
    """
    for _ in range(4):
        for child in widget.findChildren(QWidget):
            if child.isHidden() and not child.testAttribute(Qt.WA_WState_ExplicitShowHide):
                QApplication.sendPostedEvents(child, QEvent.MetaCall)      # the queued 'show it'
        QApplication.sendPostedEvents(None, QEvent.PolishRequest)
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
    is only a few picture copies. The widgets underneath are also told not to paint at all
    until it ends (they are hidden anyway), so a page that was just filled does not spend the
    first frame painting itself where nobody can see it. `paint_frame(p, e)` draws one frame
    (e = eased progress).
    """

    active = {}                      # {id(host): the overlay playing on it}

    def __init__(self, host, paint_frame, duration, easing=EASE_OUT, on_done=None):
        super().__init__(host)
        Overlay.finish(host)                                       # one transition at a time per widget
        Overlay.active[id(host)] = self
        self.host, self.paint_frame, self.on_done, self.progress = host, paint_frame, on_done, 0.0
        self.frozen = [child for child in host.findChildren(QWidget, options=Qt.FindDirectChildrenOnly)
                       if child is not self and child.isVisible() and child.updatesEnabled()]
        for child in self.frozen:                                  # hidden under the layer: no painting
            child.setUpdatesEnabled(False)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(host.rect())
        self.show()
        self.raise_()
        self.repaint()                                             # the first frame, at once
        Moving.start()
        self.moving = True
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
        for child in self.frozen:                                  # paint again (once) as the layer goes
            if alive(child):
                child.setUpdatesEnabled(True)
        self.frozen = []
        if getattr(self, "moving", False):
            self.moving = False
            Moving.end()
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
    split = 0.16                                                   # the first 16 % of the time: the old one leaves
    middle = host.width() / 2

    def frame(p, progress):
        p.fillRect(QRect(QPoint(0, 0), host.size()), paper)
        if progress < split:
            p.setOpacity(1 - ease(EASE_OUT, progress / split))
            p.drawPixmap(0, 0, old)
        else:
            e = ease(EASE_POP, (progress - split) / (1 - split))
            p.setOpacity(min(1.0, e * 1.6))                        # clear a little before it has settled
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.translate(middle, dy * (1 - e))                      # it grows from 94 % as it rises, like the report
            p.scale(POP + (1 - POP) * e, POP + (1 - POP) * e)
            p.translate(-middle, 0)
            p.drawPixmap(0, 0, new)

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
    split = 0.14
    stagger = MOTION["stagger"] / duration                         # each band starts this much later
    each = max(0.3, 1 - split - stagger * max(0, len(bands) - 1))
    middle = host.width() / 2

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
            e = ease(EASE_POP, min(1.0, local))
            p.setOpacity(min(1.0, e * 1.6))
            source = QRectF(band.x() * dpr, band.y() * dpr, band.width() * dpr, band.height() * dpr)
            p.save()
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            scale = 1 - (1 - POP_BAND) * (1 - e)                   # each section grows a little as it rises
            p.translate(band.center().x(), band.top() + dy * (1 - e))
            p.scale(scale, scale)
            p.translate(-band.center().x(), -band.top())
            p.drawPixmap(QRectF(band), new, source)
            p.restore()

    return Overlay(host, frame, duration, on_done=on_done)


def crossfade(widget, change, duration=420, on_done=None):
    """Run change() (for example: switch the theme) and let the old picture fade into the new one.
    on_done: called when the fade has finished (at once with reduced motion)."""
    if Motion.reduced or not widget.isVisible():
        change()
        if on_done:
            on_done()
        return
    old = snapshot(widget)
    change()
    new = snapshot(widget)

    def frame(p, progress):
        p.drawPixmap(0, 0, old)
        p.setOpacity(ease(EASE_OUT, progress))
        p.drawPixmap(0, 0, new)

    Overlay(widget, frame, duration, on_done=on_done)


# ---------------------------------------------------------------------------- smooth scrolling
class SmoothScrollArea(QScrollArea):
    """A scroll area where the mouse wheel moves a target and the page glides after it.

    Every frame the page covers the same share of the distance still to go (as Lenis does in
    the report), measured by the real time since the last frame, so it moves at the same pace
    whether a frame comes early or late. Notches that follow quickly add up, so a fast spin
    travels further. Touchpads already send smooth pixel steps: those are passed straight on.
    The content is opaque, so Qt can move the picture instead of drawing it again.
    """

    STEP, PACE, FRAME = 110, 7.0, 16                               # pixels per notch, glide rate per second, ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.target = self.position = 0.0
        self.last_frame, self.clock = 0, QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(self.FRAME)
        self.timer.timeout.connect(self._tick)
        self.recent = []                                           # times of the last wheel notches

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if Motion.reduced or not event.pixelDelta().isNull() or event.modifiers() or not delta or delta % 120:
            self.stop_glide()
            super().wheelEvent(event)                              # touchpad, Ctrl / Shift + wheel: as usual
            return
        bar, now = self.verticalScrollBar(), self.clock.elapsed()
        if not self.timer.isActive() or round(self.position) != bar.value():
            self.target = self.position = float(bar.value())       # start from where the page is now
            self.last_frame = now
        self.recent = [stamp for stamp in self.recent if now - stamp < 500] + [now]
        boost = 1 + min(1.0, (len(self.recent) - 1) / 8)           # a fast spin travels further
        self.target = min(max(self.target - delta / 120 * self.STEP * boost, bar.minimum()), bar.maximum())
        if not self.timer.isActive():
            self.timer.start()
        event.accept()

    def _tick(self):
        """One frame: cover the share of the remaining distance that the time since the last frame allows."""
        bar, now = self.verticalScrollBar(), self.clock.elapsed()
        if round(self.position) != bar.value():                    # moved by the scroll bar or the keys
            self.stop_glide()
            return
        dt, self.last_frame = min(now - self.last_frame, 100), now
        self.target = min(max(self.target, bar.minimum()), bar.maximum())
        self.position += (self.target - self.position) * (1 - math.exp(-dt / 1000 * self.PACE))
        if abs(self.target - self.position) < 2:                   # the last pixels: arrive, no crawl
            self.position = self.target
            self.timer.stop()
        bar.setValue(round(self.position))

    def stop_glide(self):
        self.timer.stop()
        self.target = self.position = float(self.verticalScrollBar().value())

    def scroll_to_top(self):
        self.timer.stop()
        self.verticalScrollBar().setValue(0)
        self.target = self.position = 0.0


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
        self.action_word, self.on_action = "", None
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.dismiss)
        self._animation = None
        self.hide()

    def show_message(self, text, icon_pixmap=None, action=None):
        """Show a message (with an optional icon) for a few seconds.

        action: (word, function) - the word is shown at the right; a click on the message runs it.
        """
        self.text, self.icon = text, icon_pixmap
        self.action_word, self.on_action = action if action else ("", None)
        self.setCursor(Qt.PointingHandCursor if self.on_action else Qt.ArrowCursor)
        fm = QFontMetrics(_font("body", QFont.Medium))
        extra = fm.horizontalAdvance(self.action_word) + 24 if self.action_word else 0
        width = min(self.host.width() - 48, fm.horizontalAdvance(text) + extra + (64 if icon_pixmap else 40))
        self.resize(width, 44)
        self._place()
        self.show()
        self.raise_()
        stop(self._animation)
        self._animation = animate(self, self.opacity, 1.0, 220, self._frame, EASE_OUT)
        self.hide_timer.start(MOTION["toast"] * (2 if self.on_action else 1))   # time to reach the action

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
        action, self.on_action = self.on_action, None
        self.dismiss()
        if action:
            action()

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
        right = self.width() - 16
        p.setFont(_font("body", QFont.DemiBold))
        if self.action_word:
            p.setPen(QColor(t["tooltip_action"]))
            p.drawText(QRectF(x, 0, right - x, self.height()), Qt.AlignVCenter | Qt.AlignRight, self.action_word)
            right -= QFontMetrics(p.font()).horizontalAdvance(self.action_word) + 24
        p.setPen(QColor(t["tooltip_ink"]))
        p.setFont(_font("body", QFont.Medium))
        text = QFontMetrics(p.font()).elidedText(self.text, Qt.ElideRight, int(right - x))
        p.drawText(QRectF(x, 0, right - x, self.height()), Qt.AlignVCenter | Qt.AlignLeft, text)


# ---------------------------------------------------------------------------- a row that wraps
class FlowLayout(QLayout):
    """Widgets side by side, wrapping onto the next line when the row runs out of room (like words).

    align: "left", "center" or "right" - where each row sits in the width it has.
    even=True: every item in a row gets the row's height (cards side by side look tidy).
    """

    def __init__(self, parent=None, spacing=8, row_spacing=8, align="left", even=False):
        super().__init__(parent)
        self.items, self.gap, self.row_gap, self.side, self.even = [], spacing, row_spacing, align, even
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):
        """One row with everything in it."""
        visible = [item.sizeHint() for item in self.items if not item.isEmpty()]
        m = self.contentsMargins()
        width = sum(h.width() for h in visible) + self.gap * max(0, len(visible) - 1)
        return QSize(width + m.left() + m.right(), max((h.height() for h in visible), default=0) + m.top() + m.bottom())

    def minimumSize(self):
        """As narrow as the widest item can become (text that wraps or shortens can become narrow)."""
        size = QSize()
        for item in self.items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    @staticmethod
    def _size(item, room):
        """An item's size in a row of `room` pixels: never wider than the row; wrapped text gets taller."""
        hint = item.sizeHint()
        width = max(item.minimumSize().width(), min(hint.width(), room))
        height = item.heightForWidth(width) if item.hasHeightForWidth() else hint.height()
        return QSize(width, max(height, item.minimumSize().height()))

    def _arrange(self, rect, apply):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        rows, row, used = [], [], 0
        for item in self.items:
            if item.isEmpty():
                continue
            size = self._size(item, area.width())
            if row and used + self.gap + size.width() > area.width():
                rows.append(row)
                row, used = [], 0
            used += (self.gap if row else 0) + size.width()
            row.append((item, size))
        if row:
            rows.append(row)
        y = area.y()
        for row in rows:
            height = max(size.height() for _, size in row)
            width = sum(size.width() for _, size in row) + self.gap * (len(row) - 1)
            free = max(0, area.width() - width)
            x = area.x() + {"left": 0, "center": free // 2, "right": free}[self.side]
            for item, size in row:
                if apply and self.even:
                    item.setGeometry(QRect(x, y, size.width(), height))
                elif apply:
                    item.setGeometry(QRect(QPoint(x, y + (height - size.height()) // 2), size))
                x += size.width() + self.gap
            y += height + self.row_gap
        total = y - self.row_gap - area.y() if rows else 0
        return total + m.top() + m.bottom()


# ---------------------------------------------------------------------------- sheet
class SheetCard(QFrame):
    """The card of a sheet: paper-coloured, rounded, with a hairline edge. It paints itself,
    so its corners stay round (the header and footer on it are transparent)."""

    RADIUS = 16

    def paintEvent(self, _):
        t = Look.t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(t["line"]), 1))
        p.setBrush(QColor(t["paper"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS, self.RADIUS)


class Sheet(QWidget):
    """A card in the middle of the dimmed window, for a task that needs its own space.

    Smooth because it is a flip-book: the window behind is photographed once and the card,
    with its soft shadow, is photographed once. While it appears only those two pictures and
    a dim layer are painted: the card fades in and rises 16 px (a short distance, so it looks
    smooth even where the screen and Qt are not in step). When it has arrived the real (live)
    card takes the photo's place. Closes with the close button, Esc or a click outside it.

    tall=True: the card always takes the full height (for content that grows while it is
    open); otherwise it is as tall as its content, up to the window's height.
    close_icon: given here, so that it is already on the photo (it would pop in at the end).
    """

    closed = Signal()
    arrived = Signal()               # the sheet has appeared: its content may start its own animation
    MARGIN, RISE, SHADOW = 32, 36, 28  # space around the card, how far it rises, room for its shadow

    def __init__(self, host, title, content, width=600, eyebrow="", footer=None, tall=False, close_icon=None):
        super().__init__(host)
        self.host, self.panel_width, self.tall, self.progress, self.closing = host, width, tall, 0.0, False
        self.has_arrived = False
        self.previous_focus = QApplication.focusWidget()           # gets the keyboard focus back afterwards
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.StrongFocus)
        for other in host.findChildren(Sheet):                     # a sheet still fading out is finished at once,
            if other is not self and other.isVisible():            # or it would be on the photo of the window
                other.finish_now()
        self.background = host.grab()                             # the window behind, photographed once
        self.panel = SheetCard(self)
        self.panel.setObjectName("SheetPanel")

        self.head = QFrame()
        self.head.setObjectName("SheetHeader")
        head_row = QHBoxLayout(self.head)
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
        if close_icon is not None:
            self.close_button.setIcon(close_icon)
        head_row.addWidget(self.close_button, 0, Qt.AlignTop)

        self.content = content
        content.setObjectName(content.objectName() or "SheetContent")
        make_opaque(content, Look.t["paper"])
        self.scroll = SmoothScrollArea()
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   # the content follows the width
        self.scroll.setWidget(content)
        make_opaque(self.scroll.viewport(), Look.t["paper"])
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.head)
        layout.addWidget(self.scroll, 1)
        if footer is not None:
            footer.setObjectName("SheetFooter")
            layout.addWidget(footer)
        else:                                                      # keeps the scrolling part off the round corners
            layout.addSpacing(SheetCard.RADIUS)
        self.footer = footer

        host.installEventFilter(self)                              # follow the window when it is resized
        content.installEventFilter(self)                           # and the content when it grows
        self.setGeometry(host.rect())
        self._place_panel()
        self.show()
        self.raise_()
        self.setFocus()
        self._photograph()
        self.panel.hide()
        self.repaint()                                             # the first frame, at once
        Moving.start()
        self._animation = animate(self, 0.0, 1.0, Motion.ms("sheet"), self._frame, QEasingCurve.Linear,
                                  self._arrived)

    def set_close_icon(self, qicon):
        self.close_button.setIcon(qicon)

    # -------------------------------------------------------------- where the card goes
    def _natural_height(self, width):
        """How tall the card wants to be at this width: header + content + footer."""
        QApplication.sendPostedEvents(None, QEvent.LayoutRequest)
        content = self.content
        inner = width - 16                                         # room for the scroll bar
        body = content.heightForWidth(inner) if content.hasHeightForWidth() else content.sizeHint().height()
        head = self.head.heightForWidth(width) if self.head.hasHeightForWidth() else self.head.sizeHint().height()
        foot = self.footer.sizeHint().height() if self.footer is not None else SheetCard.RADIUS
        return head + max(body, content.minimumSizeHint().height()) + foot + 2

    def _panel_rect(self):
        margin = self.MARGIN if min(self.width(), self.height()) > 640 else 16
        width = max(320, min(self.panel_width, self.width() - 2 * margin))
        room = self.height() - 2 * margin
        height = room if self.tall else min(room, self._natural_height(width))
        return QRect((self.width() - width) // 2, (self.height() - height) // 2, width, height)

    def _place_panel(self):
        self.panel.setGeometry(self._panel_rect())
        self.shadow = self._shadow(self.panel.size())

    def _shadow(self, size):
        """The card's soft shadow, painted once into a picture: a few wide, faint rounded layers."""
        t, s = Look.t, self.SHADOW
        dpr = self.devicePixelRatioF() or 1.0
        pix = QPixmap(int((size.width() + 2 * s) * dpr), int((size.height() + 2 * s) * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        card = QRectF(s, s, size.width(), size.height())
        for spread, strength in ((24, 0.10), (14, 0.18), (6, 0.32), (2, 0.40)):
            shade = QColor(t["shadow"])
            shade.setAlphaF(min(1.0, t["shadow_alpha"] * strength * 2.2))
            p.setBrush(shade)
            p.drawRoundedRect(card.adjusted(-spread, -spread + spread / 2, spread, spread + spread / 2),
                              SheetCard.RADIUS + spread, SheetCard.RADIUS + spread)
        p.end()
        return pix

    def _photograph(self):
        """The card and its shadow as one picture, for the frames while it moves."""
        photo = snapshot(self.panel)
        s, size = self.SHADOW, self.panel.size()
        dpr = self.devicePixelRatioF() or 1.0
        layer = QPixmap(int((size.width() + 2 * s) * dpr), int((size.height() + 2 * s) * dpr))
        layer.setDevicePixelRatio(dpr)
        layer.fill(Qt.transparent)
        p = QPainter(layer)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, self.shadow)
        p.setClipPath(rounded_path(QRectF(s, s, size.width(), size.height()), SheetCard.RADIUS))
        p.drawPixmap(s, s, photo)
        p.end()
        self.layer = layer

    # -------------------------------------------------------------- motion
    def _frame(self, value):
        self.progress = value
        self.update()

    def _arrived(self):
        Moving.end()
        if not self.closing:
            self.panel.show()                                      # the live card takes over
            self.update()
            self.has_arrived = True
            self.arrived.emit()

    def close_sheet(self):
        if self.closing:
            return
        self.closing = True
        if not self.has_arrived and alive(self._animation):
            Moving.end()                                           # closed while it was still appearing
        stop(self._animation)
        self.host.removeEventFilter(self)
        self.content.removeEventFilter(self)
        if self.panel.isVisible():
            self._photograph()
            self.panel.hide()

        Moving.start()
        self._animation = animate(self, self.progress, 0.0, Motion.ms("sheet_out"), self._frame, QEasingCurve.Linear,
                                  self._finished)

    def _finished(self):
        Moving.end()
        # hand the focus back first: otherwise Qt moves it on as if Tab had been pressed (a focus ring)
        back = self.previous_focus if alive(self.previous_focus) and self.previous_focus.isVisible() else self.host
        back.setFocus(Qt.OtherFocusReason)
        self.hide()
        self.closed.emit()
        self.deleteLater()

    def finish_now(self):
        """Gone at once, without the fade (another sheet is opening in its place)."""
        if not self.closing:
            self.close_sheet()
        if alive(self._animation):
            stop(self._animation)
            self._finished()

    def eventFilter(self, obj, event):
        if self.closing:
            return False
        if obj is self.host and event.type() == QEvent.Resize:
            self.refresh_background()
        elif obj is self.content and event.type() == QEvent.LayoutRequest and self.has_arrived and not self.tall:
            QTimer.singleShot(0, self._refit)                      # the content changed size: follow it
        return False

    def refresh_background(self):
        """Photograph the window behind again (it was resized, or its theme changed), without the sheet."""
        if self.closing:
            return
        self.hide()
        self.setGeometry(self.host.rect())
        self.background = self.host.grab()
        self._place_panel()
        self.show()
        self.raise_()

    def _refit(self):
        if alive(self) and not self.closing and self._panel_rect() != self.panel.geometry():
            self._place_panel()
            self.update()

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
        e = ease(EASE_POP, self.progress)
        dim = QColor(t["shadow"])
        dim.setAlphaF(t["backdrop_alpha"] * e)
        p.fillRect(self.rect(), dim)
        rect, s = self.panel.geometry(), self.SHADOW
        if self.panel.isVisible():                                 # live: only the shadow; the card paints itself
            p.drawPixmap(rect.left() - s, rect.top() - s, self.shadow)
        else:                                                      # moving: the photo fades in and rises
            p.setOpacity(min(1.0, e * 1.6))
            rise = (self.RISE if not self.closing else self.RISE / 2) * (1 - e)
            scale = 1 - (1 - POP) * (1 - e)                        # the card grows from 94 % as it rises
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.translate(rect.center().x(), rect.top() + rise)
            p.scale(scale, scale)
            p.translate(-rect.center().x(), -rect.top())
            p.drawPixmap(rect.left() - s, rect.top() - s, self.layer)


def rounded_path(rect, radius):
    """A rounded rectangle as a path (used to clip pictures to a card's corners)."""
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    return path
