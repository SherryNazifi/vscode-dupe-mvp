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

| Metric | k=20 | k=5 |
|---|---:|---:|
| Category 1 flagged duplicate | 66/200 (33.0%) | 59/200 (29.5%) |
| Category 3 true canonical retrieved | 82/100 | 67/100 |
| Category 3 exact-correct | 49/100 | 46/100 |
| Category 3 wrong canonical selected | 28 | 23 |
| Correct among retrievable cases | 49/82 (60%) | 46/67 (69%) |
| Category 4 flagged duplicate | 19/30 | 17/30 |
| Category 4 `insufficient_information` | 1/30 | 2/30 |

## Category 3: known duplicates

### k = 20

The true canonical appeared in the candidate list for 82 queries.

The judge selected it correctly for 49:

```text
49/100 end-to-end
49/82 achievable = 60%
```

The judge returned `duplicate` 77 times. Twenty-eight of those selected the wrong candidate.

In 33 cases, the true canonical was present but the judge either:

- chose a distractor
- returned `none`

### k = 5

The true canonical appeared for 67 queries.

The judge selected it correctly for 46:

```text
46/100 end-to-end
46/67 achievable = 69%
```

Top five lost 15 retrievable truths relative to top twenty, but only three final correct selections.

The additional candidates ranked 6–20 mostly acted as distractors for the current judge.

## Category 1: unlabeled controls

At top five, 59 of 200 controls were flagged as duplicates.

This is not yet a verified 29.5% false-positive rate.

The category was sampled from issues without the `*duplicate` label, but maintainers do not label every real duplicate. Some flags may be genuine unlabeled duplicates.

The number is therefore an upper bound until human review.

The small change from 33.0% at top twenty to 29.5% at top five shows that candidate depth is not the main reason for over-calling.

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

## Next step

Manually review 25 of the 59 category 1 flags from the top-five run.

Use these labels:

- genuine unlabeled duplicate
- related but not the same bug
- clear false positive
- insufficient evidence

The review should answer:

1. How contaminated is category 1 by true unlabeled duplicates?
2. What evidence patterns cause false positives?
3. Is the judge matching on title, component, symptom, or shared terminology?
4. What abstention rules should be added to the next prompt?

Do not change retrieval, k, or the evaluation sample before completing this review.
