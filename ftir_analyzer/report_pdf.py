"""
FTIR Contamination Analyzer - the PDF report

The report for people who read on paper or in an e-mail: A4 pages that look the same on every
computer, because the program lays them out itself (the HTML report is the one to explore on screen).

    page 1        the summary: four counts, one row per spectrum, the review and sign-off
    one page      per spectrum: verdict, score strip, the figure, why, band evidence, checks, where it
                  can come from, and the traceability of the raw file
    last pages    the run information (program, library, validation, settings, in-house references),
                  then every processing step in words

Every page has the program and the date at the foot and "Page x of y". Text stays real text (it can be
searched and copied); the figure is drawn at 220 dpi, sharp in print.

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
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Circle, FancyBboxPatch

from . import __author__, __title__, __version__, config
from .analytical import analytical_steps
from .checks import BELOW_ZERO_TEXT, describe_co2, describe_vapour
from .evidence import fab_sources
from .peaks import band_label
from .plots import _refit, result_figure, setup_fonts
from .records import DECISIONS, readable_time, who_text
from .theme import FONT_MONO, FONT_SANS, LIGHT

PAGE_W, PAGE_H = 595.0, 842.0                  # A4 in points
M = 40.0                                       # margin
BOTTOM = PAGE_H - 52.0                         # the last line of content (the foot lives below)
WIDTH = PAGE_W - 2 * M
T = LIGHT
STYLE = {"probable": "good", "weak": "warn", "no reliable match": "none"}
WORD = {"probable": "Probable", "weak": "Weak", "no reliable match": "No reliable match"}
SANS = [FONT_SANS, "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]
MONO = [FONT_MONO, "Consolas", "DejaVu Sans Mono"]
STATEMENT = "I have looked at the raw spectra and agree with the conclusions above, or I have noted my changes."


def plain(markup):
    """HTML (as the report writes it) as plain text."""
    text = re.sub(r"<br\s*/?>", "\n", markup)
    return html.unescape(re.sub(r"<[^>]+>", "", text))


class Ruler:
    """Measures text so lines can be wrapped to a width in points (one off-screen canvas, shared)."""
    renderer = None

    @classmethod
    def width(cls, text, size, weight="normal", family=None):
        if cls.renderer is None:
            cls.renderer = FigureCanvasAgg(Figure()).get_renderer()
        props = font_manager.FontProperties(family=family or SANS, size=size, weight=weight)
        w, _, _ = cls.renderer.get_text_width_height_descent(text, props, False)
        return w * 72.0 / cls.renderer.dpi

    @classmethod
    def wrap(cls, text, size, width, weight="normal", family=None):
        """The lines of `text` (new lines kept) none wider than `width` points; a word wider than that is cut."""
        lines = []
        for paragraph in str(text).split("\n"):
            line = ""
            for word in paragraph.split():
                while cls.width(word, size, weight, family) > width and len(word) > 1:      # a very long word
                    cut = len(word)
                    while cut > 1 and cls.width(word[:cut], size, weight, family) > width:
                        cut -= 1
                    if line:
                        lines.append(line)
                        line = ""
                    lines.append(word[:cut])
                    word = word[cut:]
                trial = f"{line} {word}".strip()
                if line and cls.width(trial, size, weight, family) > width:
                    lines.append(line)
                    line = word
                else:
                    line = trial
            lines.append(line)
        return lines


class Page:
    """One A4 page. `dry` pages draw nothing: they only tell how tall something would be."""

    def __init__(self, dry=False):
        self.dry = dry
        self.fig = Figure(figsize=(PAGE_W / 72, PAGE_H / 72), facecolor="white")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, PAGE_W)
        self.ax.set_ylim(PAGE_H, 0)
        self.ax.axis("off")

    # -- drawing --------------------------------------------------------------------------------
    def text(self, x, y, s, size=9.0, colour=None, weight="normal", ha="left", family=None):
        if not self.dry:
            self.ax.text(x, y, s, fontsize=size, color=colour or T["ink"], fontweight=weight, ha=ha, va="top",
                         family=family or SANS)

    def paragraph(self, x, y, s, width, size=9.0, colour=None, weight="normal", lead=1.38, family=None):
        """Wrapped text from y downwards; returns the y below it."""
        for line in Ruler.wrap(s, size, width, weight, family):
            self.text(x, y, line, size, colour, weight, family=family)
            y += size * lead
        return y

    def box(self, x, y, w, h, fill=None, edge=None, radius=6.0, lw=0.8):
        if not self.dry:
            self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
                                             fc=fill or "none", ec=edge or "none", lw=lw))

    def line(self, x0, y0, x1, y1, colour=None, lw=0.7):
        if not self.dry:
            self.ax.plot([x0, x1], [y0, y1], color=colour or T["line"], lw=lw, solid_capstyle="butt")

    def dot(self, x, y, radius, fill=None, edge=None, lw=1.2):
        if not self.dry:
            self.ax.add_patch(Circle((x, y), radius, fc=fill or "none", ec=edge or "none", lw=lw))

    def pill(self, x, y, word, kind, size=8.5):
        """A status label: pastel tint, dark word of the same hue. Returns its width."""
        w = Ruler.width(word, size, "bold") + 16
        self.box(x, y, w, size + 8, T[f"{kind}_bg"], radius=(size + 8) / 2)
        self.text(x + 8, y + 3.6, word, size, T[kind], "bold")
        return w

    def image(self, array, x, y, w, h):
        if not self.dry:
            self.ax.imshow(array, extent=(x, x + w, y + h, y), aspect="auto", interpolation="lanczos", zorder=1)
            self.ax.set_xlim(0, PAGE_W)
            self.ax.set_ylim(PAGE_H, 0)

    def heading(self, x, y, s, size=10.5):
        self.text(x, y, s, size, T["ink"], "bold")
        return y + size * 1.7


class Document:
    """The pages, in order; the foot with the page numbers is added when it is saved."""

    def __init__(self):
        self.pages = []

    def new(self):
        page = Page()
        self.pages.append(page)
        return page

    def save(self, path, title, stamp):
        metadata = {"Title": title, "Author": __author__, "Creator": f"{__title__} {__version__}",
                    "Subject": "FTIR contamination analysis"}
        total = len(self.pages)
        with matplotlib.rc_context({"pdf.fonttype": 42}), PdfPages(path, metadata=metadata) as pdf:
            for number, page in enumerate(self.pages, start=1):
                page.line(M, PAGE_H - 40, PAGE_W - M, PAGE_H - 40)
                page.text(M, PAGE_H - 33, f"{__title__} {__version__}  ·  {stamp}", 7.5, T["muted"])
                page.text(PAGE_W - M, PAGE_H - 33, f"Page {number} of {total}", 7.5, T["muted"], ha="right")
                pdf.savefig(page.fig)


# ------------------------------------------------------------------------------------------------ page 1

def stat_boxes(page, y, results):
    cells = [("good", sum(r.verdict == "probable" for r in results), "probable"),
             ("warn", sum(r.verdict == "weak" for r in results), "weak"),
             ("none", sum(r.verdict == "no reliable match" for r in results), "no reliable match"),
             ("bad" if any(r.flags for r in results) else "none", sum(bool(r.flags) for r in results),
              "with a flag to look at")]
    w = WIDTH / 4
    page.box(M, y, WIDTH, 52, "white", T["line"], 8)
    for i, (kind, n, word) in enumerate(cells):
        x = M + i * w
        if i:
            page.line(x, y + 6, x, y + 46)
        page.dot(x + 16, y + 15, 3.2, T[kind])
        page.text(x + 25, y + 10, word, 8.5, T["muted"])
        page.text(x + 13, y + 24, str(n), 18, T["ink"], "bold")
    return y + 52 + 18


SUMMARY_COLUMNS = [("Sample", 152), ("Verdict", 84), ("Match", 80), ("r", 28), ("Lead", 28), ("Mode", 62), ("Flags", 81)]


def summary_table(doc, page, y, results, title="Summary"):
    """The summary as a table; continues on a new page when it is full. Returns (page, y)."""
    xs = [M]
    for _, w in SUMMARY_COLUMNS:
        xs.append(xs[-1] + w)

    def header(page, y):
        page.text(M, y, title, 12, T["ink"], "bold")
        y += 22
        for (name, _), x in zip(SUMMARY_COLUMNS, xs):
            page.text(x + 4, y, name, 8, T["muted"])
        page.line(M, y + 13, M + WIDTH, y + 13, T["line_strong"])
        return y + 18

    y = header(page, y)
    for r in results:
        flags = "; ".join(label for label, _ in r.flags) or "-"
        cells = [r.name, None, r.match, f"{r.r:.2f}", f"{r.gap:.2f}", r.compared_as, flags]
        wrapped = [Ruler.wrap(c, 8, SUMMARY_COLUMNS[i][1] - 8) if c is not None and i != 1 else [""]
                   for i, c in enumerate(cells)]
        height = max(len(lines) for lines in wrapped) * 11 + 8
        if y + height > BOTTOM:
            page = doc.new()
            y = header(page, M + 4)
        kind = STYLE[r.verdict]
        for i, lines in enumerate(wrapped):
            if i == 1:
                page.dot(xs[1] + 9, y + 5, 3.2, T[kind])
                page.text(xs[1] + 16, y, WORD[r.verdict], 8, T[kind], "bold")
                continue
            for k, text in enumerate(lines):
                page.text(xs[i] + 4, y + k * 11, text, 8, T["ink"], "bold" if i == 0 else "normal")
        page.line(M, y + height - 3, M + WIDTH, y + height - 3)
        y += height
    return page, y + 14


def signoff_block(page, y, signoff, n):
    y = page.heading(M, y, "Review and sign-off", 12)
    if signoff:
        who = who_text(signoff["name"], signoff["login"])
        when = readable_time(signoff["signed_at"], with_zone=True)
        comment = Ruler.wrap(f"Comment: {signoff['comment']}", 8.5, WIDTH - 28) if signoff.get("comment") else []
        height = 34 + len(comment) * 11.7
        page.box(M, y, WIDTH, height, T["good_bg"], radius=8)
        page.text(M + 14, y + 11, f"{DECISIONS[signoff['decision']]}, signed by {who} on {when}.", 9, T["good"], "bold")
        if comment:
            page.paragraph(M + 14, y + 27, f"Comment: {signoff['comment']}", WIDTH - 28, 8.5, T["ink_2"])
        return y + height + 12
    y = page.paragraph(M, y, STATEMENT, WIDTH, 9, T["ink_2"]) + 6
    for label, x, w in (("Name", M, 150), ("Decision", M + 165, 120), ("Signature", M + 300, 120), ("Date", M + 435, 80)):
        page.line(x, y + 40, x + w, y + 40, T["ink_2"], 0.8)
        page.text(x, y + 44, label, 7.5, T["muted"])
    page.text(M, y + 66, "Not signed in the program: sign it there (Export report, Sign), or fill in the fields "
              "above by hand.", 7.5, T["muted"])
    return y + 84


def first_page(doc, results, info, signoff):
    page = doc.new()
    page.text(M, M - 4, "FTIR contamination report", 22, T["ink"], "bold")
    n = len(results)
    analysed_by = who_text(info.get("run_by_name", ""), info["run_by"])
    page.text(M, M + 28, f"{n} spectr{'um' if n == 1 else 'a'}  ·  {readable_time(info['run_at'], with_zone=True)}"
              f"  ·  analysed by {analysed_by}", 9, T["muted"])
    ok = info["validation"].passed
    badge = "Library validated" if ok else "Library NOT validated"
    w = Ruler.width(badge, 8.5, "bold") + 16
    page.pill(PAGE_W - M - w, M - 2, badge, "good" if ok else "bad")
    y = stat_boxes(page, M + 52, results)
    page, y = summary_table(doc, page, y, results)
    if y + 140 > BOTTOM:
        page = doc.new()
        y = M
    signoff_block(page, y, signoff, n)


# ------------------------------------------------------------------------------------------ one spectrum

def score_strip(page, y, r):
    """The verdict rule in one picture: r on a 0-1 scale coloured by the thresholds."""
    weak, probable = config.WEAK_R, config.PROBABLE_R
    w = 330.0

    def at(v):
        return M + min(max(v, 0.0), 1.0) * w

    for lo, hi, kind in ((0, weak, "none"), (weak, probable, "warn"), (probable, 1.0, "good")):
        page.box(at(lo), y, at(hi) - at(lo), 8, T[f"{kind}_bg"], radius=0)
    other = r.r - r.gap
    page.dot(at(other), y + 4, 4.6, "white", T["ink_2"], 1.4)
    page.dot(at(r.r), y + 4, 4.6, T["ink"])
    page.text(M, y + 13, "0", 7.5, T["muted"])
    page.text(at(weak), y + 13, f"weak from {weak:.2f}", 7.5, T["muted"], ha="center")
    page.text(M + w, y + 13, f"probable from {probable:.2f}", 7.5, T["muted"], ha="right")
    x, y2 = M, y + 28
    for filled, name, score in ((True, r.best, r.r), (False, r.runner_up, other)):
        page.dot(x + 4, y2 + 5, 3.6, T["ink"] if filled else "white", None if filled else T["ink_2"], 1.2)
        label = f"{name}  r {score:.2f}"
        page.text(x + 12, y2, label, 8.5, T["ink"], "bold" if filled else "normal")
        x += 12 + Ruler.width(label, 8.5, "bold") + 18
    page.text(x, y2, f"lead {r.gap:.2f}  (needed: {config.MIN_GAP:.2f})", 8.5, T["ink_2"])
    return y2 + 20


def facts_row(page, y, r):
    c, ev = r.checks, r.evidence
    cells = [("Key bands found", f"{len(ev.found)} of {ev.n_key}" if ev else "-"),
             ("Highest absorbance", f"{c.max_a:.2f}"), ("Compared as", r.compared_as)]
    w = WIDTH / 3
    page.box(M, y, WIDTH, 40, "white", T["line"], 8)
    for i, (label, value) in enumerate(cells):
        x = M + i * w
        if i:
            page.line(x, y + 5, x, y + 35)
        page.text(x + 12, y + 7, label, 8, T["muted"])
        page.text(x + 12, y + 19, value, 11, T["ink"], "bold")
    return y + 40 + 10


def next_step_box(page, y, r):
    alert = any(kind == "bad" for _, kind in r.flags)
    lines = Ruler.wrap(r.next_step, 9, WIDTH - 90)
    h = max(26, len(lines) * 12.4 + 14)
    page.box(M, y, WIDTH, h, T["bad_bg"] if alert else T["accent_soft"], radius=8)
    page.text(M + 12, y + 8.5, "Next step", 9, T["bad"] if alert else T["accent_ink"], "bold")
    page.paragraph(M + 72, y + 8.5, r.next_step, WIDTH - 86, 9, T["ink"])
    return y + h + 10


def chart_array(r, library, w, h):
    """The result figure for this page: w x h points, drawn at 220 dpi."""
    fig = result_figure(r, library, T, size=(w / 72, h / 72))
    fig.subplots_adjust(bottom=max(0.05, 36.0 / h))                 # room for the wavenumber axis label
    canvas = FigureCanvasAgg(fig)
    _refit(fig)
    fig.set_dpi(220)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba()).copy()


def kv_rows(page, x, y, width, rows, label_w=84, size=8.5):
    for label, value in rows:
        page.text(x, y, label, size, T["muted"])
        end = page.paragraph(x + label_w, y, value, width - label_w, size, T["ink"])
        y = max(end, y + size * 1.38) + 2.5
    return y


def spectrum_columns(page, y, r, library):
    """Why / band evidence / checks / where it can come from, in two columns. Returns the y below them."""
    col = (WIDTH - 24) / 2
    left, right = M, M + col + 24

    # left: why this verdict, the five best scores, the checks on the raw spectrum
    yl = page.heading(left, y, "Why this verdict")
    yl = page.paragraph(left, yl, r.reason, col, 8.5, T["ink_2"]) + 4
    for k, (name, score) in enumerate(r.ranking[:5]):
        page.text(left, yl, name, 8.5, T["ink"] if k == 0 else T["muted"], "bold" if k == 0 else "normal")
        page.line(left + 108, yl + 5, left + 108 + max(score, 0) * (col - 150), yl + 5,
                  T["ink"] if k == 0 else T["line_strong"], 2.2 if k == 0 else 1.6)
        page.text(left + col, yl, f"{score:.2f}", 8.5, T["ink"] if k == 0 else T["muted"], ha="right")
        yl += 13
    yl = page.heading(left, yl + 8, "Checks on the raw spectrum")
    c = r.checks
    rows = [("Saturation", f"highest A = {c.max_a:.2f}" + (" → saturated" if c.saturated else "")),
            ("CO2 artefact", describe_co2(c) + (" → probably no sample" if c.no_sample else "")),
            ("C-H", f"{c.ch} ({max(c.ch_share, 0):.3f} of the tallest band)"),
            ("O-H / N-H", f"{c.oh} ({max(c.oh_share, 0):.2f})"),
            ("Noise", f"{c.noise:.4f} A"), ("Water vapour", describe_vapour(c))]
    yl = kv_rows(page, left, yl, col, rows, 70)
    if c.below_zero:
        yl = page.paragraph(left, yl, BELOW_ZERO_TEXT, col, 7.5, T["muted"])

    # right: band evidence, where it can come from
    yr = page.heading(right, y, "Band evidence")
    ev = r.evidence
    if not ev:
        yr = page.paragraph(right, yr, "No match to explain. The tallest bands, to read by hand: "
                            + "; ".join(c.tallest_bands), col, 8.5, T["ink_2"])
    else:
        yr = page.paragraph(right, yr, f"{len(ev.found)} of {ev.n_key} key {r.best} bands are in the sample.", col,
                            8.5, T["ink"], "bold") + 1
        if ev.found:
            yr = page.paragraph(right, yr, "Found: " + ", ".join(f"{w:.0f}" for w in ev.found), col, 8.5, T["ink_2"])
        if ev.missing:
            yr = page.paragraph(right, yr, "Missing: " + ", ".join(f"{w:.0f}" for w in ev.missing), col, 8.5, T["warn"])
        if ev.unexplained:
            yr = page.paragraph(right, yr + 3, "Bands the match cannot explain (possible second component): "
                                + "; ".join(band_label(w) for w in ev.unexplained), col, 8.5, T["bad"])
            text = r.mixture.text() if r.mixture else (
                "No mix of the match and one other library reference explains these bands clearly: the second "
                "material is probably not in the library.")
            yr = page.paragraph(right, yr + 3, "Two-component fit. " + text, col, 8.5, T["ink_2"])
        else:
            yr = page.paragraph(right, yr + 2, "Every clear band of the sample is explained by the match.", col, 8, T["muted"])
    yr = page.heading(right, yr + 10, "Where it can come from in a fab")
    sources = fab_sources(r.best, library) if r.has_match else None
    if sources:
        yr = page.paragraph(right, yr, sources[0][:1].upper() + sources[0][1:] + ".", col, 8.5, T["ink"]) + 2
        yr = page.paragraph(right, yr, "Check next: " + sources[1] + ".", col, 8.5, T["ink"], "bold") + 2
        yr = page.paragraph(right, yr, "A starting point for the root-cause analysis, not proof.", col, 7.5, T["muted"])
    else:
        yr = page.paragraph(right, yr, "Only given when there is a match.", col, 8, T["muted"])
    return max(yl, yr)


def traceability_rows(r):
    s, c = r.spectrum, r.checks
    return [("File", str(s.path)), ("File SHA-256", s.sha256),
            ("Unit as measured", f"{s.unit}, recognised from the {s.unit_source}"),
            ("Data points", f"{len(s.wn)}, {s.wn.min():.0f}-{s.wn.max():.0f} cm-1"), ("Measuring mode", r.mode_text),
            ("Tallest bands", "; ".join(c.tallest_bands))]


def spectrum_page(doc, i, r, library):
    page = doc.new()
    y = M - 6
    kind = STYLE[r.verdict]
    title_w = min(Ruler.width(r.name, 15, "bold"), WIDTH - 200)
    page.text(M, y, r.name, 15, T["ink"], "bold")
    x = M + title_w + 12
    x += page.pill(x, y - 1, WORD[r.verdict], kind) + 8
    if r.has_match:
        page.text(x, y + 1, r.match, 11, T["ink"], "bold")
    y += 24
    page.text(M, y, f"{r.spectrum.path.name}, measured by {r.mode_text}", 8.5, T["muted"])
    if r.flags:
        x = PAGE_W - M
        for label, flag_kind in reversed(r.flags):
            w = Ruler.width(label, 8, "bold") + 16
            x -= w
            page.pill(x, y - 5, label, "bad" if flag_kind == "bad" else "warn", 8)
            x -= 6
    y += 20
    y = score_strip(page, y, r)
    y = facts_row(page, y, r)
    y = next_step_box(page, y, r)

    # what stands under the figure, measured on a page that draws nothing, so the figure gets the rest
    dry = Page(dry=True)
    under = spectrum_columns(dry, 0, r, library)
    trace = traceability_rows(r)
    trace_h = sum(max(len(Ruler.wrap(v, 7, WIDTH - 70, family=MONO if k in ("File", "File SHA-256") else None)), 1) * 9.6
                  + 2 for k, v in trace) + 16
    # 12 above the columns, 16 around the rule above the traceability: the rest of the page is the figure's
    chart_h = min(max(BOTTOM - y - under - trace_h - 12 - 16, 220), 340)
    page.image(chart_array(r, library, WIDTH, chart_h), M, y, WIDTH, chart_h)
    y += chart_h + 12
    y = spectrum_columns(page, y, r, library)
    y += 10
    page.line(M, y, M + WIDTH, y)
    y += 6
    for label, value in trace:
        mono = MONO if label in ("File", "File SHA-256") else None
        page.text(M, y, label, 7, T["muted"])
        end = page.paragraph(M + 70, y, value, WIDTH - 70, 7, T["ink_2"], family=mono, lead=1.37)
        y = max(end, y + 9.6) + 2


# ------------------------------------------------------------------------------------- last pages

def run_pages(doc, info, library, signoff):
    page = doc.new()
    y = page.heading(M, M - 4, "Traceability", 16) + 6
    analysed_by = who_text(info.get("run_by_name", ""), info["run_by"])
    validation = info["validation"]
    ok = validation.passed
    check = (f"{'Passed' if ok else 'FAILED'}: the best wrong answer scores {validation.score:.2f} "
             f"({validation.material} with itself removed → {validation.impostor}), "
             + (f"below the probable threshold {config.PROBABLE_R:.2f}." if ok else
                f"reaching the probable threshold {config.PROBABLE_R:.2f}: re-validate before using this report."))
    from .report import settings_html
    rows = [("Analysed", readable_time(info["run_at"], with_zone=True)), ("By", analysed_by),
            ("Program", info["program"]), ("Code SHA-256", info["code_sha256"]), ("Software", info["software"]),
            ("Library", info["library"]), ("Library SHA-256", info["library_sha256"]),
            ("Library validation", check), ("Settings", plain(settings_html()))]
    y = kv_rows(page, M, y, WIDTH, rows, 100, 9)
    if library is not None:
        in_house = [library.info_of(n) for n in library.in_house]
        y = page.heading(M, y + 10, "Reference library", 12)
        shipped = len(library) - len(in_house) - len(library.open_specy)
        text = (f"{shipped} shipped references (OpenFTIR, MIT licence)"
                + (f" and {len(in_house)} in-house reference{'s' if len(in_house) != 1 else ''} added by the lab."
                   if in_house else ". No in-house references were used.")
                + (f" Extended mode: {len(library.open_specy)} references from the Open Specy library (CC BY 4.0; "
                   "Cowger et al. 2021, Analytical Chemistry 93(21), 7543-7548), validated against every other "
                   "reference before use." if library.open_specy else ""))
        y = page.paragraph(M, y, text, WIDTH, 9, T["ink_2"]) + 6
        for i in in_house:
            need = 70
            if y + need > BOTTOM:
                page = doc.new()
                y = M
            page.box(M, y, WIDTH, need - 8, "white", T["line"], 8)
            page.text(M + 12, y + 8, i.name, 9.5, T["ink"], "bold")
            kv_rows(page, M + 12, y + 24, WIDTH - 24, [
                ("Added", f"{i.category}, by {i.added_by} on {readable_time(i.added_at)}"),
                ("Confirmed by", i.confirmation), ("Made from", f"{i.original_name}  (SHA-256 {i.sha256[:16]})")], 70, 8)
            y += need
        y = page.paragraph(M, y + 4, "Every addition and removal is kept in records/inhouse_library/library_changes.csv, "
                           "which is only ever appended to.", WIDTH, 8, T["muted"])


def steps_pages(doc, results, library):
    page = doc.new()
    y = page.heading(M, M - 4, "Appendix: every processing step", 16)
    y = page.paragraph(M, y + 2, "From the raw file to the fingerprint and the checks, in words. The raw data are "
                       "never changed.", WIDTH, 9, T["muted"]) + 8
    for r in results:
        steps = analytical_steps(r, library)
        if y + 70 > BOTTOM:
            page = doc.new()
            y = M
        page.text(M, y, r.name, 10.5, T["ink"], "bold")
        y += 17
        for step in steps:
            lines = Ruler.wrap(f"{step.number}.  {step.title}. {step.explanation}", 8.5, WIDTH - 14)
            height = len(lines) * 11.7 + 4
            if y + height > BOTTOM:
                page = doc.new()
                y = M
            page.paragraph(M + 14, y, f"{step.number}.  {step.title}. {step.explanation}", WIDTH - 14, 8.5, T["ink_2"],
                           lead=1.38)
            y += height
        y += 12


# ---------------------------------------------------------------------------------------- the entry

def write_pdf(results, library, info, path, signoff=None):
    """Write the PDF report to `path` (the report's folder is made if it is missing) and return the path."""
    setup_fonts()
    doc = Document()
    first_page(doc, results, info, signoff)
    for i, r in enumerate(results):
        spectrum_page(doc, i, r, library)
    run_pages(doc, info, library, signoff)
    steps_pages(doc, results, library)
    doc.save(path, "FTIR contamination report", readable_time(info["run_at"]))
    return path
