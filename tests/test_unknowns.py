"""Unknown groups: samples that look alike. No verdict is read from here, and none is changed."""

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ftir_analyzer import config
from ftir_analyzer.analysis import NO_MATCH, PROBABLE, WEAK
from ftir_analyzer.library import pearson
from ftir_analyzer.processing import GRID, fingerprint
from ftir_analyzer.trends import NO_MATCH_NAME, NOT_RECORDED, Sample
from ftir_analyzer.unknowns import (link_groups, read_fingerprints, save_fingerprints, similarity, unknown_groups,
                                    usable_file)

DAY = date(2026, 3, 1)


def band(*centres):
    return sum(np.exp(-((GRID - c) / 30) ** 2) for c in centres)


def result(sha, name, y, verdict=NO_MATCH, path=None):
    return SimpleNamespace(verdict=verdict, name=name, compared=y,
                           spectrum=SimpleNamespace(sha256=sha, path=Path(path or f"{name}.csv")))


def sample(sha, name, day=0, verdict=NO_MATCH, tool="Etch 3"):
    return Sample(sha, name, DAY + timedelta(days=day), verdict, NO_MATCH_NAME, tool)


def test_the_table_gives_the_same_r_as_the_library_search():
    rng = np.random.default_rng(1)
    prints = [fingerprint(band(1000, 1700) + rng.normal(0, 0.01, GRID.size)), fingerprint(band(1000, 2900)),
              fingerprint(band(3000) + rng.normal(0, 0.01, GRID.size))]
    prints[1][:40] = np.nan                                            # a spectrum that does not cover the whole range
    prints[2][100:140] = np.nan
    table = similarity(prints)
    for a in range(3):
        for b in range(3):
            if a != b:
                assert table[a, b] == pytest.approx(pearson(prints[a], prints[b]), abs=1e-9)


def test_a_flat_or_empty_fingerprint_matches_nothing():
    empty = np.full(GRID.size, np.nan)
    table = similarity([fingerprint(band(1000)), empty, empty])
    assert np.all(table[0, 1:] == 0) and np.all(table[1:, 1:] == 0)


def test_links_join_samples_through_each_other():
    scores = np.array([[1, .96, 0, 0], [.96, 1, .95, 0], [0, .95, 1, 0], [0, 0, 0, 1]])
    assert link_groups(scores, 0.95, 3) == [[0, 1, 2]]
    assert link_groups(scores, 0.97, 2) == []


def test_a_group_needs_enough_samples():
    scores = np.array([[1, .99, 0], [.99, 1, 0], [0, 0, 1]])
    assert link_groups(scores, 0.95, 3) == []
    assert link_groups(scores, 0.95, 2) == [[0, 1]]


def test_only_samples_without_a_probable_verdict_are_saved(tmp_path):
    path = tmp_path / "log.csv"
    save_fingerprints([result("a", "one", band(1000)), result("b", "two", band(1000), PROBABLE), result("c", "three", band(1000), WEAK)], path)
    assert set(read_fingerprints(path)) == {("a", "one"), ("c", "three")}


def test_nothing_to_save_writes_nothing(tmp_path):
    path = tmp_path / "log.csv"
    assert save_fingerprints([result("a", "one", band(1000), PROBABLE)], path) is None
    assert not path.exists()


def test_the_log_only_grows_and_the_latest_row_counts(tmp_path):
    path = tmp_path / "log.csv"
    save_fingerprints([result("a", "one", band(1000), path="old.csv")], path)
    first = path.read_text(encoding="utf-8")
    save_fingerprints([result("a", "one", band(1000), path="new.csv")], path)
    assert path.read_text(encoding="utf-8").startswith(first)
    y, where = read_fingerprints(path)[("a", "one")]
    assert where == "new.csv" and y.size == GRID.size


def test_a_gap_in_a_spectrum_survives_the_log(tmp_path):
    path = tmp_path / "log.csv"
    y = band(1000, 2900)
    y[300:320] = np.nan
    save_fingerprints([result("a", "one", y)], path)
    saved = read_fingerprints(path)[("a", "one")][0]
    assert np.isnan(saved[305]) and np.isfinite(saved[100])


def group_log(path):
    rows = [result(f"s{i}", f"like {i}", band(1000, 1700) + 0.002 * i * band(2900)) for i in range(4)]
    rows += [result("x", "other", band(3000))]
    save_fingerprints(rows, path)
    return [sample(f"s{i}", f"like {i}", i, tool="Etch 3" if i else "CMP 1") for i in range(4)] + [sample("x", "other", 9)]


def test_samples_that_look_alike_become_a_group(tmp_path):
    path = tmp_path / "log.csv"
    samples = group_log(path)
    groups, missing = unknown_groups(samples, read_fingerprints(path))
    assert len(groups) == 1 and missing == 0
    group = groups[0]
    assert {s.name for s in group.samples} == {f"like {i}" for i in range(4)}
    assert group.tools == ["CMP 1", "Etch 3"]
    assert (group.first, group.last) == (DAY, DAY + timedelta(days=3))
    assert group.typical in group.samples


def test_a_probable_sample_never_joins_a_group(tmp_path):
    path = tmp_path / "log.csv"
    samples = group_log(path)
    samples[0] = sample("s0", "like 0", 0, PROBABLE)
    samples[1] = sample("s1", "like 1", 1, PROBABLE)
    groups, _ = unknown_groups(samples, read_fingerprints(path))
    assert groups == []


def test_older_samples_without_a_fingerprint_are_counted(tmp_path):
    path = tmp_path / "log.csv"
    samples = group_log(path) + [sample("old", "old one", 2)]
    assert unknown_groups(samples, read_fingerprints(path))[1] == 1
    assert unknown_groups(samples, read_fingerprints(tmp_path / "missing.csv")) == ([], 6)


def test_a_group_without_tools_says_so(tmp_path):
    path = tmp_path / "log.csv"
    samples = [sample(s.sha, s.name, tool=NOT_RECORDED) for s in group_log(path)]
    assert unknown_groups(samples, read_fingerprints(path))[0][0].tools == []


def test_the_file_is_only_offered_if_it_is_still_the_same_file(tmp_path):
    path = tmp_path / "log.csv"
    file = tmp_path / "like.csv"
    file.write_bytes((config.EXAMPLES_DIR / "01_wipe_area_particle_ATR.csv").read_bytes())
    from ftir_analyzer.spectrum_io import checksum
    save_fingerprints([result(checksum(file), f"like {i}", band(1000, 1700), path=file) for i in range(3)], path)
    samples = [sample(checksum(file), f"like {i}", i) for i in range(3)]
    group = unknown_groups(samples, read_fingerprints(path))[0][0]
    assert usable_file(group) == file
    file.write_text("changed", encoding="utf-8")
    assert usable_file(group) is None
