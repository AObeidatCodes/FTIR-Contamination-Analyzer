"""
FTIR Contamination Analyzer - interactive figures

Plotly versions of the figures, used in the HTML report and by the run-as-code script
(FTIR_Analyzer.py). In the browser or in VS Code / Jupyter you can:

    hover      read every curve's value at that wavenumber, plus the name of the band there
    zoom       drag a rectangle (double-click to reset), or use the buttons top right
    pan        drag with the pan tool
    save       the camera button saves a PNG at 4x resolution (sharp enough to print)
    hide       click a legend entry to hide or show that curve

Two figures per spectrum:
    result_figure       the raw data and the comparison with the library (the "result view")
    analytical_figure   every processing step, from the raw file to the fingerprint and the checks

Short names used in this file:
    fig = the figure    t = theme colours    r = one Result    x, y = data    w = one band position
    lo, hi = the ends of a zone    row = which panel (1 = top)

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import config
from .analytical import BASELINE, BEFORE, REFERENCE, SAMPLE, analytical_steps
from .peaks import band_table
from .processing import GRID
from .theme import FONT_SANS, LIGHT

# How the figures behave in the browser
CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
    "toImageButtonOptions": {"format": "png", "scale": 4},          # 4x: print-quality PNG
}

# How each kind of curve is drawn: (colour key, width, dash)
STYLE = {SAMPLE: ("chart_sample", 1.6, "solid"), REFERENCE: ("chart_reference", 1.8, "solid"),
         BEFORE: ("line_strong", 1.4, "solid"), BASELINE: ("muted", 1.2, "dash")}
KEY = {SAMPLE: "ink", REFERENCE: "blue", BEFORE: "grey", BASELINE: "dashed"}


def band_names(x):
    """The band-table assignment for every wavenumber in x (shown when hovering)."""
    table = band_table()
    low, high = table["low"].to_numpy(float), table["high"].to_numpy(float)
    names = np.array(table["assignment"].tolist(), dtype=object)
    out = []
    for w in np.asarray(x, float):
        hits = names[(low <= w) & (high >= w)]
        out.append("; ".join(hits) if len(hits) else "no assignment in the band table")
    return out


def scaled(y):
    return (y - np.nanmin(y)) / (np.nanmax(y) - np.nanmin(y))


def _trace(x, y, name, t, role=SAMPLE, with_bands=False, legend=True, fmt=".4f"):
    """One curve. With with_bands=True the hover also names the band at that wavenumber."""
    colour, width, dash = STYLE[role]
    keep = np.isfinite(y)                                       # no data -> not drawn (never invented)
    x, y = np.asarray(x, float)[keep], np.round(np.asarray(y, float)[keep], 6)
    trace = go.Scatter(x=x, y=y, name=name, mode="lines", showlegend=legend,
                       line={"color": t[colour], "width": width, "dash": dash},
                       hovertemplate=f"{name}: %{{y:{fmt}}}<extra></extra>")
    if with_bands:
        trace.customdata = band_names(x)
        trace.hovertemplate = f"{name}: %{{y:{fmt}}}<br><i>%{{customdata}}</i><extra></extra>"
    return trace


def _x_range(fig):
    """The wavenumber range of every curve, high to low (the IR convention: 4000 on the left).

    Given to Plotly as a fixed range: with "autorange" Plotly recalculates the range whenever the
    window changes size, and on a narrow window it made room for the labels until the axis ran
    from 4800 to -5700 cm-1. A fixed range stays right at every size; double-click returns to it."""
    xs = [np.asarray(trace.x, float) for trace in fig.data if trace.x is not None and len(trace.x)]
    xs = np.concatenate(xs)
    xs = xs[np.isfinite(xs)]
    return [float(xs.max()), float(xs.min())]


def _style(fig, t, height, rows):
    """The shared look: quiet axes, crosshair across all panels, one hover box per panel."""
    fig.update_layout(
        height=height, margin={"l": 70, "r": 24, "t": 92, "b": 56},
        paper_bgcolor=t["chart_surface"], plot_bgcolor=t["chart_surface"],
        font={"family": f"{FONT_SANS}, Segoe UI, Helvetica, Arial, sans-serif", "size": 12, "color": t["ink_2"]},
        hovermode="x unified",
        hoverlabel={"bgcolor": t["surface"], "bordercolor": t["line_strong"], "font": {"color": t["ink"], "size": 12}},
        legend={"orientation": "h", "yanchor": "top", "y": 0.985, "xanchor": "left", "x": 0, "yref": "container",
                "font": {"size": 12, "color": t["ink_2"]}, "bgcolor": "rgba(0,0,0,0)"},
        dragmode="zoom",
    )
    fig.update_xaxes(range=_x_range(fig), autorange=False, showgrid=False, showline=True, linecolor=t["chart_axis"],
                     ticks="outside", tickcolor=t["chart_axis"], color=t["muted"], zeroline=False,
                     showspikes=True, spikemode="across", spikesnap="cursor", spikecolor=t["muted"],
                     spikethickness=1, spikedash="solid", hoverformat=".0f")
    fig.update_yaxes(showgrid=True, gridcolor=t["chart_grid"], zeroline=False, showline=True,
                     linecolor=t["chart_axis"], color=t["muted"], ticks="outside", tickcolor=t["chart_axis"])
    fig.update_xaxes(title_text="wavenumber (cm⁻¹)", row=rows, col=1)
    for annotation in fig.layout.annotations:                  # the panel titles: left-aligned, quiet
        if annotation.text and annotation.yref == "paper":
            annotation.update(x=0, xanchor="left", font={"size": 13, "color": t["ink"]})
    return fig


def result_figure(r, library, t=LIGHT):
    """The raw data on top; the compared copy with the library match, zones and band evidence below."""
    s = r.spectrum
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.38, 0.62],
                        subplot_titles=("Raw data, exactly as measured",
                                        "Compared with the library" if r.has_match else
                                        "Compared with the library: no reliable match"))
    unit = "transmittance (%)" if s.unit == "%T" else "absorbance"
    fig.add_trace(_trace(s.wn, s.raw, f"raw {unit}", t, SAMPLE, legend=False), 1, 1)    # every measured point
    fig.add_trace(_trace(GRID, scaled(r.compared), f"sample, as compared ({r.compared_as})", t, SAMPLE,
                         with_bands=True, fmt=".3f"), 2, 1)
    if r.has_match:
        fig.add_trace(_trace(GRID, scaled(library.spectra[r.best]), f"library: {r.best} (r = {r.r:.2f})", t,
                             REFERENCE, fmt=".3f"), 2, 1)

    # the zones the checks look at
    for (lo, hi), label in [(config.CH_ZONE[2], "C–H"), (config.OH_ZONE[2], "O–H / N–H"),
                            (config.CO2_ZONE[2], "CO₂")]:
        fig.add_vrect(x0=lo, x1=hi, fillcolor=t["chart_zone"], opacity=0.05, line_width=0, row=2, col=1,
                      annotation_text=label, annotation_position="top", annotation_font_size=11,
                      annotation_font_color=t["muted"])

    # band evidence: key bands found, bands the match cannot explain
    if r.evidence and r.evidence.found:
        fig.add_trace(go.Scatter(x=r.evidence.found, y=[-0.04] * len(r.evidence.found), mode="markers",
                                 name="key band of the match, found", hovertemplate="key band %{x:.0f}<extra></extra>",
                                 marker={"symbol": "triangle-up", "size": 10, "color": t["chart_found"],
                                         "line": {"color": t["chart_surface"], "width": 1.5}}), 2, 1)
    for w in (r.evidence.unexplained if r.evidence else []):
        fig.add_vline(x=w, line={"color": t["chart_unexplained"], "width": 1.8, "dash": "dash"}, row=2, col=1,
                      annotation_text=f"{w:.0f} cm⁻¹ unexplained", annotation_position="top left",
                      annotation_font_color=t["ink"], annotation_font_size=12)
    if r.evidence and r.evidence.unexplained:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name="band the match cannot explain",
                                 line={"color": t["chart_unexplained"], "dash": "dash", "width": 1.8}), 2, 1)

    # a large CO2 artefact: say which way it points and why
    if r.checks.co2_share >= 0.1:
        down = r.checks.co2_direction == "down"
        fig.add_annotation(x=2255, y=0.1 if down else 0.8, xref="x2", yref="y2 domain", showarrow=False,
                           text="CO₂ points down: less CO₂ in the air<br>than during the background scan" if down
                           else "CO₂ points up: more CO₂ in the air<br>than during the background scan",
                           font={"size": 11, "color": t["ink_2"]}, bgcolor=t["chart_surface"], xanchor="left",
                           align="left", bordercolor=t["line"], borderpad=4)

    fig.update_yaxes(title_text=unit, row=1, col=1)
    fig.update_yaxes(title_text="scaled 0–1", showticklabels=False, range=[-0.08, 1.15], row=2, col=1)
    return _style(fig, t, 560, 2)


def analytical_figure(r, library, t=LIGHT):
    """Every step, one panel each, sharing the wavenumber axis (see analytical.py)."""
    steps = analytical_steps(r, library)
    titles = []
    for step in steps:
        keys = ", ".join(f"{KEY[c.role]} = {c.label}" for c in step.curves) if len(step.curves) > 1 else ""
        titles.append(f"{step.number}  {step.title}" + (f"   <span style='font-size:11px'>({keys})</span>" if keys else ""))
    fig = make_subplots(rows=len(steps), cols=1, shared_xaxes=True, vertical_spacing=0.045, subplot_titles=titles)
    for row, step in enumerate(steps, start=1):
        for curve in step.curves:
            fmt = ".3f" if step.number == 4 else ".4f"
            on_grid = len(curve.x) <= len(GRID)                      # band names on the 5 cm-1 grid curves
            fig.add_trace(_trace(curve.x, curve.y, curve.label, t, curve.role,
                                 with_bands=curve.role == SAMPLE and on_grid, legend=False, fmt=fmt), row, 1)
        for lo, hi, label in step.spans:
            fig.add_vrect(x0=lo, x1=hi, fillcolor=t["chart_zone"], opacity=0.07, line_width=0, row=row, col=1,
                          annotation_text=label, annotation_position="top", annotation_font_size=11,
                          annotation_font_color=t["muted"])
        for name, m in step.rulers:
            # the ruler: a dashed straight line between the two feet, and the measured height
            fig.add_trace(go.Scatter(x=[m.x1, m.x2], y=[m.y1, m.y2], mode="lines+markers", showlegend=False,
                                     name=f"{name} ruler", hoverinfo="skip",
                                     line={"color": t["accent"], "width": 1.4, "dash": "dot"},
                                     marker={"size": 6, "color": t["accent"]}), row, 1)
            fig.add_trace(go.Scatter(x=[m.x, m.x], y=[m.line, m.curve], mode="lines", showlegend=False,
                                     name=f"{name} height", hovertemplate=f"{name} height: {m.height:+.4f}<extra></extra>",
                                     line={"color": t["chart_unexplained"] if m.height < 0 else t["accent"], "width": 2.5}),
                          row, 1)
            fig.add_annotation(x=m.x, y=max(m.line, m.curve), text=f"{name} {m.height:+.4f}", showarrow=False,
                               yshift=12, font={"size": 11, "color": t["ink"]}, row=row, col=1)
        fig.update_yaxes(title_text=step.y_label, title_font={"size": 11}, row=row, col=1)
    return _style(fig, t, 300 * len(steps), len(steps))


def figure_html(fig, div_id, file_name):
    """A figure as an HTML fragment (plotly.js itself is added once to the page)."""
    config = dict(CONFIG, toImageButtonOptions=dict(CONFIG["toImageButtonOptions"], filename=file_name))
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id, config=config)
