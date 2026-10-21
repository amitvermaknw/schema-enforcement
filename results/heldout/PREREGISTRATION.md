# Pre-registration: held-out blind relabel of failure categories

Written and committed before the held-out sample was drawn or any item was
labelled. Nothing below is changed after labelling starts; deviations, if any,
are reported in the paper as deviations.

## Purpose

The 144 hand labels reported in the paper were used while developing the
classifier, so their agreement is a development-set figure. This round
measures agreement on attempts the classifier was never checked against.

## Fixed before sampling

- **Database:** `results/archive/paper1_FINAL_DATA_locked_v4_20260913.db`,
  SHA-256 `d0f406f00882dadb4c0aa0b1bea3a4a77b562c80ec46f19fe7d6ad7d4ebfbeb4`,
  opened read-only.
- **Classifier:** `src/schemaeval/errors.py` at commit `9f146ab9491b6cc45a854955dff8a6aa0b0ed232`. The stored
  `primary_category` equals this classifier's output (re-running it over the
  corpus changes 0 of 1,326 labels; `make check-reclassify`). The classifier is
  not modified in response to this round.
- **Sampling frame:** failed attempts on the reported basis (baseline prompt,
  cells with at least 30 runs) with non-empty raw output, excluding every
  attempt in the 144-item development set. Frame size by classifier category:
  `markdown_wrap` 660, `length_bound` 239, `regex_pattern` 101 (total 1,000).
  No other category has any attempt left in the frame.
- **Draw:** `scripts/heldout_relabel.py sample` with seed `20261021` and quotas
  `markdown_wrap=40 length_bound=30 regex_pattern=30` (100 items), drawn once,
  shuffled across categories.
- **Labels:** the 12 options of `scripts/label_samples.py`
  (`GROUND_TRUTH_CHOICES`), applied as the primary category under the paper's
  category definitions and precedence.

## Protocol

- Single annotator (the author), the same person who labelled the development set.
- Blind: the labelling screen shows model, dataset, tier, node and the raw
  output, truncated as in the development round, but never the classifier's
  label; there is no default answer. Classifier labels are read only by
  `score`, after all 100 items are labelled.
- Labels are written to `results/heldout/labels.csv`, committed with the sample.

## Analysis

- **Primary:** agreement = items where the human label equals the classifier's
  primary category, over 100, with a 95% Wilson interval.
- **Secondary:** agreement per category; agreement weighted by each
  category's frame size; every disagreement listed with its notes.
- The result is reported whatever it is, alongside the development-set
  figure, never pooled with it.

## Known limits, stated in advance

- One annotator, who also labelled the development set: this measures
  generalisation to unseen items, not inter-annotator reliability.
- The held-out round covers only the three categories with attempts left in
  the frame. On the reported basis these three account for 1,070 of the 1,126
  failures (681 + 263 + 126); every reported-basis attempt of the remaining
  categories with non-empty output is already in the development set, so
  they have no held-out counterpart.
- The annotator sees the model name, as in the development round.
