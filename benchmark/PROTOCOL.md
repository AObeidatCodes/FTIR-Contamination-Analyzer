# Benchmark protocol, version 1

This file was committed before any benchmark spectrum was scored. It says what is tested, what counts as right and
wrong, and what the report must show. Git history is the proof of the order.

**Locked program:** commit `c432cee`. The tool refuses to run if `ftir_analyzer/` differs from that commit.
The verdict rule, the library and the matching are used as they are.

There is **no pass mark**. This is a measurement. A bad result is reported as it is.

## The question

The program gives one of three verdicts: *probable*, *weak* or *no reliable match*. The dangerous mistake is a
*probable* that is wrong, because a person may sign it. So the benchmark asks:

1. How often does the program say *probable* for a material that has no reference in its library?
2. When a material does have a reference, how often is *probable* right, and how often does it answer at all?

## Data

The spectra stay out of this repository. Only results are committed.

| Set | Source | SHA-256 of the file | Role |
| --- | --- | --- | --- |
| Fibres | FasTEX-KCL, `ml_datasets/feature_matrix_raw_transmittance.csv` (github.com/reeha-parkar/FasTEX-KCL) | `2739d901529a0fd97e693068d82cee5b7eee2a616f5e8d6e797a84ad859fa26f` | Main test: real physical samples, ATR, 1 cm⁻¹ |
| Open Specy | `medoid_nobaseline.rds` (Open Specy library) | `3591eb4b7be780ac12585631216bce5050cb543e9a61b8b482c91d1b4c821ab3` | Large test across many labs |
| OpenFTIR | `data/Sample_Spectra.csv` (github.com/VAMpire29122004/OpenFTIR) | `edb70bc53378e1c408e9bb29757f1f3a39b9c149a4c2a9dfad161dfb145918c3` | Extra check only, never in a headline |

### Left out, and why

- Open Specy spectra from the contributor `nist chem web book` (67): this project does not use NIST data.
- Open Specy spectra whose label fits no material group (2,194): there is no truth to score against.
- The 16 OpenFTIR spectra that are the library itself, and the 3 labelled only `Sample 00n`, and the 4 labelled
  only `Acrylic <colour>`: their material is not stated. That leaves 36 for the extra check, not 43 (see Changes
  from the approved plan).
- Any test spectrum that is a copy of a reference: Pearson r of at least 0.9999 between the two on the common grid,
  with no fingerprint step. The number left out this way is reported.

## The locked set

About 30% of Open Specy is kept back and **is not scored by this benchmark**. It is for later work: calibrated
confidence, and checking any fix to the verdict rule.

The split uses no spectrum values. Spectra are put in **clusters**, one per contributor + label + material group.
Within each material group the clusters are taken in order of `sha256("ftir-benchmark-v1|" + cluster)`. A cluster
goes to the locked set if that keeps the locked share of the group at 30% or less; otherwise it goes to the test set.
A whole cluster always stays on one side, so near-copies cannot sit on both sides.

The fibres are not split.

## Counting samples, not repeats

- **Fibres:** the unit is the physical sample (`Sample_ID`). The main result uses `Replica` 1 of each of the 137
  samples. The other 23 spectra are used only for the repeatability check: does each repeat of a sample get the same
  verdict and the same material?
- **Open Specy:** **this rule can only be partly met.** The file has no physical-sample ID: `sample_name` is unique
  per spectrum. So each spectrum counts once, and repeats of one item cannot be removed. To stop this from making the
  numbers look surer than they are, margins for Open Specy are widened using the clusters (below), and results are
  also shown per contributor.

## What each spectrum is

Open Specy truth comes from the program's own `material_group` applied to the same text the importer uses
(`material`, `spectrum_identity`, `material_class`), with these exceptions written down now:

- **Polyamides.** Only a label that says 6,6 and does not also name Nylon 6 alone counts as the library's Nylon 6,6.
  Every other polyamide is a close relative (below).
- **Aramids.** A label with `ARAMID`, `KEVLAR`, `NOMEX` or `PHENYLENE TEREPHTHALAMIDE` is the material `aramid`, not
  a polyamide, and has no reference.

Fibre truth comes from `Type` and `Subtype`:

| Fibre | Truth | Samples |
| --- | --- | --- |
| Polyester (PET), polypropylene, polyethylene, polyamide 6,6 | **In library:** PET, PP, PE, Nylon 6,6 | 29 |
| Polyamide 6, unspecified polyamide | **Close relative** of Nylon 6,6 | 11 |
| Acrylic, modacrylic | **Close relative** of PAN | 27 |
| Aramid, cotton, jute, linen, regenerated cellulose | **Not in library:** aramid, cellulose | 38 |
| Cellulose acetate | **Not in library:** cellulose acetate | 4 |
| Alpaca, silk, wool | **Not in library:** protein | 28 |

Open Specy groups:

- **In library:** PE, PS, PP, PA (6,6 only), PVC, PAN, PET, PU, EVA, PC, PMMA, PVOH, PLA, PBT, EVOH.
- **Not in library:** cellulose, cellulose acetate, fluoropolymer, silicone, PVAc, SAN, ABS, polyimide, natural rubber,
  nitrile rubber, epoxy, PEEK, POM, protein, silica, aramid.
- **Close relative:** every polyamide other than 6,6.

The library's 16th reference, PK, has no test samples.

## The buckets

**A material with a reference:**

