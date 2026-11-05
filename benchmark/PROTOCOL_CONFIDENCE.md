# Confidence protocol, version 2

This file was committed before any spectrum of the locked set was scored. It says how the confidence bar is set, how
it is tested, and what would make it worth showing in the app. Git history is the proof of the order.

**Locked program:** commit `6675e0c`. The tool refuses to run if `ftir_analyzer/` differs from that commit. The matching
code and the 16 references are the same as in the benchmark (`c432cee`); only the Open Specy import and the text around
it changed. The verdict rule is not touched. This step adds a measurement, not a new rule.

## The question

The score r is not a probability: r = 0.97 does not mean 97% sure. So can the app say something it has measured?

> "The right material is on this list about 90% of the time."

## The method, in plain words

This is conformal prediction, in its simplest form.

1. Take spectra whose material is known and which played no part in building the program.
2. For each one, note the score of its **true** material. This is its true score.
3. Find the **bar**: how low it must be for 90% of the true scores to clear it.
4. For a new sample, every material that scores at or above the bar goes on its list.

The exact rule: with n true scores sorted from high to low, the bar is the one at position (n + 1) × 0.9, rounded up.
If that position is past n, there is no bar and every material is on the list. The list covers the 16 references.

The promise holds for samples **like** those that set the bar, and it covers **materials with a reference**. It is an
average over many samples, not a statement about one sample.

## Data

The locked set of `PROTOCOL.md`: 1,396 Open Specy spectra, same file, same split, same labels, same exceptions. Until
this step none of them has been scored.

| Part of the locked set | Spectra | Use |
| --- | --- | --- |
| With a reference | 1,021 | Split in two: the **calibration half** sets the bar, the **test half** tests it |
| No reference | 308 | All tested. They cannot set a bar, because they have no true score |
| Close relatives | 67 | All tested, shown on their own |

The split works as in `PROTOCOL.md`: whole clusters, within each material, in order of
`sha256("ftir-confidence-v2|" + cluster)`, with at most 50% of a material going to calibration. It uses labels only.

EVOH has no locked spectra, and PK has none anywhere, so neither is tested here.

**The fibres** are an outside check, using Replica 1 of each of the 137 samples. They have been seen before and they
set nothing. They show whether a bar set on Open Specy travels to different data.

## Running the analysis

Every spectrum goes through the program's own `analyse()`, unchanged, as in `PROTOCOL.md`. The scores kept are the ones
the verdict uses, for all 16 references, along with how the spectrum ended up being compared.

## Two versions

- **Version A, one bar** for every spectrum.
- **Version B, three bars,** one for each way a spectrum ends up being compared: as ATR, as transmission, or as measured
  (neither reading fits). This depends only on the spectrum, never on its true material.

Both are fixed now. Nothing else is tried.

## What the report shows

For each version, and for each of its groups, on the test half unless stated:

1. **Coverage:** how often the true material is on the list, with a 95% margin. This is what the promise claims.
2. **List length:** median, and the share of lists with 0, 1, 2 to 3, and 4 or more materials.
3. Coverage per material.
4. **No reference:** how often the list is empty, and its median length.
5. Close relatives: how often the list holds the relative.
6. When the verdict is *probable*: how often that material is on the list, and how often it is alone there.
7. The same figures without doubtful labels. The headline keeps them in.
8. The fibre check: coverage, list length, and empty lists on fibres with no reference.
9. The true scores and the bar, as a picture.

Margins are as in `PROTOCOL.md`: for Open Specy, at each end, the wider of the 95% Wilson interval and a 95% cluster
bootstrap; for the fibres, Wilson.

## What counts as useful

A promise can hold and still help nobody: "one of 12 materials" is true and useless. So both must hold, for a version
or for one of its groups, on the test half:

1. **Valid:** the 95% margin of the coverage reaches 90%.
2. **Short:** the median list has **at most 3 materials**.

There is no other pass mark. A bad result is reported as it is.

## What happens next

- If something is useful, a line for the app and report may be proposed, for that group only, and it needs a separate
  yes. Showing it changes no verdict.
- If nothing is useful, the result is published and the app stays as it is.

## Disclosures

- Version B was chosen after seeing the benchmark: spectra compared as ATR scored much higher there. Those were other
  Open Specy spectra, not the locked set, but the choice is not blind.
- The list-length limit of 3 was also set after seeing the benchmark.
- The labels and counts of the locked set have been read. Its scores have not.
- The fibres have been scored before, so they are a check and not a proof.

## Known weaknesses

- Everything in `PROTOCOL.md` still applies: Open Specy spectra are processed, coarse, mostly environmental, and have
  no physical-sample ID.
- Spectra are split by cluster, so the two halves are not perfectly alike, and the promise assumes they are.
- Rare materials have few spectra, so a good average can hide a poor material.
- A bar set on Open Specy says little about a fab. A lab would have to set its own, on its own measurements.

## After this step

The test half is used up, so no unscored Open Specy spectra remain. A later change to the verdict rule needs fresh data.

Nothing above may change once results are seen. A bug in the tool may be fixed, but only if the fix would be needed
whatever the result, and it must be listed under **Deviations** in the report.
