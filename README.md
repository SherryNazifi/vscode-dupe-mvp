# vscode-dupe-mvp

An agent that reads a GitHub issue from the `microsoft/vscode` repository, searches thousands of existing issues, and recommends whether one describes the same underlying bug.

## Why this is hard

Duplicate reports often use different wording. One user may write "Copilot chat is not responding," while another writes "requests fail silently after submit." Keyword matching can miss these relationships, while a language model cannot economically compare every new issue against the entire repository.

The system therefore separates the problem into two stages:

```text
new issue
→ retrieve a small candidate list
→ judge whether any candidate is the same underlying bug
→ recommend one canonical issue or abstain
```

The system only recommends duplicates. A human still decides whether to close an issue.

## Current architecture

### 1. Ingest and normalize

Issues are fetched from GitHub and normalized into:

```json
{
  "number": 123,
  "title": "Issue title",
  "document": "Issue title + cleaned issue body"
}
```

The normalizer removes template noise such as HTML comments, `<details>` blocks, images, fenced code, version lines, and OS lines. If the body becomes empty, the title is retained.

This normalization is useful but imperfect. It can also remove distinctive evidence such as stack traces, error strings, commands, and screenshot-only reports.

### 2. Embed

All pile1 and pile2 documents are embedded with `text-embedding-3-small` and stored in one `.npz` file.

### 3. Retrieve

Cosine similarity ranks pile2 issues for each pile1 issue. The current judge baseline uses the top five candidates.

### 4. Judge

The current judge receives one query issue and its candidate list at once. It returns:

```json
{
  "verdict": "duplicate",
  "picked_canonical": 12345,
  "confidence": 0.89,
  "evidence": "Why this candidate describes the same underlying bug"
}
```

Allowed verdicts:

* `duplicate`
* `none`
* `insufficient_information`

## Data

| Pile    | Contents                                          | Count |
| ------- | ------------------------------------------------- | ----: |
| `pile1` | issues labeled `*duplicate`                       |   800 |
| `pile2` | linked canonicals plus 3,000 recent non-PR issues | 3,236 |

Ground truth came from:

* comment and body references such as `Duplicate of #12345`
* GitHub GraphQL `MarkedAsDuplicateEvent` records

After merging and cleaning:

```text
442 recovered links
397 checkable pairs
```

A later manual audit found that 55 of the 397 links did not represent the same underlying bug. They included area-level links, catch-all tracking issues, testing links, and reports too vague to confirm.

## Current results

### Retrieval

| Metric                                                |          Result |
| ----------------------------------------------------- | --------------: |
| Embedding recall@1                                    | 195/397 (49.1%) |
| Embedding recall@5                                    | 270/397 (68.0%) |
| Embedding recall@20                                   | 320/397 (80.6%) |
| Embedding recall@50                                   | 351/397 (88.4%) |
| Adjusted recall@5 after removing 55 audited bad pairs | 270/342 (78.9%) |

BM25 was weaker overall:

| Method        | Recall@5 |
| ------------- | -------: |
| Embedding     |    68.0% |
| BM25          |    54.9% |
| Symmetric RRF |    66.2% |

BM25 recovered all 26 manually identified lexical misses, but its unique contribution shrank as embedding depth increased. It is more useful as a targeted lexical source than as an equal partner in symmetric fusion.

### Multi-candidate judge

| Metric                                    |   k=20 |    k=5 |
| ----------------------------------------- | -----: | -----: |
| Known duplicates with canonical retrieved | 82/100 | 67/100 |
| Exact-correct canonical                   | 50/100 | 47/100 |
| Correct among retrievable cases           |    61% |    70% |
| Wrong canonical selected                  |     26 |     22 |
| Unlabeled controls flagged duplicate      | 62/200 | 58/200 |
| Near-empty issues flagged duplicate       |  19/30 |  17/30 |

Counts of flagged duplicates use `picked_canonical != null` throughout. A row can carry the verdict string `duplicate` without naming a candidate, so the verdict field gives slightly higher counts (66 and 59); the pick-based definition is used here because it is what the precision analysis below is computed on.

The control flag rate is not a clean false-positive rate because an issue without the `*duplicate` label may still be a genuine unlabeled duplicate.

### Manual error analysis

A manual audit of category 1 and category 3 cases showed that raw evaluation numbers mix genuine judge failures with invalid inputs and defects in the ground truth.

#### Category 3: known duplicates

Among the 82 cases where the labeled canonical was retrieved, the judge was originally counted correct on 50.

| Metric                                                   |         Result |
| -------------------------------------------------------- | -------------: |
| Raw judge accuracy on retrieved cases                    |  50/82 (61.0%) |
| Corrected accuracy after ground-truth audit              |  65/82 (79.3%) |
| Corrected accuracy excluding unjudgeable cases           |  65/79 (82.3%) |
| Corrected end-to-end accuracy including retrieval misses | 65/100 (65.0%) |

Of 32 manually reviewed apparent failures:

* 15 were ground-truth defects or valid alternative matches
* 14 were genuine judge errors
* 3 were too underspecified to adjudicate

Ground-truth defects therefore accounted for 15/32 (47%) of the reviewed apparent failures.

#### Category 1: unlabeled controls

The judge predicted a duplicate for 58/200 controls. Of 23 reviewed predictions:

* 6 were genuine duplicates
* 11 were not duplicates
* 6 were too underspecified to judge

This gives:

