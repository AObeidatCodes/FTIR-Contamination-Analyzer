"""The Trends logic and its log. Read-only on the records: no verdict or audit log row is ever changed."""

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from ftir_analyzer import config
from ftir_analyzer.analysis import NO_MATCH, PROBABLE, WEAK
from ftir_analyzer.records import TOOL_LOG_COLUMNS, append_tool_log, tidy_tool
from ftir_analyzer.trends import (NO_MATCH_NAME, NOT_RECORDED, Sample, demo_samples, in_period, known_tools, ranked,
                                  read_samples, read_tools, repeats)

DAY = date(2026, 3, 1)
AUDIT_HEADER = "run_at,run_by,program,code_sha256,library_sha256,file,file_sha256,sample,mode,verdict,match,r,flags\n"


def audit_row(when, sha, sample, verdict, match):
    return f"{when}T10:00:00+00:00,me,p,c,l,{sample}.csv,{sha},{sample},ATR,{verdict},{match},0.9,\n"


def write_audit(path, rows):
    path.write_text(AUDIT_HEADER + "".join(audit_row(*row) for row in rows), encoding="utf-8")
    return path


def spectrum(sha, name):
    return SimpleNamespace(name=name, spectrum=SimpleNamespace(sha256=sha, path=Path(f"{name}.csv")))


def sample(day=0, material="PET", tool="Etch 3", verdict=PROBABLE, name=None):
    return Sample("sha", name or f"s{day}", DAY + timedelta(days=day), verdict, material, tool)


def test_a_sample_exported_twice_counts_once_with_its_first_day_and_latest_result(tmp_path):
    log = write_audit(tmp_path / "audit.csv", [("2026-03-01", "aa", "one", WEAK, "PET"), ("2026-03-09", "aa", "one", PROBABLE, "PBT")])
    found = read_samples(log, tmp_path / "none.csv")
    assert len(found) == 1
    assert found[0].day == date(2026, 3, 1) and found[0].verdict == PROBABLE and found[0].material == "PBT"


def test_two_spectra_in_one_file_are_two_samples(tmp_path):
    log = write_audit(tmp_path / "audit.csv", [("2026-03-01", "aa", "one", PROBABLE, "PE"), ("2026-03-01", "aa", "two", PROBABLE, "PP")])
    assert [s.material for s in read_samples(log, tmp_path / "none.csv")] == ["PE", "PP"]


def test_no_reliable_match_is_named_and_a_sample_without_a_tool_says_so(tmp_path):
    log = write_audit(tmp_path / "audit.csv", [("2026-03-01", "aa", "one", NO_MATCH, "-")])
    found = read_samples(log, tmp_path / "none.csv")[0]
    assert found.material == NO_MATCH_NAME and found.tool == NOT_RECORDED


def test_a_row_without_a_date_is_left_out_and_missing_logs_are_empty(tmp_path):
    log = write_audit(tmp_path / "audit.csv", [("bad date", "aa", "one", PROBABLE, "PE")])
    assert read_samples(log, tmp_path / "none.csv") == []
    assert read_samples(tmp_path / "missing.csv", tmp_path / "none.csv") == []
    assert known_tools(tmp_path / "none.csv") == []


def test_the_tool_log_only_grows_and_the_latest_row_counts(tmp_path):
    path = tmp_path / "tool_log.csv"
    append_tool_log([spectrum("aa", "one")], "  Etch   3 ", path)
    first = path.read_text(encoding="utf-8")
    append_tool_log([spectrum("aa", "one")], "CMP 1", path)
    assert path.read_text(encoding="utf-8").startswith(first)
    assert read_tools(path) == {("aa", "one"): "CMP 1"}
    assert ",".join(TOOL_LOG_COLUMNS) in first


def test_no_tool_means_no_row(tmp_path):
    path = tmp_path / "tool_log.csv"
    assert append_tool_log([spectrum("aa", "one")], "   ", path) is None
    assert not path.exists()


def test_a_tool_written_two_ways_is_one_tool(tmp_path):
    log = write_audit(tmp_path / "audit.csv", [("2026-03-01", "aa", "one", PROBABLE, "PE"), ("2026-03-02", "bb", "two", PROBABLE, "PE")])
    tools = tmp_path / "tool_log.csv"
    append_tool_log([spectrum("aa", "one")], "etch 3", tools)
    append_tool_log([spectrum("bb", "two")], "Etch 3", tools)
    assert {s.tool for s in read_samples(log, tools)} == {"Etch 3"}
    assert known_tools(tools) == ["Etch 3"]


def test_a_tidy_tool_name():
    assert tidy_tool("  Wet   bench 2\n") == "Wet bench 2"


def test_the_period_counts_back_from_today():
    samples = [sample(0), sample(29), sample(30)]
    assert len(in_period(samples, 30, DAY + timedelta(days=30))) == 2      # days 1 to 30
    assert len(in_period(samples, 0, DAY)) == 3


def test_the_ranking_is_most_common_first_with_a_running_total():
    samples = [sample(1, "PE"), sample(2, "PE", verdict=WEAK), sample(3, "PP"), sample(4, NO_MATCH_NAME, verdict=NO_MATCH)]
    rows = ranked(samples, "material")
    assert [r.name for r in rows] == ["PE", "PP", NO_MATCH_NAME]
    assert (rows[0].probable, rows[0].weak, rows[0].total) == (1, 1, 2)
    assert [r.running for r in rows] == [0.5, 0.75, 1.0]


def test_samples_with_no_name_stay_last_even_when_they_are_the_most():
    samples = [sample(i, tool=NOT_RECORDED) for i in range(3)] + [sample(9, tool="Etch 3")]
    assert [r.name for r in ranked(samples, "tool")] == ["Etch 3", NOT_RECORDED]


def test_a_repeat_needs_enough_samples_within_the_days():
    assert repeats([sample(0), sample(10), sample(29)], 3, 30)[0].samples == 3      # 30 days: day 0 to day 29
    assert repeats([sample(0), sample(10), sample(30)], 3, 30) == []
    assert repeats([sample(0), sample(10)], 3, 30) == []


def test_a_repeat_gives_its_fullest_stretch():
    found = repeats([sample(0), sample(40), sample(41), sample(42), sample(43)], 3, 30)[0]
    assert (found.samples, found.first, found.last) == (4, DAY + timedelta(days=40), DAY + timedelta(days=43))


def test_a_repeat_is_one_material_on_one_tool():
    assert repeats([sample(0), sample(1, tool="CMP 1"), sample(2, "PE")], 3, 30) == []


@pytest.mark.parametrize("extra", [{"tool": NOT_RECORDED}, {"material": "PET or PBT", "verdict": WEAK},
                                   {"material": NO_MATCH_NAME, "verdict": NO_MATCH}])
def test_what_cannot_make_a_repeat(extra):
    assert repeats([sample(i, **{"material": "PET", **extra}) for i in range(5)], 3, 30) == []


def test_weak_answers_naming_one_material_count_towards_a_repeat():
    assert repeats([sample(i, verdict=WEAK) for i in range(3)], 3, 30)[0].samples == 3


def test_the_demo_is_marked_made_up_and_never_ages():
    today = date(2031, 6, 1)
    found = demo_samples(today=today)
    assert found and found[-1].day == today
    assert all(s.sha.startswith("demo") for s in found)
    for name in ("audit_log.csv", "tool_log.csv", "unknown_fingerprints.csv"):
        assert (config.TRENDS_DEMO_DIR / name).read_text(encoding="utf-8").startswith("# Demo data")
    assert repeats(in_period(found, 90, today), config.REPEAT_COUNT, config.REPEAT_DAYS)
