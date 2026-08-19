# Results

Consolidated results for the current baseline. Retrieval detail lives in
[`retrieval-experiments.md`](retrieval-experiments.md), judge design and the evaluation
dataset in [`judge-evaluation.md`](judge-evaluation.md), label construction in
[`data-and-ground-truth.md`](data-and-ground-truth.md), and the review vocabulary in
[`taxonomy.md`](taxonomy.md).

All duplicate-flag counts on this page use `picked_canonical != null`. The `verdict`
string is not used as the flag signal because a row can carry `verdict: "duplicate"`
without naming a candidate; under that looser definition the category 1 counts are 66
(k=20) and 59 (k=5) instead of 62 and 58.

## Baseline

```text
embedding top 5 → multi-candidate judge → one recommendation or abstain
```

## Retrieval

Recall over the 397 checkable ground-truth pairs.

| Metric | Result |
|---|---:|
| Embedding recall@1 | 195/397 (49.1%) |
| Embedding recall@5 | 270/397 (68.0%) |
| Embedding recall@20 | 320/397 (80.6%) |
| Embedding recall@50 | 351/397 (88.4%) |
| Adjusted recall@5 after removing 55 audited bad pairs | 270/342 (78.9%) |

| Method | Recall@5 |
|---|---:|
| Embedding | 68.0% |
| BM25 | 54.9% |
| Symmetric RRF | 66.2% |

BM25 recovered all 26 manually identified lexical misses but contributed less as
embedding depth grew. It suits a targeted lexical role rather than symmetric fusion.

## Judge, by candidate depth

| Metric | k=20 | k=5 |
|---|---:|---:|
| Category 3 true canonical retrieved | 82/100 | 67/100 |
| Category 3 exact-correct | 50/100 | 47/100 |
| Correct among retrievable cases | 50/82 (61%) | 47/67 (70%) |
| Wrong canonical selected | 26 | 22 |
| Abstained | 24 | 31 |
| Category 1 controls flagged duplicate | 62/200 | 58/200 |
| Category 4 near-empty flagged duplicate | 19/30 | 17/30 |
| Category 4 `insufficient_information` | 1/30 | 2/30 |

Widening from 5 to 20 adds 15 retrievable truths but only 3 exact-correct decisions.
The candidates ranked 6–20 function mainly as distractors for the current judge, so
top five is the baseline: a quarter of the cost, three decisions worse, and more
accurate among the cases where the answer is actually available.

## Category 3 after ground-truth audit

All 32 apparent failures at k=20 were manually reviewed against
[`taxonomy.md`](taxonomy.md). Taxonomy 4 labels mean the judge was right and the
evaluation label was at fault, so those rows move from the error column to the correct
column.

| Metric | Result |
|---|---:|
| Raw accuracy on retrieved cases | 50/82 (61.0%) |
| Corrected accuracy after audit | 65/82 (79.3%) |
| Corrected, excluding unjudgeable cases | 65/79 (82.3%) |
| Corrected end-to-end, including retrieval misses | 65/100 (65.0%) |

Review labels across the 32 reviewed failures:

| Label | Taxonomy | Count |
|---|---|---:|
| `judge_error` | 3 (under-calling) | 10 |
| `bucket_sibling` | 4 | 9 |
| `pick_wrong` | 3 (over-calling) | 4 |
| `insufficient_information` | 1 | 3 |
| `pick_better_than_gt` | 4 | 2 |
| `gt_wrong` | 4 | 2 |
| `gt_questionable` | 4 | 2 |

Split by what the judge did:

| Failure mode | Count | Dominant labels |
|---|---:|---|
| `picked_distractor` | 17 | `bucket_sibling` 9, `pick_wrong` 4 |
| `picked_none` | 15 | `judge_error` 10 |

Two findings follow. Ground-truth defects (Taxonomy 4) account for **15 of 32 (47%)**
of apparent failures — the single largest group, larger than genuine judge error in
either direction. And every wrong abstention is an under-calling failure: of the 15
`picked_none` rows, 10 are real judge errors where the canonical was present and
correct.

## Category 1 controls, reviewed sample

The judge flagged 58/200 controls at k=5. Twenty-four were reviewed, 23 of which
carried a pick.

| Verdict | Count (of 23 picks) |
|---|---:|
| not duplicate | 11 |
| insufficient information | 6 |
| duplicate | 6 |

| Metric | Result |
|---|---:|
| Precision among reviewed predictions | 6/23 (26.1%) |
| Precision excluding unjudgeable inputs | 6/17 (35.3%) |

Two limits on this number. Only 23 of 58 predictions were reviewed, so it is precision
on a sample, not on the control set. That sample is also not random: the 35 unreviewed
picks average 0.918 confidence against 0.881 for the reviewed ones, so the sample skews
toward lower-confidence picks and likely understates true precision.

Category 1 has no Taxonomy 4 analogue — it is the non-duplicate control, so there is no
ground-truth canonical that could be wrong. Its corrected figure is adjusted only for
unjudgeable inputs, whereas the Category 3 figure is adjusted for label error. The two
corrected numbers are therefore not symmetric and should not be read as comparable.

## Confidence is not a usable threshold

Correct and incorrect decisions occupy the same confidence band.

| Set | Confidence |
|---|---|
| Category 3 reviewed failures | 0.62–0.99 |
| Category 1 reviewed false positives | mean 0.87 |
| Category 1 reviewed true positives | mean 0.95 |

The most confident judgment in the Category 1 review (0.99) was made on an issue with a
blank body and no candidate selected. No threshold in the observed range separates true
canonical selections from plausible distractors.

## Known measurement defects

Two defects were found and fixed while producing these numbers; both are corrected in
the figures above.

**Ground-truth merge aliasing.** `fetch_timeline.py` wrote to `ground_truth.jsonl` and
`merge_ground_truth.py` read and overwrote that same path. The merge had run only once,
so no data was corrupted, but a re-run would have re-labeled comment-derived pairs as
timeline-derived and flipped their direction. The timeline stage now writes
`timeline_pairs.jsonl` and the merge reads it, so inputs and output are disjoint.

**Judge pick parsing.** The judge occasionally returned a candidate's rank index instead
of its issue number, and the value was written through unvalidated. Six rows across both
runs were affected; two of them were correct judgments scored as failures. Picks are now
resolved against the candidate list, and Category 3 exact-correct rose from 49 to 50
(k=20) and 46 to 47 (k=5).

## What the results point to

1. **Retrieval is not the main bottleneck.** Depth 20 supplies a 82/100 ceiling the
   judge converts at 61%.
2. **The judge compares surfaces, not defects.** It over-calls on shared component,
   vocabulary, or symptom, and under-calls when reports differ in detail, specificity,
   environment, or the reporter's proposed cause.
3. **The labels need auditing before the judge does.** 47% of apparent Category 3
   failures were label defects. Single-canonical ground truth mis-scores any judge that
   picks another valid member of the same duplicate class; equivalence classes would
   resolve most of it.
4. **There is no input-quality gate.** Feature requests, test-plan artifacts, and empty
   templates reach the judge, which commits rather than abstaining.
