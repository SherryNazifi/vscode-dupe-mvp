# Retrieval experiments

This document contains the full retrieval investigation for `vscode-dupe-mvp`.

## Evaluation definition

Recall@k asks:

> For each known duplicate issue, did its true canonical appear anywhere among the first k retrieved candidates?

Retrieval and judging are measured separately. If the canonical is absent from the candidate list, the judge cannot recover it.

## Baseline embedding retrieval

The baseline embeds normalized title and body text with `text-embedding-3-small` and ranks pile2 issues using cosine similarity.

| k | Recall |
|---:|---:|
| 1 | 195/397 (49.1%) |
| 5 | 270/397 (68.0%) |
| 10 | 301/397 (75.8%) |
| 20 | 320/397 (80.6%) |
| 50 | 351/397 (88.4%) |

Among the 127 pairs missed at `k = 5`:

| Canonical rank | Count |
|---|---:|
| 6–10 | 31 |
| 11–20 | 19 |
| 21–50 | 31 |
| 51–100 | 16 |
| 101–500 | 19 |
| >500 | 11 |

Median miss rank: 29  
Maximum miss rank: 2,186

The ranking contains many answers below the original top-five cutoff. That raises the retrieval ceiling, but later judge experiments show that deeper candidate lists also add distractors.

## Arm comparison

| Arm | Method | Recall@5 |
|---|---|---:|
| A | raw normalized text embeddings | 68.0% |
| B | LLM canonicalization before embedding | 61.0% |
| C | k-means cluster restriction | 55.9% best |
| D | canonicalization plus clustering | 46.6% best |
| E | BM25 lexical retrieval | 54.9% |

## Arm B: canonicalization

Each issue was rewritten into one sentence describing the underlying bug before embedding.

The prompt instructed the model to discard:

- code blocks
- stack traces
- error strings
- version numbers
- operating-system information

Recall fell from 68.0% to 61.0%.

The likely failure is information loss. Error strings and technical identifiers often provide the most distinctive duplicate signal.

## Arm C: clustering

K-means was run over all 4,036 embedding vectors. Retrieval searched only within the query issue’s assigned cluster.

| k | True pairs in same cluster | Recall@5 |
|---:|---:|---:|
| 20 | 61.2% | 49.6% |
| 50 | 59.4% | 54.4% |
| 100 | 57.2% | 53.4% |
| 200 | 58.7% | 55.9% |
| 400 | 56.9% | 55.4% |

Only around 60% of true pairs landed in the same cluster. Hard clustering therefore made about 40% of answers unreachable before ranking began.

## Arm D: canonicalization plus clustering

This combined the weaknesses of Arms B and C:

- canonicalization removed useful technical evidence
- clustering made valid candidates unreachable

Best recall@5: 46.6% at `k = 100`.

## Arm E: BM25

The tokenizer:

- splits `camelCase`
- splits `snake_case`
- lowercases
- strips punctuation
- drops pure-digit tokens
- drops tokens shorter than two characters

Pile2 was indexed with `bm25s`.

| Method | Recall@5 |
|---|---:|
| Embedding | 270/397 (68.0%) |
| BM25 | 218/397 (54.9%) |
| Symmetric RRF | 263/397 (66.2%) |
| Oracle embedding@5 ∪ BM25@5 | 287/397 (72.3%) |

Additional results:

| Candidate pool | Recall |
|---|---:|
| BM25@10 | 239/397 (60.2%) |
| BM25@20 | 262/397 (66.0%) |
| embedding@20 ∪ BM25@20 | 333/397 (83.9%) |
| embedding@50 ∪ BM25@20 | 357/397 (89.9%) |

Embedding@50 alone reaches 351/397, so BM25@20 adds only six pairs at that depth.

Symmetric RRF underperforms because it gives the weaker BM25 retriever equal influence. BM25 is more useful as a targeted lexical candidate source.

## Audit of embedding@5 misses

The 127 misses were manually classified:

| Tag | Meaning | Count |
|---|---|---:|
| lexical | same bug with rare shared strings or identifiers | 26 |
| hard | same bug without distinctive shared wording | 46 |
| bad_pair | not defensibly the same underlying bug | 55 |

The audit required two passes. Thirty-six labels changed during the second review.

### BM25 recovery by tag

| Tag | Recovered | Rate |
|---|---:|---:|
| lexical | 26/26 | 100% |
| hard | 3/46 | 6.5% |
| bad_pair | 7/55 | 12.7% |

Excluding bad pairs:

```text
29/72 = 40.3% complementary BM25 recovery
```

### Bad-pair patterns

- area-level maintainer links
- catch-all canonicals
- pull-request-to-issue links
- “Testing #NNNNN” links
- vague issues that do not establish the same bug

After removing the 55 bad pairs:

```text
embedding recall@5 = 270/342 = 78.9%
```

## Near-empty analysis

| Normalized body length | Count | % of pile2 |
|---|---:|---:|
| title only | 121 | 3.7% |
| ≤3 words | 217 | 6.7% |
| ≤5 words | 274 | 8.5% |
| ≤10 words | 482 | 14.9% |

Only 8 of the 127 embedding@5 misses have a near-empty canonical. Near-empty input is a real but minor contributor to retrieval failure.

Some issues become empty because normalization strips:

- fenced stack traces
- screenshot-only content
- code blocks containing commands or errors

## Retrieval conclusion

The embedding retriever is the strongest general-purpose arm.

Current guidance:

```text
use embedding top 5 for the present judge baseline
retain deeper rankings for future reranking experiments
use BM25 only as a targeted lexical source
do not use symmetric RRF
do not use hard clustering
```
