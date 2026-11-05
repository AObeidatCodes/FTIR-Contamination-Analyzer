"""The instrument check, the second-person review, the spectrum quality check, the search in a known material and
the shift-tolerant search."""
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from benchmark import shift as shift_tool
from ftir_analyzer import config
from ftir_analyzer.analysis import PROBABLE, analyse
from ftir_analyzer.checks import Checks, measure_again
from ftir_analyzer.instrument_check import (FAILED, PASSED, FilmCheck, append_check, band_top, check_file, measure_film,
                                            movement, read_checks)
from ftir_analyzer.known_material import take_out
from ftir_analyzer.library import load_library, search, search_shifted
from ftir_analyzer.processing import absorbance, on_grid
from ftir_analyzer.records import make_signoff, read_mode_note
from ftir_analyzer.review import (CHANGED, MISSING, REVIEWED, WAITING, Report, append_report, append_review, read_reports,
                                  reviewer_problem, same_person)
from ftir_analyzer.spectrum_io import Spectrum, SpectrumFileError, read_spectra

FILM = config.EXAMPLES_DIR / "06_PS_calibration_film_transmission.csv"


@pytest.fixture(scope="module")
def library():
    return load_library()


def example(name, library):
    path = config.EXAMPLES_DIR / name
    return analyse(read_spectra(path)[0], library, read_mode_note(path) or "unknown", "file note")


def film():
    spectrum = read_spectra(FILM)[0]
    order = np.argsort(spectrum.wn)
    return spectrum.wn[order], absorbance(spectrum)[order]


def check_with(shift):
    return FilmCheck(tuple(x + shift for x in config.FILM_BANDS))


# ---------------------------------------------------------------------------- the instrument check
def test_the_real_film_passes_and_a_known_shift_is_measured():
    wn, a = film()
    plain = measure_film(wn, a)
    assert plain.result == PASSED and len(plain.measured) == len(config.FILM_BANDS)
    for shift in (0.4, -0.7, 1.5):
        assert measure_film(wn + shift, a).mean - plain.mean == pytest.approx(shift, abs=0.02)
    assert measure_film(wn + 1.5, a).result == FAILED


def test_the_position_is_found_between_two_points():
    wn = np.arange(1000.0, 1100.0, 2.0)
    a = np.exp(-((wn - 1050.6) / 8) ** 2)
    assert band_top(wn, a, 1050.0) == pytest.approx(1050.6, abs=0.05)


def test_a_band_that_is_too_dark_or_missing_is_not_measured():
    wn = np.arange(1000.0, 1100.0, 1.0)
    assert np.isnan(band_top(wn, 3 * np.exp(-((wn - 1050) / 8) ** 2), 1050.0))     # flat, dark top
    assert np.isnan(band_top(wn, np.exp(-((wn - 1080) / 8) ** 2), 1050.0))         # no top near it
    assert np.isnan(band_top(wn, np.ones_like(wn), 1050.0))


@pytest.mark.parametrize("name", ["01_wipe_area_particle_ATR.csv", "03_litho_rework_film_ATR.csv", "13_clear_film_on_tool_ATR.csv",
                                  "15_green_paint_flake_ATR.csv"])
def test_another_material_is_not_taken_for_the_film(name):
    spectrum = read_spectra(config.EXAMPLES_DIR / name)[0]
    assert measure_film(spectrum.wn, absorbance(spectrum)) is None


def test_files_that_cannot_be_used_say_why(tmp_path):
    with pytest.raises(SpectrumFileError, match="ATR"):
        check_file(config.EXAMPLES_DIR / "12_shipping_box_film_ATR.csv")
    with pytest.raises(SpectrumFileError, match="apart"):
        check_file(config.EXAMPLES_DIR / "08_fibre_on_filter.csv")
    with pytest.raises(SpectrumFileError, match="polystyrene"):
        check_file(config.EXAMPLES_DIR / "07_particle_on_filter.csv")


def test_checks_are_added_and_read_back(tmp_path):
    log = tmp_path / "records" / "instrument_checks.csv"
    append_check(check_with(0.2), "FTIR 1", FILM, log, who="sam", when="2026-11-01T09:00:00+00:00")
    append_check(check_with(-1.4), " FTIR  1 ", FILM, log, who="sam", when="2026-11-02T09:00:00+00:00")
    assert log.read_text(encoding="utf-8").startswith("# Instrument checks")
    first, second = read_checks(log)
    assert (first.instrument, first.result) == ("FTIR 1", PASSED) and first.mean == pytest.approx(0.2)
    assert (second.instrument, second.result) == ("FTIR 1", FAILED) and second.largest == pytest.approx(1.4)
    assert len(first.shifts) == len(config.FILM_BANDS)


