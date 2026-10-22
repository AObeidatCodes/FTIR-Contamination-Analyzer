"""
FTIR Contamination Analyzer - figures

One drawing function used by both the desktop window and the report, so what the
user sees on screen is exactly what goes into the report.

Result view
    top panel     the raw data exactly as measured (%T or absorbance), nothing changed
    bottom panel  the copy that was compared (ink) over the best library match (blue),
                  the zones the checks look at (C-H, O-H / N-H, CO2), the key bands
                  that were found (blue triangles) and any unexplained band (coral);
                  optionally a second sample as a dashed line, to see if two finds are the
                  same material
Analytical view
    one panel per processing step (see analytical.py): raw data, absorbance, mode
    correction on the grid, derivative fingerprints, checks with baseline and rulers

Every drawing also returns the list of its curves, so the window can trace them:
under the mouse it shows the value of each curve at that wavenumber.

Labels never touch: every text in the result view (zone names, the tallest bands' wavenumbers,
"unexplained", the CO2 note) has a few places it may go. Each label takes the first place
where it touches no other label, no curve and no line; a label that only adds detail (a peak
wavenumber) is left out if no place is free. This is worked out again whenever the figure
changes size, so it holds on every window size and display scale.

Figures are drawn as vectors: on screen they follow the display's resolution, in the
report they are embedded as SVG (sharp at any zoom and in print), and "Save figure"
writes PNG at 300 dpi, SVG or PDF.

Uses matplotlib's Figure object directly (not pyplot): the safe way inside an app.

Short names used in this file:
    fig = the figure    top, bottom = its two panels (axes)    t = theme colours
    y = a spectrum    lo, hi = the ends of a zone    w = one band position
    pt = points (1/72 inch, the unit of text sizes)    box = a label's rectangle on screen

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
from .library import pearson
from .peaks import find_real_peaks
from .processing import GRID, fingerprint
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


# ---------------------------------------------------------------------------- labels that never touch
@dataclass
class Label:
    """A text that may go to one of several places: [(x offset pt, y offset pt, ha, va), ...].
    required: always shown (if no place is free, the first place is used anyway);
    otherwise it is hidden when nothing is free (a peak wavenumber only adds detail)."""

    artist: object
    places: list
    required: bool = False
    summary_of: list = None      # a summary label: lists the labels of these that found no place

    def _hidden(self):
        return [label for label in self.summary_of if not label.artist.get_visible()]


def _renderer(fig):
    """Something that can measure text: the figure's own canvas, or an off-screen one."""
    if not hasattr(fig.canvas, "get_renderer"):
        FigureCanvasAgg(fig)
    return fig.canvas.get_renderer()


def _line_points(ax):
    """Every curve and line of a panel as points on screen (straight lines filled in, so a label
    that crosses one between its two ends is still caught)."""
    points = []
    for line in ax.get_lines():
        xy = line.get_xydata()
        if not len(xy):
            continue
        screen = line.get_transform().transform(xy)
        if len(screen) < 50:                                       # e.g. a vertical line: only two ends
            steps = np.linspace(0, 1, 40)[:, None]
            screen = np.vstack([a + steps * (b - a) for a, b in zip(screen[:-1], screen[1:])] or [screen])
        points.append(screen[np.all(np.isfinite(screen), axis=1)])
    return np.vstack(points) if points else np.empty((0, 2))


def _touches(box, others, points, pad):
    """Does this label's box (made `pad` pixels bigger) overlap another label, or hold a curve point?"""
    grown = box.expanded(1, 1).padded(pad)
    if any(grown.overlaps(other) for other in others):
        return True
    if len(points):
        inside = ((points[:, 0] > grown.x0) & (points[:, 0] < grown.x1) &
                  (points[:, 1] > grown.y0) & (points[:, 1] < grown.y1))
        return bool(inside.any())
    return False


