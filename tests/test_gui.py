"""
FTIR Contamination Analyzer - tests of the desktop window

The window is started without a screen (Qt's "offscreen" mode), the demo spectra are
loaded, and every part a user touches is exercised: selecting results, the dark theme,
the band readout under the mouse, "compare with", the Library page and its sheets, adding
a reference (and being stopped from adding one that is too similar), removing it again,
saving a figure and exporting the report. Most tests run with reduced motion, so every
change is there at once; one test checks that the animations finish in the right state.
Skipped automatically if PySide6 is not installed.

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import os
import re
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")       # no screen needed
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QPoint, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from ftir_analyzer import __author__, __version__, config  # noqa: E402
from ftir_analyzer.analysis import PROBABLE, WEAK  # noqa: E402
from ftir_analyzer.gui import LIBRARY, MainWindow, load_fonts  # noqa: E402
from ftir_analyzer.motion import Motion  # noqa: E402
from ftir_analyzer.plots import setup_fonts  # noqa: E402
from ftir_analyzer.widgets import MatchShow  # noqa: E402

DEMO = config.EXAMPLES_DIR / "library_demo"


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    # the tests keep their window settings in a temporary folder, never in the user's own settings
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path_factory.mktemp("settings")))
    application = QApplication.instance() or QApplication([])
    load_fonts()
    setup_fonts()
    return application


def wait(app, condition, timeout=60):
    """Let Qt work until the condition is true (or the time is up)."""
    end = time.time() + timeout
    while not condition() and time.time() < end:
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.01)
    app.processEvents()
    return condition()


@pytest.fixture(scope="module")
def window(app, tmp_path_factory):
    records = tmp_path_factory.mktemp("records")
    win = MainWindow(ask_for_files=False, sample_log=records / "sample_log.csv", audit_log=records / "audit_log.csv",
                     inhouse_dir=records / "inhouse_library", openspecy_dir=records / "openspecy")
    Motion.reduced = True                                            # every change at once (see test_animations)
    win.show()
    assert wait(app, lambda: win.library is not None and not win.busy), "the library did not load"
    yield win
    win.close()


def answer_modes(paths):
    """Stands in for the dialog: 07 was measured by ATR, the others are not known."""
    return {p: ("ATR" if p.name.startswith("07") else "unknown") for p in paths}


def select(app, window, name):
    names = [r.name for r in window.model.results]
    window.list.setCurrentIndex(window.proxy.index(names.index(name), 0))
    wait(app, lambda: window.result_view.name.text() == name, 5)


def test_library_is_validated_on_start(window):
    assert window.validation.passed
    assert window.badge.kind == "good"


def test_demo_spectra_are_analysed(app, window):
    window.analyse_paths([config.EXAMPLES_DIR], ask=answer_modes)
    assert wait(app, lambda: not window.busy and len(window.model.results) == 20)
    assert window.stack.currentWidget() is window.result_view
    assert window.act_export.isEnabled()


def test_files_are_not_added_twice(app, window):
    window.analyse_paths([config.EXAMPLES_DIR / "01_wipe_area_particle_ATR.csv"], ask=answer_modes)
    wait(app, lambda: not window.busy, 5)
    assert len(window.model.results) == 20


def test_selecting_a_result_fills_the_page(app, window):
    select(app, window, "07_particle_on_filter")
    page = window.result_view
    assert f"{page.strip.best_r:.2f}" == "0.97" and page.strip.rival == "EVA (25% VA)"
    assert page.fact_bands.value.text() == "4 of 4" and page.fact_how.value.text() == "ATR"
    assert "second component" in page.next_text.text()


def test_filter_box(app, window):
    window.search.setText("PVOH")
    assert window.proxy.rowCount() == 1
    window.search.setText("")
    assert window.proxy.rowCount() == 20


def test_dark_theme_and_back(window):
    window.apply_theme("dark")
    assert window.act_theme.isChecked()
    window.apply_theme("light")
    assert not window.act_theme.isChecked()


def test_tracing_under_the_mouse(app, window):
    select(app, window, "07_particle_on_filter")
    plot = window.result_view.plot
    bottom = plot.drawing.axes[1]

    class Event:                                                     # a pretend mouse move to 1030 cm-1
        inaxes, xdata = bottom, 1030.0

    plot._on_move(Event())
    text = plot.readout.text()
    assert "1030 cm⁻¹" in text and "Si-O-Si" in text                 # the band's name
    assert "sample (scaled)" in text and "PE (high density) (scaled)" in text   # every curve's value


def test_analytical_view(app, window):
    plot = window.result_view.plot
    plot.set_view(plot.ANALYTICAL)
    assert len(plot.drawing.axes) == 5                               # one panel per step
    assert plot.steps_text.isVisibleTo(plot) and "Derivative fingerprint" in plot.steps_text.text()
    plot.set_view(plot.RESULT)
    assert len(plot.drawing.axes) == 2


def test_compare_with_another_material(app, window):
    select(app, window, "01_wipe_area_particle_ATR")
    plot = window.result_view.plot
    # best match, a line, the other materials, a line, the samples' submenu
    assert len(plot.compare_menu.actions()) == len(window.library) + 3
    plot.set_compare("PBT")
    labels = [trace[0] for trace in plot.drawing.traces[plot.drawing.axes[1]]]
    assert "PBT (scaled)" in labels and "Compared with PBT" in plot.compare_button.text()
    plot.set_compare(None)
    assert "PET (scaled)" in [trace[0] for trace in plot.drawing.traces[plot.drawing.axes[1]]]


def test_another_sample_over_this_one(app, window):
    """Two finds from the same wafer: draw the second over the first, with how alike they are."""
    select(app, window, "02_wafer_box_particle_ATR")
    plot = window.result_view.plot
    other = next(r for r in window.model.results if r.name == "07_particle_on_filter")
    plot.set_overlay(other)
    labels = [trace[0] for trace in plot.drawing.traces[plot.drawing.axes[1]]]
    assert "07_particle_on_filter (scaled)" in labels and "over 07_particle_on_filter" in plot.compare_button.text()
    legend = [text.get_text() for text in plot.figure.legends[0].get_texts()]
    assert any(line.startswith("other sample: 07_particle_on_filter (r = 0.9") for line in legend)  # both PE
    select(app, window, "07_particle_on_filter")                     # never drawn over itself
    assert plot.overlay is None
    plot.set_overlay(None)


def test_animations_finish_in_the_right_state(app, window):
    Motion.reduced = False
    try:
        select(app, window, "07_particle_on_filter")
        wait(app, lambda: False, 1.5)                                  # let every animation run to the end
        page = window.result_view
        assert page.strip.progress == 1.0 and page.fact_bands.value.text() == "4 of 4"
        assert all(section.graphicsEffect() is None for section in page.sections())   # effects removed again
        assert page.bars.growth == 1.0
    finally:
        Motion.reduced = True


def test_the_wheel_glides_and_stops(app, window):
    select(app, window, "07_particle_on_filter")
    page = window.result_view
    bar, viewport = page.verticalScrollBar(), page.viewport()
    bar.setValue(0)
    centre = QPointF(viewport.width() / 2, viewport.height() / 2)

    def notch():
        app.sendEvent(viewport, QWheelEvent(centre, viewport.mapToGlobal(centre), QPoint(0, 0), QPoint(0, -120),
                                            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
    Motion.reduced = False
    try:
        notch()
        assert bar.value() == 0 and page.timer.isActive()            # it glides, it does not jump
        assert wait(app, lambda: not page.timer.isActive(), 3)
        assert bar.value() == min(page.STEP, bar.maximum())          # and arrives exactly one notch down
        bar.setValue(0)
        notch()
        bar.setValue(bar.maximum())                                  # the scroll bar takes over: the glide gives way
        wait(app, lambda: not page.timer.isActive(), 1)
        assert bar.value() == bar.maximum()
    finally:
        Motion.reduced = True
    bar.setValue(0)
    notch()
    assert not page.timer.isActive()                                 # reduced motion: the usual scroll step


def test_library_page(app, window):
    window.show_page(LIBRARY)
    page = window.library_page
    assert window.pages.currentWidget() is page and len(page.cards) == 16
    page.categories.setCurrentRow([page.categories.item(i).data(0x0100)
                                   for i in range(page.categories.count())].index("Packaging"))
    assert {card.name for card in page.grid.visible_cards()} == {"PE (high density)", "PS", "EVOH (44% ethylene)"}
    page.categories.setCurrentRow(0)
    page.search.setText("polyketone")
    assert [card.name for card in page.grid.visible_cards()] == ["PK (polyketone)"]
    page.search.setText("")
    window.show_page("analyze")


def test_detail_and_similarity_sheets(app, window):
    detail = window.open_material("PET")
    assert window.sheet is not None and detail.chart.main is not None
    window.sheet.close_sheet()
    wait(app, lambda: window.sheet is None, 5)
    panel = window.open_similarity()
    assert panel is not None and window.sheet is not None
    window.sheet.close_sheet()
    wait(app, lambda: window.sheet is None, 5)


def adding_panel(app, window, path):
    """Open the add sheet, load a reference file and wait for its validation."""
    panel = window.open_add_reference(use_current=False)
    panel.load_file(path)
    assert wait(app, lambda: panel.preview is not None, 30), "the validation did not finish"
    return panel


def test_adding_a_reference_catches_the_unknown(app, window):
    assert window.model.results[[r.name for r in window.model.results].index("10_tool_cover_fragment_ATR")].verdict \
        == WEAK
    panel = adding_panel(app, window, DEMO / "ABS_reference_known_part.csv")
    assert panel.name.text() == "ABS" and panel.category.currentText() == "Equipment & fixtures"   # from the notes
    impact, changes = panel.preview
    assert impact.passed and impact.distinct
    assert "10_tool_cover_fragment_ATR" in [c.sample for c in changes]            # previewed before saving
    assert panel.problems() == [] and panel.add_button.isEnabled()
    panel._submit()
    assert wait(app, lambda: not window.busy and "ABS" in window.library.spectra, 60)
    results = {r.name: r for r in window.model.results}
    assert (results["10_tool_cover_fragment_ATR"].verdict, results["10_tool_cover_fragment_ATR"].match) \
        == (PROBABLE, "ABS")
    assert "10_tool_cover_fragment_ATR" in window.model.updated                   # marked in the list
    assert "ABS" in window.library_page.cards and window.validation.passed
    window.show_page("analyze")


def test_a_too_similar_reference_cannot_be_added(app, window):
    panel = adding_panel(app, window, DEMO / "SAN_reference_cover_sample.csv")
    impact, _ = panel.preview
    assert not impact.passed and impact.nearest[0] == "ABS"
    assert "a reference that keeps the library valid" in panel.problems()
    assert not panel.add_button.isEnabled()
    window.sheet.close_sheet()
    wait(app, lambda: window.sheet is None, 5)


def test_removing_a_reference(app, window):
    window.remove_reference("ABS", reason="end of the demo")
    assert wait(app, lambda: not window.busy and "ABS" not in window.library.spectra, 60)
    results = {r.name: r for r in window.model.results}
    assert results["10_tool_cover_fragment_ATR"].verdict == WEAK
    log = (window.inhouse_dir / "library_changes.csv").read_text(encoding="utf-8")
    assert ",add,ABS," in log and ",remove,ABS," in log and "end of the demo" in log   # both kept
    window.show_page("analyze")


def test_open_specy_references_and_library_modes(app, window):
    pytest.importorskip("rdata")
    from pathlib import Path
    assert not window.library_page.mode.isVisibleTo(window.library_page)      # nothing to switch to yet
    window.get_openspecy(str(Path(__file__).parent / "data" / "openspecy_sample.rds"))
    assert wait(app, lambda: not window.busy and window.extended and len(window.library) == 22, 60)
    assert window.validation.passed and window.library_page.mode.isVisibleTo(window.library_page)
    assert len([c for c in window.library_page.cards.values() if c.info.origin == "open specy"]) == 6
    window.set_library_mode("essentials")
    assert wait(app, lambda: not window.busy and len(window.library) == 16, 60)
    assert not window.extended
    window.show_page("analyze")


def test_closest_matches(app, window):
    select(app, window, "01_wipe_area_particle_ATR")
    top = window.result_view.top
    assert [tile.name for tile in top.tiles] == [name for name, _ in window.current_result().ranking[:4]]
    top._choose(top.tiles[1].name)                                            # click the second one ...
    assert window.result_view.plot.compare == top.tiles[1].name               # ... it is drawn in the big figure
    top.set_view("fingerprint")
    assert top.tiles[0].sample is not None
    top._choose(top.tiles[0].name)                                            # back to the best match
    assert window.result_view.plot.compare is None


def test_save_figure(window, tmp_path):
    from ftir_analyzer.plots import save_figure
    r = window.current_result()
    for suffix in ("png", "svg", "pdf"):
        for view in ("result", "analytical"):
            path = tmp_path / f"figure_{view}.{suffix}"
            save_figure(r, window.library, path, view=view)
            assert path.stat().st_size > 10_000


def test_bands_can_be_pointed_at_and_clicked(app, window):
    from ftir_analyzer.widgets import BandButton
    view = window.result_view
    buttons = [b for b in view.findChildren(BandButton) if b.kind == "found"]
    assert buttons, "the best spectrum has key bands to point at"
    button = buttons[0]
    button.click()                                                                  # pin: mark, zoom, say what it is
    assert view.pinned_band is button and len(view.plot.band_artists) == 2 and not view.band_info.isHidden()
    low, high = sorted(view.plot.drawing.axes[-1].get_xlim())
    assert high - low < 400 and low < button.w < high
    assert f"{button.w:.0f} cm" in view.band_text.text()
    button.click()                                                                  # a second click lets go
    assert view.pinned_band is None and not view.plot.band_artists and view.band_info.isHidden()
    low, high = sorted(view.plot.drawing.axes[-1].get_xlim())
    assert high - low > 3000                                                        # the whole spectrum again


def test_export_report(app, window, tmp_path):
    window.write_report_to(tmp_path, ask_to_open=False)
    assert wait(app, lambda: not window.busy and hasattr(window, "last_report"), 120)
    html = window.last_report.read_text(encoding="utf-8")
    assert html.count('class="js-plotly-plot"') + html.count("Plotly.newPlot") >= 18   # 2 interactive figures each
    assert "Ali Obeidat" in html
    assert window.audit_log.exists()


def test_the_tool_entered_at_export_reaches_the_trends_page(app, window, tmp_path, monkeypatch):
    monkeypatch.setattr("ftir_analyzer.gui.QDesktopServices", type("Desktop", (), {"openUrl": staticmethod(lambda url: None)}))
    first = window.audit_log.read_text(encoding="utf-8") if window.audit_log.exists() else ""
    panel = window.export_report()
    panel.set_folder(tmp_path)
    panel.tool.setText("  Etch   3 ")
    panel._submit("html")
    assert wait(app, lambda: not window.busy and window.tool_log.exists() and window.unknown_log.exists(), 120)
    assert window.audit_log.read_text(encoding="utf-8").startswith(first)         # the audit log only grew
    window.show_page("trends")
    page = window.trends_page
    assert page.tool.findText("Etch 3") >= 0
    samples = len({(s.sha, s.name) for s in page.samples})
    assert samples == len(page.samples) >= len(window.model.results)              # each sample once
    panel = window.export_report()                                                # the tool is offered next time
    assert panel.tool.completer().model().rowCount() == 1
    window.sheet.close_sheet()
    window.show_page("analyze")


def test_the_name_and_version_sit_on_the_home_screen_alone(app, window, monkeypatch):
    show = window.empty.show_match
    assert __author__ in show.signature and __version__ in show.signature
    words = " ".join(label.text() for label in window.findChildren(QLabel))
    assert f"by {__author__}" not in words and "Developed by" not in words
    show = MatchShow()                                                           # its own: the window's opens a real box
    seen = []
    show.about_requested.connect(lambda: seen.append(True))
    show.over_signature = False
    show.mousePressEvent(None)
    assert not seen                                                              # only a click on the signature
    show.over_signature = True
    show.mousePressEvent(None)
    show.over_signature = False
    assert seen == [True]


def test_the_light_crosses_the_signature_once_after_the_verdict(app, window, monkeypatch):
    show = window.empty.show_match
    monkeypatch.setattr("ftir_analyzer.widgets.Motion.reduced", False)
    keep = show.seconds
    show.rows = show.rows or [("PE", 0.9, None)]
    locked = show.INTRO + (len(show.rows) - 1) * show.STEP + show.SLIDE + show.GLINT_WAIT
    show.seconds = locked - 0.1
    assert show._glint() is None
    show.seconds = locked + show.GLINT / 2
    assert show._glint() == pytest.approx(0.5) and not show._still()
    show.seconds = locked + show.GLINT + 0.1
    assert show._glint() is None
    monkeypatch.setattr("ftir_analyzer.widgets.Motion.reduced", True)
    show.seconds = locked + show.GLINT / 2
    assert show._glint() is None
    show.seconds = keep


def test_an_unknown_group_opens_the_add_reference_sheet(app, window, tmp_path):
    from ftir_analyzer.unknowns import UnknownGroup
    sample = type("Sample", (), {"sha": "not this file"})()
    window.trends_page.add_from_group.emit(UnknownGroup((sample,), sample, str(tmp_path / "gone.csv")))
    assert window.sheet is not None and window.sheet.content.spectrum is None    # the file is gone: an empty form
    window.sheet.close_sheet()


def test_the_trends_page_shows_demo_data_as_made_up(app, window):
    window.show_page("trends")
    page = window.trends_page
    page.demo_button.setChecked(True)
    assert page.demo_note.isVisible() and page.samples and all(s.sha.startswith("demo") for s in page.samples)
    assert page.repeat_rows.count() >= 1 and page.material_chart.rows and page.tool_chart.rows
    assert page.group_card.isVisible() and page.group_rows.count() == 2          # two made-up groups
    page.period.set_value("0")
    page.show_samples()
    assert len(page.shown) == len(page.samples)
    page.tool.setCurrentText("Etch 3")
    assert {s.tool for s in page.shown} == {"Etch 3"}
    page.demo_button.setChecked(False)
    assert not page.demo_note.isVisible()
    window.show_page("analyze")


def test_the_report_message_offers_the_pdf(app, window, tmp_path):
    window.write_report_to(tmp_path, ask_to_open=False)
    assert wait(app, lambda: not window.busy and hasattr(window, "last_report"), 120)
    assert window.last_report.with_name("report.pdf").exists()
    window._report_written(window.last_report)
    texts = [button.text() for button in window.report_box.buttons()]
    assert set(texts) == {"Open the PDF", "Open the web report", "Show the folder", "Close"}
    window.report_box.close()


def test_copy_the_result(app, window):
    """Ctrl+C in the list puts a short, traceable summary of the result on the clipboard."""
    if not window.model.results:
        window.analyse_paths([config.EXAMPLES_DIR], ask=answer_modes)
        assert wait(app, lambda: not window.busy and len(window.model.results) == 20)
    window.show_page("analyze")
    select(app, window, "07_particle_on_filter")
    window.copy_result()
    text = QApplication.clipboard().text()
    assert text.startswith("07_particle_on_filter - Probable: PE (high density)")
    assert "Score r = 0.97" in text and "Second component" in text and "Next step:" in text
    assert window.current_result().spectrum.sha256 in text and window.library.sha256 in text


def test_bars_grow_when_a_sheet_arrives(app, window):
    """With animations on, the bars in the sheets grow to their full length (they start at zero)."""
    Motion.reduced = False
    try:
        detail = window.open_material("PET")
        assert wait(app, lambda: detail.bars.growth >= 1.0, 5)
        window.sheet.close_sheet()
        assert wait(app, lambda: window.sheet is None, 5)
        panel = window.open_add_reference(use_current=False)
        panel.load_file(DEMO / "ABS_reference_known_part.csv")
        assert wait(app, lambda: panel.preview is not None, 30)
        bars = [b for b in panel.findChildren(type(detail.bars)) if b.ranking]
        assert bars and wait(app, lambda: all(b.growth >= 1.0 for b in bars), 5)
        window.sheet.close_sheet()
        assert wait(app, lambda: window.sheet is None, 5)
    finally:
        Motion.reduced = True


def test_new_badges_are_in_the_transition_picture(app, window):
    """Qt shows a widget put into a layout a moment later; the picture a transition plays must
    already have it, or the badge pops in when the transition ends."""
    from PySide6.QtWidgets import QLabel
    from ftir_analyzer.motion import snapshot
    window.show_page("analyze")
    row = window.result_view.badges                                # the title row's layout
    badge = QLabel("new badge")
    row.addWidget(badge)
    assert not badge.isVisible()                                   # Qt has not shown it yet ...
    snapshot(window.result_view.viewport())
    assert badge.isVisible()                                       # ... the picture is taken with it
    row.removeWidget(badge)
    badge.deleteLater()


def test_the_close_button_is_on_the_sheet_from_the_first_frame(app, window):
    Motion.reduced = False
    try:
        window.open_material("PET")
        sheet = window.sheet
        assert not sheet.close_button.icon().isNull() and not sheet.has_arrived   # on the photo, not added later
        sheet.close_sheet()
        assert wait(app, lambda: window.sheet is None, 5)
    finally:
        Motion.reduced = True


def test_a_change_is_shown_where_it_is_seen(app, window):
    """Added on the Analyze page: the changed row glows there and its page says what changed. Removed on the
    Library page: the rows glow when the Analyze page is shown (the message offers to show them)."""
    window.show_page("analyze")
    select(app, window, "05_fibre_on_wafer_ATR")
    panel = adding_panel(app, window, DEMO / "Nylon6_reference_fibre_collection.csv")
    panel._submit()
    assert wait(app, lambda: not window.busy and "Nylon 6" in window.library.spectra, 60)
    assert window.pages.currentWidget() is window.analyze_page                     # stays where it was seen
    view = window.result_view
    assert view.change_box.isVisible() and "Probable: Nylon 6" in view.change_text.text()
    assert window.toast.action_word == "See it in the library"
    window.show_page("library")
    window.remove_reference("Nylon 6", reason="end of the check")
    assert wait(app, lambda: not window.busy and "Nylon 6" not in window.library.spectra, 60)
    assert window.pages.currentWidget() is window.library_page and window.pending_glow
    assert window.toast.action_word == "Show"
    window.toast.on_action()                                                        # "Show"
    assert window.pages.currentWidget() is window.analyze_page and not window.pending_glow
    assert window.current_result().name == "05_fibre_on_wafer_ATR" and "Weak" in view.change_text.text()


def test_exporting_a_signed_report(app, window, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("ftir_analyzer.gui.QDesktopServices",
                        type("Desktop", (), {"openUrl": staticmethod(lambda url: opened.append(url.toLocalFile()))}))
    panel = window.export_report()
    panel.set_folder(tmp_path)
    panel.name.setText("Ali Obeidat")
    panel.decision._choose(panel.decision.values().index("re-measure"))
    assert "a comment" in panel.problems() and "the statement ticked" in panel.problems()
    assert not panel.export_button.isEnabled()                                   # not signed without them
    panel.comment.setText("06 is saturated: measure a thinner film")
    panel.statement_text.mousePressEvent(type("Click", (), {"button": lambda self: Qt.LeftButton})())
    assert panel.statement.isChecked() and panel.problems() == [] and "Sign" in panel.export_button.text()
    assert "PDF" in panel.export_button.text() and "web page" in panel.html_button.text()
    panel._submit("pdf")
    assert wait(app, lambda: not window.busy and str(tmp_path) in str(window.last_report), 60)
    assert opened and opened[-1].endswith("report.pdf")                        # the button opens what it names
    window.open_last("report.html")
    assert opened[-1].endswith("report.html")
    page = window.last_report.read_text(encoding="utf-8")
    assert "Signed: Re-measure" in re.sub(r"<[^>]+>", "", page) and "06 is saturated" in page
    assert window.settings.value("user_name") == "Ali Obeidat"                  # remembered for next time
    assert "Ali Obeidat" in window.signature_log.read_text(encoding="utf-8")


def test_a_band_lights_its_bonds_and_the_structure_follows_the_figure(app, window):
    select(app, window, "01_wipe_area_particle_ATR")
    view = window.result_view
    panel = view.structure
    assert panel.isVisible() and panel.name.text() == "Structure of PET"
    assert panel.view.key == ["C", "H", "O"]                                     # the legend: only the atoms it has
    carbonyl = next(b for b in view.band_buttons if 1700 <= b.w <= 1765)
    view._pin_band(carbonyl)
    assert panel.view.lit == set(panel.model["groups"]["C=O"]["bonds"])
    assert [b.group for b in panel.buttons if b.isChecked()] == ["C=O"]
    view._pin_band(carbonyl)                                                     # a second click lets go
    assert panel.view.lit == set()
    chip = next(b for b in panel.buttons if b.group == "C=O")                    # the same from the model's side
    chip.click()
    assert view.pinned_band is carbonyl and panel.view.lit == set(panel.model["groups"]["C=O"]["bonds"])
    view._pin_band(carbonyl)
    view.plot.set_compare("PBT")
    assert panel.name.text() == "Structure of PBT"
    view.plot.set_compare(None)
    assert panel.name.text() == "Structure of PET"


def test_a_close_call_shows_the_family_and_where_they_differ(app, window):
    select(app, window, "13_clear_film_on_tool_ATR")
    view = window.result_view
    assert view.close_box.isVisible() and "Polyesters" in view.close_text.text()
    view.close_button.click()
    assert view.plot.compare == "PBT" and len(view.plot.band_artists) == 2
    view.plot.set_compare(None)
    select(app, window, "01_wipe_area_particle_ATR")
    assert not view.close_box.isVisible()                                        # a probable needs no such box


def test_the_tour_works_and_keeps_nothing(app, window):
    sizes = window.library.sha256, len(window.library)
    tour_window = window.start_tour()
    folder = tour_window.tour_folder
    assert wait(app, lambda: tour_window.tour is not None, 60)
    tour, seen = tour_window.tour, []
    for _ in tour.steps:
        assert wait(app, lambda: tour.card.isVisible(), 60), f"stuck after {seen}"
        seen.append(tour.card.title.text())
        for words in (tour.card.title, tour.card.text):                          # no step's words are cut off
            assert words.height() >= words.heightForWidth(words.width()), seen[-1]
        if tour.at == 5:                                                         # the reference was added
            assert tour_window.current_result().match == "Nylon 6"
        if tour.at < len(tour.steps) - 1:
            tour.next()
    assert seen[0] == "A tour with real data" and seen[-1] == "That is the app"
    assert "Nylon 6" in tour_window.library.spectra and len(tour_window.library) == 17
    assert (window.library.sha256, len(window.library)) == sizes                 # the real window saw nothing
    assert window.settings.value("library_mode", "essentials") == "essentials"
    assert "Nylon 6" not in window.library.spectra
    assert all(str(p).startswith(str(folder)) for p in (tour_window.audit_log, tour_window.inhouse_dir, tour_window.openspecy_dir))
    tour.card.next_button.click()                                                # Close
    assert wait(app, lambda: not folder.exists(), 5)


def test_sheets_never_leave_a_trace(app, window):
    """With animations on: a sheet opened while another is still fading out does not keep it in its
    picture of the window; switching the page closes the sheet; switching the theme re-photographs
    the window behind an open sheet."""
    from ftir_analyzer.motion import Sheet
    Motion.reduced = False
    try:
        window.show_page(LIBRARY)
        wait(app, lambda: False, 0.6)
        window.open_similarity()
        wait(app, lambda: window.sheet is not None and window.sheet.has_arrived, 5)
        first = window.sheet
        first.close_sheet()                                              # still fading out ...
        window.open_material("PET")                                      # ... when the next one opens
        assert not first.isVisible()                                     # finished at once, not photographed
        wait(app, lambda: window.sheet.has_arrived, 5)
        assert [s for s in window.centralWidget().findChildren(Sheet) if s.isVisible()] == [window.sheet]
        before = window.sheet.background.toImage()
        window.apply_theme("dark")
        wait(app, lambda: window.sheet.background.toImage() != before, 5)  # the window behind, photographed again
        window.show_page("analyze")
        wait(app, lambda: window.sheet is None, 5)                       # a sheet belongs to its page
    finally:
        window.apply_theme("light")
        Motion.reduced = True
