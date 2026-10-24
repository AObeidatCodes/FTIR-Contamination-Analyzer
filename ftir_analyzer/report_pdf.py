"""
FTIR Contamination Analyzer - the PDF report

The report for people who read on paper or in an e-mail: A4 pages that look the same on every
computer, because the program lays them out itself (the HTML report is the one to explore on screen).

    page 1        the summary: four counts, one line per spectrum, the review and sign-off
    one page      per spectrum: the verdict, four figures, the figure of the spectrum (vector, sharp at
                  any zoom), why, band evidence, the checks, where it can come from
    last page     the traceability: program, library, validation, settings, in-house references

The look is quiet: white paper, hairlines instead of boxes, large figures as plain numbers, colour only
on data (the verdict dot, the curves, the marked bands). Every fact is one line. Text stays real text
(it can be searched and copied).

Short names used in this file:
    t = theme colours    x, y = position on the page in points (1/72 inch), y counting down from the top
    r = one Result       M = the page margin    w = a width in points

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import html
import re

import matplotlib
import numpy as np
from matplotlib import font_manager, ticker
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Circle

from . import __author__, __title__, __version__, config
from .brief import check_rows, clean_name, short_flag
from .evidence import fab_sources
from .peaks import band_label
from .plots import peak_positions, scaled, setup_fonts
from .processing import GRID
from .records import DECISIONS, readable_time, who_text
from .theme import FONT_MONO, FONT_SANS, LIGHT

PAGE_W, PAGE_H = 595.0, 842.0                  # A4 in points
M = 40.0                                       # margin
BOTTOM = PAGE_H - 56.0                         # the last line of content (the foot lives below)
WIDTH = PAGE_W - 2 * M
T = LIGHT
STYLE = {"probable": "good", "weak": "warn", "no reliable match": "none"}
WORD = {"probable": "Probable", "weak": "Weak", "no reliable match": "No match"}
SANS = [FONT_SANS, "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]
MONO = [FONT_MONO, "Consolas", "DejaVu Sans Mono"]
STATEMENT = "I have looked at the raw spectra and agree with the conclusions, or I have noted my changes."
HAIR = 0.5                                     # the width of a hairline, in points
RULE = "#A8A29E"                               # the rule under a table header


def plain(markup):
    """HTML (as the report writes it) as plain text."""
    text = re.sub(r"<br\s*/?>", "\n", markup)
    return html.unescape(re.sub(r"<[^>]+>", "", text))


class Ruler:
    """Measures text so a line can be fitted to a width in points (one off-screen canvas, shared)."""
    renderer = None

    @classmethod
    def width(cls, text, size, weight="normal", family=None):
        if cls.renderer is None:
            cls.renderer = FigureCanvasAgg(Figure()).get_renderer()
        props = font_manager.FontProperties(family=family or SANS, size=size, weight=weight)
        w, _, _ = cls.renderer.get_text_width_height_descent(text, props, False)
        return w * 72.0 / cls.renderer.dpi

    @classmethod
    def fit(cls, text, size, width, weight="normal", family=None):
        """One line: the text, cut with "…" if it is wider than `width` points."""
        text = " ".join(str(text).split())
        if cls.width(text, size, weight, family) <= width:
            return text
        while len(text) > 1 and cls.width(text + "…", size, weight, family) > width:
            text = text[:-1]
        return text.rstrip() + "…"

    @classmethod
    def wrap(cls, text, size, width, weight="normal", family=None):
        """The lines of `text` (new lines kept), none wider than `width` points."""
        lines = []
        for paragraph in str(text).split("\n"):
            line = ""
            for word in paragraph.split():
                trial = f"{line} {word}".strip()
                if line and cls.width(trial, size, weight, family) > width:
                    lines.append(line)
                    line = word
                else:
                    line = trial
            lines.append(line)
        return lines


class Page:
    """One A4 page; everything is placed in points from the top left."""

    def __init__(self):
        self.fig = Figure(figsize=(PAGE_W / 72, PAGE_H / 72), facecolor="white")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, PAGE_W)
        self.ax.set_ylim(PAGE_H, 0)
        self.ax.axis("off")

    def text(self, x, y, s, size=9.0, colour=None, weight="normal", ha="left", family=None):
        self.ax.text(x, y, s, fontsize=size, color=colour or T["ink"], fontweight=weight, ha=ha, va="top",
                     family=family or SANS)

    def line_text(self, x, y, s, width, size=9.0, colour=None, weight="normal", ha="left", family=None):
        """One line that always fits `width`."""
        self.text(x if ha == "left" else x + width, y, Ruler.fit(s, size, width, weight, family), size, colour,
                  weight, ha, family)

    def paragraph(self, x, y, s, width, size=9.0, colour=None, weight="normal", lead=1.42, family=None, most=None):
        """Wrapped text from y downwards (at most `most` lines); returns the y below it."""
        lines = Ruler.wrap(s, size, width, weight, family)
        if most and len(lines) > most:
            lines = lines[:most]
            lines[-1] = Ruler.fit(lines[-1] + " …", size, width, weight, family)
        for line in lines:
            self.text(x, y, line, size, colour, weight, family=family)
            y += size * lead
        return y

    def line(self, x0, y0, x1, y1, colour=None, lw=HAIR, dash=None):
        self.ax.plot([x0, x1], [y0, y1], color=colour or T["line_strong"], lw=lw, solid_capstyle="butt",
                     **({"dashes": dash} if dash else {}))

    def dot(self, x, y, radius=2.6, fill=None, edge=None, lw=1.0):
        self.ax.add_patch(Circle((x, y), radius, fc=fill or "none", ec=edge or "none", lw=lw))

    def verdict(self, x, y, r, size=9.0, weight="normal"):
        """The verdict: a dot in its colour and the word. Returns the width."""
        self.dot(x + 3, y + size * 0.55, 2.7, T[STYLE[r.verdict]])
        self.text(x + 11, y, WORD[r.verdict], size, T["ink"], weight)
        return 11 + Ruler.width(WORD[r.verdict], size, weight)

    def figure_axes(self, x, y, w, h):
        """A matplotlib axes at a place on the page (points)."""
        return self.fig.add_axes([x / PAGE_W, 1 - (y + h) / PAGE_H, w / PAGE_W, h / PAGE_H])


class Document:
    """The pages, in order; the foot with the page numbers is added when it is saved."""

    def __init__(self):
        self.pages = []

    def new(self, left="", right=""):
        page = Page()
        page.line_text(M, 30, left or "FTIR Contamination Analyzer", WIDTH / 2, 7.5, T["muted"])
        if right:
            page.line_text(M, 30, right, WIDTH, 7.5, T["muted"], ha="right")
        self.pages.append(page)
        return page

    def foot(self, stamp):
        total = len(self.pages)
        for number, page in enumerate(self.pages, start=1):
            page.line(M, PAGE_H - 44, PAGE_W - M, PAGE_H - 44, T["line"])
            page.text(M, PAGE_H - 36, f"{__title__} {__version__}  ·  {stamp}", 7.2, T["muted"])
            page.text(PAGE_W - M, PAGE_H - 36, f"Page {number} of {total}", 7.2, T["muted"], ha="right")

    def save(self, path, title, stamp):
        self.foot(stamp)
        metadata = {"Title": title, "Author": __author__, "Creator": f"{__title__} {__version__}",
                    "Subject": "FTIR contamination analysis"}
        with matplotlib.rc_context({"pdf.fonttype": 42}), PdfPages(path, metadata=metadata) as pdf:
            for page in self.pages:
                pdf.savefig(page.fig)


# ------------------------------------------------------------------------------------------------ page 1

def counts_row(page, y, results):
    cells = [(sum(r.verdict == "probable" for r in results), "probable"),
             (sum(r.verdict == "weak" for r in results), "weak"),
             (sum(r.verdict == "no reliable match" for r in results), "no reliable match"),
             (sum(bool(r.flags) for r in results), "with a flag")]
    x = M
    for n, word in cells:
        page.text(x, y, str(n), 28, T["ink"], "medium")
        page.text(x, y + 36, word, 8.5, T["muted"])
        x += max(Ruler.width(word, 8.5), 30) + 40
    return y + 62


COLUMNS = [("Sample", 0, 168, "left"), ("Verdict", 168, 74, "left"), ("Match", 242, 100, "left"),
           ("r", 342, 30, "right"), ("Lead", 372, 34, "right"), ("Flag", 424, WIDTH - 424, "left")]
ROW = 22.0


def table_head(page, y):
    for name, x, w, align in COLUMNS:
        page.line_text(M + x, y, name, w - (8 if align == "right" else 0), 8, T["muted"], ha=align)
    page.line(M, y + 15, M + WIDTH, y + 15, RULE, 0.7)
    return y + 15


def summary_table(doc, page, y, results):
    """One line per spectrum, a fixed row height; continues on a new page if it must."""
    y = table_head(page, y)
    for r in results:
        if y + ROW > BOTTOM:
            page = doc.new()
            y = table_head(page, M + 12)
        top = y + 6
        page.line_text(M, top, clean_name(r.name), COLUMNS[0][2] - 10, 9, T["ink"], "medium")
        page.verdict(M + COLUMNS[1][1], top, r, 9)
        page.line_text(M + COLUMNS[2][1], top, r.match if r.has_match else "–", COLUMNS[2][2] - 8, 9, T["ink"])
        page.line_text(M + COLUMNS[3][1], top, f"{r.r:.2f}", COLUMNS[3][2] - 8, 9, T["ink"], ha="right")
        page.line_text(M + COLUMNS[4][1], top, f"{r.gap:.2f}", COLUMNS[4][2] - 8, 9, T["ink"], ha="right")
        fx, fw = M + COLUMNS[5][1], COLUMNS[5][2]
        if r.flags:
            label, kind = r.flags[0]
            more = f" +{len(r.flags) - 1}" if len(r.flags) > 1 else ""
            page.dot(fx + 3, top + 5, 2.6, T["bad"] if kind == "bad" else T["warn"])
            page.line_text(fx + 11, top, short_flag(label) + more, fw - 11, 9, T["ink"])
        else:
            page.line_text(fx, top, "–", fw, 9, T["muted"])
        y += ROW
        page.line(M, y, M + WIDTH, y, T["line"])
    return page, y + 18


def signoff_block(page, y, signoff):
    page.text(M, y, "Review and sign-off", 11, T["ink"], "medium")
    y += 22
    if signoff:
        who = who_text(signoff["name"], signoff["login"])
        when = readable_time(signoff["signed_at"], with_zone=True)
        page.dot(M + 3, y + 5, 2.7, T["good"])
        page.line_text(M + 11, y, f"{DECISIONS[signoff['decision']]} · signed by {who} · {when}", WIDTH - 11, 9.5,
                       T["ink"], "medium")
        if signoff.get("comment"):
            page.paragraph(M + 11, y + 16, signoff["comment"], WIDTH - 11, 8.5, T["ink_2"], most=3)
        return
    page.line_text(M, y, STATEMENT, WIDTH, 8.5, T["ink_2"])
    y += 46
    x = M
    room = WIDTH - 3 * 24
    for label, share in (("Reviewed by", 0.30), ("Decision", 0.20), ("Signature", 0.30), ("Date", 0.20)):
        w = room * share
        page.line(x, y, x + w, y, T["ink"], 0.7)
        page.text(x, y + 4, label, 7.5, T["muted"])
        x += w + 24


def first_page(doc, results, info, signoff):
    n = len(results)
    page = doc.new(right=f"{readable_time(info['run_at'], with_zone=True)}  ·  analysed by "
                   f"{who_text(info.get('run_by_name', ''), info['run_by'])}")
    page.text(M, 60, "Contamination report", 26, T["ink"], "medium")
    ok = info["validation"].passed
    page.dot(M + 3, 106, 2.7, T["good"] if ok else T["bad"])
    page.line_text(M + 11, 100, f"{n} spectr{'um' if n == 1 else 'a'}  ·  "
                   f"{'library validated' if ok else 'LIBRARY NOT VALIDATED'}  ·  {info['library']}", WIDTH - 11, 9,
                   T["muted"])
    y = counts_row(page, 134, results)
    page, y = summary_table(doc, page, y + 14, results)
    if y + 110 > BOTTOM:
        page = doc.new()
        y = M + 12
    signoff_block(page, max(y + 6, BOTTOM - 96), signoff)


# ------------------------------------------------------------------------------------------ one spectrum

def figures_row(page, y, r):
    ev = r.evidence
    cells = [(f"{r.r:.2f}", "score r"), (f"{r.gap:.2f}", f"lead, needs {config.MIN_GAP:.2f}"),
             (f"{len(ev.found)} of {ev.n_key}" if ev else "–", "key bands found"),
             (f"{r.checks.max_a:.2f}", "highest absorbance"), (r.compared_as, "compared as")]
    x = M
    for value, label in cells:
        size = 20 if len(value) <= 6 else 14
        page.text(x, y + (20 - size) * 0.9, value, size, T["ink"], "medium")
        page.text(x, y + 26, label, 8, T["muted"])
        x += max(Ruler.width(value, size, "medium"), Ruler.width(label, 8)) + 32
    return y + 48


def score_strip(page, y, r):
    """The verdict rule in one picture: r on a 0-1 scale, the two thresholds marked."""
    weak, probable = config.WEAK_R, config.PROBABLE_R
    w = WIDTH

    def at(v):
        return M + min(max(v, 0.0), 1.0) * w

    page.line(M, y, M + w, y, T["line_strong"], 0.8)
    for v in (weak, probable):
        page.line(at(v), y - 3, at(v), y + 3, T["muted"], 0.6)
    page.dot(at(r.r - r.gap), y, 3.1, "white", T["ink_2"], 1.0)
    page.dot(at(r.r), y, 3.1, T["ink"])
    page.text(M, y + 7, "0", 7, T["muted"])
    page.text(at(weak) + 4, y + 7, f"weak from {weak:.2f}", 7, T["muted"])
    page.text(at(probable) - 4, y + 7, f"probable from {probable:.2f}", 7, T["muted"], ha="right")
    return y + 22


def next_step(page, y, r):
    alert = any(kind == "bad" for _, kind in r.flags)
    page.line(M, y + 1, M, y + 12, T["bad"] if alert else T["accent"], 1.6)
    page.text(M + 9, y, "Next step", 8.5, T["bad"] if alert else T["accent_ink"], "medium")
    end = page.paragraph(M + 68, y, r.next_step, WIDTH - 68, 8.8, T["ink"], most=3)
    return end + 8


def draw_chart(page, x, y, w, h, r, library):
    """The figure of one spectrum, drawn as vectors straight onto the page: the raw data above, the
    compared copy with the library match below, the zones, the key bands and the unexplained ones."""
    s = r.spectrum
    ev = r.evidence
    unit = "transmittance (%)" if s.unit == "%T" else "absorbance"
    shown = r.best if r.has_match else None
    reference = scaled(library.spectra[shown]) if shown else None
    compared = scaled(r.compared)

    # the legend: one line above the figure
    lx = x
    items = [("line", T["chart_sample"], f"sample, as compared ({r.compared_as})")]
    if shown:
        items.append(("line", T["chart_reference"], f"library: {shown}"))
    if ev and ev.found:
        items.append(("mark", T["chart_found"], "key band, found"))
    if ev and ev.unexplained:
        items.append(("dash", T["chart_unexplained"], "not explained by the match"))
    for kind, colour, label in items:
        if kind == "mark":
            page.ax.plot([lx + 5], [y + 5], marker="^", ms=4.2, color=colour, mew=0)
        else:
            page.line(lx, y + 5, lx + 14, y + 5, colour, 1.2, (3, 2) if kind == "dash" else None)
        page.text(lx + 19, y, label, 7.6, T["ink_2"])
        lx += 19 + Ruler.width(label, 7.6) + 18

    left, axis_h, title_h, gap = 8.0, 30.0, 14.0, 14.0
    top0 = y + 24
    inner = h - 24 - axis_h
    top_h = (inner - 2 * title_h - gap) * 0.27
    bot_h = inner - 2 * title_h - gap - top_h
    ax1 = page.figure_axes(x + left, top0 + title_h, w - left, top_h)
    ax2 = page.figure_axes(x + left, top0 + 2 * title_h + top_h + gap, w - left, bot_h)
    page.text(x + left, top0, "Raw data, exactly as measured", 8, T["ink_2"])
    page.text(x + left, top0 + title_h + top_h + gap, "Compared with the library" if shown
              else "Compared with the library: no reliable match", 8, T["ink_2"])

    def quiet(ax, labels):
        ax.patch.set_alpha(0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(T["chart_axis"])
            ax.spines[side].set_linewidth(0.6)
        ax.tick_params(colors=T["muted"], labelsize=7, length=2.5, width=0.5, pad=2,
                       labelbottom=labels)
        ax.set_xlim(config.GRID_STOP, config.GRID_START)           # FTIR convention: high wavenumber on the left

    ax1.plot(s.wn, s.raw, color=T["chart_sample"], lw=0.8)
    quiet(ax1, False)
    ax1.yaxis.set_major_locator(ticker.MaxNLocator(3))
    ax1.margins(y=0.08)
    ax1.set_ylabel(unit, fontsize=7, color=T["muted"], labelpad=3)

    for (lo, hi), label in [(config.CH_ZONE[2], "C–H"), (config.OH_ZONE[2], "O–H / N–H"), (config.CO2_ZONE[2], "CO₂")]:
        ax2.axvspan(lo, hi, color=T["chart_zone"], alpha=0.06, lw=0, zorder=0)
        ax2.text((lo + hi) / 2, 0.985, label, ha="center", va="top", fontsize=6.6, color=T["muted"],
                 transform=ax2.get_xaxis_transform(), family=SANS)
    if shown:
        ax2.plot(GRID, reference, color=T["chart_reference"], lw=1.0, zorder=2)
    ax2.plot(GRID, compared, color=T["chart_sample"], lw=0.9, zorder=3)
    quiet(ax2, True)
    ax2.set_ylim(-0.04, 1.3)
    ax2.set_yticks([])
    ax2.set_xticks(range(500 * int(np.ceil(config.GRID_START / 500)), int(config.GRID_STOP) + 1, 500))
    if ev:
        for wn in ev.found:
            ax2.plot(wn, 0.0, marker="^", ms=4.2, color=T["chart_found"], mew=0, clip_on=False, zorder=5,
                     transform=ax2.get_xaxis_transform())
        for wn in ev.unexplained:
            ax2.axvline(wn, ymax=0.9, color=T["chart_unexplained"], lw=0.9, ls=(0, (3, 2)), zorder=4)
            ax2.text(wn - 30, 0.86, f"{wn:.0f} unexplained", ha="right", va="center", fontsize=7, color=T["ink"],
                     transform=ax2.get_xaxis_transform(), family=SANS)

    # the tallest bands, named just above their peak; a label that would touch another is left out
    scale = 72.0 / page.fig.dpi
    taken = [(wn, 1.1) for wn in (ev.unexplained if ev else [])]
    placed = []
    for wn, height in ([] if r.checks.no_sample else peak_positions(compared, 8)):
        if any(abs(wn - u) < 22 for u, _ in taken):
            continue
        peak = max(height, float(np.interp(wn, GRID, np.nan_to_num(reference)))) if shown else height
        px, py = (v * scale for v in ax2.transData.transform((wn, peak)))
        if peak > 1.12 or any(abs(px - qx) < 30 and abs(py - qy) < 18 for qx, qy in placed):
            continue
        placed.append((px, py))
        ax2.text(wn, peak + 0.035, f"{wn:.0f}", ha="center", va="bottom", fontsize=7, color=T["ink_2"], family=SANS)
    page.text(x + left + (w - left) / 2, top0 + 2 * title_h + top_h + gap + bot_h + 16, "wavenumber (cm⁻¹)", 7.4,
              T["muted"], ha="center")


def kv(page, x, y, width, rows, label_w, size=8.4):
    """Label and value on one line each, a hairline under each."""
    for label, value in rows:
        page.line_text(x, y, label, label_w - 4, size, T["muted"])
        page.line_text(x + label_w, y, value, width - label_w, size, T["ink"])
        y += size * 1.38
        page.line(x, y + 2.5, x + width, y + 2.5, T["line"])
        y += 6
    return y


def spectrum_columns(page, y, r, library):
    """Why / band evidence / checks, three columns. Returns the y below them."""
    col = (WIDTH - 2 * 24) / 3
    xs = [M, M + col + 24, M + 2 * (col + 24)]
    for x, title in zip(xs, ("Why this verdict", "Band evidence", "Checks on the raw spectrum")):
        page.text(x, y, title, 9.5, T["ink"], "medium")
    y += 17

    end = [y, y, y]
    # why
    yy = page.paragraph(xs[0], y, r.reason, col, 8.2, T["ink_2"], most=3) + 3
    for k, (name, score) in enumerate(r.ranking[:4]):
        first = k == 0
        page.line_text(xs[0], yy, name, 78, 8.2, T["ink"] if first else T["muted"])
        page.line(xs[0] + 82, yy + 5, xs[0] + 82 + max(score, 0) * (col - 118), yy + 5,
                  T["ink"] if first else T["line_strong"], 1.6 if first else 1.1)
        page.text(xs[0] + col, yy, f"{score:.2f}", 8.2, T["ink"] if first else T["muted"], ha="right")
        yy += 13.5
    end[0] = yy

    # band evidence
    ev = r.evidence
    if not ev:
        yy = page.paragraph(xs[1], y, "No match to explain. The tallest bands, to read by hand:", col, 8.2,
                            T["ink_2"], most=2) + 2
        for label in r.checks.tallest_bands[:3]:
            page.line_text(xs[1], yy, label, col, 8.2, T["ink"])
            yy += 12
    else:
        yy = page.paragraph(xs[1], y, f"{len(ev.found)} of {ev.n_key} key bands found", col, 8.4,
                            T["ink"], "medium", most=1)
        if ev.found:
            yy = page.paragraph(xs[1], yy + 1, " · ".join(f"{w:.0f}" for w in ev.found), col, 8.2, T["ink_2"], most=2)
        if ev.missing:
            yy = page.paragraph(xs[1], yy + 1, "missing " + " · ".join(f"{w:.0f}" for w in ev.missing), col, 8.2,
                                T["warn"], most=1)
        if ev.unexplained:
            yy = page.paragraph(xs[1], yy + 5, "not explained: " + " · ".join(f"{w:.0f}" for w in ev.unexplained),
                                col, 8.2, T["bad"], most=2)
            names = "; ".join(band_label(w) for w in ev.unexplained)
            yy = page.paragraph(xs[1], yy, names, col, 7.4, T["muted"], most=3)
        else:
            yy = page.paragraph(xs[1], yy + 4, "Every clear band is explained by the match.", col, 7.8, T["muted"],
                                most=2)
    end[1] = yy

    # checks
    end[2] = kv(page, xs[2], y, col, check_rows(r.checks), 62, 8.2)
    return max(end)


def spectrum_page(doc, i, n, r, library):
    page = doc.new(right=f"Spectrum {i + 1} of {n}")
    y = 52
    match = r.match if r.has_match else ""
    block = 11 + Ruler.width(WORD[r.verdict], 10.5) + (14 + Ruler.width(match, 10.5, "medium") if match else 0)
    page.line_text(M, y, clean_name(r.name), WIDTH - block - 24, 20, T["ink"], "medium")
    vx = PAGE_W - M - block
    page.verdict(vx, y + 6, r, 10.5)
    if match:
        page.text(vx + 11 + Ruler.width(WORD[r.verdict], 10.5) + 14, y + 6, match, 10.5, T["ink"], "medium")
    y += 31
    page.line_text(M, y, f"{r.spectrum.path.name}  ·  measured by {r.mode_text}", WIDTH, 8.2, T["muted"])
    y += 24
    y = figures_row(page, y, r)
    y = score_strip(page, y + 2, r) + 6
    y = next_step(page, y, r) + 4

    # what stands under the figure: three columns (about 118 pt) and the traceability line (about 40 pt)
    chart_h = BOTTOM - y - 118 - 40 - 24
    draw_chart(page, M, y, WIDTH, chart_h, r, library)
    y += chart_h + 14
    y = spectrum_columns(page, y, r, library)

    sources = fab_sources(r.best, library) if r.has_match else None
    s = r.spectrum
    foot_y = BOTTOM - 28
    page.line(M, foot_y - 8, M + WIDTH, foot_y - 8, T["line"])
    if sources:
        page.line_text(M, foot_y, f"Where it can come from: {sources[0]}.  Check next: {sources[1]}.", WIDTH, 7.6,
                       T["ink_2"])
    page.line_text(M, foot_y + 12, f"SHA-256 {s.sha256}  ·  {len(s.wn)} points, {s.wn.min():.0f}–{s.wn.max():.0f} cm⁻¹  "
                   f"·  {s.unit}, from the {s.unit_source}", WIDTH, 6.8, T["muted"])


# ------------------------------------------------------------------------------------------- the last page

def run_page(doc, info, library):
    page = doc.new(right="Traceability")
    page.text(M, 52, "Traceability", 20, T["ink"], "medium")
    validation = info["validation"]
    ok = validation.passed
    check = (f"{'passed' if ok else 'FAILED'} · the best wrong answer scores {validation.score:.2f} "
             f"({validation.material} without itself → {validation.impostor}), "
             + (f"below {config.PROBABLE_R:.2f}" if ok else f"reaching {config.PROBABLE_R:.2f}: re-validate"))
    from .report import settings_html
    settings = plain(settings_html()).split("\n")
    rows = [("Analysed", readable_time(info["run_at"], with_zone=True)),
            ("By", who_text(info.get("run_by_name", ""), info["run_by"])), ("Program", info["program"]),
            ("Code SHA-256", info["code_sha256"]), ("Software", info["software"]), ("Library", info["library"]),
            ("Library SHA-256", info["library_sha256"]), ("Library validation", check),
            ("Probable when", settings[0].replace("probable: ", "")), ("Saturation, CO₂", settings[1]),
            ("C–H present", settings[2].replace("C–H present: ", "")),
            ("O–H / N–H", settings[3].replace("O–H / N–H: ", ""))]
    y = 96
    for label, value in rows:
        mono = label.endswith("SHA-256")
        page.line_text(M, y, label, 110, 8.6, T["muted"])
        page.line_text(M + 118, y, value, WIDTH - 118, 7.8 if mono else 8.6, T["ink"], family=MONO if mono else None)
        y += 12.4
        page.line(M, y + 2.5, M + WIDTH, y + 2.5, T["line"])
        y += 6.5
    if library is None:
        return
    in_house = [library.info_of(name) for name in library.in_house]
    shipped = len(library) - len(in_house) - len(library.open_specy)
    y += 22
    page.text(M, y, "Reference library", 11, T["ink"], "medium")
    y += 22
    text = (f"{shipped} shipped references (OpenFTIR, MIT licence)"
            + (f" and {len(in_house)} in-house reference{'s' if len(in_house) != 1 else ''} added by the lab."
               if in_house else ". No in-house references were used.")
            + (f" Extended mode: {len(library.open_specy)} references from the Open Specy library (CC BY 4.0; Cowger "
               "et al. 2021, Analytical Chemistry 93(21), 7543-7548), validated against every other reference "
               "before use." if library.open_specy else ""))
    y = page.paragraph(M, y, text, WIDTH, 8.6, T["ink_2"]) + 8
    for ref in in_house:
        if y + 70 > BOTTOM:
            page = doc.new(right="Traceability")
            y = 60
        page.text(M, y, ref.name, 9.2, T["ink"], "medium")
        y += 15
        y = kv(page, M, y, WIDTH, [("Added", f"{ref.category} · {ref.added_by} · {readable_time(ref.added_at)}"),
                                   ("Confirmed by", ref.confirmation),
                                   ("Made from", f"{ref.original_name} · SHA-256 {ref.sha256[:16]}")], 90, 8.2) + 6
    page.line_text(M, min(y + 6, BOTTOM - 10), "Every addition and removal is kept in "
                   "records/inhouse_library/library_changes.csv, which is only ever appended to.", WIDTH, 7.6, T["muted"])


# ---------------------------------------------------------------------------------------- the entry

def write_pdf(results, library, info, path, signoff=None):
    """Write the PDF report to `path` and return the path."""
    setup_fonts()
    doc = Document()
    first_page(doc, results, info, signoff)
    for i, r in enumerate(results):
        spectrum_page(doc, i, len(results), r, library)
    run_page(doc, info, library)
    doc.save(path, "FTIR contamination report", readable_time(info["run_at"]))
    return path
