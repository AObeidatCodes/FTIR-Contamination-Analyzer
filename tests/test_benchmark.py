"""The benchmark's rules (benchmark/PROTOCOL.md). None of this needs the data files."""

import numpy as np
import pytest

from benchmark import run, scoring, sets, stress
from benchmark.sets import IN, OUT, PA_OTHER, RELATIVE
from ftir_analyzer.analysis import NO_MATCH, PROBABLE, WEAK


@pytest.mark.parametrize("label, expected", [
    ("nylon 6,6 - poly(hexamethylene adipamide) nylon6,6-fragment", True),
    ("polyamides pa66 polyamides", True),
    ("Nylon (6,6) GF", True),
    ("polyamides pa6/pa66 polyamides", False),
    ("nylon 6 - poly(caprolactam) pa6 polyamides", False),
    ("Nylon (6) GF", False),
    ("nylon 11 - poly(11-aminoundecanoic acid)", False),
    ("polyamides mffrc066_nylon polyamides", False),
    ("nylon polyamides", False),
])
def test_only_a_label_that_says_6_6_is_the_library_nylon(label, expected):
    assert sets.says_nylon_66(label) is expected


def test_an_aramid_is_not_a_polyamide_here():
    assert sets.open_specy_truth("poly(p-phenylene terephthalamide) (Kevlar) aramid_ref polyamides") == "aramid"
    assert sets.open_specy_truth("nylon polyamides") == PA_OTHER
    assert sets.kind_of(PA_OTHER) == (RELATIVE, "PA")
    assert sets.kind_of("aramid") == (OUT, "")


def test_a_material_the_protocol_does_not_name_stops_the_run():
    with pytest.raises(ValueError):
        sets.kind_of("PK")
    with pytest.raises(ValueError):
        sets.fibre_truth("Glass", "")


def test_fibres_follow_the_protocol_table():
    assert sets.fibre_truth("Polyamide", "PA 6,6") == ("PA", IN, "")
    assert sets.fibre_truth("Polyamide", "PA 6") == (PA_OTHER, RELATIVE, "PA")
    assert sets.fibre_truth("Modacrylic", "PAN/VBr")[1:] == (RELATIVE, "PAN")
    assert sets.fibre_truth("Regenerated cellulose", "Lyocell") == ("cellulose", OUT, "")
    assert sets.fibre_truth("Protein", "Silk") == ("protein", OUT, "")


@pytest.mark.parametrize("label, expected", [
    ("polyethylene glycol", True),
    ("polyethylene wax", True),
    ("polypropylene copolymer", True),
    ("polyethylene", False),
    ("polyacrylonitrile", False),                # only NITRILE inside the name
    ("ethylene vinyl acetate copolymer", False), # a copolymer by nature
    ("cellulose acetate", False),
    ("polyethylene and polypropylene", True),
])
def test_doubtful_labels(label, expected):
    assert sets.is_doubtful(label) is expected


def _items(sizes, truth="PE"):
    """Items in clusters of the given sizes; the spectra are not used."""
    empty = np.zeros(1)
    return [sets.Item(f"{i}-{j}", sets.OPEN_SPECY, truth, IN, "", f"source {i}", "", "", False, "ATR", "A", empty, empty)
            for i, size in enumerate(sizes) for j in range(size)]


def test_the_locked_set_keeps_clusters_whole_and_stays_under_its_share():
    done = sets.split_locked(_items([1] * 40 + [5, 9, 3]))
    sides = {}
    for item in done:
        sides.setdefault(item.cluster, set()).add(item.locked)
    assert all(len(side) == 1 for side in sides.values())
    locked = sum(item.locked for item in done)
    assert 0 < locked <= 0.30 * len(done)


def test_the_locked_set_never_changes_and_does_not_swallow_a_material():
    first = [i.locked for i in sets.split_locked(_items([3] * 20))]
    assert first == [i.locked for i in sets.split_locked(_items([3] * 20))]
    assert not any(i.locked for i in sets.split_locked(_items([12])))


def test_analyse_never_sees_a_gap_in_a_spectrum():
    wn, y = sets.measured_points([800.0, 806.0, 812.0, 818.0], [0.1, np.nan, 0.3, np.inf])
    assert wn.tolist() == [800.0, 812.0] and y.tolist() == [0.1, 0.3]


def test_a_locked_spectrum_cannot_be_scored():
    locked = sets.split_locked(_items([1] * 20))
    with pytest.raises(ValueError, match="locked"):
        run.answer_of(next(i for i in locked if i.locked), None)