| Metric                                       |       Result |
| -------------------------------------------- | -----------: |
| Precision among reviewed predictions         | 6/23 (26.1%) |
| Precision after excluding unjudgeable inputs | 6/17 (35.3%) |

Only 23 of the 58 duplicate predictions have been manually reviewed, so these figures should be interpreted as precision on the reviewed sample rather than the final precision of the full control set.

## Error taxonomy

Manual review produced four complementary taxonomies.

### 1. Issue type

Determines whether an issue is appropriate for duplicate judging:

* defect report
* feature request
* non-defect artifact
* insufficient content

### 2. Pair relationship

Describes the true semantic relationship between two defect reports:

* same defect
* same symptom, different cause
* same component, different defect
* opposite symptom

Only `same defect` is treated as a duplicate. The other categories may still represent related issues, but they should not be collapsed into the same underlying bug.

### 3. Judge failure mode

Describes why the judge makes an incorrect decision.

Over-calling failures include:

* component or vocabulary overmatch
* symptom overmatch
* contradictory-behavior overmatch
* unjudgeable-input overmatch

Under-calling failures include:

* detail asymmetry
* instance-vs-general mismatch
* environment-as-defect
* reporter-hypothesis-as-defect

The over-calling categories intentionally mirror several pair relationships from Taxonomy 2. Taxonomy 2 describes what the pair actually is, while Taxonomy 3 describes why the judge failed to recognize that relationship. Under-calling failures do not have the same mirror because they are all `same defect` pairs that the judge incorrectly rejected.

### 4. Ground-truth defect

Describes cases where the evaluation label rather than the judge is the main source of error:

* bucket sibling
* ground truth wrong
* judge pick better than ground truth

Categories are mutually exclusive within each taxonomy. A case may receive one applicable label from multiple taxonomies. Taxonomy 4 replaces Taxonomy 3 when the apparent failure is caused by the evaluation label rather than by the judge.

## Main findings

### Retrieval is not the only bottleneck

Widening retrieval from five to twenty raises the number of available true canonicals, but the judge fails to use most of that extra ceiling. It often selects a plausible distractor instead.

### Top five is the current baseline

Top five is:

* one quarter the judging cost of top twenty
* only three exact-correct decisions worse
* more accurate among cases where the true canonical is available
* less exposed to distractors

A stronger reranker or judge may make deeper retrieval useful later.

### Judge errors come from surface-level comparison

Manual review revealed failures in both directions.

For false positives, the judge often over-matches reports that share a component, vocabulary, or visible symptom while ignoring distinguishing conditions.

For false negatives, the judge often rejects true duplicates when the reports differ in detail, specificity, environment, or reporter-proposed cause.

These failures point to the same underlying problem: the judge is too sensitive to contextual and surface-level differences rather than isolating the observed defect itself.

### Ground truth must be audited

GitHub duplicate links are useful, but they are not clean same-bug labels.

Of 32 manually reviewed apparent judge failures in the known-duplicate evaluation, 15 (47%) were attributable to ground-truth defects or valid alternative matches rather than judge errors.

A common failure was the bucket-sibling case: several issues describe the same defect, but the evaluation names only one issue as canonical. A judge that selects another valid member of the same duplicate-equivalence class is therefore scored as wrong.

This suggests that duplicate evaluation should use equivalence classes or duplicate buckets rather than a single query-to-canonical mapping where possible.

### Input quality affects false-positive behavior

The judge frequently commits to a duplicate decision on feature requests, non-defect artifacts, and severely underspecified reports.

Among reviewed category 1 predictions, excluding unjudgeable inputs increased measured precision from 26.1% to 35.3%.

This suggests that an input-quality gate or stronger abstention policy should be applied before duplicate judging.

### Normalization removes useful evidence

About 8.5% of pile2 issues have five or fewer normalized body words. Some were genuinely sparse, but others lost stack traces or screenshots during preprocessing.

## Current decision

The current end-to-end baseline remains:

```text
embedding top 5
→ multi-candidate judge
→ one recommendation or abstain
```

The next improvements should target input judgeability and defect-level reasoning before increasing retrieval depth. Current failures are driven heavily by judging behavior and ground-truth quality rather than retrieval alone.

## Next steps

* Test an input-quality gate that prevents feature requests, non-defect artifacts, and severely underspecified issues from reaching the duplicate judge.
* Revise the judge prompt to prioritize observed behavior over incidental environment, report specificity, and reporter-proposed causes.
* Represent duplicate ground truth as equivalence classes or buckets where possible.
* Review the remaining category 1 duplicate predictions to obtain a stronger precision estimate.
* Re-run the reviewed failure set after prompt changes to measure how many genuine judge errors are recovered.

## Detailed documentation

* [`docs/retrieval-experiments.md`](https://github.com/SherryNazifi/vscode-dupe-mvp/blob/main/docs/retrieval-experiments.md)
* [`docs/judge-evaluation.md`](https://github.com/SherryNazifi/vscode-dupe-mvp/blob/main/docs/judge-evaluation.md)
* [`docs/data-and-ground-truth.md`](https://github.com/SherryNazifi/vscode-dupe-mvp/blob/main/docs/data-and-ground-truth.md)
* [`docs/taxonomy.md`](https://github.com/SherryNazifi/vscode-dupe-mvp/blob/main/docs/taxonomy.md)
* [`docs/results.md`](https://github.com/SherryNazifi/vscode-dupe-mvp/blob/main/docs/results.md)