def test_a_steady_movement_is_noticed_and_a_wobble_is_not():
    def logged(means):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [SimpleNamespace(time=start + timedelta(days=i), mean=m) for i, m in enumerate(means)]
    assert movement(logged([0.1, 0.3, 0.7])) == pytest.approx(0.6)
    assert movement(logged([0.1, -0.2, -0.5])) == pytest.approx(-0.6)
    assert movement(logged([0.1, 0.5, 0.3])) == 0                       # up and down
    assert movement(logged([0.1, 0.2, 0.3])) == 0                       # too little to matter
    assert movement(logged([0.1, 0.9])) == 0                            # too few


# ---------------------------------------------------------------------------- the second-person review
def exported(tmp_path, name="Sam Lee", login="sam"):
    html = tmp_path / "report.html"
    html.write_text("the report", encoding="utf-8")
    log = tmp_path / "reports.csv"
    results = [SimpleNamespace(verdict=v) for v in ("probable", "probable", "weak", "no reliable match")]
    append_report(results, {"run_at": "2026-11-01T09:00:00+00:00", "run_by": login, "run_by_name": name}, html, " Etch  3 ", log)
    return html, log


def test_an_exported_report_waits_for_review(tmp_path):
    html, log = exported(tmp_path)
    report, = read_reports(log, tmp_path / "reviews.csv")
    assert (report.tool, report.spectra, report.probable, report.weak, report.no_match) == ("Etch 3", 4, 2, 1, 1)
    assert report.path == html and report.state == WAITING


def test_the_analyst_cannot_review_their_own_report(tmp_path):
    _, log = exported(tmp_path)
    report, = read_reports(log, tmp_path / "reviews.csv")
    assert reviewer_problem(report, " sam  LEE ", "someone") == "a different person from the analyst"
    assert reviewer_problem(report, "  ", "someone") == "your name"
    assert reviewer_problem(report, "Noor Haddad", "noor") == ""
    with pytest.raises(ValueError, match="different person"):
        signoff = make_signoff("Sam Lee", "accept")
        append_review(report, signoff, tmp_path / "reviews.csv")
    assert not (tmp_path / "reviews.csv").exists()


def test_without_an_analyst_name_the_login_decides(tmp_path):
    _, log = exported(tmp_path, name="", login="sam")
    report, = read_reports(log, tmp_path / "reviews.csv")
    assert same_person(report, "Whoever", "SAM")
    assert not same_person(report, "Whoever", "noor")


def test_a_review_is_recorded_with_who_and_a_shared_login_shows(tmp_path):
    _, log = exported(tmp_path, login="labpc")
    reviews = tmp_path / "reviews.csv"
    report, = read_reports(log, reviews)
    signoff = dict(make_signoff("Noor Haddad", "accept with changes", "Sample 3 is PET."), login="labpc")
    append_review(report, signoff, reviews)
    report, = read_reports(log, reviews)
    assert report.state == REVIEWED
    assert (report.review.name, report.review.decision, report.review.comment) == ("Noor Haddad", "accept with changes",
                                                                                  "Sample 3 is PET.")
    assert report.review.same_login


def test_a_report_changed_after_export_cannot_be_reviewed(tmp_path):
    html, log = exported(tmp_path)
    html.write_text("a changed report", encoding="utf-8")
    report, = read_reports(log, tmp_path / "reviews.csv")
    assert report.state == CHANGED
    with pytest.raises(ValueError, match="changed"):
        append_review(report, make_signoff("Noor Haddad", "accept"), tmp_path / "reviews.csv")
    html.unlink()
    assert read_reports(log, tmp_path / "reviews.csv")[0].state == MISSING


def test_the_newest_report_comes_first(tmp_path):
    log = tmp_path / "reports.csv"
    for name in ("first", "second"):
        html = tmp_path / f"{name}.html"
        html.write_text(name, encoding="utf-8")
        append_report([], {"run_at": "2026-11-01T09:00:00+00:00", "run_by": "sam"}, html, "", log)
    assert [Path(r.path).stem for r in read_reports(log, tmp_path / "none.csv")] == ["second", "first"]
    assert isinstance(read_reports(log, tmp_path / "none.csv")[0], Report)


# ---------------------------------------------------------------------------- the spectrum quality check
def checks(**changes):
    values = dict(max_a=1.0, co2_share=0.1, ch="present", ch_share=0.5, oh="none or trace", oh_share=0.0, noise=0.001,
                  co2_signed=0.01, tall=1.0)
    return Checks(**{**values, **changes})


def test_a_good_spectrum_has_no_reason_to_be_measured_again():
    assert measure_again(checks()) == []


