"""
FTIR Contamination Analyzer - desktop application

The window a lab user works in:

    toolbar       logo and name; the Analyze | Library switch in the middle; Open spectra /
                  Open folder / Demo / Export report; the library validation badge; light-dark; help
    Analyze       left: the analysed spectra (status icon, name, match, score, flags), with a filter
                  right: the result of the selected spectrum
                    name, verdict, match and flags
                    the score strip: the score r and the next material's against the verdict rule
                    three facts: key bands found, highest absorbance, how it was compared
                    the next step, in one sentence (and "add to library" when it is not known)
                    the figure, with zoom / pan / save, "compare with ..." and a live band readout
                    (switch to the Analytical view to see every processing step)
                    the closest matches: the best four materials side by side with the sample,
                    where the shapes differ shaded
                    why this verdict (ranking bars with thresholds), band evidence (chips),
                    checks on the raw spectrum, where it can come from in a fab, traceability
    Library       every reference as a card, by category; the similarity map; adding a reference
                  (validated before it is saved, with a preview of which results would change)
    bottom        status bar with activity indicator and progress

Files can also be dropped onto the window. When a file does not say how it was measured,
a dialog asks once and the answer is saved in the sample log. Nothing is ever written
into the raw files. Slow work (loading the library, analysing, validating, writing the
report) runs in the background, so the window never freezes.

Motion (see motion.py): selecting a spectrum first fills the page and draws the figure,
then the new page rises in from two snapshots, then the numbers count up and the bars
grow. Nothing is drawn while something moves, so it stays smooth. View > Reduce motion
switches it off (and it starts off if Windows' "Show animations" is off).

Built with Qt (PySide6) and matplotlib.

Short names used in this file:
    r = one Result    t = the current theme colours    ev = band evidence    c = checks    s = spectrum

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import gc
import html
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QPoint, QRect, QSettings, QSize, QSortFilterProxyModel, Qt, QThreadPool,
                            QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFontDatabase, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListView, QMainWindow, QMenu,
                               QMessageBox, QProgressBar, QPushButton, QSplitter, QStackedWidget, QTextBrowser,
                               QToolButton, QVBoxLayout, QWidget)

from . import __author__, __license__, __title__, __version__, config
from .analysis import NO_MATCH, PROBABLE, WEAK, analyse
from .checks import BELOW_ZERO_TEXT, describe_co2
from .evidence import fab_sources
from .export_view import ExportPanel
from .inhouse import InHouseLibrary, changes_between, reanalyse
from .jobs import Job
from .library import impostor_test, load_library
from .library_view import (EXTENDED, AddReferencePanel, LibraryPage, MaterialDetail, OpenSpecyPanel, SimilarityPanel,
                           similarity_for)
from .openspecy import OpenSpecyLibrary, download_and_import, import_library
from .compare_view import TopMatches
from .motion import (MOTION, Card, FadeStack, Motion, Overlay, Sheet, SmoothScrollArea, Spinner, Tabs, Toast,
                     animate, count_up, crossfade, fade_through, make_opaque, rise_in, snapshot, zero_like)
from .peaks import band_label
from .plots import save_figure, setup_fonts
from .records import SampleLog, readable_time, resolve_modes, run_info
from .report import write_report
from .spectrum_io import SpectrumFileError, find_spectrum_files, read_spectra
from .theme import FONT_FILES, FONTS, THEMES, VERDICT_LOOK, stylesheet
from .widgets import (ElidedLabel, EmptyState, FlowLayout, ModeDialog, Pill, PlotPanel, ScoreBars, ScoreStrip,
                      SpectrumDelegate, SpectrumListModel, Theme, chip, clear_layout, flag_pill, icon, icon_pixmap,
                      logo_pixmap, verdict_pill)

FILE_FILTER = "Spectrum files (" + " ".join(f"*{ext}" for ext in config.SPECTRUM_FILE_TYPES) + ");;All files (*)"
ANALYZE, LIBRARY = "analyze", "library"

HOW_IT_WORKS = f"""
<h2>How the analyzer works</h2>
<p>For every spectrum the program runs the same nine steps. Every rule and number lives in
<code>config.py</code>, with the reason for its value.</p>
<ol>
<li><b>Read</b> the file exactly as measured. The values are made read-only and the file's SHA-256
checksum is recorded, so the report can be traced to this exact file.</li>
<li><b>Absorbance</b>: %T is converted with A = −log₁₀ T, on a copy.</li>
<li><b>Measuring mode</b>: the library was measured by ATR, so a transmission spectrum is given the
ATR look (× 1000 / wavenumber) before it is compared; a reference measured in transmission too.
Mode not known: the spectrum is read both ways and the better fit is used (and named). A given mode
that fits clearly worse than the other one is flagged <i>mode doubt</i>.</li>
<li><b>Common grid</b>: 650–4000 cm⁻¹ every 5 cm⁻¹. Nothing is invented outside the measured range.</li>
<li><b>Fingerprint</b>: |first derivative| (Savitzky–Golay, 11 points, cubic), scaled 0–1, so offsets,
sloping baselines and sample thickness drop out.</li>
<li><b>Search</b>: Pearson r against every reference; the CO₂ region 2280–2400 cm⁻¹ is left out.</li>
<li><b>Verdict</b>: <i>probable</i> if r ≥ {config.PROBABLE_R} and the lead over the next material is
≥ {config.MIN_GAP}; <i>weak</i> if r ≥ {config.WEAK_R}; otherwise <i>no reliable match</i>.
Each time the library is loaded the impostor test removes each material and searches for it:
the best <i>wrong</i> answer must stay below {config.PROBABLE_R}.</li>
<li><b>Checks</b> on the raw spectrum: saturation (A &gt; {config.SATURATED_A}), the CO₂ artefact
(is there a sample at all?), C–H (organic?) and O–H / N–H. Each band is measured above a straight
line between its feet and must be at least 3× the noise.</li>
<li><b>Band evidence</b>: which key bands of the match are present or missing, and which clear
bands the match cannot explain: a possible second component.</li>
</ol>
<p>The program suggests; a person reviews the raw spectrum and signs the report.</p>
<h3>The library</h3>
<p>Open <b>Library</b> (Ctrl+2) to see every reference as a card, by category, with where it came from.
Click a card for its spectrum, key bands, fab sources and its nearest neighbours. The <b>similarity map</b>
shows every reference against every other one.</p>
<p><b>Adding a reference</b>: when a material was identified by other means (a known part, a data sheet,
SEM-EDX), add its spectrum. Before anything is saved, the program shows the most similar existing
reference, the impostor test with the new reference, and which of the spectra on screen would get a
different answer. A reference that would make two materials impossible to tell apart cannot be added.
Every addition and removal is kept in <code>records/inhouse_library/library_changes.csv</code>,
which is only ever appended to.</p>
<p><b>More references (Open Specy)</b>: <b>Library → Open Specy…</b> downloads the Open Specy library
(Cowger et al. 2021, CC BY 4.0) on this computer, or imports a file you downloaded. Only FTIR spectra of
materials a fab is likely to see are kept, and every one that could be confused with a different material is
left out, so the extended library still passes the impostor test. Switch between <b>Fab essentials</b> and
<b>Extended</b> on the Library page.</p>
<h3>Checking it by eye</h3>
<p>Switch the figure to <b>Analytical view</b> to see every step on its own panel: the raw data, the
absorbance, the mode correction, the two fingerprints the score is calculated from, and the checks with
their baseline and ruler lines. Move the mouse over any panel to read every curve's value and the name
of the band at that wavenumber. <b>Ctrl + mouse wheel</b> zooms around the mouse; a double-click resets.
<b>Compare with</b> draws any other library material instead of the best match.</p>
<p><b>Closest matches</b> shows the best four materials next to each other, each over the sample, with
the area where the shapes differ shaded peach. Switch to <b>Fingerprint</b> to see exactly the two curves
each score is calculated from. Click one to show it in the big figure.</p>
<p>A CO₂ band that points <i>down</i> is not an error: absorbance is relative to the background, so less
CO₂ in the air during the sample scan than during the background scan gives a negative band.</p>
<h3>Keyboard</h3>
<p>Ctrl+O open files · Ctrl+Shift+O open folder · Ctrl+E export report · Ctrl+F filter / search ·
Delete remove from the list · Ctrl+1 Analyze · Ctrl+2 Library · Ctrl+N add a reference ·
Ctrl+T light / dark · Esc close a sheet · F1 this help</p>
"""


# ---------------------------------------------------------------------------- background work
def load_and_validate(inhouse_dir, extended, openspecy_dir, progress):
    """Background job: load the library (shipped + in-house [+ Open Specy]) and run the impostor test."""
    progress(0, 1, "Loading the reference library")
    library = load_library(inhouse_dir=inhouse_dir, extended=extended, openspecy_dir=openspecy_dir)
    progress(0, 1, "Running the impostor test")
    validation = impostor_test(library)
    similarity_for(library)                                            # the similarity map, worked out once
    return library, validation


def analyse_files(paths, modes, library, progress):
    """Background job: read and analyse every file. Problem files are reported, not fatal."""
    results, problems = [], []
    for n, path in enumerate(paths, start=1):
        progress(n, len(paths), f"Analysing {path.name}")
        info = modes[path]
        try:
            results.extend(analyse(s, library, info.mode, info.source, info.conflict) for s in read_spectra(path))
        except SpectrumFileError as error:
            problems.append(str(error))
        except Exception as error:
            problems.append(f"{path.name}: unexpected error ({type(error).__name__}: {error}).")
    return results, problems


def change_library(inhouse_dir, results, change, extended, openspecy_dir, progress):
    """Background job: change the library, load it again, validate it, analyse the results again.

    change(inhouse) does the change (add or remove an in-house reference); None = only reload,
    e.g. after switching between the shipped and the extended library.
    """
    progress(0, 1, "Changing the library")
    if change is not None:
        change(InHouseLibrary(inhouse_dir))
    library = load_library(inhouse_dir=inhouse_dir, extended=extended, openspecy_dir=openspecy_dir)
    progress(0, 1, "Running the impostor test")
    validation = impostor_test(library)
    similarity_for(library)
    progress(0, 1, "Analysing the spectra again")
    new_results = reanalyse(results, library)
    return library, validation, new_results, changes_between(results, new_results)


# ---------------------------------------------------------------------------- small layout helpers
def label(text="", name="Body", wrap=False, rich=False):
    """A QLabel with a style name from the theme (Body, Body2, Meta, SectionTitle ...)."""
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    widget.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    if rich:
        widget.setTextInteractionFlags(Qt.TextBrowserInteraction)
        widget.setOpenExternalLinks(False)
    return widget


def panel(title, hint=""):
    """A card with a title (and an optional grey hint). Returns (card, layout for its content)."""
    frame = Card()
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(20, 16, 20, 20)                           # + the card's own 4 px = 24 / 20 / 24
    outer.setSpacing(12)
    head = QHBoxLayout()
    head.setSpacing(16)
    head.addWidget(label(title, "SectionTitle"), 0, Qt.AlignTop)
    if hint:                                                           # the hint wraps when the card is narrow
        note = label(hint, "SectionHint", wrap=True)
        note.setAlignment(Qt.AlignRight | Qt.AlignTop)
        head.addWidget(note, 1)
    else:
        head.addStretch()
    outer.addLayout(head)
    body = QVBoxLayout()
    body.setSpacing(8)
    outer.addLayout(body)
    return frame, body


class Fact(QWidget):
    """One number with its label underneath, e.g. 0.97 / 'score (Pearson r)'. The number counts up."""

    def __init__(self, caption):
        super().__init__()
        self.value = label("–", "FactValue")
        self.caption = label(caption, "FactLabel", wrap=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.value)
        layout.addWidget(self.caption)

    def set(self, value, caption=None, animated=True):
        """New value. animated=True: shown at zero first; play() then counts it up."""
        self.target = value
        count_up(self.value, value, duration=0)
        if animated and not Motion.reduced:
            self.value.setText(zero_like(value))
        if caption:
            self.caption.setText(caption)

    def play(self):
        count_up(self.value, self.target)


# ---------------------------------------------------------------------------- the result page
class ResultView(SmoothScrollArea):
    """Everything about one spectrum, top to bottom. Built once, refilled for each selection."""

    save_figure = Signal()
    add_reference = Signal()

    def __init__(self):
        super().__init__()
        page = QWidget()
        page.setObjectName("ResultPage")
        self.setWidget(page)
        make_opaque(page, Theme.t["paper"])                             # opaque: Qt can scroll it by copying pixels
        self.page = page
        col = QVBoxLayout(page)
        col.setContentsMargins(32, 24, 32, 32)
        col.setSpacing(16)

        # 1. title row: name, verdict, match, flags (they wrap onto a second line if needed); file and mode below
        self.head = QWidget()
        head = QVBoxLayout(self.head)
        head.setContentsMargins(4, 0, 4, 0)
        head.setSpacing(8)
        self.name = ElidedLabel("", "SampleName")                        # a very long name is shortened with …
        self.title_row = QWidget()
        self.badges = FlowLayout(self.title_row, spacing=8, row_spacing=8)
        self.badges.addWidget(self.name)
        self.badge_widgets = []
        self.meta = label("", "Meta", wrap=True)
        head.addWidget(self.title_row)
        head.addWidget(self.meta)
        col.addWidget(self.head)

        # 1b. what the last library change did to this result (only for a result that changed)
        self.change_box = QFrame()
        self.change_box.setObjectName("ChangeNote")
        change_row = QHBoxLayout(self.change_box)
        change_row.setContentsMargins(16, 10, 16, 10)
        self.change_icon = QLabel()
        self.change_text = label("", "Body", wrap=True, rich=True)
        change_row.addWidget(self.change_icon, 0, Qt.AlignTop)
        change_row.addSpacing(6)
        change_row.addWidget(self.change_text, 1)
        self.change_box.hide()
        col.addWidget(self.change_box)
        self.changes, self.change_reason = {}, ""

        # 2. one card: the score strip (the verdict rule in one picture, as in the report), and
        #    under it three facts in one row (one under the other on a very narrow window)
        self.facts = Card()
        card = QVBoxLayout(self.facts)
        card.setContentsMargins(20, 16, 20, 12)
        card.setSpacing(12)
        self.strip = ScoreStrip()
        card.addWidget(self.strip)
        rule = QFrame()
        rule.setObjectName("Divider")
        rule.setFixedHeight(1)
        card.addWidget(rule)
        self.fact_grid = QGridLayout()
        self.fact_grid.setHorizontalSpacing(16)
        self.fact_grid.setVerticalSpacing(12)
        card.addLayout(self.fact_grid)
        self.fact_bands = Fact("key bands found")
        self.fact_a = Fact("highest absorbance")
        self.fact_how = Fact("compared as")
        self.fact_list = [self.fact_bands, self.fact_a, self.fact_how]
        self.dividers = []
        for _ in range(2):
            divider = QFrame()
            divider.setObjectName("Divider")
            divider.setFixedWidth(1)
            self.dividers.append(divider)
        self.columns = None
        self._lay_out(3)
        col.addWidget(self.facts)

        # 3. the next step (with "add to library" when the material is not known well)
        self.next_box = QFrame()
        self.next_box.setObjectName("NextStep")
        next_row = QHBoxLayout(self.next_box)
        next_row.setContentsMargins(16, 12, 16, 12)
        self.next_icon = QLabel()
        self.next_text = label("", "Body", wrap=True, rich=True)
        self.add_button = QPushButton(" Add to library…")
        self.add_button.setToolTip("Identified it another way? Add its spectrum as an in-house reference")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self.add_reference.emit)
        next_row.addWidget(self.next_icon, 0, Qt.AlignTop)
        next_row.addSpacing(6)
        next_row.addWidget(self.next_text, 1)
        next_row.addSpacing(8)
        next_row.addWidget(self.add_button, 0, Qt.AlignVCenter)
        col.addWidget(self.next_box)

        # 4. the figure
        self.plot = PlotPanel()
        self.plot.save_requested.connect(self.save_figure.emit)
        col.addWidget(self.plot)

        # 5. the closest matches, side by side (click one: it is drawn in the figure above)
        self.top = TopMatches()
        self.top.chosen.connect(self.plot.set_compare)
        self.plot.compare_changed.connect(self.top.set_current)
        col.addWidget(self.top)

        # 5. two rows of two cards (one column on a narrow window)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        self.panel_grid = grid
        self.verdict_panel, verdict_body = panel("Why this verdict", "best 5 of the library")
        self.reason = label("", "Body", wrap=True)
        self.bars = ScoreBars()
        verdict_body.addWidget(self.reason)
        verdict_body.addWidget(self.bars)
        self.evidence_panel, self.evidence_body = panel("Band evidence")
        self.checks_panel, self.checks_body = panel("Checks on the raw spectrum")
        self.sources_panel, self.sources_body = panel("Where it can come from in a fab")
        self.panels = [self.verdict_panel, self.evidence_panel, self.checks_panel, self.sources_panel]
        self._lay_panels(2)
        col.addLayout(grid)

        # 6. traceability
        self.trace_panel, trace_body = panel("Traceability", "proves which file, code and library made this result")
        self.trace = QGridLayout()
        self.trace.setHorizontalSpacing(18)
        self.trace.setVerticalSpacing(6)
        trace_body.addLayout(self.trace)
        col.addWidget(self.trace_panel)
        col.addStretch()

    # ------------------------------------------------------------------ fitting the width
    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width()
        side = 32 if width >= 760 else 16                               # narrow: the page keeps its width for content
        if self.page.layout().contentsMargins().left() != side:
            self.page.layout().setContentsMargins(side, 24, side, 32)
        self._lay_out(3 if width >= 520 else 1)
        self._lay_panels(2 if width >= 720 else 1)

    def _lay_out(self, columns):
        """The three facts in one row (with dividers), or one under the other."""
        if columns == self.columns:
            return
        self.columns = columns
        for widget in self.fact_list + self.dividers:
            self.fact_grid.removeWidget(widget)
        for k in range(6):
            self.fact_grid.setColumnStretch(k, 0)
        if columns == 3:
            for i, fact in enumerate(self.fact_list):
                self.fact_grid.addWidget(fact, 0, 2 * i)
                self.fact_grid.setColumnStretch(2 * i, 1)
                if i < 2:
                    self.fact_grid.addWidget(self.dividers[i], 0, 2 * i + 1)
                    self.dividers[i].show()
        else:
            for i, fact in enumerate(self.fact_list):
                self.fact_grid.addWidget(fact, i, 0)
            self.fact_grid.setColumnStretch(0, 1)
            for divider in self.dividers:
                divider.hide()

    def _lay_panels(self, columns):
        """The four cards in two columns, or one under the other."""
        if getattr(self, "panel_columns", None) == columns:
            return
        self.panel_columns = columns
        for widget in self.panels:
            self.panel_grid.removeWidget(widget)
        for i, widget in enumerate(self.panels):
            self.panel_grid.addWidget(widget, i // columns, i % columns)
        self.panel_grid.setColumnStretch(0, 1)
        self.panel_grid.setColumnStretch(1, 1 if columns == 2 else 0)

    def sections(self):
        """The parts of the page, top to bottom (they rise in one after the other)."""
        parts = [self.head, self.change_box, self.facts, self.next_box, self.plot, self.top, self.verdict_panel,
                 self.evidence_panel, self.checks_panel, self.sources_panel, self.trace_panel]
        return [part for part in parts if not part.isHidden()]

    def bands(self):
        """The visible parts of the page, as rectangles of the viewport (they rise in one after the other)."""
        viewport, bands = self.viewport(), []
        for widget in self.sections():
            rect = QRect(widget.mapTo(viewport, QPoint(0, 0)), widget.size()).intersected(viewport.rect())
            if not rect.isEmpty():
                bands.append(rect)
        return bands

    def set_changes(self, changes, reason=""):
        """What the last library change did: {sample name: Change}, and which change it was."""
        self.changes, self.change_reason = dict(changes), reason

    def play(self):
        """After the page has risen in: the dots slide to their scores, the numbers count up, the bars grow."""
        self.strip.play()
        for fact in self.fact_list:
            fact.play()
        self.bars.grow()

    # ------------------------------------------------------------------
    def display(self, r, library, sample_log_path, animated=True):
        """Fill every part of the page with one result."""
        t = Theme.t
        c, ev, s = r.checks, r.evidence, r.spectrum
        if animated:
            self.scroll_to_top()

        # title row
        self.name.setText(r.name)
        for widget in self.badge_widgets:                                   # the badges of the last result go
            self.badges.removeWidget(widget)
            widget.hide()                                                   # at once, not when Qt deletes them
            widget.deleteLater()
        self.badge_widgets = [verdict_pill(r.verdict, size_key="body")]
        if r.has_match:
            self.badge_widgets.append(label(r.match, "SectionTitle"))
        self.badge_widgets += [flag_pill(text, severity) for text, severity in r.flags]
        for widget in self.badge_widgets:
            self.badges.addWidget(widget)
        how = "measuring mode unknown" if r.mode == "unknown" else f"measured by {r.mode}"
        fit = f", compared as {r.reading}: the better fit" if r.mode == "unknown" and r.reading != "unknown" else ""
        self.meta.setText(f"{s.path.name}   {how} ({r.mode_source}){fit}")
        change = self.changes.get(r.name)                                   # changed with the library?
        if change is not None:
            self.change_icon.setPixmap(icon_pixmap("history", t["accent_ink"], 20, self.devicePixelRatioF()))
            self.change_text.setText(
                f"<span style='color:{t['accent_ink']}; font-weight:600'>Changed</span>&nbsp;&nbsp;"
                f"{html.escape(change.before)}&nbsp;&nbsp;→&nbsp;&nbsp;<b>{html.escape(change.after)}</b>"
                + (f"<br><span style='color:{t['muted']}'>{html.escape(self.change_reason)}</span>"
                   if self.change_reason else ""))
        self.change_box.setVisible(change is not None)

        # the score strip, and the facts (the numbers count up)
        self.strip.set_data(r, animated)
        self.fact_how.set(r.compared_as, "compared as" + ("" if r.mode in ("ATR", "transmission") else
                                                          ", the better reading"), animated=False)
        self.fact_bands.set(f"{len(ev.found)} of {ev.n_key}" if ev else "–",
                            f"key {r.best} bands found" if ev else "key bands (no match)", animated)
        self.fact_a.set(f"{c.max_a:.2f}", "highest absorbance, saturated" if c.saturated else "highest absorbance",
                        animated)

        # next step
        alert = any(severity == "bad" for _, severity in r.flags)         # a red flag: do not trust as it is
        if alert:
            colour, icon_name = t["bad"], "triangle-alert"
        elif r.verdict == PROBABLE:
            colour, icon_name = t["accent_ink"], "circle-check"
        else:
            colour, icon_name = t["accent_ink"], "circle-alert"
        self.next_box.setProperty("alert", alert)                          # red box for a red flag
        self.next_box.style().unpolish(self.next_box)
        self.next_box.style().polish(self.next_box)
        self.next_icon.setPixmap(icon_pixmap(icon_name, colour, 20, self.devicePixelRatioF()))
        self.next_text.setText(f"<span style='color:{colour}; font-weight:600'>Next step</span>&nbsp;&nbsp;"
                               f"{r.next_step}")
        self.add_button.setVisible(r.verdict != PROBABLE and not c.no_sample)
        self.add_button.setIcon(icon("circle-plus", t["ink_2"]))

        # figure, and the closest matches
        self.plot.show_result(r, library)
        self.top.show_result(r, library, self.plot.compare)

        # why this verdict
        self.reason.setText(r.reason)
        self.bars.set_data(r.ranking[:5], r.verdict, animated)

        # band evidence
        clear_layout(self.evidence_body)
        if ev:
            self.evidence_body.addWidget(label(f"{len(ev.found)} of {ev.n_key} key bands of {r.best} are in the "
                                               "sample." + (" Missing bands are dashed." if ev.missing else ""),
                                               "Body2", wrap=True))
            chips = QWidget()
            flow = FlowLayout(chips)
            for w in ev.found:
                flow.addWidget(chip(f"{w:.0f}"))
            for w in ev.missing:
                flow.addWidget(chip(f"{w:.0f} missing", "ChipMissing"))
            self.evidence_body.addWidget(chips)
            if ev.unexplained:
                self.evidence_body.addWidget(label("Bands the match cannot explain (possible second component):",
                                                   "Body", wrap=True))
                for w in ev.unexplained:
                    self.evidence_body.addWidget(chip(band_label(w), "ChipExtra"))
            else:
                self.evidence_body.addWidget(label("Every clear band of the sample is explained by the match.",
                                                   "Body2", wrap=True))
        else:
            self.evidence_body.addWidget(label("No match to explain. The tallest bands, to read by hand:",
                                               "Body2", wrap=True))
            for text in c.tallest_bands or ["none found"]:
                self.evidence_body.addWidget(chip(text))
        self.evidence_body.addStretch()

        # checks
        clear_layout(self.checks_body)
        organic = c.ch == "present"
        rows = [
            ("good" if not c.saturated else "bad", "Saturation",
             f"highest A = {c.max_a:.2f}" + (": too dark, measure thinner or use ATR" if c.saturated else ": fine")),
            ("bad" if c.no_sample else "good", "Sample present",
             f"CO₂ artefact {describe_co2(c)}" + (". Probably no sample" if c.no_sample else "")),
            ("good" if organic else "none", "C–H (organic)", f"{c.ch}, {max(c.ch_share, 0):.3f} of the tallest band"),
            ("warn" if c.oh in ("major", "minor") else "none", "O–H / N–H",
             f"{c.oh}, {max(c.oh_share, 0):.2f} of the tallest band"),
            ("none", "Noise", f"{c.noise:.4f} A (a band must be ≥ 3× this to count)"),
        ]
        if c.below_zero:
            rows.append(("warn", "Below zero", BELOW_ZERO_TEXT))
        icons = {"good": "circle-check", "warn": "circle-alert", "bad": "triangle-alert", "none": "circle-minus"}
        for kind, name, text in rows:
            line = QHBoxLayout()
            mark = QLabel()
            mark.setPixmap(icon_pixmap(icons[kind], t[kind], 16, self.devicePixelRatioF()))
            line.addWidget(mark, 0, Qt.AlignTop)
            line.addWidget(label(name, "Body"), 0, Qt.AlignTop)
            line.addSpacing(12)
            value = label(text, "Body2", wrap=True)
            value.setAlignment(Qt.AlignRight | Qt.AlignTop)
            line.addWidget(value, 1)
            self.checks_body.addLayout(line)
        self.checks_body.addStretch()

        # fab sources
        clear_layout(self.sources_body)
        sources = fab_sources(r.best, library) if r.has_match else None
        if sources:
            in_house = library.info_of(r.best).origin == "in-house"
            self.sources_body.addWidget(label(sources[0][:1].upper() + sources[0][1:] + ".", "Body", wrap=True))
            self.sources_body.addWidget(label(f"<b>Check next:</b> {sources[1]}.", "Body2", wrap=True, rich=True))
            self.sources_body.addWidget(label("A starting point for the root-cause analysis, not proof."
                                              + (" Entered when this in-house reference was added." if in_house
                                                 else ""), "SectionHint", wrap=True))
        else:
            self.sources_body.addWidget(label("Only given when there is a match. Read the bands by hand and, "
                                              "for an inorganic, consider SEM-EDX.", "Body2", wrap=True))
        self.sources_body.addStretch()

        # traceability
        clear_layout(self.trace)
        info = library.info_of(r.best)
        reference = (f"{r.best}: in-house, added by {info.added_by} on {readable_time(info.added_at)}"
                     if info.origin == "in-house" else f"{r.best}: {info.source} ({info.licence})")
        facts = [("File", str(s.path), "Mono"), ("File SHA-256", s.sha256, "Mono"),
                 ("Unit as measured", f"{s.unit}, recognised from the {s.unit_source}", "Body2"),
                 ("Data points", f"{len(s.wn)}, {s.wn.min():.0f}–{s.wn.max():.0f} cm⁻¹", "Body2"),
                 ("Measuring mode", r.mode_text, "Body2"),
                 ("Library", f"{library.name}, compared in {library.mode} mode", "Body2"),
                 ("Library SHA-256", library.sha256, "Mono"),
                 ("Best reference", reference, "Body2"),
                 ("Sample log", str(sample_log_path), "Mono")]
        for i, (key, value, style) in enumerate(facts):
            self.trace.addWidget(label(key, "FactLabel"), i, 0, Qt.AlignTop)
            if style == "Mono":                                             # checksums and paths: one line,
                text = ElidedLabel(value, "Mono", Qt.ElideMiddle, copyable=True)   # shortened in the middle
            else:
                text = label(value, style, wrap=True)
                text.setTextInteractionFlags(Qt.TextSelectableByMouse)      # can be selected and copied
            self.trace.addWidget(text, i, 1)
        self.trace.setColumnStretch(1, 1)



# ---------------------------------------------------------------------------- the main window
class MainWindow(QMainWindow):
    """The application window."""

    def __init__(self, files=(), ask_for_files=True, sample_log=None, audit_log=None, inhouse_dir=None,
                 openspecy_dir=None):
        super().__init__()
        # remembers theme, folder and window size, in a small settings file (Windows: %APPDATA%\\Ali Obeidat)
        self.settings = QSettings(QSettings.IniFormat, QSettings.UserScope, __author__, __title__)
        Motion.reduced = self.settings.value("reduce_motion", Motion.system_prefers_reduced(), type=bool)
        self.library, self.validation = None, None
        self.sample_log = SampleLog(sample_log or config.SAMPLE_LOG_FILE)
        self.audit_log = Path(audit_log or config.AUDIT_LOG_FILE)
        self.signature_log = self.audit_log.parent / "signatures.csv"   # next to the audit log
        self.inhouse_dir = Path(inhouse_dir or config.INHOUSE_DIR)
        self.openspecy_dir = Path(openspecy_dir or config.RECORDS_DIR / "openspecy")
        self.extended = self.settings.value("library_mode", "essentials") == EXTENDED
        self.pool = QThreadPool.globalInstance()
        self.jobs = []                                                     # running jobs (kept alive here)
        self.busy = False
        self.sheet = None                                                  # the sheet that is open, if any
        default_dir = config.EXAMPLES_DIR if config.EXAMPLES_DIR.is_dir() else Path.home()
        self.last_dir = self.settings.value("last_dir", str(default_dir))
        if not Path(self.last_dir).is_dir():                               # the folder was moved or deleted
            self.last_dir = str(default_dir)
        self.files_on_start, self.ask_on_start = list(files), ask_for_files

        self.setWindowTitle(__title__)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.setMinimumSize(960, 560)                                     # fits a 1366 x 768 laptop at 125 %
        self._fit_to_screen()

        self._build_actions()
        self._build_menu()
        self._build_header()
        self._build_body()
        self._build_statusbar()
        self._apply_theme(self.settings.value("theme", "light"))
        self.set_ready(False)
        QTimer.singleShot(50, self._start)

    def _fit_to_screen(self):
        """Open at the last size, but never larger than the screen; small screens get a maximised window."""
        screen = QGuiApplication.primaryScreen().availableGeometry()
        size = self.settings.value("size", QSize(1480, 920))
        width, height = max(size.width(), 1280), max(size.height(), 800)   # never start uncomfortably small ...
        width, height = min(width, int(screen.width() * 0.94)), min(height, int(screen.height() * 0.92))  # ... or too big
        self.resize(width, height)
        self.move(screen.x() + (screen.width() - width) // 2, screen.y() + (screen.height() - height) // 2)
        self.start_maximised = screen.width() < 1300 or screen.height() < 760

    # ------------------------------------------------------------------ actions, menu, toolbar
    def _build_actions(self):
        def make(text, shortcut, slot, tip=""):
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.setToolTip(tip or text)
            action.triggered.connect(slot)
            self.addAction(action)                                         # shortcut works anywhere in the window
            return action

        self.act_open = make("Open spectra…", "Ctrl+O", self.open_files, "Choose one or more spectrum files")
        self.act_folder = make("Open folder…", "Ctrl+Shift+O", self.open_folder, "Analyse every spectrum in a folder")
        self.act_demo = make("Open demo spectra", "Ctrl+D", self.open_demo, "Twelve example measurements")
        self.act_export = make("Export report…", "Ctrl+E", self.export_report,
                               "Write the report (web page and Excel table), and sign it if you like")
        self.act_remove = make("Remove from list", "Delete", self.remove_selected)
        self.act_clear = make("Clear list", "", self.clear_list)
        self.act_quit = make("Exit", "Ctrl+Q", self.close)
        self.act_theme = make("Dark theme", "Ctrl+T", lambda: self.apply_theme(
            "dark" if Theme.t["name"] == "light" else "light"))
        self.act_theme.setCheckable(True)
        self.act_motion = make("Reduce motion", "", self.toggle_motion, "Switch the animations off")
        self.act_motion.setCheckable(True)
        self.act_motion.setChecked(Motion.reduced)
        self.act_filter = make("Filter / search", "Ctrl+F", self._focus_search)
        self.act_analyze = make("Analyze", "Ctrl+1", lambda: self.show_page(ANALYZE))
        self.act_library = make("Library", "Ctrl+2", lambda: self.show_page(LIBRARY))
        self.act_add = make("Add a reference…", "Ctrl+N", lambda: self.open_add_reference(),
                            "Add a material the lab identified itself")
        self.act_map = make("Similarity map", "", self.open_similarity)
        self.act_help = make("How it works", "F1", self.show_help)
        self.act_about = make(f"About {__title__}", "", self.show_about)

    def _build_menu(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        for action in (self.act_open, self.act_folder, self.act_demo, None, self.act_export, None,
                       self.act_remove, self.act_clear, None, self.act_quit):
            file_menu.addSeparator() if action is None else file_menu.addAction(action)
        view_menu = bar.addMenu("&View")
        for action in (self.act_analyze, self.act_library, None, self.act_theme, self.act_motion, None,
                       self.act_filter):
            view_menu.addSeparator() if action is None else view_menu.addAction(action)
        library_menu = bar.addMenu("&Library")
        library_menu.addAction(self.act_add)
        library_menu.addAction(self.act_map)
        library_menu.addSeparator()
        library_menu.addAction("Library change log (Excel)",
                               lambda: self.open_record(InHouseLibrary(self.inhouse_dir).log, "Library change log"))
        library_menu.addAction("Open the in-house library folder", lambda: self.open_record(self.inhouse_dir))
        records = bar.addMenu("&Records")
        records.addAction("Sample log (Excel)", lambda: self.open_record(self.sample_log.path, "Sample log"))
        records.addAction("Audit log (Excel)", lambda: self.open_record(self.audit_log, "Audit log"))
        records.addAction("Signatures (Excel)", lambda: self.open_record(self.signature_log, "Signatures"))
        records.addSeparator()
        records.addAction("Open the records folder", lambda: self.open_record(self.sample_log.path.parent))
        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_help)
        help_menu.addAction(self.act_about)

    def _build_header(self):
        header = QWidget()
        header.setObjectName("Header")
        grid = QGridLayout(header)
        grid.setContentsMargins(16, 0, 16, 0)
        grid.setHorizontalSpacing(16)
        header.setFixedHeight(56)

        # left: logo and name
        left = QHBoxLayout()
        left.setSpacing(10)
        self.logo = QLabel()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(__title__)
        title.setObjectName("AppTitle")
        self.subtitle = subtitle = QLabel(f"Version {__version__} · by {__author__}")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        left.addWidget(self.logo)
        left.addLayout(titles)
        left.addStretch()

        # middle: the two pages
        self.nav = Tabs(ANALYZE, (("Analyze", ANALYZE), ("Library", LIBRARY)))
        self.nav.setToolTip("Analyze spectra (Ctrl+1) · Browse and extend the reference library (Ctrl+2)")
        self.nav.changed.connect(self.show_page)

        # right: the actions, the validation badge, theme and help
        right = QHBoxLayout()
        right.setSpacing(4)
        right.addStretch()
        self.header_buttons, self.header_texts, self.compact = {}, {}, None
        for key, text, icon_name, action, primary in [
                ("folder", "Folder", "folder-open", self.act_folder, False),
                ("demo", "Demo", "flask-conical", self.act_demo, False),
                ("export", "Export report", "file-down", self.act_export, False),
                ("open", "Open spectra", "files", self.act_open, True)]:
            button = QPushButton(f" {text}")                               # a space between icon and text
            button.setToolTip(action.toolTip() + f"  ({action.shortcut().toString()})")
            button.setIconSize(QSize(17, 17))
            button.setCursor(Qt.PointingHandCursor)
            if primary:
                button.setObjectName("Primary")
            button.clicked.connect(action.trigger)
            right.addWidget(button)
            self.header_buttons[key] = (button, icon_name, primary)
            self.header_texts[key] = text
        right.addSpacing(8)
        self.badge = Pill("none", "Validating the library…", "shield-check")
        self.badge.setCursor(Qt.PointingHandCursor)
        self.badge.mousePressEvent = lambda _: self.show_page(LIBRARY)    # click: open the library
        right.addWidget(self.badge)
        self.theme_button = QToolButton()
        self.theme_button.setToolTip("Light / dark (Ctrl+T)")
        self.theme_button.setIconSize(QSize(18, 18))
        self.theme_button.clicked.connect(self.act_theme.trigger)
        self.help_button = QToolButton()
        self.help_button.setToolTip("How it works (F1)")
        self.help_button.setIconSize(QSize(18, 18))
        self.help_button.clicked.connect(self.show_help)
        for button in (self.theme_button, self.help_button):
            button.setCursor(Qt.PointingHandCursor)
            right.addWidget(button)

        grid.addLayout(left, 0, 0)
        grid.addWidget(self.nav, 0, 1, Qt.AlignCenter)
        grid.addLayout(right, 0, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        self.header = header

    def _build_body(self):
        # ---- the Analyze page. Left: the list
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(8, 24, 8, 16)
        side.setSpacing(8)
        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 8, 0)
        head.addWidget(label("Spectra", "SidebarTitle"))
        head.addStretch()
        self.count = label("none yet", "Count")
        head.addWidget(self.count)
        side.addLayout(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or material")
        self.search.setClearButtonEnabled(True)
        side.addWidget(self.search)

        self.model = SpectrumListModel()
        self.pending_glow = False                                      # changed rows still to glow when shown
        self.last_report, self._signed_last = None, False
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterRole(SpectrumListModel.SEARCH)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.list = QListView()
        self.list.setModel(self.proxy)
        self.list.setItemDelegate(SpectrumDelegate(self.list))
        self.list.setMouseTracking(True)                                   # for the hover highlight
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        copy = QAction("Copy the result", self.list)                       # Ctrl+C in the list
        copy.setShortcut(QKeySequence.Copy)
        copy.setShortcutContext(Qt.WidgetShortcut)
        copy.triggered.connect(self.copy_result)
        self.list.addAction(copy)
        self.list.selectionModel().currentChanged.connect(lambda *_: self.show_current())
        side.addWidget(self.list, 1)
        self.summary = QHBoxLayout()
        self.summary.setSpacing(6)
        self.summary.setContentsMargins(6, 0, 6, 0)
        side.addLayout(self.summary)

        # right: welcome page or result page
        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        self.empty = EmptyState()
        self.empty.choose_files.connect(self.open_files)
        self.empty.open_demo.connect(self.open_demo)
        self.empty.open_library.connect(lambda: self.show_page(LIBRARY))
        self.result_view = ResultView()
        self.result_view.save_figure.connect(self.save_current_figure)
        self.result_view.add_reference.connect(lambda: self.open_add_reference())
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.result_view)

        splitter = QSplitter()
        splitter.addWidget(sidebar)
        splitter.addWidget(self.stack)
        splitter.setSizes([344, 1136])
        splitter.setStretchFactor(1, 1)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        sidebar.setMinimumWidth(248)
        self.analyze_page = splitter

        # ---- the Library page
        self.library_page = LibraryPage()
        self.library_page.open_material.connect(self.open_material)
        self.library_page.add_requested.connect(lambda: self.open_add_reference())
        self.library_page.similarity_requested.connect(self.open_similarity)
        self.library_page.mode_changed.connect(self.set_library_mode)
        self.library_page.openspecy_requested.connect(self.open_openspecy)

        self.pages = FadeStack()
        self.pages.addWidget(self.analyze_page)
        self.pages.addWidget(self.library_page)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        # the overlay shown while files are dragged over the window, and the message bubble
        self.drop_overlay = QLabel("Drop spectrum files or a folder to analyse them", central)
        self.drop_overlay.setAlignment(Qt.AlignCenter)
        self.drop_overlay.hide()
        self.toast = Toast(central)

    def _build_statusbar(self):
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        self.spinner = Spinner(16)
        self.status = QLabel("Starting…")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        bar.addWidget(self.spinner)
        bar.addWidget(self.status, 1)
        bar.addPermanentWidget(self.progress)
        bar.addPermanentWidget(QLabel(f"Developed by {__author__}"))

    # ------------------------------------------------------------------ theme and motion
    def apply_theme(self, name):
        """Switch between the light and the dark theme; the old look fades into the new one."""
        crossfade(self, lambda: self._apply_theme(name))

    def _apply_theme(self, name):
        Theme.t = THEMES.get(name, THEMES["light"])
        t = Theme.t
        QApplication.instance().setStyleSheet(stylesheet(t))
        self.settings.setValue("theme", t["name"])
        self.act_theme.setChecked(t["name"] == "dark")
        self.logo.setPixmap(logo_pixmap(34, self.devicePixelRatioF()))
        for button, icon_name, primary in self.header_buttons.values():
            button.setIcon(icon(icon_name, t["on_primary"] if primary else t["header_ink"]))
        self.theme_button.setIcon(icon("sun" if t["name"] == "dark" else "moon", t["header_ink"]))
        self.help_button.setIcon(icon("circle-help", t["header_ink"]))
        if not self.search.actions():                                      # the magnifier inside the filter box
            self.search.addAction(icon("search", t["muted"], 16), QLineEdit.LeadingPosition)
        self.search.actions()[0].setIcon(icon("search", t["muted"], 16))
        tint = QColor(t["primary"])                                        # the drop overlay: the pastel, nearly opaque
        self.drop_overlay.setStyleSheet(
            f"background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 235); color: {t['on_primary']};"
            f"font-size: 22px; font-weight: 600; border: 2px dashed {t['accent']}; border-radius: 20px;")
        self.empty.retheme()
        self.library_page.retheme()
        self.result_view.plot.retheme()
        self.badge.update()
        self.nav.update()
        self.list.viewport().update()
        self._update_summary()
        if self.current_result() is not None:
            self.result_view.display(self.current_result(), self.library, self.sample_log.path, animated=False)
        make_opaque(self.result_view.page, t["paper"])
        self.result_view.top.retheme()

    def toggle_motion(self):
        Motion.reduced = self.act_motion.isChecked()
        self.settings.setValue("reduce_motion", Motion.reduced)
        self.notify("Animations off." if Motion.reduced else "Animations on.")

    def notify(self, text, icon_name="circle-check", action=None):
        """A short message in the bubble at the bottom (and in the status bar); action = (word, function)."""
        self.set_status(text)
        self.toast.show_message(text, icon_pixmap(icon_name, Theme.t["tooltip_ink"], 18, self.devicePixelRatioF()),
                                action)

    # ------------------------------------------------------------------ pages
    def show_page(self, page):
        """Show the Analyze page or the Library page (the new page slides in)."""
        target = self.library_page if page == LIBRARY else self.analyze_page
        self.nav.set_value(page)
        if target is self.analyze_page and self.pending_glow:          # results changed while it was not shown:
            self.pending_glow = False                                  # they glow once the page has arrived
            QTimer.singleShot(Motion.ms("page") if self.pages.currentWidget() is not target else 0, self._start_glow)
        if self.pages.currentWidget() is target:
            return
        self.pages.slide_to(target, 1 if page == LIBRARY else -1)

    def _focus_search(self):
        if self.pages.currentWidget() is self.library_page:
            self.library_page.search.setFocus()
        else:
            self.search.setFocus()

    # ------------------------------------------------------------------ start-up
    def _start(self):
        """Load and validate the library in the background, then open files or ask for some."""
        self.empty.play()
        self.set_status("Loading the reference library and running the impostor test…", busy=True)
        self.run_job(Job(load_and_validate, self.inhouse_dir, self.extended, self.openspecy_dir), self._library_ready,
                     "The reference library could not be loaded")

    def _library_ready(self, payload):
        self._set_library(*payload)
        self.set_ready(True)
        self.set_status("Ready. Open spectrum files, open a folder, or drop files on the window.")
        if self.files_on_start:
            self.analyse_paths(self.files_on_start)
        elif self.ask_on_start:
            QTimer.singleShot(250, self.open_files)                         # "which spectrum?" straight away

    def _set_library(self, library, validation):
        """Use a (new) library: the badge, the Library page and its validation."""
        if self.library is None:                       # the first time: everything made at start-up stays,
            gc.collect()                               # so the garbage collector can skip it from now on
            gc.freeze()                                # (its rounds get shorter: no pause while things move)
        self.library, self.validation = library, validation
        v = validation
        self.badge.kind = "good" if v.passed else "bad"
        self.badge.text = "Library validated" if v.passed else "Library NOT validated"
        self.badge.icon_name = "shield-check" if v.passed else "shield-alert"
        self.badge.setToolTip(f"{library.name}, compared in {library.mode} mode.\n"
                              f"Impostor test: the best WRONG match scores {v.score:.2f} ({v.material} with itself "
                              f"removed → {v.impostor}).\n" + (f"Below the 'probable' threshold {config.PROBABLE_R}: "
                              "the verdict rule is valid for this library." if v.passed else
                              "This reaches 'probable': re-validate the thresholds.") + "\nClick to open the library.")
        self.badge.updateGeometry()
        self.badge.update()
        self.library_page.set_mode("extended" if self.extended else "essentials",
                                   OpenSpecyLibrary(self.openspecy_dir).installed)
        self.library_page.set_library(library, validation)

    def set_ready(self, ready):
        """Enable the actions once the library is loaded (and while no job is running)."""
        for action in (self.act_open, self.act_folder, self.act_demo, self.act_add, self.act_map):
            action.setEnabled(ready)
        self.act_export.setEnabled(ready and bool(self.model.results))
        for key, (button, _, _) in self.header_buttons.items():
            button.setEnabled(ready and (key != "export" or bool(self.model.results)))
        self.empty.choose.setEnabled(ready)
        self.empty.demo.setEnabled(ready)
        self.library_page.add_button.setEnabled(ready)
        self.library_page.map_button.setEnabled(ready)

    # ------------------------------------------------------------------ jobs
    def run_job(self, job, on_done, failure_title):
        """Start a background job; show progress; call on_done with its result when it is finished.

        The signals are connected to methods of the window, so Qt delivers them in the
        window's own thread: the window is only ever changed from one thread.
        """
        self.busy = True
        self.set_ready(False)
        job.on_done, job.failure_title = on_done, failure_title
        self.jobs.append(job)                                              # keep it alive until it reports back
        job.signals.progress.connect(self._on_progress)
        job.signals.done.connect(self._job_done)
        job.signals.failed.connect(self._job_failed)
        self.pool.start(job)

    def _job_finished(self, job):
        self.busy = False
        self.jobs.remove(job)
        self.progress.hide()
        self.spinner.stop()
        self.set_ready(self.library is not None)

    def _job_done(self, job, result):
        self._job_finished(job)
        job.on_done(result)

    def _job_failed(self, job, message):
        self._job_finished(job)
        self.set_status(job.failure_title + ".")
        log = write_error_log(f"{job.failure_title}\n{job.details}")
        box = QMessageBox(QMessageBox.Critical, __title__, f"{job.failure_title}:\n\n{message}", parent=self)
        if log:
            box.setInformativeText(f"The details were saved in:\n{log}")
        box.setDetailedText(job.details)
        box.setAttribute(Qt.WA_DeleteOnClose)
        box.open()                                         # not blocking: the window stays usable behind it

    def _on_progress(self, step, total, text):
        self.spinner.start()
        if total > 1:
            self.progress.setRange(0, total)
            self.progress.setValue(step)
            self.progress.show()
            self.set_status(f"{text} ({step} of {total})…")
        else:
            self.set_status(f"{text}…")

    def set_status(self, text, busy=False):
        self.status.setText(text)
        if busy:
            self.spinner.start()

    # ------------------------------------------------------------------ opening files
    def open_files(self):
        if self.library is None or self.busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose one or more spectrum files", str(self.last_dir),
                                                FILE_FILTER)
        if paths:
            self._remember_dir(Path(paths[0]).parent)
            self.analyse_paths(paths)

    def open_folder(self):
        if self.library is None or self.busy:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder of spectrum files", str(self.last_dir))
        if folder:
            self._remember_dir(Path(folder))
            self.analyse_paths([folder])

    def open_demo(self):
        if self.library is None or self.busy:
            return
        if not config.EXAMPLES_DIR.is_dir():
            QMessageBox.information(self, __title__, f"The demo folder was not found:\n{config.EXAMPLES_DIR}")
            return
        self.analyse_paths([config.EXAMPLES_DIR])

    def _remember_dir(self, folder):
        self.last_dir = folder
        self.settings.setValue("last_dir", str(folder))

    def _ask_modes(self, paths):
        """Called by resolve_modes for files whose measuring mode is not known yet."""
        dialog = ModeDialog(paths, self.library.mode, self)
        return dialog.answers() if dialog.exec() == QDialog.Accepted else {}

    def analyse_paths(self, items, ask=None):
        """Analyse files and folders (folders are opened), skipping files already in the list."""
        paths = []
        for item in map(Path, items):
            paths.extend(find_spectrum_files(item) if item.is_dir() else [item])
        paths = [p.resolve() for p in paths]
        loaded = {r.spectrum.path for r in self.model.results}
        new = [p for p in dict.fromkeys(paths) if p not in loaded]            # dict.fromkeys: no duplicates
        if not new:
            self.set_status("Those files are already in the list." if paths else "No spectrum files found there.")
            return
        modes = resolve_modes(new, self.sample_log, ask=ask or self._ask_modes)   # asks in the window, if needed
        self.show_page(ANALYZE)
        self.set_status(f"Analysing {len(new)} file(s)…", busy=True)
        self.run_job(Job(analyse_files, new, modes, self.library), self._analysed, "The analysis failed")

    def _analysed(self, payload):
        results, problems = payload
        first_new = len(self.model.results)
        self.model.add(results)
        self._update_summary()
        if results:
            self.stack.setCurrentWidget(self.result_view)
            index = self.proxy.mapFromSource(self.model.index(first_new))
            self.list.setCurrentIndex(index)
            self.list.scrollTo(index)
        text = f"{len(results)} spectra analysed."
        self.set_status(text + (f" {len(problems)} file(s) skipped." if problems else ""))
        if problems:
            box = QMessageBox(QMessageBox.Warning, __title__, "Some files could not be analysed.", parent=self)
            box.setInformativeText("\n\n".join(problems))
            box.exec()

    # ------------------------------------------------------------------ the list
    def current_result(self):
        index = self.list.currentIndex()
        return index.data(SpectrumListModel.RESULT) if index.isValid() else None

    def show_current(self, animated=True):
        """Show the selected result. Animated: the list paints the new selection first, then the
        page is filled and drawn (nothing moves meanwhile), then it rises in from snapshots."""
        r = self.current_result()
        if r is None:
            return
        if animated and not Motion.reduced and self.isVisible():
            QTimer.singleShot(0, self, lambda: self._transition_to(r))
            return
        self.stack.setCurrentWidget(self.result_view)
        self.result_view.display(r, self.library, self.sample_log.path, animated=False)

    def _transition_to(self, r):
        if r is not self.current_result():                                # a newer click has come in
            return
        view = self.result_view
        if self.stack.currentWidget() is not view:                       # the first result: the page fades through
            Overlay.finish(self.stack)
            before = snapshot(self.stack)
            self.stack.setCurrentWidget(view)
            view.display(r, self.library, self.sample_log.path, animated=True)
            fade_through(self.stack, before, snapshot(self.stack), dy=12, duration=MOTION["page"],
                         on_done=view.play)
            return
        viewport = view.viewport()
        Overlay.finish(viewport)
        before = snapshot(viewport)
        view.display(r, self.library, self.sample_log.path, animated=True)     # all the slow work, now
        after = snapshot(viewport)
        if rise_in(viewport, before, after, view.bands(), dy=8, on_done=view.play) is None:
            view.play()

    def copy_result(self):
        """The selected result as a few lines of text on the clipboard (for a lab notebook, an e-mail, a ticket)."""
        r = self.current_result()
        if r is None or self.library is None:
            return
        QGuiApplication.clipboard().setText(result_summary(r, self.library))
        self.notify(f"{r.name}: result copied.", "copy")

    def _update_summary(self):
        results = self.model.results
        self.count.setText(f"{len(results)} analysed" if results else "none yet")
        clear_layout(self.summary)
        if results:
            for verdict in (PROBABLE, WEAK, NO_MATCH):
                n = sum(r.verdict == verdict for r in results)
                if n:
                    kind, word, icon_name = VERDICT_LOOK[verdict]
                    short = "no match" if verdict == NO_MATCH else word.lower()
                    self.summary.addWidget(Pill(kind, f"{n} {short}", icon_name))
            self.summary.addStretch()
        self.set_ready(self.library is not None and not self.busy)
        if not results:
            self.stack.setCurrentWidget(self.empty)

    def _list_menu(self, position):
        r = self.current_result()
        if r is None:
            return
        menu = QMenu(self)
        menu.addAction(icon("external-link", Theme.t["ink_2"]), "Show the file in its folder",
                       lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(r.spectrum.path.parent))))
        menu.addAction(icon("copy", Theme.t["ink_2"]), "Copy the result  (Ctrl+C)", self.copy_result)
        menu.addAction(icon("image-down", Theme.t["ink_2"]), "Save the figure…", self.save_current_figure)
        menu.addAction(icon("circle-plus", Theme.t["ink_2"]), "Add to the library as a reference…",
                       lambda: self.open_add_reference())
        menu.addSeparator()
        menu.addAction(icon("trash-2", Theme.t["ink_2"]), "Remove from the list", self.remove_selected)
        menu.exec(self.list.viewport().mapToGlobal(position))

    def remove_selected(self):
        rows = {self.proxy.mapToSource(i).row() for i in self.list.selectionModel().selectedIndexes()}
        if rows:
            self.model.remove_rows(rows)
            self._update_summary()
            self.set_status(f"{len(rows)} spectra removed from the list. The files are unchanged.")
            if self.proxy.rowCount():
                self.list.setCurrentIndex(self.proxy.index(0, 0))

    def clear_list(self):
        if self.model.results and QMessageBox.question(
                self, __title__, "Remove every spectrum from the list?\nThe files themselves are not touched.") \
                == QMessageBox.Yes:
            self.model.clear()
            self.result_view.set_changes({})
            self._update_summary()
            self.set_status("List cleared.")

    # ------------------------------------------------------------------ the library: sheets
    def _open_sheet(self, title, content, width, eyebrow="", footer=None, on_close=None, tall=False):
        """Show content in a sheet: a card in the middle of the dimmed window (one at a time)."""
        if self.sheet is not None:
            self.sheet.close_sheet()
        sheet = Sheet(self.centralWidget(), title, content, width, eyebrow, footer, tall,
                      close_icon=icon("x", Theme.t["ink_2"]))
        if hasattr(content, "play"):                                       # its own animation starts on arrival
            if sheet.has_arrived:
                content.play()
            else:
                sheet.arrived.connect(content.play)

        def closed():
            if self.sheet is sheet:
                self.sheet = None
            if on_close:
                on_close()

        sheet.closed.connect(closed)
        self.sheet = sheet
        return sheet

    def open_material(self, name):
        """The details of one reference."""
        if self.library is None or name not in self.library.spectra:
            return None
        detail = MaterialDetail(self.library, name, similarity_for(self.library), self.current_result())
        detail.compare.connect(self.compare_with)
        detail.remove.connect(lambda n: self.remove_reference(n))
        detail.show_file.connect(self._show_reference_file)
        in_house = self.library.info_of(name).origin == "in-house"
        self._open_sheet(name, detail, 640)
        return detail

    def open_similarity(self):
        if self.library is None:
            return None
        content = SimilarityPanel(self.library, self.validation, similarity_for(self.library))
        self._open_sheet("Similarity map: which references could be confused?", content, 1040)
        return content

    def open_add_reference(self, use_current=True):
        """The sheet for adding a reference (from the selected result, or from a file)."""
        if self.library is None or self.busy:
            return None
        current = self.current_result() if use_current else None
        content = AddReferencePanel(self.library, self.validation, self.model.results, current, self.last_dir)
        sheet = self._open_sheet("Add a reference to the library", content, 720, "",
                                 content.footer, content.closing, tall=True)
        content.cancelled.connect(sheet.close_sheet)
        content.submitted.connect(self.add_reference)
        return content

    def compare_with(self, name):
        """Show the selected spectrum compared with reference `name` (from the library's detail sheet)."""
        if self.sheet is not None:
            self.sheet.close_sheet()
        self.show_page(ANALYZE)
        self.result_view.plot.set_compare(name)
        QTimer.singleShot(Motion.ms("page"), lambda: self.result_view.ensureWidgetVisible(self.result_view.plot, 0, 40))

    def _show_reference_file(self, name):
        in_house = self.library.info_of(name).origin == "in-house"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.inhouse_dir if in_house else config.DATA_DIR)))

    # ------------------------------------------------------------------ the library: changes
    def add_reference(self, fields):
        """Add an in-house reference (fields as the add sheet sends them), then analyse everything again."""
        name = fields["name"]

        def change(inhouse):
            inhouse.add(name, fields["wn"], fields["a"], fields["mode"], category=fields.get("category", "In-house"),
                        fab_sources=fields.get("fab_sources", ""), check_next=fields.get("check_next", ""),
                        confirmation=fields.get("confirmation", ""), notes=fields.get("notes", ""),
                        source_path=fields.get("source_path"), existing=self.library.spectra)

        if self.sheet is not None:
            self.sheet.close_sheet()
        self.set_status(f"Adding {name} to the library…", busy=True)
        self.run_job(Job(change_library, self.inhouse_dir, list(self.model.results), change, self.extended,
                         self.openspecy_dir),
                     lambda payload: self._library_changed(payload, f"{name} added to the library", name),
                     "The reference could not be added")

    def remove_reference(self, name, reason=None):
        """Take an in-house reference out of the library (its file and history are kept)."""
        if reason is None:
            reason, ok = QInputDialog.getText(self, "Remove from the library",
                                              f"Why is {name} being removed? (kept in the change log)")
            if not ok or not reason.strip():
                return
        if self.sheet is not None:
            self.sheet.close_sheet()
        self.set_status(f"Removing {name} from the library…", busy=True)
        self.run_job(Job(change_library, self.inhouse_dir, list(self.model.results),
                         lambda inhouse: inhouse.remove(name, reason.strip()), self.extended, self.openspecy_dir),
                     lambda payload: self._library_changed(payload, f"{name} removed from the library"),
                     "The reference could not be removed")

    # ------------------------------------------------------------------ the library: shipped or extended
    def set_library_mode(self, mode):
        """Use the shipped library ("essentials") or also the Open Specy references ("extended")."""
        extended = mode == EXTENDED
        if extended == self.extended or self.library is None or self.busy:
            return
        self.extended = extended
        self.settings.setValue("library_mode", mode)
        self.set_status("Loading the " + ("extended" if extended else "shipped") + " library…", busy=True)
        self.run_job(Job(change_library, self.inhouse_dir, list(self.model.results), None, extended,
                         self.openspecy_dir),
                     lambda payload: self._library_changed(payload, "Library: " + payload[0].name),
                     "The library could not be loaded")

    def open_openspecy(self):
        """The sheet for getting the Open Specy references (download or import)."""
        if self.library is None or self.busy:
            return None
        content = OpenSpecyPanel(OpenSpecyLibrary(self.openspecy_dir), self.last_dir)
        content.download_requested.connect(lambda: self.get_openspecy(None))
        content.import_requested.connect(self.get_openspecy)
        self._open_sheet("More references from Open Specy", content, 640)
        return content

    def get_openspecy(self, path=None):
        """Download (path None) or import an Open Specy library, keep the fab-relevant validated spectra, use them."""
        if self.sheet is not None:
            self.sheet.close_sheet()
        inhouse_dir, folder, results = self.inhouse_dir, self.openspecy_dir, list(self.model.results)

        def work(progress):
            base = load_library(inhouse_dir=inhouse_dir)                   # shipped + in-house, without Open Specy
            summary = (import_library(path, base, folder, progress) if path else
                       download_and_import(base, folder, progress))
            payload = change_library(inhouse_dir, results, None, True, folder, progress)
            return payload, summary

        self.set_status("Getting the Open Specy library…", busy=True)
        self.run_job(Job(work), self._openspecy_ready, "The Open Specy library could not be added")

    def _openspecy_ready(self, payload):
        payload, summary = payload
        self.extended = True
        self.settings.setValue("library_mode", EXTENDED)
        self._library_changed(payload, f"Open Specy: {summary.kept} references added")
        self.show_page(LIBRARY)
        box = QMessageBox(QMessageBox.Information, __title__, "The Open Specy references are ready.", parent=self)
        box.setInformativeText(summary.text())
        box.setAttribute(Qt.WA_DeleteOnClose)
        box.open()                                         # not blocking: the window stays usable behind it
        self.openspecy_summary = box

    def _library_changed(self, payload, message, highlight=None):
        """After a library change: the new library and results, and a clear sign of what changed."""
        library, validation, results, changes = payload
        current = self.current_result()
        self._set_library(library, validation)
        self.model.replace(results, {c.sample: c for c in changes}, message)
        self.result_view.set_changes(self.model.updated, f"Library change: {message}")
        self._update_summary()
        on_library = self.pages.currentWidget() is self.library_page
        changed_here = current is not None and current.name in self.model.updated and not on_library
        self.show_current(animated=changed_here)                          # the new verdict rises in where it is seen
        if self.model.results:
            message += f". {len(changes)} result{'s' if len(changes) != 1 else ''} changed"
        action = None
        if changes and on_library:                                        # the list is not on screen: the rows
            self.pending_glow = True                                      # glow when the Analyze page is shown
            action = ("Show", self.show_changed)
        elif changes:
            self._start_glow()
        if highlight and on_library:
            QTimer.singleShot(Motion.ms("content"), lambda: self.library_page.highlight(highlight))
        elif highlight and action is None:
            action = ("See it in the library", lambda: self._show_in_library(highlight))
        self.notify(message + ".", action=action)

    def show_changed(self):
        """The Analyze page, with the first result that the last library change changed."""
        for row in range(self.proxy.rowCount()):
            r = self.proxy.index(row, 0).data(SpectrumListModel.RESULT)
            if r is not None and r.name in self.model.updated:
                self.list.setCurrentIndex(self.proxy.index(row, 0))
                break
        self.show_page(ANALYZE)

    def _show_in_library(self, name):
        self.show_page(LIBRARY)
        QTimer.singleShot(Motion.ms("page") + 60, lambda: self.library_page.highlight(name))

    def _start_glow(self):
        animate(self, 1.0, 0.0, 3200, self._glow, QEasingCurve.InQuad)   # the changed rows glow, then fade

    def _glow(self, value):
        self.model.glow = value
        self.list.viewport().update()

    # ------------------------------------------------------------------ figure and report
    def save_current_figure(self):
        r = self.current_result()
        if r is None:
            return
        plot = self.result_view.plot
        view = plot.view                                                  # save what is on screen: result or steps
        suffix = "_analytical_view" if view == "analytical" else ""
        png_300, png_600 = "PNG image, 300 dpi (*.png)", "PNG image, 600 dpi, for posters (*.png)"
        path, chosen = QFileDialog.getSaveFileName(
            self, "Save the figure", str(Path(self.last_dir) / f"{r.name}{suffix}.png"),
            f"{png_300};;{png_600};;SVG vector image, any size (*.svg);;PDF vector document (*.pdf)")
        if path:
            save_figure(r, self.library, path, view=view, dpi=600 if chosen == png_600 else 300,
                        compare=plot.compare)
            self.notify(f"Figure saved: {Path(path).name}", "image-down")

    def export_report(self):
        """The sheet for the report: where it goes, your name, and (if you like) the review and signature."""
        if not self.model.results or self.busy:
            return None
        folder = self.settings.value("report_dir", str(self.last_dir))
        if not Path(folder).is_dir():
            folder = str(self.last_dir)
        content = ExportPanel(self.model.results, folder, self.settings.value("user_name", ""))
        sheet = self._open_sheet("Export the report", content, 640, "", content.footer)
        content.cancelled.connect(sheet.close_sheet)
        content.submitted.connect(self._export_chosen)
        return content

    def _export_chosen(self, choice):
        self.settings.setValue("user_name", choice["name"])               # remembered for next time
        self.settings.setValue("report_dir", str(choice["folder"]))
        if self.sheet is not None:
            self.sheet.close_sheet()
        self.write_report_to(choice["folder"], name=choice["name"], signoff=choice["signoff"])

    def write_report_to(self, folder, ask_to_open=True, name=None, signoff=None):
        """Write the report into a new, dated sub-folder of `folder` (in the background)."""
        out_dir = Path(folder) / f"FTIR_report_{datetime.now():%Y-%m-%d_%H%M%S}"
        name = self.settings.value("user_name", "") if name is None else name
        info = run_info(self.library, self.validation, name)
        self._signed_last = signoff is not None
        results = list(self.model.results)

        def job(progress):
            progress(0, 1, "Writing the report")
            return write_report(results, self.library, info, out_dir, audit_log=self.audit_log, signoff=signoff,
                                signature_log=self.signature_log)

        self.set_status("Writing the report…", busy=True)
        self.run_job(Job(job), lambda path: self._report_written(path, ask_to_open), "The report could not be written")

    def _report_written(self, html_path, ask_to_open=True):
        self.last_report = html_path
        self.set_status(f"Report written: {html_path}")
        if not ask_to_open:
            return
        signed = "signed and " if self._signed_last else ""
        self.notify(f"The report is ready ({signed}added to the audit log).", "file-down",
                    ("Open", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(html_path)))))
        box = QMessageBox(QMessageBox.Information, __title__, "The report is ready.", parent=self)
        box.setInformativeText(f"{html_path}\n\nThe run was added to the audit log"
                               + (", and your signature to the signature log" if self._signed_last else "")
                               + ". The folder also has the results as an Excel table (report.xlsx).")
        open_button = box.addButton("Open the report", QMessageBox.AcceptRole)
        box.addButton("Close", QMessageBox.RejectRole)
        box.setAttribute(Qt.WA_DeleteOnClose)
        box.buttonClicked.connect(lambda button: QDesktopServices.openUrl(QUrl.fromLocalFile(str(html_path)))
                                  if button is open_button else None)
        box.open()                                         # not blocking: the window stays usable behind it
        self.report_box = box

    # ------------------------------------------------------------------ records and help
    def open_record(self, path, title=None):
        """Open a record. A log (title given) opens as a formatted Excel copy; the record itself is unchanged."""
        path = Path(path)
        if not path.exists():
            QMessageBox.information(self, __title__, f"{path.name} does not exist yet. "
                                    "It is created the first time it is needed.")
            return
        if title and path.suffix.lower() == ".csv":
            try:
                from .log_views import view_of
                path = view_of(path, title)
                self.notify(f"{title}: opened as a formatted copy. The record itself is not changed.", "files")
            except ImportError:                                            # openpyxl missing: the plain file
                self.set_status("For a formatted Excel view: python -m pip install openpyxl")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("How it works")
        browser = QTextBrowser()
        browser.setHtml(HOW_IT_WORKS)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.clicked.connect(dialog.accept)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.addWidget(browser)
        layout.addWidget(close, 0, Qt.AlignRight)
        dialog.resize(760, 700)
        dialog.exec()

    def show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"About {__title__}")
        logo = QLabel()
        logo.setPixmap(logo_pixmap(84, self.devicePixelRatioF()))
        name = label(__title__, "DialogTitle")
        version = label(f"Version {__version__}", "Meta")
        author = label(f"Developed by {__author__}", "SectionTitle")
        about = label("Identifies the material behind a contamination (a particle, a fibre, a film or a residue) "
                      "from its FTIR spectrum: a validated library search, checks on the raw spectrum, "
                      "band-by-band evidence, an in-house library the lab can extend safely, and a traceable "
                      "report with an audit trail.", "Body", wrap=True)
        credits = label(f"License: {__license__}. Reference spectra: OpenFTIR (MIT). Demo spectra: OpenFTIR (MIT), "
                        "Open Specy test data (CC BY 4.0, Cowger et al. 2021), polystyrene film (public domain). "
                        "Typefaces: Inter and IBM Plex Mono (SIL OFL 1.1). Icons: Lucide (ISC). "
                        "Details in THIRD_PARTY_NOTICES.md.", "SectionHint", wrap=True)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.clicked.connect(dialog.accept)
        text = QVBoxLayout()
        text.setSpacing(4)
        for widget in (name, version):
            text.addWidget(widget)
        text.addSpacing(10)
        text.addWidget(author)
        text.addSpacing(8)
        text.addWidget(about)
        text.addSpacing(10)
        text.addWidget(credits)
        row = QHBoxLayout()
        row.addWidget(logo, 0, Qt.AlignTop)
        row.addSpacing(16)
        row.addLayout(text, 1)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.addLayout(row)
        layout.addSpacing(12)
        layout.addWidget(close, 0, Qt.AlignRight)
        dialog.setFixedWidth(580)
        dialog.exec()

    # ------------------------------------------------------------------ drag and drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self.library is not None and not self.busy:
            event.acceptProposedAction()
            area = self.centralWidget().rect().adjusted(24, 80, -24, -24)
            self.drop_overlay.setGeometry(area)
            self.drop_overlay.raise_()
            self.drop_overlay.show()

    def dragLeaveEvent(self, event):
        self.drop_overlay.hide()

    def dropEvent(self, event):
        self.drop_overlay.hide()
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.analyse_paths(paths)

    def resizeEvent(self, event):
        """On a narrow window the toolbar makes room in two steps (the tooltips still name everything):
        below 1440 px the buttons show only their icons; below 1180 px the library badge shows only its
        shield and the version line under the name is left out."""
        super().resizeEvent(event)
        compact = 2 if self.width() < 1180 else 1 if self.width() < 1440 else 0
        if compact != self.compact:
            self.compact = compact
            for key, (button, _, primary) in self.header_buttons.items():
                button.setText(f" {self.header_texts[key]}" if primary or not compact else "")
            self.badge.set_compact(compact == 2)
            self.subtitle.setVisible(compact < 2)

    def closeEvent(self, event):
        if not self.isMaximized():
            self.settings.setValue("size", self.size())
        super().closeEvent(event)


