"""
FTIR Contamination Analyzer - tests of the Open Specy references (extended mode)

The test file tests/data/openspecy_sample.rds has the structure of an Open Specy library
file (wavenumber, spectra, metadata). Its spectra are OpenFTIR spectra (MIT), labelled the
way Open Specy labels its own, with one Raman spectrum and one soil spectrum among them.

Checked: only fab-relevant FTIR spectra are kept; a spectrum that could be confused with a
different material is left out (and reported); the extended library passes the impostor
test; a second reference of the SAME material does not weaken a verdict; the 'derivative'
library is refused; the download finds the 'nobaseline' library (AWS first, then OSF); an
untidy library file (names with '#', wavenumbers high -> low, empty or short spectra,
missing metadata rows) is imported without stopping, and every odd spectrum is counted;
a file laid out like Open Specy's current one (one library per kind of spectrum, FTIR /
Raman / NIR, with R classes, and the FTIR range cut to 800-2200 + 2420-3200) is read, its
FTIR part is used, and no data is made up across the cut-out region; references measured
in transmission are put into the library's ATR look, as samples are.

Author : Ali Obeidat
Version: 1.1.0
License: MIT (see LICENSE)
"""

import io
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ftir_analyzer import config
from ftir_analyzer.analysis import PROBABLE, WEAK, analyse, decide
from ftir_analyzer.evidence import fab_sources
from ftir_analyzer.library import impostor_test, load_library, material_group
from ftir_analyzer.processing import GRID, fingerprint, on_grid
from ftir_analyzer.spectrum_io import read_spectra

pytest.importorskip("rdata")
from ftir_analyzer.openspecy import (AWS_LIBRARY, OpenSpecyLibrary, choose_file, curate, download,  # noqa: E402
                                     download_and_import, import_library, list_osf_files, prepare,
                                     read_library_file)

FIXTURE = Path(__file__).parent / "data" / "openspecy_sample.rds"


@pytest.fixture
def base(tmp_path):
    return load_library(inhouse_dir=tmp_path / "inhouse")


def test_material_groups():
    assert material_group("PE (high density)") == "PE" and material_group("PET Biaxial Film") == "PET"
    assert material_group("POLY(ETHYLENE)") == "PE" and material_group("Nylon 6,6") == "PA"
    assert material_group("POLY(DIMETHYLSILOXANE) (PDMS)") == "silicone"
    assert material_group("something else") == ""


def test_only_fab_relevant_ftir_spectra_are_kept():
    wn, X, metadata = read_library_file(FIXTURE)
    assert X.shape == (len(wn), 10)
    entries, skipped = prepare(wn, X, metadata)
    assert skipped["Raman"] == 1 and skipped["not likely in a fab"] == 1          # the PET Raman and the soil
    assert len(entries) == 8 and all(e["name"].endswith("(Open Specy)") for e in entries)


def test_confusable_spectra_are_left_out(base):
    entries, _ = prepare(*read_library_file(FIXTURE))
    kept, dropped = curate(base, entries)
    confused = {name: other for name, other, r in dropped}
    assert confused == {"acrylic coating (Open Specy)": "PMMA", "polyolefin pellet (Open Specy)": "PP"}
    assert all(r >= config.PROBABLE_R for _, _, r in dropped)
    assert len(kept) == 6


def test_import_gives_a_valid_extended_library(base, tmp_path):
    folder = tmp_path / "openspecy"
    summary = import_library(FIXTURE, base, folder)
    assert summary.kept == 6 and "confused" in summary.text()
    assert (folder / "import_report.txt").exists()
    extended = load_library(inhouse_dir=tmp_path / "inhouse", extended=True, openspecy_dir=folder)
    assert len(extended) == 22 and "6 Open Specy" in extended.name and len(extended.open_specy) == 6
    assert impostor_test(extended).passed
    pe = "Poly(ethylene) (Open Specy)"
    assert extended.group_of(pe) == "PE" and extended.info_of(pe).licence == "CC BY 4.0"
    assert extended.info_of(pe).category == "Packaging"                       # the shipped PE's category
    assert fab_sources(pe, extended) == fab_sources("PE (high density)", extended)
    shipped_only = load_library(inhouse_dir=tmp_path / "inhouse", extended=False, openspecy_dir=folder)
    assert len(shipped_only) == 16


