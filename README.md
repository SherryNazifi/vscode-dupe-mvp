# vscode-dupe-mvp

An agent that reads a GitHub issue from the `microsoft/vscode` repository, searches thousands of existing issues, and recommends whether one describes the same underlying bug.

## Why this is hard

Duplicate reports often use different wording. One user may write “Copilot chat is not responding,” while another writes “requests fail silently after submit.” Keyword matching can miss these relationships, while a language model cannot economically compare every new issue against the entire repository.

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

- `duplicate`
- `none`
- `insufficient_information`

## Data

| Pile | Contents | Count |
|---|---|---:|
| `pile1` | issues labeled `*duplicate` | 800 |
| `pile2` | linked canonicals plus 3,000 recent non-PR issues | 3,236 |

Ground truth came from:

- comment and body references such as `Duplicate of #12345`
- GitHub GraphQL `MarkedAsDuplicateEvent` records

After merging and cleaning:

```text
442 recovered links
397 checkable pairs
```

A later manual audit found that 55 of the 397 links did not represent the same underlying bug. They included area-level links, catch-all tracking issues, testing links, and reports too vague to confirm.

## Current results

### Retrieval

| Metric | Result |
|---|---:|
| Embedding recall@1 | 195/397 (49.1%) |
| Embedding recall@5 | 270/397 (68.0%) |
| Embedding recall@20 | 320/397 (80.6%) |
| Embedding recall@50 | 351/397 (88.4%) |
| Adjusted recall@5 after removing 55 audited bad pairs | 270/342 (78.9%) |

BM25 was weaker overall:

| Method | Recall@5 |
|---|---:|
| Embedding | 68.0% |
| BM25 | 54.9% |
| Symmetric RRF | 66.2% |

BM25 recovered all 26 manually identified lexical misses, but its unique contribution shrank as embedding depth increased. It is more useful as a targeted lexical source than as an equal partner in symmetric fusion.

### Multi-candidate judge

| Metric | k=20 | k=5 |
|---|---:|---:|
| Known duplicates with canonical retrieved | 82/100 | 67/100 |
| Exact-correct canonical | 49/100 | 46/100 |
| Correct among retrievable cases | 60% | 69% |
| Wrong canonical selected | 28 | 23 |
| Unlabeled controls flagged duplicate | 66/200 | 59/200 |
| Near-empty issues flagged duplicate | 19/30 | 17/30 |

The control flag rate is not yet a clean false-positive rate because an issue without the `*duplicate` label may still be a genuine unlabeled duplicate.

## Main findings

### Retrieval is not the only bottleneck

Widening retrieval from five to twenty raises the number of available true canonicals, but the judge fails to use most of that extra ceiling. It often selects a plausible distractor instead.

### Top five is the current baseline

Top five is:

- one quarter the judging cost of top twenty
- only three exact-correct decisions worse
- more accurate among cases where the true canonical is available
- less exposed to distractors

A stronger reranker or judge may make deeper retrieval useful later.

### The judge over-matches

The current judge frequently treats “related” as “same bug.” It also almost never abstains on near-empty issues.

Confidence is not a reliable filter in the multi-candidate setting. Correct and incorrect decisions receive similar confidence scores.

### Ground truth must be audited

GitHub duplicate links are useful, but they do not always mean “same underlying bug.” Product evaluation must distinguish true same-bug pairs from broad maintainer relationships.

### Normalization removes useful evidence

About 8.5% of pile2 issues have five or fewer normalized body words. Some were genuinely sparse, but others lost stack traces or screenshots during preprocessing.

## Current decision

The current end-to-end baseline is:

```text
embedding top 5
→ multi-candidate judge
→ one recommendation or abstain
```

Do not widen retrieval, add a reranker, or tune confidence thresholds until the judge’s false-positive behavior is better understood.

## Next step

Manually review 25 of the 59 category 1 issues flagged as duplicates at `k = 5`.

Label each as:

- genuine unlabeled duplicate
- related but not the same bug
- clear false positive
- insufficient evidence

This review will estimate the real false-positive rate and reveal which evidence patterns cause over-matching.

## Detailed documentation

- [`docs/retrieval-experiments.md`](docs/retrieval-experiments.md)
- [`docs/judge-evaluation.md`](docs/judge-evaluation.md)
- [`docs/data-and-ground-truth.md`](docs/data-and-ground-truth.md)
