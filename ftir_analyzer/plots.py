"""
FTIR Contamination Analyzer - figures

One drawing function used by both the desktop window and the report, so what the
user sees on screen is exactly what goes into the report.

Result view
    top panel     the raw data exactly as measured (%T or absorbance), nothing changed
    bottom panel  the copy that was compared (ink) over the best library match (blue),
                  the zones the checks look at (C-H, O-H / N-H, CO2), the key bands
                  that were found (blue triangles) and any unexplained band (coral)
Analytical view
    one panel per processing step (see analytical.py): raw data, absorbance, mode
    correction on the grid, derivative fingerprints, checks with baseline and rulers

Every drawing also returns the list of its curves, so the window can trace them:
under the mouse it shows the value of each curve at that wavenumber.

Figures are drawn as vectors: on screen they follow the display's resolution, in the
report they are embedded as SVG (sharp at any zoom and in print), and "Save figure"
writes PNG at 300 dpi, SVG or PDF.

Uses matplotlib's Figure object directly (not pyplot): the safe way inside an app.

Short names used in this file:
    fig = the figure    top, bottom = its two panels (axes)    t = theme colours
    y = a spectrum    lo, hi = the ends of a zone    w = one band position

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import io
from dataclasses import dataclass, field

import matplotlib
import numpy as np
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_svg import FigureCanvasSVG
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from . import __author__, __title__, __version__, config
from .analytical import BASELINE, BEFORE, REFERENCE, SAMPLE, analytical_steps
from .processing import GRID
from .theme import FONT_FILES, FONT_SANS, FONTS, LIGHT

# How each kind of curve is drawn in the analytical view: (colour key, line width, line style)
CURVE_STYLE = {SAMPLE: ("chart_sample", 1.2, "-"), REFERENCE: ("chart_reference", 1.4, "-"),
               BEFORE: ("line_strong", 1.2, "-"), BASELINE: ("muted", 1.0, (0, (4, 3)))}


@dataclass
class Drawing:
    """What was drawn: the panels (axes), and per panel the curves that can be traced with the mouse."""

    axes: list = field(default_factory=list)
    traces: dict = field(default_factory=dict)      # {axes: [(label, x, y, colour, number format)]}

    def trace(self, ax, label, x, y, colour, fmt=".4f"):
        self.traces.setdefault(ax, []).append((label, np.asarray(x, float), np.asarray(y, float), colour, fmt))

_fonts_ready = False


def setup_fonts():
    """Register the app's font (Inter) with matplotlib, once. Falls back quietly if missing."""
    global _fonts_ready
    if _fonts_ready:
        return
    found = False
    for name in FONT_FILES:
        path = FONTS / name
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            found = True
    family = [FONT_SANS] if found else []
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": family + ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"],
        "svg.fonttype": "path",            # text becomes vector outlines: looks identical everywhere
        "axes.unicode_minus": True,
        "mathtext.default": "regular",     # cm$^{-1}$ is set in the same font as the rest
    })
    _fonts_ready = True


def scaled(y):
    """Scale to 0-1 so a sample and a reference fit on the same axis (the shape is what matters)."""
    return (y - np.nanmin(y)) / (np.nanmax(y) - np.nanmin(y))


