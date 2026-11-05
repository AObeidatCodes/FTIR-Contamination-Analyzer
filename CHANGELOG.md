# Changelog

## 2.0.0 (not yet released)

### Added

- A redesigned desktop app, with light and dark themes, and a guided tour that keeps nothing.
- A report as a PDF, as an interactive web page and as an Excel table.
- 3D models of the materials, with the bonds of a band shown on the model.
- Material families, and where two close materials differ.
- Trends: the most common materials and tools, and repeats of one material on one tool, with where it can come from.
- Unknown groups: samples with no probable verdict that look alike.
- Quality: an instrument check on a polystyrene film with a drift chart, and a second-person review of exported reports.
- Measure again: a mark on a poor spectrum that says what to do.
- Contaminant in a known material: a clean spectrum is taken out, and what is left is searched.
- Open Specy references, imported by the user, each with the licence its source gives.
- A benchmark with pre-committed rules and locked data. See `benchmark/`.

### Changed

- "Library validated" now reads "Library checked". It reports the impostor test and is not a formal validation.
- The CO₂ warning now says "weak or no sample", as real samples with a weak signal can trigger it.
- The demo spectra are part of an installed package.
- `openpyxl`, `jcamp` and `brukeropus` are now installed with the package.

### Not included

- A search that tries small band shifts is in the code and switched off. It failed one rule of its test.
  See `benchmark/results/shift_report.html`.

### Records

New record files, created when first needed: `tool_log.csv`, `unknown_fingerprints.csv`, `instrument_checks.csv`,
`reports.csv` and `reviews.csv`. Existing records keep working and are not changed.

## 1.1.0 and earlier

See the commit history.