# ---------------------------------------------------------------------------- start the application
def app_icon():
    """The window and taskbar icon, sharp at every size."""
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(logo_pixmap(size, 1.0))
    return result


def load_fonts():
    """Make the app's own fonts available to Qt (the same on every computer)."""
    for name in FONT_FILES:
        path = FONTS / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


def run_app(files=(), ask_for_files=True):
    """Start the desktop application."""
    if sys.platform.startswith("win"):
        try:                                                     # own taskbar icon instead of Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AliObeidat.FTIRContaminationAnalyzer.1")
        except Exception:
            pass
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(__title__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(__author__)
    app.setWindowIcon(app_icon())
    load_fonts()
    setup_fonts()                                                # matplotlib uses the same font
    sys.excepthook = show_error                                  # unexpected errors: a message, not a crash
    window = MainWindow(files, ask_for_files)
    if window.start_maximised:
        window.showMaximized()
    else:
        window.show()
    return app.exec()


def result_summary(r, library):
    """One result as plain text: verdict, numbers, flags, next step and what proves where it came from."""
    ev = r.evidence
    verdict = r.verdict.capitalize() + (f": {r.match}" if r.has_match else "")
    lines = [f"{r.name} - {verdict}",
             f"Score r = {r.r:.2f}, lead {r.gap:.2f} over {r.runner_up}"
             + (f", {len(ev.found)} of {ev.n_key} key {r.best} bands found" if ev else ""),
             f"Measuring mode: {r.mode_text}"]
    if r.flags:
        lines.append("Flags: " + "; ".join(text[:1].upper() + text[1:] for text, _ in r.flags))
    lines += [f"Next step: {r.next_step}",
              f"File: {r.spectrum.path.name} (SHA-256 {r.spectrum.sha256})",
              f"Library: {library.name} (SHA-256 {library.sha256})",
              f"{__title__} {__version__}"]
    return "\n".join(lines)


def write_error_log(details):
    """Add the details of an error to records/error_log.txt; returns the file, or None if it could not be written."""
    log = config.RECORDS_DIR / "error_log.txt"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S}\n{details}\n")
    except OSError:
        return None
    return log


def show_error(kind, error, trace):
    """Show an unexpected error in a message box and keep the details in records/error_log.txt."""
    details = "".join(traceback.format_exception(kind, error, trace))
    print(details, file=sys.stderr)
    log = write_error_log(details)
    QMessageBox.critical(None, __title__, f"Something went wrong:\n\n{error}\n\nThe details were saved in:\n{log}")