def _style(ax, t):
    """Quiet axes: hairline left and bottom spines, muted ticks, no box."""
    ax.set_facecolor(t["chart_surface"])
    ax.tick_params(colors=t["muted"], labelsize=8, length=3, width=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(t["chart_axis"])
        ax.spines[side].set_linewidth(0.8)


def _legend_room(fig, rows=0):
    """Keep room above the panels for a legend of `rows` lines (0: no room, and stop keeping it).

    The room is a fixed height in points (the unit of the text), not a share of the figure, and it
    is worked out again whenever the figure changes size, so the legend never meets the panel
    title, whatever the window size or the display scale."""
    old = getattr(fig, "_legend_room", None)
    if old is not None and fig.canvas is not None:
        fig.canvas.mpl_disconnect(old)
        fig._legend_room = None
    if not rows:
        return

    def fit(_=None):
        height = max(fig.get_figheight() * 72, 200)                # the figure's height in points
        fig.subplots_adjust(top=1 - (28 + 12 * rows) / height)

    fit()
    if fig.canvas is not None:
        fig._legend_room = fig.canvas.mpl_connect("resize_event", fit)


def draw_result(fig, result, library, t=LIGHT, compare=None):
    """Draw one Result into a Figure (cleared first). `t` is the theme (light or dark colours).

    compare: the name of another library material to draw instead of the best match
             ("compare with ..."), to see by eye why it scored lower. None = the best match.
    """
    setup_fonts()
    fig.clear()
    fig.set_facecolor(t["chart_surface"])
    top, bottom = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [1, 1.6], "hspace": 0.28})
    spectrum = result.spectrum

    drawing = Drawing([top, bottom])
    unit = "transmittance (%)" if spectrum.unit == "%T" else "absorbance"

    # Top: the file exactly as measured
    top.plot(spectrum.wn, spectrum.raw, color=t["chart_sample"], lw=1.1, solid_joinstyle="round")
    drawing.trace(top, f"raw {unit}", spectrum.wn, spectrum.raw, t["chart_sample"])
    top.set_ylabel(unit, color=t["muted"], fontsize=8.5)
    top.set_title("Raw data, exactly as measured", loc="left", fontsize=9.5, color=t["ink_2"], pad=6)

    # Bottom: the compared copy and, if there is a match, the library reference
    bottom.plot(GRID, scaled(result.compared), color=t["chart_sample"], lw=1.3, solid_joinstyle="round",
                zorder=3)
    drawing.trace(bottom, "sample (scaled)", GRID, scaled(result.compared), t["chart_sample"], ".3f")
    handles = [Line2D([], [], color=t["chart_sample"], lw=2, label=f"sample, as compared ({result.compared_as})")]
    shown = compare if compare in library.spectra else (result.best if result.has_match else None)
    if shown:
        score = dict(result.ranking).get(shown, float("nan"))
        reference = scaled(library.spectra[shown])
        bottom.plot(GRID, reference, color=t["chart_reference"], lw=1.5, alpha=0.9, solid_joinstyle="round", zorder=2)
        drawing.trace(bottom, f"{shown} (scaled)", GRID, reference, t["chart_reference"], ".3f")
        word = "library" if shown == result.best else "compared with"
        handles.append(Line2D([], [], color=t["chart_reference"], lw=2, label=f"{word}: {shown} (r = {score:.2f})"))
    title = "Compared with the library" if result.has_match else "Compared with the library: no reliable match"
    if shown and shown != result.best:
        title = f"Compared by hand with {shown} (the best match is {result.best})"
    bottom.set_title(title, loc="left", fontsize=9.5, color=t["ink_2"], pad=6)

    # The zones the checks look at: a light wash with a label on top
    for (lo, hi), label in [(config.CH_ZONE[2], "C–H"), (config.OH_ZONE[2], "O–H / N–H"),
                            (config.CO2_ZONE[2], "CO₂")]:
        bottom.axvspan(lo, hi, color=t["chart_zone"], alpha=0.05, lw=0, zorder=0)
        bottom.text((lo + hi) / 2, 0.985, label, ha="center", va="top", fontsize=7.5, color=t["muted"],
                    transform=bottom.get_xaxis_transform())      # x in data units, y as a share of the panel

    # Band evidence: key bands found (blue triangles on the axis) and unexplained bands (coral lines)
    if result.evidence and shown == result.best:
        for w in result.evidence.found:
            bottom.plot(w, 0.0, marker="^", color=t["chart_found"], ms=6, mec=t["chart_surface"], mew=1.2,
                        transform=bottom.get_xaxis_transform(), clip_on=False, zorder=5)
        if result.evidence.found:
            handles.append(Line2D([], [], color=t["chart_found"], marker="^", ls="", ms=6,
                                  label="key band of the match, found"))
        for w in result.evidence.unexplained:
            bottom.axvline(w, color=t["chart_unexplained"], lw=1.6, ls=(0, (4, 3)), zorder=4)
            bottom.text(w - 12, 0.86, f"{w:.0f} cm$^{{-1}}$ unexplained", color=t["ink"], fontsize=8, ha="right",
                        transform=bottom.get_xaxis_transform(), zorder=6,
                        bbox={"boxstyle": "round,pad=0.25", "fc": t["chart_surface"], "ec": "none", "alpha": 0.85})
        if result.evidence.unexplained:
            handles.append(Line2D([], [], color=t["chart_unexplained"], lw=1.6, ls=(0, (4, 3)),
                                  label="band the match cannot explain"))

    # A large CO2 artefact: say which way it points, and why
    if result.checks.co2_share >= 0.1:
        down = result.checks.co2_direction == "down"
        bottom.annotate("CO$_2$ points " + ("down: less" if down else "up: more") + " CO$_2$ in the air\nthan "
                        "during the background scan", xy=(2255, 0.08 if down else 0.72),   # just right of the zone
                        xycoords=("data", "axes fraction"), ha="left", fontsize=7.5, color=t["ink_2"],
                        bbox={"boxstyle": "round,pad=0.3", "fc": t["chart_surface"], "ec": t["line"], "lw": 0.6})

    # The legend sits above both panels, in two columns, so it never covers a curve or a zone
    rows = (len(handles) + 1) // 2
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.07, 0.995), ncol=2, fontsize=8,
               frameon=False, labelcolor=t["ink_2"], handlelength=1.8, columnspacing=2.0, borderaxespad=0.2)
    bottom.set_ylim(-0.04, 1.16)                                  # head room for the zone labels
    bottom.set_yticks([])
    bottom.set_xlim(config.GRID_STOP, config.GRID_START)          # FTIR convention: high wavenumber on the left
    bottom.set_xlabel("wavenumber (cm$^{-1}$)", color=t["muted"], fontsize=8.5)
    for ax in (top, bottom):
        _style(ax, t)
    fig.subplots_adjust(left=0.07, right=0.985, bottom=0.1)
    _legend_room(fig, rows)
    return drawing