def place_labels(fig, fixed, labels):
    """Put every label in its first free place (see Label). `fixed` texts never move; they are
    obstacles, like the panel titles and the legend."""
    renderer = _renderer(fig)
    pad = 3 * fig.dpi / 72                                         # 3 pt of air around every label
    taken = [artist.get_window_extent(renderer) for artist in fixed if artist.get_visible()]
    points = {}
    for label in labels:
        if label.summary_of is not None:                          # "also unexplained: …" for the ones left out
            hidden = label._hidden()
            if not hidden:
                label.artist.set_visible(False)
                continue
            words = ", ".join(other.artist.get_text().split(" ")[0] for other in hidden)
            label.artist.set_text(f"also unexplained: {words} cm$^{{-1}}$")
        ax = label.artist.axes
        if ax not in points:
            points[ax] = _line_points(ax)
        frame = ax.get_window_extent(renderer)
        chosen = None
        for strict in ((True, False) if label.required else (True,)):
            for dx, dy, ha, va in label.places:
                label.artist.xyann = (dx, dy)
                label.artist.set_ha(ha)
                label.artist.set_va(va)
                box = label.artist.get_window_extent(renderer)
                # inside the panel, or on its title line (up to 22 pt above it), never past its sides
                inside = box.x0 >= frame.x0 and box.x1 <= frame.x1 and box.y1 <= frame.y1 + 22 * fig.dpi / 72
                if inside and not _touches(box, taken, points[ax] if strict else np.empty((0, 2)), pad):
                    chosen = box
                    break
            if chosen is not None:
                break
        if chosen is None and label.required:                     # nowhere free: the first place anyway
            dx, dy, ha, va = label.places[0]
            label.artist.xyann = (dx, dy)
            label.artist.set_ha(ha)
            label.artist.set_va(va)
            chosen = label.artist.get_window_extent(renderer)
        label.artist.set_visible(chosen is not None)
        if chosen is not None:
            taken.append(chosen)


def _keep_layout(fig, rows=0, fixed=(), labels=()):
    """Keep room above the panels for a legend of `rows` lines, and keep the labels apart.

    The room is a fixed height in points (the unit of the text), not a share of the figure, and
    both are worked out again whenever the figure changes size, so the legend never meets the panel
    title and no label meets another, whatever the window size or the display scale.
    rows=0 and no labels: stop keeping anything (the analytical view uses the same figure)."""
    old = getattr(fig, "_keep_layout", None)
    if old is not None and fig.canvas is not None:
        fig.canvas.mpl_disconnect(old)
        fig._keep_layout = None
    if not rows and not labels:
        return

    def fit(_=None):
        if rows:
            height = max(fig.get_figheight() * 72, 200)            # the figure's height in points
            fig.subplots_adjust(top=1 - (28 + 12 * rows) / height)
        if labels:
            place_labels(fig, fixed, labels)

    fig._fit_labels = fit                                          # saving calls it once more (see save_figure)
    fit()
    if fig.canvas is not None:
        fig._keep_layout = fig.canvas.mpl_connect("resize_event", fit)


def peak_positions(y, most=8):
    """The tallest real peaks of a scaled spectrum (wavenumber, height), tallest first, at most `most`.
    The CO2 region is left out: it is the air, not the sample."""
    filled = np.nan_to_num(y, nan=0.0)
    wn, heights = find_real_peaks(GRID, filled, min_share=0.06, min_distance_cm=30)
    lo, hi = config.CO2_ZONE[2]
    keep = [(w, a) for w, a in zip(wn, heights) if not lo <= w <= hi]
    return sorted(keep, key=lambda pair: -pair[1])[:most]


def sample_similarity(a, b):
    """How alike two analysed samples are: the same score r as against the library, sample to sample."""
    return pearson(fingerprint(a.compared), fingerprint(b.compared))