def test_a_second_reference_of_the_same_material_does_not_weaken_the_verdict(base, tmp_path):
    folder = tmp_path / "openspecy"
    import_library(FIXTURE, base, folder)
    extended = load_library(inhouse_dir=tmp_path / "inhouse", extended=True, openspecy_dir=folder)
    result = analyse(read_spectra(config.EXAMPLES_DIR / "02_wafer_box_particle_ATR.csv")[0], extended, "ATR")
    assert result.verdict == PROBABLE and extended.group_of(result.match) == "PE"
    assert extended.group_of(result.runner_up) != "PE" and result.gap >= config.MIN_GAP
    # the rule itself: the lead is measured to the next DIFFERENT material
    ranking = [("PE a", 0.97), ("PE b", 0.96), ("PP", 0.60)]
    assert decide(ranking, rival=2) == (PROBABLE, "PE a") and decide(ranking, rival=1)[0] == WEAK


def test_the_derivative_library_is_refused(tmp_path):
    copy = tmp_path / "derivative.rds"
    copy.write_bytes(FIXTURE.read_bytes())
    with pytest.raises(ValueError, match="nobaseline"):
        read_library_file(copy)


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_download_finds_the_nobaseline_library(tmp_path):
    root = {"data": [{"attributes": {"kind": "file", "name": "derivative.rds", "size": 10},
                      "links": {"download": "https://osf.example/derivative"}},
                     {"attributes": {"kind": "folder", "name": "medoids"},
                      "relationships": {"files": {"links": {"related": {"href": "https://api.example/medoids"}}}}}],
            "links": {"next": None}}
    folder = {"data": [{"attributes": {"kind": "file", "name": "mediod_nobaseline.rds", "size": 4},
                        "links": {"download": "https://osf.example/mediod_nobaseline"}}], "links": {}}
    payload = FIXTURE.read_bytes()

    def opener(url, timeout=0):
        if url.startswith("https://api.osf.io/") and "x7dpz" in url:
            return FakeResponse(json.dumps(root).encode())
        if url == "https://api.example/medoids":
            return FakeResponse(json.dumps(folder).encode())
        if url == "https://osf.example/mediod_nobaseline":
            return FakeResponse(payload, {"Content-Length": str(len(payload))})
        raise AssertionError(url)

    files = list_osf_files(opener=opener)
    name, _, link = choose_file(files)
    assert name == "mediod_nobaseline.rds"                                    # not the derivative library
    steps = []
    target = download(link, tmp_path / name, lambda *a: steps.append(a), opener)
    assert target.read_bytes() == payload and steps
    with pytest.raises(FileNotFoundError):
        choose_file([("derivative.rds", 1, "x")])


def test_names_with_a_hash_survive_saving_and_loading(base, tmp_path):
    """A '#' in a name once cut the saved table short: every Open Specy reference became empty."""
    entries, _ = prepare(*read_library_file(FIXTURE))
    kept, _ = curate(base, entries)
    kept[0]["name"] = "Nylon 6 #2 (Open Specy)"
    kept[1]["original_name"] = "sample #7, from a glove box"
    folder = tmp_path / "openspecy"
    from ftir_analyzer.openspecy import ImportSummary
    OpenSpecyLibrary(folder).save(kept, ImportSummary("test", len(kept)))
    extended = load_library(inhouse_dir=tmp_path / "inhouse", extended=True, openspecy_dir=folder)
    assert len(extended.open_specy) == 6 and "Nylon 6 #2 (Open Specy)" in extended.spectra
    assert extended.info_of(kept[1]["name"]).original_name == "sample #7, from a glove box"
    assert impostor_test(extended).passed


def untidy_library(path):
    """The test library made untidy the way a big real library can be."""
    import rdata
    wn, X, metadata = read_library_file(FIXTURE)
    columns = {f"s{i}": X[:, i] for i in range(X.shape[1])}
    columns["empty"] = np.full(len(wn), np.nan)                        # no data at all
    short = np.full(len(wn), np.nan)
    short[100:130] = np.linspace(0, 1, 30)
    columns["short"] = short                                            # 30 points only
    columns["flat"] = np.ones(len(wn))                                  # no shape at all
    spectra = pd.DataFrame(columns).iloc[::-1].reset_index(drop=True)  # wavenumbers high -> low
    rows = metadata.to_dict("records")
    rows[3]["spectrum_identity"] = "Nylon #6 fibre"                     # a '#' in a name
    rows += [{"spectrum_type": "ftir", "spectrum_identity": "PE film #1", "polymer": "POLYETHYLENE",
              "material_class": "polyolefins (polyalkenes)"}] * 2      # the last spectrum has no row at all
    obj = {"wavenumber": wn[::-1], "spectra": spectra, "metadata": pd.DataFrame(rows)}
    rdata.write_rds(path, obj, compression="gzip")
    return path


