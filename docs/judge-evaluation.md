# Multi-candidate judge evaluation

This document describes the evaluation of the multi-candidate LLM judge.

## Judge design

The original judge evaluated one pair at a time. The newer judge receives:

```text
one query issue
+
N retrieved candidates
```

It must select one canonical or abstain.

Output:

```json
{
  "verdict": "duplicate",
  "picked_canonical": 12345,
  "confidence": 0.89,
  "evidence": "Why this candidate describes the same underlying bug"
}
```

Allowed verdicts:

- `duplicate`
- `none`
- `insufficient_information`

## Evaluation dataset

`evaluation-candidates.jsonl` contains 480 records.

| Category | Purpose | Count |
|---|---|---:|
| 1 | live-fetched issues not labeled `*duplicate` | 200 |
| 2 | close-but-wrong hard-negative candidates from 50 pile1 queries | 150 |
| 3 | known duplicate queries with known canonicals | 100 |
| 4 | near-empty issues | 30 |

Fifty category 3 queries share their base query with category 2. Category 2 supplies distractors rather than an additional query-level verdict group.

The aggregate judge run covers 330 query records from categories 1, 3, and 4.

Each record stores:

- query issue
- category
- retrieved candidates
- candidate ranks
- embedding scores
- true canonical when known

## Results

Flagged-duplicate counts use `picked_canonical != null`. A row can carry the verdict
string `duplicate` without naming a candidate, so the verdict-based counts are slightly
higher (category 1: 66 and 59).

| Metric | k=20 | k=5 |
|---|---:|---:|
| Category 1 flagged duplicate | 62/200 (31.0%) | 58/200 (29.0%) |
| Category 3 true canonical retrieved | 82/100 | 67/100 |
| Category 3 exact-correct | 50/100 | 47/100 |
| Category 3 wrong canonical selected | 26 | 22 |
| Correct among retrievable cases | 50/82 (61%) | 47/67 (70%) |
| Category 4 flagged duplicate | 19/30 | 17/30 |
| Category 4 `insufficient_information` | 1/30 | 2/30 |

These counts reflect the `picked_canonical` parse fix described in
[`results.md`](results.md#known-measurement-defects). Before that fix the judge's
rank-index responses were written through unvalidated, understating category 3
exact-correct by one at each depth.

## Category 3: known duplicates

### k = 20

The true canonical appeared in the candidate list for 82 queries.

The judge selected it correctly for 50:

```text
50/100 end-to-end
50/82 achievable = 61%
```

The judge named a candidate 76 times. Twenty-six of those selected the wrong candidate.

In 32 cases, the true canonical was present but the judge either:

- chose a distractor (17)
- returned `none` (15)

All 32 were manually reviewed; see [`results.md`](results.md#category-3-after-ground-truth-audit).

### k = 5

The true canonical appeared for 67 queries.

The judge selected it correctly for 47:

```text
47/100 end-to-end
47/67 achievable = 70%
```

Top five lost 15 retrievable truths relative to top twenty, but only three final correct selections.

The additional candidates ranked 6–20 mostly acted as distractors for the current judge.

## Category 1: unlabeled controls

At top five, 58 of 200 controls were flagged as duplicates.

This is not a verified 29.0% false-positive rate.

The category was sampled from issues without the `*duplicate` label, but maintainers do not label every real duplicate. Some flags may be genuine unlabeled duplicates.

The number is therefore an upper bound; the review below converts part of it.

The small change from 31.0% at top twenty to 29.0% at top five shows that candidate depth is not the main reason for over-calling.

### Review outcome

Twenty-four of the 58 flags were reviewed, 23 of which carried a pick:

| Verdict | Count |
|---|---:|
| not duplicate | 11 |
| insufficient information | 6 |
| duplicate | 6 |

That gives 6/23 (26.1%) precision on the reviewed sample, or 6/17 (35.3%) once
unjudgeable inputs are excluded. The sample is not random — the 35 unreviewed picks
average 0.918 confidence against 0.881 for the reviewed ones — so it skews toward
lower-confidence picks and likely understates precision. Full breakdown in
[`results.md`](results.md#category-1-controls-reviewed-sample).

## Category 4: near-empty issues

At top five:

```text
17/30 flagged duplicate
2/30 insufficient_information
```

The model relies heavily on title overlap and rarely abstains even when the normalized body provides almost no evidence.

This exposes a major product risk:

> same topic or feature area is being treated as the same underlying bug.

## Confidence

The original pairwise judge appeared calibrated in a small manual sample.

The multi-candidate judge does not.

Correct and incorrect picks mostly receive confidence around 0.84–0.92. Confidence does not separate:

- true canonical selections
- plausible but wrong distractors
- over-called controls

Another confidence threshold is unlikely to solve the problem.

## Current configuration decision

Top five is the current baseline because it is:

- four times cheaper than top twenty
- only three exact-correct cases worse
- more accurate among retrievable cases
- exposed to fewer distractors

This is not a claim that deeper retrieval is useless. It means the current judge cannot use deeper retrieval safely.

## Main failure mode

The bottleneck is not simply whether the correct answer is retrieved.

The judge frequently:

1. sees several related candidates
2. identifies one plausible match
3. fails to prove it is the same underlying bug
4. selects it instead of abstaining

The richer candidate pool raises both opportunity and confusion.

The manual review qualified this. Over-calling is the dominant failure on the category 1
controls, but on category 3 the larger problem is the opposite: 10 of the 32 reviewed
failures are wrong abstentions where the correct canonical was present, against 4 genuine
wrong picks. The judge over-calls when the input carries no judgeable defect and
under-calls when both reports describe the same defect at different levels of detail.
Both behaviors follow from comparing surface features instead of the defect itself.

## Review status

The category 1 review is complete for 24 of the 58 top-five flags, and all 32 category 3
failures at k=20 have also been reviewed. Both used the vocabulary in
[`taxonomy.md`](taxonomy.md) rather than the four ad-hoc labels originally planned here.

What the review answered:

1. **How contaminated is category 1 by true unlabeled duplicates?** Materially. 6 of 23
   reviewed picks were genuine duplicates, so the raw flag count is not a false-positive
   count.
2. **What evidence patterns cause false positives?** Shared component or vocabulary,
   shared visible symptom with a different trigger, and boilerplate template text.
3. **Is the judge matching on title, component, symptom, or terminology?** All four, in
   place of the observed defect. Rank is not used as a prior — in at least one case the
   judge passed over a rank-1 correct canonical for a weaker match.
4. **What abstention rules should be added?** An input-quality gate, since the judge
   commits on feature requests, test-plan artifacts, and empty templates.

## Next step

- Review the remaining 34 category 1 flags to replace the sampled precision figure with
  a full one.
- Add an input-quality gate ahead of the judge for the categories in Taxonomy 1 that are
  not defect reports.
- Revise the judge prompt to weight observed behavior over environment, report
  specificity, and reporter-proposed cause — the four under-calling modes in Taxonomy 3.
- Represent ground truth as equivalence classes so bucket siblings stop scoring as
  errors.
- Re-run the 32-row category 3 failure set after prompt changes and count how many of
  the 14 genuine judge errors are recovered.

Retrieval, k, and the evaluation sample should stay fixed across those changes so the
reviewed failure set remains a valid before/after comparison.