def draw_result(fig, result, library, t=LIGHT, compare=None, overlay=None):
    """Draw one Result into a Figure (cleared first). `t` is the theme (light or dark colours).

    compare: the name of another library material to draw instead of the best match
             ("compare with ..."), to see by eye why it scored lower. None = the best match.
    overlay: another analysed sample (a Result) drawn as a dashed line over this one. None = none.
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
    if overlay is not None and overlay is not result:
        other = scaled(overlay.compared)
        bottom.plot(GRID, other, color=t["ink_2"], lw=1.3, ls=(0, (5, 3)), solid_joinstyle="round", zorder=3)
        drawing.trace(bottom, f"{overlay.name} (scaled)", GRID, other, t["ink_2"], ".3f")
        handles.append(Line2D([], [], color=t["ink_2"], lw=1.6, ls=(0, (5, 3)),
                              label=f"other sample: {overlay.name} (r = {sample_similarity(result, overlay):.2f} to this one)"))
    title = "Compared with the library" if result.has_match else "Compared with the library: no reliable match"
    if shown and shown != result.best:
        title = f"Compared by hand with {shown} (the best match is {result.best})"
    bottom.set_title(title, loc="left", fontsize=9.5, color=t["ink_2"], pad=6)

    # The zones the checks look at: a light wash with a label on top (these labels never move)
    fixed, labels = [top.title, bottom.title], []
    for (lo, hi), label in [(config.CH_ZONE[2], "C–H"), (config.OH_ZONE[2], "O–H / N–H"),
                            (config.CO2_ZONE[2], "CO₂")]:
        bottom.axvspan(lo, hi, color=t["chart_zone"], alpha=0.05, lw=0, zorder=0)
        fixed.append(bottom.text((lo + hi) / 2, 0.985, label, ha="center", va="top", fontsize=7.5,
                                 color=t["muted"], transform=bottom.get_xaxis_transform()))

    # Band evidence: key bands found (blue triangles on the axis) and unexplained bands (coral lines)
    if result.evidence and shown == result.best:
        for w in result.evidence.found:
            bottom.plot(w, 0.0, marker="^", color=t["chart_found"], ms=6, mec=t["chart_surface"], mew=1.2,
                        transform=bottom.get_xaxis_transform(), clip_on=False, zorder=5)
        if result.evidence.found:
            handles.append(Line2D([], [], color=t["chart_found"], marker="^", ls="", ms=6,
                                  label="key band of the match, found"))
        for w in result.evidence.unexplained:
            bottom.axvline(w, ymax=0.9, color=t["chart_unexplained"], lw=1.6, ls=(0, (4, 3)), zorder=4)  # stops under the zone names
            # beside its line (left, else right), at one of three heights; never on the line itself
            text = bottom.annotate(f"{w:.0f} cm$^{{-1}}$ unexplained", xy=(w, 0.86), xycoords=("data", "axes fraction"),
                                   xytext=(-6, 0), textcoords="offset points", color=t["ink"], fontsize=8,
                                   zorder=6)
            labels.append(Label(text, [(dx, dy, ha, "center") for dy in (0, -22, -44)
                                       for dx, ha in ((-6, "right"), (6, "left"))]))
        if result.evidence.unexplained:
            # the bands whose label found no place beside its line are named together, in one free spot
            own = labels[-len(result.evidence.unexplained):]
            # first choice: the panel's title line, on the right (above the curves, so always clear of them)
            summary = bottom.annotate("", xy=(1, 1), xycoords="axes fraction", xytext=(0, 6),
                                      textcoords="offset points", color=t["ink"], fontsize=8, zorder=6)
            places = [(0, 6, "right", "bottom")] + [(-6, -y, "right", "top") for y in (16, 38, 60, 82)]
            labels.append(Label(summary, places, required=True, summary_of=own))
        if result.evidence.unexplained:
            handles.append(Line2D([], [], color=t["chart_unexplained"], lw=1.6, ls=(0, (4, 3)),
                                  label="band the match cannot explain"))

    # A large CO2 artefact: say which way it points, and why
    if result.checks.co2_share >= 0.1:
        down = result.checks.co2_direction == "down"
        note = bottom.annotate("CO$_2$ points " + ("down: less" if down else "up: more") + " CO$_2$ in the air\nthan "
                               "during the background scan", xy=(2280, 0.12 if down else 0.72),
                               xycoords=("data", "axes fraction"), xytext=(6, 0), textcoords="offset points",
                               ha="left", fontsize=7.5, color=t["ink_2"], zorder=6,
                               bbox={"boxstyle": "round,pad=0.3", "fc": t["chart_surface"], "ec": t["line"], "lw": 0.6})
        labels.append(Label(note, [(6, 0, "left", "center"), (6, 40, "left", "center"), (-130, 0, "right", "center"),
                                   (-130, 40, "right", "center")], required=True))

    # The tallest bands of the sample: their wavenumber just above the peak (the name is in the readout)
    near = list(result.evidence.unexplained) if result.evidence else []
    peaks = [] if result.checks.no_sample else peak_positions(scaled(result.compared))   # no sample: only noise
    for w, a in peaks:
        if any(abs(w - u) < 20 for u in near):                      # already labelled as unexplained
            continue
        if shown:                                                   # above whichever curve is higher there
            a = max(a, float(np.interp(w, GRID, np.nan_to_num(reference))))
        text = bottom.annotate(f"{w:.0f}", xy=(w, a), xytext=(0, 4), textcoords="offset points", ha="center",
                               va="bottom", fontsize=7.5, color=t["ink_2"], zorder=6)
        labels.append(Label(text, [(0, 4, "center", "bottom"), (5, 2, "left", "bottom"), (-5, 2, "right", "bottom")]))

    # The legend sits above both panels, in two columns, so it never covers a curve or a zone
    rows = (len(handles) + 1) // 2
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.07, 0.995), ncol=2, fontsize=8,
               frameon=False, labelcolor=t["ink_2"], handlelength=1.8, columnspacing=2.0, borderaxespad=0.2)
    bottom.set_ylim(-0.04, 1.3)                                   # head room for the peak and zone labels
    bottom.set_yticks([])
    bottom.set_xlim(config.GRID_STOP, config.GRID_START)          # FTIR convention: high wavenumber on the left
    bottom.set_xlabel("wavenumber (cm$^{-1}$)", color=t["muted"], fontsize=8.5)
    for ax in (top, bottom):
        _style(ax, t)
    fig.subplots_adjust(left=0.07, right=0.985, bottom=0.1)
    _keep_layout(fig, rows, fixed + [fig.legends[0]], labels)
    return drawing


def draw_analytical(fig, result, library, t=LIGHT):
    """Draw every processing step, one panel each, sharing the wavenumber axis."""
    setup_fonts()
    _keep_layout(fig)                                            # no legend room or label keeping here
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


def result_figure(result, library, t=LIGHT, size=(10, 5.2), compare=None, overlay=None):
    """A new off-screen figure with one result drawn into it."""
    fig = Figure(figsize=size)
    draw_result(fig, result, library, t, compare, overlay)
    return fig


def _refit(fig):
    """After a new canvas is attached for saving: place the labels once more for that canvas."""
    if getattr(fig, "_fit_labels", None):
        fig._fit_labels()


def result_svg(result, library, t=LIGHT):
    """The figure as SVG text, ready to be placed inside the HTML report (vector: sharp at any zoom)."""
    fig = result_figure(result, library, t)
    FigureCanvasSVG(fig)
    _refit(fig)
    buffer = io.StringIO()
    fig.savefig(buffer, format="svg", facecolor=t["chart_surface"],
                metadata={"Creator": f"{__title__} {__version__}", "Contributor": __author__})
    svg = buffer.getvalue()
    return svg[svg.index("<svg"):]                                 # drop the XML header lines


def save_figure(result, library, path, t=LIGHT, view="result", dpi=300, compare=None, overlay=None):
    """Save the result view or the analytical view as PNG (dpi as given), SVG or PDF (by file extension)."""
    if view == "analytical":
        fig = Figure(figsize=(10, 15))
        draw_analytical(fig, result, library, t)
    else:
        fig = result_figure(result, library, t, compare=compare, overlay=overlay)
    FigureCanvasAgg(fig)
    _refit(fig)
    suffix = str(path).lower().rsplit(".", 1)[-1]
    metadata = ({"Software": f"{__title__} {__version__}", "Author": __author__} if suffix == "png"
                else {"Creator": f"{__title__} {__version__}", "Author": __author__} if suffix == "pdf"
                else {"Creator": f"{__title__} {__version__}"})
    fig.savefig(path, dpi=dpi, facecolor=t["chart_surface"], metadata=metadata)