@pytest.mark.parametrize("changes, words", [(dict(max_a=-0.1), "below zero"), (dict(co2_share=0.7), "no sample"),
                                            (dict(max_a=3.2), "saturated (A up to 3.2)"), (dict(noise=0.1), "10 times the noise")])
def test_each_problem_says_what_to_do(changes, words):
    reasons = measure_again(checks(**changes))
    assert len(reasons) == 1 and words in reasons[0]


def test_the_demos_with_a_real_problem_are_marked_and_their_verdicts_stay(library):
    saturated = example("06_PS_calibration_film_transmission.csv", library)
    empty = example("09_empty_spot_on_filter.csv", library)
    good = example("01_wipe_area_particle_ATR.csv", library)
    assert saturated.next_step.startswith("Measure again.") and empty.next_step.startswith("Measure again.")
    assert (saturated.verdict, saturated.match) == ("weak", "PS")
    assert ("measure again", "bad") not in good.flags and good.verdict == PROBABLE


def test_a_noisy_spectrum_is_marked(library):
    spectrum = read_spectra(config.EXAMPLES_DIR / "01_wipe_area_particle_ATR.csv")[0]
    a = absorbance(spectrum)
    noisy = a + np.random.default_rng(1).normal(0, 0.2 * np.ptp(a), len(a))
    result = analyse(Spectrum("noisy", spectrum.wn, noisy, "absorbance", "test", Path("test"), ""), library, "ATR", "test")
    assert "times the noise" in result.next_step and ("measure again", "bad") in result.flags


# ---------------------------------------------------------------------------- a contaminant in a known material
def mix(library, main, other, share):
    y = (1 - share) * np.asarray(library.spectra[main]) + share * np.asarray(library.spectra[other])
    return SimpleNamespace(compared=y + np.random.default_rng(3).normal(0, 1e-4, y.size))


def test_a_clean_spectrum_is_taken_out_and_the_contaminant_is_named(library):
    rest = take_out(mix(library, "PP", "PMMA", 0.15), "my clean PP", library.spectra["PP"], library)
    assert rest.found == "PMMA" and "looks most like PMMA" in rest.text() and "A hint" in rest.text()


def test_the_main_material_is_not_named_as_its_own_contaminant(library):
    rest = take_out(mix(library, "PP", "PMMA", 0.15), "my clean PP", library.spectra["PP"], library)
    assert "PP" not in [name for name, _ in rest.ranking]


def test_two_spectra_that_hardly_overlap_are_refused(library):
    y = np.asarray(library.spectra["PP"], float).copy()
    y[100:] = np.nan
    clean = np.asarray(library.spectra["PET"], float).copy()
    clean[:100] = np.nan
    with pytest.raises(ValueError, match="hardly cover"):
        take_out(SimpleNamespace(compared=y), "clean", clean, library)


def test_nothing_is_named_when_what_is_left_matches_nothing(library):
    y = np.asarray(library.spectra["PP"], float)
    y = y + np.random.default_rng(5).normal(0, 0.002, len(y))
    rest = take_out(SimpleNamespace(compared=y), "my clean PP", library.spectra["PP"], library)
    assert rest.found is None and "Nothing in the library clearly matches" in rest.text()


# ---------------------------------------------------------------------------- the shift-tolerant search
def test_the_search_is_switched_off_until_the_protocol_passes():
    assert config.SHIFT_TRIES == ()


def test_switched_off_the_results_are_the_ordinary_search(library):
    spectrum = read_spectra(config.EXAMPLES_DIR / "01_wipe_area_particle_ATR.csv")[0]
    result = analyse(spectrum, library, "ATR", "test")
    assert result.ranking == search(on_grid(spectrum.wn, absorbance(spectrum)), library)


def test_the_tolerant_search_recovers_a_shifted_spectrum(library):
    spectrum = read_spectra(config.EXAMPLES_DIR / "01_wipe_area_particle_ATR.csv")[0]
    moved = Spectrum("moved", spectrum.wn + 6, spectrum.raw, spectrum.unit, "test", Path("test"), "")
    assert analyse(moved, library, "ATR", "test").verdict != PROBABLE
    tolerant = analyse(moved, library, "ATR", "test", shifts=config.SHIFT_TEST)
    assert (tolerant.verdict, tolerant.best) == (PROBABLE, "PET")


def test_each_reference_keeps_its_best_score(library):
    spectrum = read_spectra(config.EXAMPLES_DIR / "01_wipe_area_particle_ATR.csv")[0]
    a = absorbance(spectrum)
    plain = dict(search(on_grid(spectrum.wn, a), library))
    tolerant = dict(search_shifted(spectrum.wn, a, library, config.SHIFT_TEST))
    assert all(tolerant[name] >= plain[name] - 1e-9 for name in plain)