def draw_analytical(fig, result, library, t=LIGHT):
    """Draw every processing step, one panel each, sharing the wavenumber axis."""
    setup_fonts()
    _legend_room(fig)                                            # no legend room here
    fig.clear()
    fig.set_facecolor(t["chart_surface"])
    steps = analytical_steps(result, library)
    axes = fig.subplots(len(steps), 1, sharex=True, gridspec_kw={"hspace": 0.42})
    drawing = Drawing(list(axes))
    for ax, step in zip(axes, steps):
        for curve in step.curves:
            colour_key, width, style = CURVE_STYLE[curve.role]
            ax.plot(curve.x, curve.y, color=t[colour_key], lw=width, ls=style, label=curve.label,
                    solid_joinstyle="round", zorder=3 if curve.role == SAMPLE else 2)
            drawing.trace(ax, curve.label, curve.x, curve.y, t[colour_key], ".3f" if step.number == 4 else ".4f")
        for lo, hi, label in step.spans:
            ax.axvspan(lo, hi, color=t["chart_zone"], alpha=0.07, lw=0, zorder=0)
            ax.text((lo + hi) / 2, 0.97, label, ha="center", va="top", fontsize=7, color=t["muted"],
                    transform=ax.get_xaxis_transform())
        for name, m in step.rulers:
            # the ruler: a dotted straight line between the two feet, and the measured height as a bar
            ax.plot([m.x1, m.x2], [m.y1, m.y2], color=t["accent"], lw=1.1, ls=":", marker="o", ms=3.5, zorder=4)
            ax.plot([m.x, m.x], [m.line, m.curve], color=t["chart_unexplained"] if m.height < 0 else t["accent"],
                    lw=2.2, zorder=5, solid_capstyle="butt")
            ax.annotate(f"{name} {m.height:+.4f}", xy=(m.x, max(m.line, m.curve)), xytext=(0, 6),
                        textcoords="offset points", ha="center", fontsize=7.5, color=t["ink"], zorder=6)
        ax.set_title(f"{step.number}  {step.title}", loc="left", fontsize=9.5, color=t["ink_2"], pad=5)
        ax.set_ylabel(step.y_label, color=t["muted"], fontsize=8)
        if len(step.curves) > 1:
            ax.legend(loc="upper left", fontsize=7.5, frameon=True, framealpha=0.9, edgecolor="none",
                      facecolor=t["chart_surface"], labelcolor=t["ink_2"], handlelength=1.6)
        _style(ax, t)
    axes[-1].set_xlim(config.GRID_STOP, config.GRID_START)
    axes[-1].set_xlabel("wavenumber (cm$^{-1}$)", color=t["muted"], fontsize=8.5)
    fig.subplots_adjust(left=0.08, right=0.985, top=0.97, bottom=0.05)
    return drawing


def result_figure(result, library, t=LIGHT, size=(10, 5.2), compare=None):
    """A new off-screen figure with one result drawn into it."""
    fig = Figure(figsize=size)
    draw_result(fig, result, library, t, compare)
    return fig


def result_svg(result, library, t=LIGHT):
    """The figure as SVG text, ready to be placed inside the HTML report (vector: sharp at any zoom)."""
    fig = result_figure(result, library, t)
    FigureCanvasSVG(fig)
    buffer = io.StringIO()
    fig.savefig(buffer, format="svg", facecolor=t["chart_surface"],
                metadata={"Creator": f"{__title__} {__version__}", "Contributor": __author__})
    svg = buffer.getvalue()
    return svg[svg.index("<svg"):]                                 # drop the XML header lines


def save_figure(result, library, path, t=LIGHT, view="result", dpi=300, compare=None):
    """Save the result view or the analytical view as PNG (dpi as given), SVG or PDF (by file extension)."""
    if view == "analytical":
        fig = Figure(figsize=(10, 15))
        draw_analytical(fig, result, library, t)
    else:
        fig = result_figure(result, library, t, compare=compare)
    FigureCanvasAgg(fig)
    suffix = str(path).lower().rsplit(".", 1)[-1]
    metadata = ({"Software": f"{__title__} {__version__}", "Author": __author__} if suffix == "png"
                else {"Creator": f"{__title__} {__version__}", "Author": __author__} if suffix == "pdf"
                else {"Creator": f"{__title__} {__version__}"})
    fig.savefig(path, dpi=dpi, facecolor=t["chart_surface"], metadata=metadata)
