"""
FTIR Contamination Analyzer - tests of the layout at different window sizes

The window is opened at the sizes a lab laptop and a desktop screen give it (from the
smallest window the program allows, 960 x 560, up to full HD) and every page and sheet is
checked the way a careful person would look at it:
    - no page scrolls sideways (everything fits the width; text wraps or is shortened), and no
      page is cut off at the side (wider than the area that shows it)
    - no text is cut off and no button is too narrow for its words
    - nothing overlaps its neighbour
    - a sheet sits in the middle of the window
    - the welcome page fits a 1280 x 720 window without scrolling
Skipped automatically if PySide6 is not installed.

Author : Ali Obeidat
Version: 1.0.0
License: MIT (see LICENSE)
"""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")       # no screen needed
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QPoint, QRect, QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QApplication, QLabel,  # noqa: E402
                               QScrollArea, QStackedWidget, QWidget)

from ftir_analyzer import config  # noqa: E402
from ftir_analyzer.gui import MainWindow, load_fonts  # noqa: E402
from ftir_analyzer.motion import Motion, Overlay, Sheet, Toast  # noqa: E402
from ftir_analyzer.plots import setup_fonts  # noqa: E402
from ftir_analyzer.widgets import ElidedLabel  # noqa: E402

SIZES = [(960, 560), (1280, 720), (1920, 1080)]


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path_factory.mktemp("settings")))
    app = QApplication.instance() or QApplication([])
    load_fonts()
    setup_fonts()
    records = tmp_path_factory.mktemp("records")
    add_nylon_6(records / "inhouse_library")                       # an in-house reference: its sheet has more buttons
    win = MainWindow(ask_for_files=False, sample_log=records / "sample_log.csv", audit_log=records / "audit_log.csv",
                     inhouse_dir=records / "inhouse_library", openspecy_dir=records / "openspecy")
    Motion.reduced = True
    win.resize(*SIZES[1])
    win.show()
    assert wait(app, lambda: win.library is not None and not win.busy, 60), "the library did not load"
    yield win
    win.close()


def add_nylon_6(folder):
    from ftir_analyzer.inhouse import InHouseLibrary, reference_notes
    from ftir_analyzer.processing import absorbance
    from ftir_analyzer.spectrum_io import read_spectra
    path = config.EXAMPLES_DIR / "library_demo" / "Nylon6_reference_fibre_collection.csv"
    s, notes = read_spectra(path)[0], reference_notes(path)
    InHouseLibrary(folder).add(notes["reference"], s.wn, absorbance(s), notes["mode"], category=notes["category"],
                               confirmation=notes["confirmation"], source_path=path)


def demo_results(window):
    """The twelve demo spectra analysed (once), and their names."""
    if not window.model.results:
        window.analyse_paths([config.EXAMPLES_DIR], ask=lambda paths: {p: "ATR" for p in paths})
        assert wait(QApplication.instance(), lambda: not window.busy and len(window.model.results) == 12, 60)
    return [r.name for r in window.model.results]


def wait(app, condition=lambda: False, timeout=0.4):
    end = time.time() + timeout
    while not condition() and time.time() < end:
        app.processEvents(QEventLoop.AllEvents, 30)
        time.sleep(0.005)
    app.processEvents()
    return condition()


def settle(seconds=0.4):
    wait(QApplication.instance(), timeout=seconds)


