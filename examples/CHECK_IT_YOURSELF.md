# Check it yourself: adding references and the measuring mode

A hands-on check of the library workflow, done in the window. Every step says what you should
see. The numbers are the ones `tests/test_library.py` and `tests/test_analyzer.py` check, so if
the screen shows something else, something is wrong.

Nothing here changes the demo files. Every addition and removal is written to
`records/inhouse_library/library_changes.csv` (append-only), and you take everything out again
at the end.

## 0. Start

1. Start the program (`run_analyzer.bat`).
2. Click **Open spectra** and select all twelve files in `examples` (Ctrl+A in the file dialog).
3. If it asks how some files were measured: set `07_particle_on_filter` to **ATR** and the others
   to **Don't know**, then OK. (It only asks for files that do not say it themselves and are not in
   the sample log yet.)

**You should see** the twelve results of the table in `examples/README.md`, for example
`01` probable PET (r 0.97), `05` weak Nylon 6,6 (r 0.88), `10` weak PS (r 0.88). The badge at the top
says **Library validated**.

## A. Nylon 6: a new reference raises the score

`05_fibre_on_wafer_ATR` is a Nylon 6 fibre, but the shipped library only has Nylon 6,6, so the
best it can say is *weak*. Here you add a Nylon 6 reference measured on a different sample and a
different instrument: a fibre from a forensic fibre reference collection (Microtrace
MTF_NYL_083), where the collection itself names the polymer.

1. Click **05_fibre_on_wafer_ATR** in the list.
   **You should see:** Weak · Nylon 6,6, score **0.88**, lead 0.62 over PU.
2. **Library → Add a reference…** (Ctrl+N). Under **1 The spectrum**, switch from **Selected
   result** to **A file**, click **Choose a file…** and pick
   `examples/library_demo/Nylon6_reference_fibre_collection.csv`.
   **You should see:** name **Nylon 6**, category **People & clothing**, measured by **ATR**, and
   under the chart "3451 points, 550–4000 cm⁻¹, %T · details read from the file's notes". The file
   is in transmittance; the program turns it into absorbance itself.
3. Scroll to **3 Validation before adding** and wait a second.
   **You should see:**
   - Most similar existing reference: **Nylon 6,6, r 0.90** (below the 0.95 line: different enough)
   - Impostor test: now 0.90 → with it **0.90 (Nylon 6,6 → Nylon 6)**, green
   - 1 of 12 results would change: **05_fibre_on_wafer_ATR  Weak: Nylon 6,6 (r 0.88) → Probable:
     Nylon 6 (r 0.96)**
   - **Safe to add.**
4. The measuring mode matters. Under **Measured by**, click **transmission** and wait a second.
   **You should see:** most similar Nylon 6,6 at r 0.86, and 05 now only goes to **Weak: Nylon 6
   or Nylon 6,6 (r 0.89)**. Measured by ATR but entered as transmission, the reference is
   multiplied by 1000 / wavenumber for nothing and no longer fits. Click **ATR** again: the numbers
   from step 3 come back.
5. Click **Add to library**.
   **You should see:** "Nylon 6 added to the library. 1 result changed.", the 05 row glows, the
   Library page shows **In-house 1**, and the badge still says **Library validated**.
6. Click 05 again.
   **You should see:** **Probable · Nylon 6**, score **0.96**, lead **0.08** over Nylon 6,6. Switch to
   **Analytical view**: step 4 shows the two fingerprints and r = 0.957.
7. **Library → Open the library change log.**
   **You should see:** one `add` row for Nylon 6 with your login name, the time, mode ATR, the
   confirmation text and the SHA-256 of the saved file and of the source file.
8. Take it out again: Library page → **In-house** → the Nylon 6 card → **Remove from the library…**,
   reason e.g. "walkthrough done".
   **You should see:** 05 back to Weak · Nylon 6,6 (0.88). The change log now has the `add` row
   **and** a `remove` row: nothing was deleted.

## B. ABS is safe, SAN after ABS is refused

1. **Add a reference… → A file → Choose a file…** → `examples/library_demo/ABS_reference_known_part.csv`.
   **You should see:** most similar PS at r 0.88; impostor test stays at 0.90; 2 results change:
   `10_tool_cover_fragment_ATR` Weak: PS (r 0.88) → **Probable: ABS (r 0.99)** and
   `06_PS_calibration_film_transmission` Weak: PS (r 0.80) → Weak: ABS (r 0.94). **Safe to add.**
   Add it.
2. **Add a reference… → A file → Choose a file…** → `examples/library_demo/SAN_reference_cover_sample.csv`.
   **You should see:** most similar **ABS at r 0.98** (red, above 0.95), impostor test with it 0.98
   (SAN → ABS), **Not safe to add**, and the **Add to library** button stays grey. Click Cancel.
3. Remove ABS again (In-house → ABS → Remove from the library…).

## C. The measuring mode: unknown, and wrong

The program compares everything in the library's look (ATR). When the mode is not known it reads
the spectrum both ways and uses the one that fits better, and says so. When a mode is given but
the other one fits clearly better, it flags **mode doubt**.

1. So that the program asks again: **Records → Open records folder** and rename `sample_log.csv`
   to `sample_log_before_check.csv` (rename, don't delete: it is a record).
2. In the list, right-click `07_particle_on_filter` → **Remove from the list**. Then **Open spectra**
   → `examples/07_particle_on_filter.csv`, and answer **Don't know**.
   **You should see:** Probable · PE (high density), score 0.97, flags **mode unknown** and
   **second component?**; under the name "compared as ATR: the better fit"; the next step ends with
   "read both ways, it fits better as ATR (r 0.97 against 0.81), so it is compared that way".
3. Remove 07 from the list again, open it again, and this time answer **transmission**.
   **You should see:** Weak · PE (high density), score 0.81, and the flag **mode doubt**: "it fits
   clearly better as ATR (r 0.97 against 0.81). Check how it was measured."
4. Put the sample log back: close the program, delete the new `sample_log.csv` (it only holds the
   wrong test answer) and rename `sample_log_before_check.csv` back to `sample_log.csv`.

## D. Open Specy (if you use the extended library)

**Library → Open Specy… → Download.** The report at the end has a line **Measured by: …**: how
many of the kept references were ATR, how many were transmission (put into the ATR look, like a
transmission sample) and how many did not say (used as measured). The badge must still say
**Library validated**.

## Checklist

| Check | Expected |
| --- | --- |
| 05 before | Weak · Nylon 6,6, r 0.88 |
| Nylon 6 preview | closest Nylon 6,6 r 0.90, impostor 0.90, 05 → Probable Nylon 6 (r 0.96), safe |
| Nylon 6 entered as transmission | 05 → Weak: Nylon 6 or Nylon 6,6 (r 0.89) |
| 05 after adding | Probable · Nylon 6, r 0.96, lead 0.08 over Nylon 6,6 |
| After removing | 05 back to weak Nylon 6,6; change log has add + remove |
| ABS | safe; 10 → Probable ABS (r 0.99) |
| SAN after ABS | not safe (r 0.98 to ABS), button grey |
| 07, mode don't know | Probable PE, compared as ATR (0.97 against 0.81) |
| 07, mode transmission | Weak PE (0.81), flag mode doubt |

The Nylon 6 reference is from FasTEX-KCL (MIT, Reeha Parkar) and the dataset of Parkar et al.
(2025), see `../THIRD_PARTY_NOTICES.md`.
