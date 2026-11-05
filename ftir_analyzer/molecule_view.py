"""
FTIR Contamination Analyzer - the 3D view of a material

    MoleculeView     a short model chain that turns slowly: drag it to look around. The bonds of a band glow.
    StructurePanel   that view with the material's band groups beside it, as a card

It is drawn with the window's own painter, so it needs no 3D package and shows in every snapshot of a transition.
A frame is made once, into a picture: scrolling the page only copies that picture. The chain only turns while it
can be seen and nothing else is moving, and with reduced motion it stands still until it is dragged.

Short names used in this file:
    p = the painter    t = theme colours    w, h = width and height    xyz = atom positions in angstrom

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import math

import numpy as np
from PySide6.QtCore import QElapsedTimer, QLineF, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .motion import Card, FlowLayout, Motion, Moving, SmoothScrollArea
from .structures import ELEMENTS, GLOW, bonds_at, groups_at, model_of, ranges_text
from .widgets import BandButton, Theme

LEVELS, SIZES = 7, 2.0                                                  # steps of depth, and of ball size in pixels


def mix(colour, ground, share):
    """A colour with this share of the ground colour in it."""
    a, b = QColor(colour), QColor(ground)
    return QColor(round(a.red() + (b.red() - a.red()) * share), round(a.green() + (b.green() - a.green()) * share),
                  round(a.blue() + (b.blue() - a.blue()) * share))


class MoleculeView(QWidget):
    """One model chain, turning slowly about its long axis. light() makes some of its bonds glow."""

    SPIN, TILT, MARGIN, FAR = 0.26, -0.24, 18, 0.62                     # radians a second, the lean, pixels, far = paler

    def __init__(self, height=300, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.OpenHandCursor)
        self.model, self.xyz, self.elements, self.bonds = None, None, [], []
        self.lit, self.glow, self.angle, self.turn, self.dragging = set(), 0.0, 0.5, self.TILT, None
        self.long, self.round = 1.0, 1.0
        self._frame, self._balls, self._theme, self.scroller = None, {}, "", None
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    def sizeHint(self):
        return QSize(640, self.minimumHeight())

    def set_model(self, model):
        self.model = model
        self.lit, self.glow = set(), 0.0
        if model is not None:
            self.elements = [atom[0] for atom in model["atoms"]]
            self.xyz = np.array([atom[1:] for atom in model["atoms"]], float)
            self.bonds = [(int(i), int(j), order) for i, j, order in model["bonds"]]
            self.long = float(np.abs(self.xyz[:, 0]).max()) + 1.0
            self.round = float(np.hypot(self.xyz[:, 1], self.xyz[:, 2]).max()) + 1.0
        self._render()
        self.update()
        self._run()

    def light(self, bonds):
        """Let these bonds glow (an empty set: none). The chain stands still while one does."""
        bonds = set(bonds)
        if bonds == self.lit:
            return
        self.lit = bonds
        if Motion.reduced or not self.isVisible():
            self.glow = 1.0 if bonds else 0.0
            self._render()
            self.update()
        self._run()

    # ---------------------------------------------------------------- when it moves
    def _run(self):
        if self.isVisible() and self.model is not None and not Motion.reduced:
            self.clock.start()
            self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, SmoothScrollArea):
            parent = parent.parentWidget()
        self.scroller = parent
        self._run()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def _busy(self):
        """True when a turn would only get in the way, or nobody would see it."""
        return (Moving.count or self.window().isMinimized() or self.visibleRegion().isEmpty()
                or (self.scroller is not None and self.scroller.timer.isActive()))

    def _tick(self):
        step = min(self.clock.restart() / 1000, 0.05)
        if self._busy():
            return
        moved = False
        if not self.lit and self.dragging is None:
            self.angle += self.SPIN * step
            moved = True
        target = 1.0 if self.lit else 0.0
        if abs(self.glow - target) > 0.004:
            self.glow += (target - self.glow) * min(1.0, step * 9)
            moved = True
        if moved:
            self._render()
            self.update()

    def mousePressEvent(self, event):
        self.dragging = event.position()
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.dragging is not None:
            step = event.position() - self.dragging
            self.dragging = event.position()
            self.turn += step.x() * 0.008
            self.angle += step.y() * 0.008
            self._render()
            self.update()

    def mouseReleaseEvent(self, _):
        self.dragging = None
        self.setCursor(Qt.OpenHandCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._frame = None
        self._render()

    # ---------------------------------------------------------------- drawing one frame
    def _ball(self, element, radius, shade):
        """A shaded ball, painted once: a frame only copies it. shade: 0 = far away and pale, LEVELS - 1 = near."""
        size = max(2.0, round(radius / SIZES * 2) / 2 * SIZES)
        key = (element, size, shade)
        if key not in self._balls:
            t, dpr = Theme.t, self.devicePixelRatioF() or 1.0
            side = int((2 * size + 4) * dpr)
            pix = QPixmap(side, side)
            pix.setDevicePixelRatio(dpr)
            pix.fill(Qt.transparent)
            base = self._colour(element, shade)
            c = size + 2
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            light = QRadialGradient(QPointF(c - size * 0.35, c - size * 0.4), size * 1.5)
            light.setColorAt(0.0, base.lighter(150))
            light.setColorAt(0.4, base)
            light.setColorAt(1.0, base.darker(150 if t["name"] == "dark" else 125))
            p.setPen(Qt.NoPen)
            p.setBrush(light)
            p.drawEllipse(QPointF(c, c), size, size)
            p.end()
            self._balls[key] = (pix, c)
        return self._balls[key]

    def _colour(self, element, shade):
        look = ELEMENTS.get(element, ELEMENTS["C"])
        t = Theme.t
        return mix(look[0 if t["name"] == "dark" else 1], t["surface"], self.FAR * (1 - shade / (LEVELS - 1)))

    def _render(self):
        """Draw one frame into the picture."""
        t = Theme.t
        width, height, dpr = self.width(), self.height(), self.devicePixelRatioF() or 1.0
        if width < 2 or height < 2:
            return
        if self._theme != t["name"]:
            self._theme, self._balls = t["name"], {}
        if self._frame is None:
            self._frame = QPixmap(int(width * dpr), int(height * dpr))
            self._frame.setDevicePixelRatio(dpr)
        self._frame.fill(QColor(t["surface"]))
        if self.model is None:
            return
        cos_a, sin_a, cos_t, sin_t = math.cos(self.angle), math.sin(self.angle), math.cos(self.turn), math.sin(self.turn)
        x, y, z = self.xyz[:, 0], self.xyz[:, 1], self.xyz[:, 2]
        y, z = y * cos_a - z * sin_a, y * sin_a + z * cos_a               # about the chain's long axis ...
        x, z = x * cos_t + z * sin_t, z * cos_t - x * sin_t               # ... then the lean
        scale = min((width - 2 * self.MARGIN) / (2 * self.long), (height - 2 * self.MARGIN) / (2 * self.round))
        camera = 3.2 * max(self.long, self.round)
        near = camera / (camera - z)
        sx = (width / 2 + x * scale * near).tolist()
        sy = (height / 2 - y * scale * near).tolist()
        reach = max(self.long, self.round)
        depth = np.clip((z + reach) / (2 * reach), 0, 1)
        near, zs = near.tolist(), depth.tolist()
        dim = 1 - 0.75 * self.glow
        lit_atoms = {a for n, (i, j, _) in enumerate(self.bonds) if n in self.lit for a in (i, j)}
        items = [((zs[i] + zs[j]) / 2 - 0.03, 0, n) for n, (i, j, _) in enumerate(self.bonds)]
        items += [(zs[i], 1, i) for i in range(len(self.elements))]
        items.sort()
        gold = QColor(GLOW.get(t["name"], GLOW["dark"]))
        halo = QColor(gold)
        halo.setAlphaF(0.42 * self.glow)
        tube = 0.2 * scale
        p = QPainter(self._frame)
        p.setRenderHint(QPainter.Antialiasing)
        for _, kind, n in items:
            if kind == 1:
                shade = zs[n] * (1 if n in lit_atoms else dim)
                radius = 0.52 * scale * near[n] * ELEMENTS.get(self.elements[n], ELEMENTS["C"])[2] * 0.72
                pix, c = self._ball(self.elements[n], radius, round(shade * (LEVELS - 1)))
                p.drawPixmap(QPointF(sx[n] - c, sy[n] - c), pix)
                continue
            i, j, order = self.bonds[n]
            on = n in self.lit
            a, b = QPointF(sx[i], sy[i]), QPointF(sx[j], sy[j])
            dx, dy = sy[j] - sy[i], sx[i] - sx[j]
            length = math.hypot(dx, dy) or 1.0
            size = tube * (near[i] + near[j]) / 2 * (0.62 if "H" in (self.elements[i], self.elements[j]) else 1.0)
            count = 3 if order == 3 else 2 if order > 1 else 1
            offsets = [0.0] if count == 1 else [-0.62, 0.62] if count == 2 else [-1.0, 0.0, 1.0]
            thick = size * (1.0 if count == 1 else 0.62) * (1.2 if on else 1.0)
            if on and self.glow > 0.02:
                p.setPen(QPen(halo, size * 4.4, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QLineF(a, b))
            middle = QPointF((sx[i] + sx[j]) / 2, (sy[i] + sy[j]) / 2)
            shade_i = round(zs[i] * (1 if on else dim) * (LEVELS - 1))
            shade_j = round(zs[j] * (1 if on else dim) * (LEVELS - 1))
            for k in offsets:
                shift = QPointF(dx / length * size * k * 0.62, dy / length * size * k * 0.62)
                if on:                                                  # a lit bond is one bright tube
                    p.setPen(QPen(mix(gold, t["surface"], 1 - self.glow), thick, Qt.SolidLine, Qt.FlatCap))
                    p.drawLine(QLineF(a + shift, b + shift))
                    continue
                # each half of a bond in its atom's colour, so a C=O shows red at once
                for start, end, element, shade in ((a, middle, self.elements[i], shade_i),
                                                   (middle, b, self.elements[j], shade_j)):
                    p.setPen(QPen(self._colour(element, shade), thick, Qt.SolidLine, Qt.FlatCap))
                    p.drawLine(QLineF(start + shift, end + shift))
        p.end()

    def retheme(self):
        self._render()
        self.update()

    def paintEvent(self, _):
        if self._frame is None:
            self._render()
        if self._frame is not None:
            QPainter(self).drawPixmap(0, 0, self._frame)


class StructurePanel(Card):
    """A card with the 3D view of a material and its band groups: hover or click a group to find its bonds."""

    picked = Signal(object)                                             # a band group was clicked: its wavenumber, or None
    SIDE = 236

    def __init__(self, height=300, parent=None):
        super().__init__(parent)
        self.name = QLabel()
        self.name.setObjectName("SectionTitle")
        hint = QLabel("short model chain · drag to turn")
        hint.setObjectName("SectionHint")
        self.view = MoleculeView(height)
        self.formula = QLabel()
        self.formula.setObjectName("Body2")
        self.note = QLabel()
        self.note.setObjectName("SectionHint")
        self.note.setWordWrap(True)
        self.chips_box = QWidget()
        self.chips = FlowLayout(self.chips_box)
        self.buttons, self.pinned, self.model = [], None, None
        side = QVBoxLayout()
        side.setSpacing(8)
        side.addWidget(self.formula)
        side.addWidget(self.chips_box)
        side.addWidget(self.note)
        side.addStretch()
        self.side = QWidget()
        self.side.setLayout(side)
        self.row = QBoxLayout(QBoxLayout.LeftToRight)
        self.row.setSpacing(12)
        self.row.addWidget(self.view, 1)
        self.row.addWidget(self.side)
        head = QHBoxLayout()
        head.addWidget(self.name)
        head.addStretch()
        head.addWidget(hint)
        column = QVBoxLayout(self)
        column.setContentsMargins(20, 16, 20, 16)
        column.setSpacing(8)
        column.addLayout(head)
        column.addLayout(self.row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < 720
        self.row.setDirection(QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight)
        self.side.setMinimumWidth(0 if narrow else self.SIDE)            # never a fixed width when narrow: the card
        self.side.setMaximumWidth(16777215 if narrow else self.SIDE)     # could then not get narrower with the window

    def show_material(self, name, library=None):
        """Show the model of a material, or hide the card if it has none. Returns True if it is shown."""
        self.model = model_of(name, library) if name else None
        self.pinned = None
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.buttons = []
        self.setVisible(self.model is not None)
        if self.model is None:
            self.view.set_model(None)
            return False
        self.name.setText(f"Structure of {name}")
        self.formula.setText(_formula(self.model["formula"]))
        self.note.setText(self.model["note"])
        self.note.setVisible(bool(self.model["note"]))
        for label, group in self.model["groups"].items():
            low, high = group["ranges"][0]
            button = BandButton((low + high) / 2, f"{label} · {low}–{high}", "group")
            button.setToolTip(f"{label}: {ranges_text(group)}")
            button.group = label
            button.hovered.connect(lambda on, b=button: self._preview(b.group if on else None))
            button.clicked.connect(lambda _=False, b=button: self._pick(b))
            self.chips.addWidget(button)
            self.buttons.append(button)
        self.view.set_model(self.model)
        return True

    def _bonds_of(self, group):
        return set(self.model["groups"][group]["bonds"]) if group and self.model else set()

    def _preview(self, group):
        self.view.light(self._bonds_of(group) if group else self._pinned_bonds())

    def _pinned_bonds(self):
        return bonds_at(self.model, self.pinned) if self.model and self.pinned is not None else set()

    def _pick(self, button):
        """A click on a group: its bonds stay lit (a second click lets go), and the spectrum can follow."""
        on = button.isChecked()
        self.show_band(button.w if on else None)
        button.setChecked(on)
        self.picked.emit(button.w if on else None)

    def show_band(self, w):
        """Light the bonds of a band at wavenumber w (None: no band). The groups it belongs to are marked."""
        self.pinned = w
        names = groups_at(self.model, w) if self.model and w is not None else []
        for button in self.buttons:
            button.setChecked(button.group in names)
        self.view.light(self._pinned_bonds())

    def preview_band(self, w):
        """Light a band's bonds while the mouse is on it; None: back to the pinned one."""
        self.view.light(bonds_at(self.model, w) if self.model and w is not None else self._pinned_bonds())


def _formula(text):
    """C20H18O8 with its numbers lowered."""
    return text.translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))
