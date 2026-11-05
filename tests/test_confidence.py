"""The confidence bar's rules (benchmark/PROTOCOL_CONFIDENCE.md). None of this needs the data files."""

import numpy as np
import pytest

from benchmark import confidence, sets
from benchmark.confidence import AS_MEASURED, NO_BAR, ONE_BAR, bar_of, bars_for, group_of, list_of, measure
from benchmark.sets import IN
from ftir_analyzer.analysis import PROBABLE, WEAK


def test_the_bar_follows_the_exact_rule():
    scores = [i / 100 for i in range(1, 20)]                  # 19 scores: position (19 + 1) x 0.9 = 18, from the top
    assert bar_of(scores) == sorted(scores, reverse=True)[17] == pytest.approx(0.02)
    assert bar_of(list(range(9)) ) == 0                        # 9 scores: position 9, the lowest


def test_too_few_scores_give_no_bar_rather_than_a_false_one():
    assert bar_of([0.9, 0.8, 0.7]) == NO_BAR                  # position 4 of 3
    assert bar_of([]) == NO_BAR


def test_rounding_cannot_move_the_bar_a_place():
    for n in range(9, 400):
        scores = list(range(n))
        position = ((n + 1) * 9 + 9) // 10                     # (n + 1) x 0.9 rounded up, in whole numbers
        assert bar_of(scores) == sorted(scores, reverse=True)[position - 1]


def test_on_exchangeable_data_the_promise_holds():
    rng = np.random.default_rng(1)
    misses = []
    for _ in range(300):
        scores = rng.uniform(0, 1, 501)
        misses.append(scores[-1] >= bar_of(scores[:-1]))
    assert np.mean(misses) == pytest.approx(0.90, abs=0.04)


def test_a_material_is_on_the_list_when_it_clears_the_bar():
    scores = {"PET": 0.93, "PBT": 0.85, "PC": 0.72, "PU": 0.60}
    assert list_of(scores, 0.72) == ["PET", "PBT", "PC"]       # at the bar counts
    assert list_of(scores, 0.99) == []
    assert list_of(scores, NO_BAR) == ["PET", "PBT", "PC", "PU"]


def test_the_groups_depend_on_the_spectrum_alone():
    assert group_of("ATR") == "ATR" and group_of("transmission") == "transmission"
    assert group_of("unknown") == AS_MEASURED


def row(truth, true_r, group="ATR", other=0.2, verdict=WEAK, best=None, cluster="c"):
    return {"truth": truth, "true_r": true_r, "group": group, "cluster": cluster, "verdict": verdict,
            "best": best or truth, "scores": {truth: true_r, "PP" if truth != "PP" else "PE": other}}


def test_each_version_sets_its_own_bars():
    rows = [row("PE", 0.9 - i / 100) for i in range(20)] + [row("PE", 0.5 - i / 100, "transmission") for i in range(20)]
    bars = bars_for(rows)
    assert set(bars["A"]) == {ONE_BAR} and set(bars["B"]) == {"ATR", "transmission"}
    assert bars["B"]["ATR"] > bars["A"][ONE_BAR] > bars["B"]["transmission"]


def test_a_group_with_no_calibration_spectra_gets_no_bar():
    bars = {"A": {ONE_BAR: 0.5}, "B": {"ATR": 0.8}}
    assert confidence.bar_for(row("PE", 0.9, AS_MEASURED), bars, "B") == NO_BAR


def test_coverage_and_list_length_are_counted():
    rows = [row("PE", 0.9, cluster=f"c{i}") for i in range(9)] + [row("PE", 0.1, cluster="last")]
    bars = {"A": {ONE_BAR: 0.5}, "B": {"ATR": 0.5}}
    done = measure(rows, bars, "A", sets.FIBRES)
    assert done["all"]["coverage"]["k"] == 9 and done["all"]["coverage"]["n"] == 10
    assert done["all"]["lengths"]["one"] == 9 and done["all"]["lengths"]["empty"] == 1
    assert done["per_material"]["PE"] == {"n": 10, "hits": 9, "median_list": 1.0}


def test_useful_needs_both_a_kept_promise_and_a_short_list():
    long = [{"PE": 0.9, "PP": 0.8, "PS": 0.8, "PET": 0.8}] * 40
    rows = [dict(row("PE", 0.9, cluster=f"c{i}"), scores=s) for i, s in enumerate(long)]
    assert not measure(rows, {"A": {ONE_BAR: 0.5}, "B": {}}, "A", sets.FIBRES)["all"]["useful"]     # valid, but four long
    rows = [row("PE", 0.2, cluster=f"c{i}") for i in range(40)]
    assert not measure(rows, {"A": {ONE_BAR: 0.5}, "B": {}}, "A", sets.FIBRES)["all"]["useful"]     # short, but it misses
    rows = [row("PE", 0.9, cluster=f"c{i}") for i in range(40)]
    assert measure(rows, {"A": {ONE_BAR: 0.5}, "B": {}}, "A", sets.FIBRES)["all"]["useful"]


def test_a_probable_answer_is_checked_against_the_list():
    rows = [row("PE", 0.97, verdict=PROBABLE, cluster=f"c{i}") for i in range(4)]
    done = measure(rows, {"A": {ONE_BAR: 0.5}, "B": {}}, "A", sets.FIBRES)
    assert done["probable"] == {"n": 4, "on_list": 4, "alone": 4}


def test_an_empty_list_is_counted_for_materials_with_no_reference():
    rows = [{"scores": {"PE": 0.3}, "group": "ATR"}, {"scores": {"PE": 0.8}, "group": "ATR"}]
    assert confidence.on_unknowns(rows, {"A": {ONE_BAR: 0.5}, "B": {}}, "A")["empty"] == 1


def _items(sizes):
    empty = np.zeros(1)
    return [sets.Item(f"{i}-{j}", sets.OPEN_SPECY, "PE", IN, "", f"source {i}", "", "", False, "ATR", "A", empty, empty,
                      locked=True) for i, size in enumerate(sizes) for j in range(size)]


def test_the_halves_keep_clusters_whole_and_are_fixed():
    calibration, test = confidence.split_halves(_items([2] * 30))
    assert not {i.cluster for i in calibration} & {i.cluster for i in test}
    assert len(calibration) + len(test) == 60 and 0 < len(calibration) <= 30
    again, _ = confidence.split_halves(_items([2] * 30))
    assert [i.key for i in again] == [i.key for i in calibration]


def test_the_halves_do_not_repeat_the_first_split():
    items = _items([1] * 200)
    calibration, _ = confidence.split_halves(items)
    first = sets.split_locked([sets.replace(i, locked=False) for i in items], confidence.CALIBRATION_SHARE)
    assert {i.key for i in calibration} != {i.key for i in first if i.locked}


def test_the_tool_stops_on_a_changed_data_file(tmp_path):
    for name, _ in (confidence.FIBRE_FILE, confidence.SPECY_FILE):
        (tmp_path / name).write_text("not the file")
    with pytest.raises(SystemExit, match="not the file the protocol names"):
        confidence.check_data(tmp_path)


def test_the_report_rebuilds_from_the_saved_results_alone(tmp_path):
    from benchmark.confidence_report import build
    page = build(confidence.RESULTS / "confidence_results.json", tmp_path / "report.html").read_text(encoding="utf-8")
    assert "The promise held" in page and "Deviations from the protocol" in page


def test_only_counts_of_the_true_scores_leave_the_tool():
    picture = confidence.histogram([0.1, 0.9, 0.91])
    assert set(picture) == {"edges", "counts"} and sum(picture["counts"]) == 3