def test_an_untidy_library_file_is_imported_without_stopping(base, tmp_path):
    folder = tmp_path / "openspecy"
    summary = import_library(untidy_library(tmp_path / "medoid_nobaseline.rds"), base, folder)
    assert summary.kept >= 6
    assert summary.skipped["too little data"] + summary.skipped["not likely in a fab"] >= 3
    wn, X, _ = read_library_file(tmp_path / "medoid_nobaseline.rds")
    assert np.all(np.diff(wn) > 0)                                      # low -> high after reading
    extended = load_library(inhouse_dir=tmp_path / "inhouse", extended=True, openspecy_dir=folder)
    assert impostor_test(extended).passed
    assert all(np.isfinite(y).sum() >= 200 for y in extended.spectra.values())


def test_the_download_tries_aws_first_then_osf(base, tmp_path):
    payload, asked = FIXTURE.read_bytes(), []

    def opener(url, timeout=0):
        asked.append(url)
        if url == AWS_LIBRARY:
            return FakeResponse(b"<html>blocked</html>")                 # a web page, not a library
        if url.startswith("https://api.osf.io/"):
            return FakeResponse(json.dumps({"data": [{"attributes": {"kind": "file", "name": "mediod_nobaseline.rds"},
                                                      "links": {"download": "https://osf.example/m"}}]}).encode())
        if url == "https://osf.example/m":
            return FakeResponse(payload, {"Content-Length": str(len(payload))})
        raise AssertionError(url)

    summary = download_and_import(base, tmp_path / "openspecy", opener=opener)
    assert asked[0] == AWS_LIBRARY and summary.kept == 6

    def offline(url, timeout=0):
        raise OSError("no internet")

    with pytest.raises(ConnectionError, match="Import a library file"):
        download_and_import(base, tmp_path / "other", opener=offline)


class RClassed:
    """A value R keeps with a class: an Open Specy object (a list) or a data.table."""

    def __init__(self, value, *classes):
        self.value, self.classes = value, classes


def classed_to_r(data, converter):
    """How rdata writes an RClassed: the list or table, with its R class."""
    from rdata.conversion.to_r import build_r_object
    from rdata.missing import R_INT_NA
    from rdata.parser import RObjectType
    value = data.value
    table = isinstance(value, pd.DataFrame)
    columns = [value[c].to_numpy() for c in value.columns] if table else list(value.values())
    attributes = {"names": np.array([str(c) for c in (value.columns if table else value)]),
                  "class": np.array(data.classes)}
    if table:
        attributes["row.names"] = np.ma.array([R_INT_NA, -len(value)], mask=[True, False])
    return build_r_object(RObjectType.VEC, value=[converter.convert_to_r_object(c) for c in columns],
                          is_object=True, attributes=converter.convert_to_r_attributes(attributes))


def open_specy_object(wn, spectra, metadata):
    data_table = ("data.table", "data.frame")
    return RClassed({"wavenumber": wn, "spectra": RClassed(spectra, *data_table),
                     "metadata": RClassed(metadata, *data_table)}, "OpenSpecy", "list")


def typed_library(path, kinds=("ftir", "raman", "nir"), transmission=()):
    """The test library laid out like Open Specy's current files: {ftir, raman, nir}."""
    import rdata
    from rdata.conversion.to_r import DEFAULT_CLASS_MAP
    wn, X, metadata = read_library_file(FIXTURE)
    ftir = np.concatenate([np.arange(800.0, 2201.0, 2.0), np.arange(2420.0, 3201.0, 2.0)])   # CO2 cut out
    spectra = pd.DataFrame({f"os{i:03d}": np.interp(ftir, wn, X[:, i]) for i in range(X.shape[1])})
    spectra.iloc[40:43, 2] = np.nan                                     # a few points missing, as in a medoid
    how = ["ATR"] * len(metadata)
    for i in transmission:                                              # these as measured in transmission
        spectra.iloc[:, i] *= ftir / config.REFERENCE_WN
        how[i] = "Transmission"
    rows = pd.DataFrame({"spectrum_id": metadata["sample_name"].astype(str),
                         "spectrum_type": metadata["spectrum_type"].str.lower().astype(str),
                         "spectrum_identity": metadata["spectrum_identity"].astype(str),
                         "material": metadata["polymer"].fillna("").astype(str),
                         "material_class": metadata["material_class"].astype(str),
                         "library_name": metadata["organization"].fillna("").astype(str),
                         "instrument_mode": how})
    raman = np.arange(200.0, 3201.0, 4.0)
    bundle = {"ftir": open_specy_object(ftir, spectra, rows),
              "raman": open_specy_object(raman, pd.DataFrame({"r1": np.sin(raman / 90.0)}),
                                         pd.DataFrame({"spectrum_type": ["raman"]})),
              "nir": open_specy_object(np.arange(4000.0, 12001.0, 8.0), pd.DataFrame({"n1": np.ones(1001)}),
                                       pd.DataFrame({"spectrum_type": ["nir"]}))}
    bundle = {k: v for k, v in bundle.items() if k in kinds}
    rdata.write_rds(path, bundle, compression="gzip", constructor_dict={**DEFAULT_CLASS_MAP, RClassed: classed_to_r})
    return path


