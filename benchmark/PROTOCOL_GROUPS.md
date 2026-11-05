# Unknown groups protocol, version 3

This file was committed before the grouping below was measured. Git history is the proof of the order.

The tool refuses to run if the program's matching code differs from the commit named in the tool. Verdicts are not
changed: a group only says that samples look alike, not what they are.

## The question

Samples without a probable verdict have no name, so Trends cannot count them. If samples with no name are grouped by
how alike they are, do the groups hold one material?

## Method

Each sample is compared with every other using the program's own score r on its fingerprint, on the common grid. Two
samples are linked when r is at least **0.95**. A group is every sample that can be reached through links. A group
needs at least **3** samples. The limit and the size are fixed here and are not tuned.

## Data

| Set | Spectra | Why |
| --- | --- | --- |
| Fibres with no reference | 70, Replica 1 | Physical samples from one source, the same situation as one lab |
| Open Specy, no reference | All in the benchmark's test set and the locked set | Many labs: the harder case |

Spectra are compared in the mode each was measured or read in by `analyse()`.

## What is measured

1. **Purity:** the share of groups that hold one material, and the share of samples in a group that belong to its most
   common material.
2. **Splitting:** how many groups each material falls into.
3. **Reach:** the share of samples that end up in any group.
4. **False grouping:** the share of linked pairs that are different materials, with a 95% interval.

## What counts as useful

The groups are useful for a data set if at least **90% of grouped samples** belong to their group's most common
material, and at least **half of the samples** are in a group. Otherwise the feature is reported as not useful on that
data set.

## Disclosures

- A quick look on these fibres was taken before this protocol: at r of at least 0.95, 232 of 233 linked pairs were one
  material, and six groups of 3 or more each held one material. The limit of 0.95 was chosen after that look.
- All of these spectra have been scored before, against the library. They have not been scored against each other,
  except the fibre look above.
- Open Specy has no physical-sample ID, so a group may hold repeats of one item. That would flatter its purity.
- Labels of materials with no reference come from the same rules as `PROTOCOL.md`.

## Known weaknesses

- Fibres come from one source. A group across instruments may behave differently.
- Close materials can join one group, and this test cannot see a difference that the labels do not record.
- This says nothing about real fab samples.

Nothing above may change once results are seen. A bug in the tool may be fixed, but only if the fix would be needed
whatever the result, and it must be listed under **Deviations** in the report.
