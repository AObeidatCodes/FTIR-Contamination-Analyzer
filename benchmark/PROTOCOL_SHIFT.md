# Protocol v4: shift-tolerant search

Written and committed before any fresh data was read. It decides whether the shift-tolerant search is switched on.

## The question

The search compares a sample with each reference at one position. Benchmark v1 showed that a band shift of 2 cm⁻¹ halves the answers. A search that also tries small shifts of the sample may keep those answers. It may also let more wrong materials reach "probable". This test measures both.

## What is compared

| Search | Setting |
|---|---|
| Today | `SHIFT_TRIES = ()`, one position |
| Tolerant | `SHIFT_TEST`, shifts of −8 to +8 cm⁻¹ in steps of 2, each reference keeping its best score |

Everything else is the same: the verdict rule, its thresholds, the library in essentials mode, and the mode correction.

## Data

Spectra that no earlier step of this project has read.

Candidate: FTIR-Plastics (Zenodo record 10736650, `FTIR-PLASTIC.zip`). Its use depends on two things recorded here before the first run:

1. the licence of the version downloaded, confirmed from the record itself, and
2. the file's SHA-256, entered in `benchmark/shift.py` as `DATA_SHA256`.

The spectra stay out of the repository, in `benchmark/data/`. If the licence does not allow this use, another set is chosen and named here before it is read.

### The data as found

Added before the first run. Up to this point only the file's labels and headers were read, and no spectrum was compared with the library.

| | |
|---|---|
| File | `FTIR-PLASTIC.zip`, 265,006,200 bytes, the MD5 on the record matches |
| SHA-256 | `c8a5a378efcff70e959cfe7af26d7e7131e2508043ee99675328e582aa7b8dd9` |
| Licence | CC BY 4.0 on Zenodo record 10736650 and on the newer record 11176740, which holds only a calibration certificate and a notes file. The spectra are only in 10736650 |
| Citation | Villegas Camacho et al., FTIR-Plastics, Zenodo, 2024, doi:10.5281/zenodo.10736650 |
| Spectra | 6,000: `FTIR_PLASTIC_c4.csv` at 4 cm⁻¹ and `FTIR_PLASTIC_c8.csv` at 8 cm⁻¹, each with 500 spectra of PET, HDPE, LDPE, PVC, PP and PS |
| Instrument | every file header says FT/IR ATR-4X, serial A009662111, accessory ATR PRO 4x, 32 scans, %T |
| NIST or Bosch | no such words in any of the 6,000 file headers or names |

Every spectrum is read as ATR and %T, as its header says. HDPE and LDPE both count as the library's material PE. All 6,000 spectra are used.

The record does not say whether the 500 sample numbers are 500 physical pieces, and the same numbers appear in both tables. The Wilson intervals treat the spectra as independent, so they may be too narrow. The rules stay as written, and the results are also given per resolution and per material.

## Measures

Each spectrum belongs to one material that has a reference in the library.

| Measure | How |
|---|---|
| Right probable | full library, verdict probable, the material is the true one |
| Not right probable | full library, verdict probable, the material is another one |
| False probable | every reference of the true material removed, verdict probable |

Right probable and not right probable are also measured with every spectrum shifted by 2 and by 4 cm⁻¹. The direction is drawn at random with the seed in `benchmark/scoring.py`.

## Pass rules

All four must hold. They are fixed now.

1. False probable, tolerant: the upper end of the 95 % Wilson interval is at most 5 %, and the rate is at most 1 percentage point above today's.
2. Not right probable, tolerant: at most 1 percentage point above today's, at shift 0.
3. Right probable, tolerant: at most 1 percentage point below today's, at shift 0.
4. Right probable, tolerant: above today's at shifts of both 2 and 4 cm⁻¹.

If all four hold, `SHIFT_TRIES` is set to `SHIFT_TEST` in a separate commit that quotes the results. If any fails, the setting stays empty. The results are committed either way.

No threshold is changed after the results are seen. A second attempt needs a new protocol and data that have not been read.

## What the result will not show

The set holds a few common plastics, so a pass says nothing about materials outside it. Two quick looks before this protocol, on the fibres and on the Open Specy test spectra, suggested the idea. Those sets are not evidence here.