def test_the_current_open_specy_file_is_read_and_its_ftir_part_used(base, tmp_path):
    path = typed_library(tmp_path / "medoid_nobaseline.rds")
    with warnings.catch_warnings():
        warnings.simplefilter("error")                                  # reading it is quiet
        wn, X, metadata = read_library_file(path)
    assert X.shape == (len(wn), 10) and wn.min() == 800 and wn.max() == 3200
    folder = tmp_path / "openspecy"
    summary = import_library(path, base, folder)
    assert summary.kept >= 5 and summary.skipped["not likely in a fab"] == 1   # the soil
    extended = load_library(inhouse_dir=tmp_path / "inhouse", extended=True, openspecy_dir=folder)
    assert len(extended.open_specy) == summary.kept and impostor_test(extended).passed
    hole, outside = (GRID > 2200) & (GRID < 2420), (GRID < 800) | (GRID > 3200)
    for name in extended.open_specy:
        y = extended.spectra[name]
        assert np.isnan(y[hole | outside]).all() and np.isfinite(y[~hole & ~outside]).sum() >= 400
    result = analyse(read_spectra(config.EXAMPLES_DIR / "02_wafer_box_particle_ATR.csv")[0], extended, "ATR")
    assert result.verdict == PROBABLE and extended.group_of(result.match) == "PE"


def test_a_file_with_no_ftir_library_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no FTIR"):
        read_library_file(typed_library(tmp_path / "medoid_nobaseline.rds", kinds=("raman", "nir")))


def test_no_data_is_made_up_across_a_cut_out_region():
    wn = np.concatenate([np.arange(800.0, 2201.0, 2.0), np.arange(2420.0, 3201.0, 2.0)])
    y = on_grid(wn, np.cos(wn / 70.0))
    assert np.isnan(y[(GRID > 2200) & (GRID < 2420)]).all() and np.isfinite(y[GRID == 2200]).all()
    d = fingerprint(y)
    left, right = (GRID >= 800) & (GRID <= 2200), (GRID >= 2420) & (GRID <= 3200)
    alone = fingerprint(np.where(left, y, np.nan))                      # each stretch is differentiated on its own
    assert np.corrcoef(d[left], alone[left])[0, 1] > 0.99999 and np.isfinite(d[right]).all()


def test_transmission_references_are_put_into_the_atr_look(base, tmp_path):
    from ftir_analyzer.openspecy import measuring_mode
    assert [measuring_mode(t) for t in ("ATR", "Diamond ATR", "Transmission", "Reflectance", "")] == \
        ["ATR", "ATR", "transmission", "unknown", "unknown"]
    folders = {}
    for label, transmission in (("atr", ()), ("mixed", (0, 2, 6))):     # PE, Nylon 6 and PS by transmission
        (tmp_path / label).mkdir()
        path = typed_library(tmp_path / label / "medoid_nobaseline.rds", transmission=transmission)
        folders[label] = tmp_path / label / "openspecy"
        summary = import_library(path, base, folders[label])
    assert "transmission (put into the ATR look)" in summary.text()
    libraries = {k: load_library(inhouse_dir=tmp_path / "inhouse", extended=True, openspecy_dir=f)
                 for k, f in folders.items()}
    for name in ("Poly(ethylene) (Open Specy)", "Nylon 6 (Open Specy)", "Polystyrene (Open Specy)"):
        a, b = libraries["atr"].spectra[name], libraries["mixed"].spectra[name]
        assert np.allclose(a, b, equal_nan=True, atol=1e-4)            # converted back: the same reference
        assert libraries["mixed"].info_of(name).mode == "transmission"
