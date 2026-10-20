# Data shipped with the FTIR Contamination Analyzer

| File | What it is | Source |
| --- | --- | --- |
| `library_index.csv` | The reference library: one row per material, with the file that holds its spectrum, how it was measured, its fab category, its source and licence, and its name in the original source | Written for this project by Ali Obeidat |
| `library_openftir_atr.csv` | The 16 reference spectra, ATR, absorbance, 650–4000 cm⁻¹. One wavenumber column and one column per material | OpenFTIR, MIT License (Viraj Ajay Mhetar) |
| `band_table.csv` | Wavenumber ranges (`low`, `high`) and their assignments, used to name bands. Includes the CO₂ and water-vapour artefacts | Compiled for this project by Ali Obeidat from standard IR correlation tables |
| `fab_sources.csv` | For each library material (and material group): where it can come from in a semiconductor fab, and what to check next | Written for this project by Ali Obeidat. These are hints for the root-cause analysis, not proof |

The 16 shipped references: PE (high density), PP, PS, PET, PBT, PMMA, PC, Nylon 6,6, PVOH, PAN,
EVA (25 % VA), PLA, PVC, PU, EVOH (44 % ethylene) and PK (polyketone).

## Adding a reference

Use the app: **Library → Add a reference…** (or *Add to library…* on a result). The spectrum is
stored in `records/inhouse_library/` with who added it, when, and how its identity was confirmed;
every addition and removal is appended to `records/inhouse_library/library_changes.csv`. Before
anything is saved, the program shows the most similar existing reference, the impostor test with the
new reference, and which of the spectra on screen would get a different answer. A reference that
would make two materials impossible to tell apart cannot be added.

The shipped files above are never changed by the app.

## Open Specy references (optional, extended mode)

Not shipped. **Library → Open Specy…** downloads Open Specy's *nobaseline* library (baseline-corrected
absorbance, CC BY 4.0, Cowger et al. 2021) on your computer, or imports a file you downloaded. Only
fab-relevant FTIR spectra are kept, every one that could be confused with a different material is left
out, and the result is saved in `records/openspecy/` with an import report (see
`ftir_analyzer/openspecy.py`). The *derivative* library is refused: its processed derivative spectra
cannot be compared with absorbance. (Open Specy's small *test* library, inside its R package, mixes
Raman and differently processed spectra and is not used.)

`fab_sources.csv` also has rows for the material groups Open Specy adds (silicone, fluoropolymer,
nitrile rubber, natural rubber, epoxy, polyimide, POM, PEEK, polyamide, SAN, cellulose, protein, silica).

Full licence texts: [`../../THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).