def counts(right, not_right, false, spectra=200):
    return shift_tool.Tally(spectra, right, not_right, false)


def test_the_protocol_rules_decide():
    today = {0: counts(100, 2, 0), 2: counts(50, 2, 0), 4: counts(10, 2, 0)}
    good = {0: counts(100, 3, 1), 2: counts(90, 3, 1), 4: counts(90, 3, 1)}
    assert shift_tool.verdict(today, good)[1]
    false = {**good, 0: counts(100, 3, 8)}
    assert shift_tool.verdict(today, false)[0]["1 false probable"] is False
    wrong = {**good, 0: counts(100, 8, 1)}
    assert shift_tool.verdict(today, wrong)[0]["2 not right probable"] is False
    lost = {**good, 0: counts(90, 3, 1)}
    assert shift_tool.verdict(today, lost)[0]["3 right probable at shift 0"] is False
    same = {**good, 4: counts(10, 3, 1)}
    assert shift_tool.verdict(today, same)[0]["4 right probable at shifts 2 and 4"] is False


def test_the_tool_will_not_run_on_any_other_data(tmp_path, monkeypatch):
    monkeypatch.setattr(shift_tool, "DATA_FILE", tmp_path / "gone.zip")
    with pytest.raises(SystemExit, match="is not in"):
        shift_tool.locked()
    other = tmp_path / "other.zip"
    other.write_text("other data", encoding="utf-8")
    monkeypatch.setattr(shift_tool, "DATA_FILE", other)
    with pytest.raises(SystemExit, match="not the one"):
        shift_tool.locked()
    monkeypatch.setattr(shift_tool, "DATA_SHA256", "")
    with pytest.raises(SystemExit, match="not filled in"):
        shift_tool.locked()


def test_the_table_layout_is_read_into_pairs():
    text = "IDE,Polymer,Technic,Sample,BR,RST,Data(x),Data(Y),Data(x),Data(Y)\nPETFTIR001,PET,FTIR,1,32,4,400.0,88.0,401.0,89.5\n"
    item, = shift_tool.read_table(io.BytesIO(text.encode()), "c4")
    assert (item.key, item.polymer, item.truth) == ("PETFTIR001-c4", "PET", "PET")
    assert item.wn.tolist() == [400.0, 401.0] and item.y.tolist() == [88.0, 89.5]


def test_both_kinds_of_polyethylene_count_as_the_librarys_material(library):
    assert shift_tool.TRUTH["HDPE"] == shift_tool.TRUTH["LDPE"] == library.group_of("PE (high density)")
    assert set(shift_tool.TRUTH.values()) <= {library.group_of(name) for name in library.spectra}


def test_the_applied_direction_is_fixed_by_the_spectrum():
    assert shift_tool.direction("PET1") == shift_tool.direction("PET1")
    assert {shift_tool.direction(f"PET{i}") for i in range(40)} == {-1, 1}


def test_the_report_is_built_from_a_results_file(tmp_path):
    counts = {"spectra": 100, "right": 40, "not_right": 1, "false": 0}
    part = {search: {shift: counts for shift in ("0", "2", "4")} for search in ("today", "tolerant")}
    results = {"protocol": "protocol", "locked_commit": "abc", "ran_at_commit": "abc", "ran_on": "today", "spectra": 100,
               "shifts_tried": [-8, 8], "passed": False, "overall": part,
               "rules": {"1 false probable": True, "2 not right probable": True, "3 right probable at shift 0": True,
                         "4 right probable at shifts 2 and 4": False},
               "per_material": {"PET": part}, "per_resolution": {"c4": part, "c8": part}}
    source = tmp_path / "results.json"
    source.write_text(json.dumps(results), encoding="utf-8")
    page = shift_tool.build(source, tmp_path / "report.html").read_text(encoding="utf-8")
    assert "stays switched off" in page and "Failed" in page and "40 of 100 (40.0%)" in page


def test_one_spectrum_gets_all_three_measures(library):
    spectrum = read_spectra(config.EXAMPLES_DIR / "01_wipe_area_particle_ATR.csv")[0]
    item = shift_tool.Item("demo", "PET", "c4", spectrum.wn, 100 * 10 ** (-absorbance(spectrum)))
    without = shift_tool.without_material(library, "PET")
    done = shift_tool.answers(item, library, without, config.SHIFT_TEST)
    assert set(done) == set(shift_tool.SHIFTS) and done[0][0] and not done[0][1]
    assert done[2][2] is False and done[4][2] is False                           # false probable: at shift 0 only


def test_a_material_can_be_left_out_of_the_library(library):
    smaller = shift_tool.without_material(library, library.group_of("PET"))
    assert "PET" not in smaller.spectra and len(smaller) < len(library)