def problems(root):
    """Every visible widget checked: sideways scrolling, cut text, too narrow buttons, overlapping neighbours."""
    found = []
    widgets = [w for w in root.findChildren(QWidget) if w.isVisible() and w.width() > 0 and not w.isWindow()
               and not isinstance(w, (Overlay, Toast))]
    for widget in widgets:
        if isinstance(widget, QAbstractScrollArea) and widget.objectName() != "MapScroller":
            bar = widget.horizontalScrollBar()
            if bar.isVisible() and bar.maximum() > 0:
                found.append(f"{type(widget).__name__} scrolls sideways by {bar.maximum()} px")
            inner = widget.widget() if isinstance(widget, QScrollArea) else None
            if inner is not None and inner.width() > widget.viewport().width() + 1:   # no scroll bar: cut off
                found.append(f"{type(widget).__name__} cut off at the side by "
                             f"{inner.width() - widget.viewport().width()} px")
        if isinstance(widget, ElidedLabel):
            continue                                                  # shortened with … on purpose
        if isinstance(widget, QLabel) and widget.text() and widget.pixmap().isNull():
            if widget.wordWrap():
                if widget.heightForWidth(widget.width()) > widget.height() + 2:
                    found.append(f"text cut: {widget.text()[:40]!r}")
            elif widget.textFormat() != Qt.RichText and (widget.sizeHint().width() > widget.width() + 2
                                                         or widget.sizeHint().height() > widget.height() + 2):
                found.append(f"text cut: {widget.text()[:40]!r}")
        if isinstance(widget, QAbstractButton) and widget.text().strip() and widget.sizeHint().width() > widget.width() + 2:
            found.append(f"button too narrow: {widget.text().strip()!r}")
    by_parent = {}
    for widget in widgets:
        parent = widget.parentWidget()
        if parent is not None and not isinstance(parent, QStackedWidget) and not isinstance(widget, Sheet) \
                and not widget.objectName().startswith("qt_"):
            by_parent.setdefault(id(parent), []).append(widget)
    for siblings in by_parent.values():
        for i, a in enumerate(siblings):
            for b in siblings[i + 1:]:
                overlap = a.geometry().intersected(b.geometry())
                if overlap.width() > 2 and overlap.height() > 2:
                    found.append(f"overlap: {type(a).__name__} / {type(b).__name__}")
    return found


@pytest.mark.parametrize("size", SIZES)
def test_pages_fit_the_window(window, size):
    window.showNormal()
    window.resize(*size)
    settle()
    assert (window.width(), window.height()) == size
    names = demo_results(window)
    window.show_page("analyze")
    window.list.setCurrentIndex(window.proxy.index(names.index("06_PS_calibration_film_transmission"), 0))
    settle(0.8)
    assert problems(window) == [], f"Analyze page at {size}"
    window.show_page("library")
    settle()
    assert problems(window) == [], f"Library page at {size}"


@pytest.mark.parametrize("size", SIZES)
def test_sheets_sit_in_the_middle_and_fit(window, size):
    window.showNormal()
    window.resize(*size)
    window.show_page("library")
    settle()
    names = demo_results(window)                                   # a long name on the "compare" button
    window.list.setCurrentIndex(window.proxy.index(names.index("06_PS_calibration_film_transmission"), 0))
    for opener in (window.open_similarity, window.open_openspecy, lambda: window.open_material("PET"),
                   lambda: window.open_material("Nylon 6"), window.export_report):
        opener()
        settle(0.5)
        sheet = window.sheet
        card, host = sheet.panel.geometry(), sheet.rect()
        assert abs(card.left() - (host.width() - card.right() - 1)) <= 2              # centred left-right
        assert abs(card.top() - (host.height() - card.bottom() - 1)) <= 2              # and top-bottom
        assert problems(sheet) == [], f"sheet at {size}"
        sheet.close_sheet()
        settle(0.3)
    window.open_similarity()
    settle(0.5)
    scroller = window.sheet.findChild(QAbstractScrollArea, "MapScroller")
    assert not scroller.horizontalScrollBar().isVisible()                            # 17 references fit
    window.sheet.close_sheet()
    settle(0.3)


def test_the_welcome_page_fits_a_laptop_window(tmp_path):
    app = QApplication.instance()
    win = MainWindow(ask_for_files=False, sample_log=tmp_path / "s.csv", audit_log=tmp_path / "a.csv",
                     inhouse_dir=tmp_path / "inhouse", openspecy_dir=tmp_path / "openspecy")
    win.resize(1280, 720)
    win.show()
    assert wait(app, lambda: win.library is not None and not win.busy, 60)
    settle()
    page = win.empty
    assert not page.scroll.verticalScrollBar().isVisible()                         # no scrolling needed
    assert problems(win) == []
    tiles = [QRect(t.mapTo(page, QPoint(0, 0)), t.size()) for t in page.tiles]
    assert len({t.top() for t in tiles}) == 1 and len({t.height() for t in tiles}) == 1   # one tidy row
    win.close()
