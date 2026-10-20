# Demo spectra

Twelve real measurements with known answers, named after where they were "found". The analyzer
must give these results; `tests/test_analyzer.py` checks that it does.

| File | Mode | Expected result | What it shows |
| --- | --- | --- | --- |
| `01_wipe_area_particle_ATR.csv` | ATR (file note) | **probable PET** (r 0.97) | A clean match. Polyester wipes and garments |
| `02_wafer_box_particle_ATR.csv` | ATR | **probable PE** (r 0.99) | Bags, liners, wafer-box parts |
| `03_litho_rework_film_ATR.csv` | ATR | **probable PMMA** (r 0.96) | Methacrylate resist residue after a rework |
| `04_post_CMP_clean_particle_ATR.csv` | ATR | **probable PVOH** (r 0.99), O–H major | PVA brushes in the post-CMP clean |
| `05_fibre_on_wafer_ATR.csv` | ATR | **weak**: Nylon 6,6 (r 0.88) | The sample is Nylon 6; the library only has Nylon 6,6. *Weak* says "similar, not proven". After the Nylon 6 reference is added it becomes **probable Nylon 6** (r 0.96, see below) |
| `06_PS_calibration_film_transmission.csv` | transmission (file note) | **weak PS** (r 0.80), **saturated** | A transmission film corrected to the ATR look. The saturation warning says: measure thinner or use ATR |
| `07_particle_on_filter.csv` | *not in the file*: the program asks (answer **ATR**) | **probable PE** with an **unexplained band at 1030 cm⁻¹** | A second component: Si–O from soil or a silicate. The match alone would have missed it |
| `08_fibre_on_filter.csv` | not in the file (answer *don't know*) | **no reliable match**, C–H present, O–H major | An organic that is not in the library (cellulose acetate): read the bands by hand |
| `09_empty_spot_on_filter.csv` | not in the file | **no reliable match**, **CO₂ artefact: probably no sample** | An empty measurement: noise, water vapour and a CO₂ band that points **down** (less CO₂ in the air than during the background scan). The whole spectrum is below zero: more light came through than in the background. Open the **Analytical view** to see the CO₂ ruler |
| `10_tool_cover_fragment_ATR.csv` | ATR | **weak PS** (r 0.88) | ABS is **not** in the shipped library. ABS contains styrene, so PS is the closest thing the library knows: *weak*, not *probable*. After the ABS reference is added it becomes **probable ABS** (see below) |
| `11_second_fibre_on_filter.csv` | not in the file | **no reliable match** | A second fibre spot on the same filter as 08. After 08 is added to the library as cellulose acetate, this one is **probable** |
| `12_shipping_box_film_ATR.csv` | ATR | **probable EVOH** (r 0.96) | A barrier film from a wafer shipping box, a different EVOH grade from the reference |

The mode answers are saved in `records/sample_log.csv`. Rename that file to be asked again. A *don't
know* answer is not saved: the program then reads the spectrum both ways (as ATR and as transmission)
and uses the reading that fits better, and says so (07 with *don't know*: compared as ATR, r 0.97
against 0.81). A given mode that fits clearly worse than the other one is flagged **mode doubt**.

**Check it yourself:** [`CHECK_IT_YOURSELF.md`](CHECK_IT_YOURSELF.md) walks through adding the
references below and the measuring-mode checks in the window, with the numbers you should see.

## `library_demo/`: adding a reference, and the validation that guards it

Two reference files measured on known parts. Their header lines carry everything the program needs
(`# reference:`, `# category:`, `# fab sources:`, `# check next:`, `# confirmation:`), so the
add-reference sheet fills itself in.

| File | What happens when you add it |
| --- | --- |
| `ABS_reference_known_part.csv` | ABS from a known equipment cover (a different ABS sample from demo 10). **Safe to add**: the closest existing reference is PS at r 0.88 and the impostor test stays at 0.90. The preview shows, before saving, that `10_tool_cover_fragment_ATR` will change from *weak PS* to **probable ABS** (r 0.99), and that the saturated PS film (06) shifts from *weak PS* to *weak ABS* |
| `Nylon6_reference_fibre_collection.csv` | Nylon 6 (PA 6) fibre from a forensic fibre reference collection (Microtrace MTF_NYL_083): a different sample from demo 05, measured on a different instrument (diamond ATR, saved as transmittance). **Safe to add**: the closest existing reference is Nylon 6,6 at r 0.90 and the impostor test stays at 0.90. The preview shows that `05_fibre_on_wafer_ATR` will change from *weak Nylon 6,6* (r 0.88) to **probable Nylon 6** (r 0.96). Entered with the wrong mode (transmission) it only reaches *weak: Nylon 6 or Nylon 6,6*: the measuring mode of a reference matters |
| `SAN_reference_cover_sample.csv` | SAN (styrene–acrylonitrile), chemically almost the same as ABS. Added **after** ABS, it is **not safe**: SAN and ABS score r 0.98 against each other, so a wrong *probable* would become possible. The program refuses to add it and says why |

Sources: OpenFTIR (MIT), Open Specy (CC BY 4.0), FasTEX-KCL (MIT; Parkar et al. 2025) and a
public-domain polystyrene film. See
`../THIRD_PARTY_NOTICES.md`.