@pytest.mark.parametrize("kind, verdict, named, truth, relative, expected", [
    (IN, PROBABLE, "PET", "PET", "", scoring.RIGHT),
    (IN, PROBABLE, "PBT", "PET", "", scoring.RIGHT_FAMILY),
    (IN, PROBABLE, "PP", "PET", "", scoring.WRONG),
    (IN, WEAK, "PET", "PET", "", scoring.NO_ANSWER),
    (IN, NO_MATCH, "PET", "PET", "", scoring.NO_ANSWER),
    (OUT, PROBABLE, "PS", "SAN", "", scoring.FALSE_PROBABLE),     # a relative is still a false probable
    (OUT, WEAK, "PS", "SAN", "", scoring.HELD_BACK),
    (OUT, NO_MATCH, "PS", "SAN", "", scoring.HELD_BACK),
    (RELATIVE, PROBABLE, "PA", PA_OTHER, "PA", scoring.RELATIVE_NAMED),
    (RELATIVE, PROBABLE, "PET", PA_OTHER, "PA", scoring.WRONG),
    (RELATIVE, WEAK, "PA", PA_OTHER, "PA", scoring.NO_ANSWER),
])
def test_the_buckets(kind, verdict, named, truth, relative, expected):
    assert scoring.bucket(kind, verdict, named, truth, relative) == expected


def test_wilson_matches_worked_values():
    low, high = scoring.wilson(0, 70)
    assert low == 0 and high == pytest.approx(3.8415 / 73.8415, abs=0.0001)     # z² / (n + z²)
    low, high = scoring.wilson(10, 100)
    assert (low, high) == (pytest.approx(0.0552, abs=0.0005), pytest.approx(0.1744, abs=0.0005))
    assert scoring.wilson(0, 0) == (0.0, 1.0)


def test_clusters_widen_the_margin_when_failures_share_a_source():
    hits = np.array([1] * 30 + [0] * 270)
    together = np.array(["a"] * 30 + [f"c{i // 30}" for i in range(270)])
    alone = np.arange(300).astype(str)
    assert scoring.margin(hits, together, sets.FIBRES) == scoring.wilson(30, 300)
    wide = scoring.margin(hits, together, sets.OPEN_SPECY)
    narrow = scoring.cluster_interval(hits, alone)
    assert wide[1] - wide[0] > narrow[1] - narrow[0]
    assert wide[1] > scoring.wilson(30, 300)[1]


def test_the_margin_never_collapses_at_zero_failures():
    low, high = scoring.margin(np.zeros(50), np.arange(50).astype(str), sets.OPEN_SPECY)
    assert low == 0 and high > 0.05


def test_the_lead_rule_is_only_the_score_when_taken_out():
    assert scoring.without_lead(0.95) and not scoring.without_lead(0.9499)


WN = np.arange(800.0, 3200.0, 2.0)
BAND = np.exp(-((WN - 1700) / 20) ** 2)


@pytest.mark.parametrize("test", list(stress.LEVELS))
def test_stress_changes_a_copy_and_repeats_exactly(test):
    level = stress.LEVELS[test][1]
    before = BAND.copy()
    wn_one, a_one = stress.perturb(WN, BAND, test, level, "sample")
    wn_two, a_two = stress.perturb(WN, BAND, test, level, "sample")
    assert np.array_equal(BAND, before)
    assert np.array_equal(a_one, a_two) and np.array_equal(wn_one, wn_two)
    assert not np.array_equal(wn_one, WN) or not np.array_equal(a_one, BAND)


def test_stress_is_the_size_the_protocol_says():
    assert np.std(stress.perturb(WN, BAND, stress.NOISE, 0.02)[1] - BAND) == pytest.approx(0.02, rel=0.1)
    assert np.max(np.abs(stress.perturb(WN, BAND, stress.DRIFT, 0.25)[1] - BAND)) == pytest.approx(0.25)
    assert abs(stress.perturb(WN, BAND, stress.SHIFT, 4)[0][0] - WN[0]) == 4


def test_lower_resolution_widens_a_band_and_keeps_a_hole():
    wn = np.concatenate((np.arange(800.0, 2196.0, 6.0), np.arange(2424.0, 3198.0, 6.0)))
    a = np.exp(-((wn - 1700) / 12) ** 2)
    blurred_wn, blurred = stress.perturb(wn, a, stress.BLUR, 32)
    assert np.max(blurred) < np.max(a)
    assert np.median(np.diff(blurred_wn)) == 16
    assert not np.any((blurred_wn > 2200) & (blurred_wn < 2420))


def test_the_tool_stops_on_a_changed_data_file(tmp_path):
    for name in run.FILES:
        (tmp_path / name).write_text("not the file")
    with pytest.raises(SystemExit, match="not the file the protocol names"):
        run.check_data(tmp_path)


def test_the_committed_outcomes_keep_labels_only_for_failures():
    import pandas as pd
    rows = pd.DataFrame([{"id": "a", "dataset": "x", "truth": "PE", "kind": IN, "contributor": "c", "doubtful": False,
                          "replica": 1, "verdict": PROBABLE, "best_material": name, "r": 0.99, "gap": 0.2, "reading": "ATR",
                          "bucket": bucket, "label": "text"}
                         for name, bucket in (("PE", scoring.RIGHT), ("PP", scoring.WRONG))])
    table = run.to_csv_rows(rows)
    assert table.label.tolist() == ["", "text"]
    assert "wn" not in table.columns and "y" not in table.columns