| Bucket | Meaning |
| --- | --- |
| Right | *probable*, naming the true material |
| Right family | *probable*, naming a different material of the same family (`data/families.csv`) |
| Wrong | *probable*, naming a material of another family |
| No answer | *weak* or *no reliable match* |

*Right family* never counts as right in the strict figures. *No answer* is split in the report into weak that points
at the true material, weak that points elsewhere, and no reliable match.

**A material without a reference:** correct means *not* saying *probable*. Any *probable* is a false probable, even
if it names a relative. The report also shows how many of those named the same family.

**A close relative:** its own bucket, in neither figure.

| Bucket | Meaning |
| --- | --- |
| Relative named | *probable*, naming the relative (Nylon 6 fibre called Nylon 6,6, acrylic fibre called PAN) |
| Wrong | *probable*, naming anything else |
| No answer | *weak* or *no reliable match* |

## Doubtful labels

A label can be wrong. **Failures are never deleted.** A spectrum is flagged *doubtful* if its text has any of
`GLYCOL`, `SULFON`, `WAX`, `BLEND`, `MIXTURE`, `COMPOSITE`, or `COPOLYMER` (except EVA, EVOH, SAN and ABS, which are
copolymers by nature), or if it fits two material groups in a way that is not one name inside another. Those nested
pairs are written in the tool (for example PAN and nitrile rubber, because `POLYACRYLONITRILE` contains `NITRILE`).

Doubtful spectra stay in every headline. The report also gives each headline without them, and the failures list
marks them.

## Running the analysis

Every spectrum goes through the program's own `analyse()`, unchanged.

- Fibres: unit %T, mode ATR, as measured.
- Open Specy: unit absorbance. Mode from `measuring_mode()` on `instrument_mode` + `instrument_accessories`, else
  `unknown`, in which case the program reads it both ways, as it does for a real user.
- OpenFTIR: unit absorbance, mode ATR.

## What the report shows

Fibres and Open Specy are always reported **separately and never pooled**: they measure different things.

1. **False-probable rate** on materials without a reference, with a 95% margin. This is the headline.
2. **Strict share right among *probable* answers** on materials with a reference, the family-level share, and how
   often the program answers at all (coverage).
3. Per-material table.
4. Confusion chart: true material against what was named.
5. Per-contributor table for Open Specy.
6. Fibre repeatability.
7. The close-relatives bucket.
8. **Value of the lead rule:** *probable* needs r ≥ 0.95 **and** a lead of at least 0.08 over the next different
   material. Recomputed from stored scores, without the lead, showing wrong answers avoided and right answers lost.
   The app is not changed.
9. Best-match accuracy: how often the true material ranks first, whatever the verdict.
10. Stress tests, on all fibre samples and 500 Open Specy test spectra (first 500 by hash), seed 20261105:

    | Test | Levels |
    | --- | --- |
    | Noise, as a share of the absorbance range | 0.5%, 1%, 2%, 5% |
    | Baseline drift, slope plus slow curve, same share | 5%, 10%, 25%, 50% |
    | Shifted bands | 1, 2, 4, 8 cm⁻¹ |
    | Lower resolution, Gaussian blur, FWHM | 8, 16, 32 cm⁻¹ (resampled at half that) |

11. **Second run with the extended library** (`install_pack`, 145 references). Spectra used as references are left
    out, with their whole cluster, and the default library is scored on the same reduced set so the two compare
    fairly. A material counts as in library if that library holds its group.
12. OpenFTIR extra check, marked as out of the headline.

## Margins

- Fibres: 95% Wilson interval.
- Open Specy: at each end, the wider of the 95% Wilson interval and a 95% cluster bootstrap (2,000 resamples of
  clusters, seed 20261105). Wilson alone would treat every spectrum as independent, which they are not.

## Disclosures

This benchmark is not fully blind, and the report must say so.

- OpenFTIR scores were seen while the program was built, and it is the source of the library. That is why it stays
  out of the headline.
- Scores for a handful of fibre samples were seen before this protocol, while checking that the file could be read.
- The Open Specy pack was used to set the family limit (`FAMILY_R` = 0.85), so that limit gets no credit here. The
  family line in the app is not what this benchmark scores.
- The verdict rules (0.95, 0.08, 0.60) were not set on either test set.
- The file metadata was read before this protocol was written, to find labels and counts. Spectrum scores were not.
- The shipped library comes from one source. A second lab's sample of the same material may simply differ.

## Known weaknesses of the data

- Open Specy spectra are already processed, on a 6 cm⁻¹ step, cover 804 to 3198 cm⁻¹, and have a hole at 2196 to
  2424 cm⁻¹. A real measurement has more to compare.
- Fibres are one form of a material. Results say little about films, powders or particles from a fab.
- Most Open Specy spectra are environmental microplastics, not fab contamination, and may be weathered.
- This tests identification only. It says nothing about a person's sign-off or the rest of the workflow.

## Changes after this commit

Nothing above may change once results are seen. A bug in the tool may be fixed, but only if the fix would be needed
whatever the result, and it must be listed under **Deviations** in the report with what it changed. Any change to a
threshold, label or data rule is a new protocol version, tested on the locked set.

## Changes from the approved plan

Written before scoring, from reading labels only:

- Most Open Specy polyamides have no stated type, so they move to the close-relatives bucket. Aramids move to
  not-in-library. The in-library count falls by about 280.
- All counts above are before the locked set is taken out, so the Open Specy test set is about 70% of them.
- "Count samples, not repeats" is only partly possible for Open Specy (see above).
- OpenFTIR is 36 spectra, not 43, because 7 have no stated material.
