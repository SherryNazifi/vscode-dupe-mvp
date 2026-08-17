# Data and ground truth

This document explains how the dataset and duplicate ground truth were constructed.

## Piles

| Pile | Contents | Count |
|---|---|---:|
| `pile1` | issues labeled `*duplicate` | 800 |
| `pile2` | linked canonicals plus 3,000 recent non-PR issues | 3,236 |

The searchable corpus contains 4,036 documents total.

## Label correction

An early version queried the label `duplicate`. That label is rarely used in the VS Code repository and returned only 358 issues.

The correct triage label is:

```text
*duplicate
```

That one-character correction changed the recoverable ground truth from 8 usable pairs to 442.

## Ground-truth sources

### Comment and body references

`find_dupe_refs.py` searches duplicate issue bodies and comments for references such as:

```text
Duplicate of #12345
```

Recovered pairs: 427

### GitHub timeline events

`fetch_timeline.py` retrieves GraphQL `MarkedAsDuplicateEvent` records and writes
them to `timeline_pairs.jsonl`.

Recovered pairs: 57

Timeline events are more structured and reliable than regex extraction from free text.

## Merge rules

`merge_ground_truth.py`:

- reads `timeline_pairs.jsonl` + `matched_dupes.json`, writes `ground_truth.jsonl`
- deduplicates by unordered issue pair
- drops self-references
- lets the timeline event determine direction when sources disagree

Inputs and output are disjoint paths, so the merge is idempotent and re-runnable.
Never point the output back at an input: reading a previous `ground_truth.jsonl`
back in as the timeline source re-labels comment pairs as `timeline`, which then
win the direction tiebreak on every subsequent run.

Final result:

```text
442 unique links
397 checkable pairs
```

A pair is checkable when:

- the duplicate issue is present in pile1
- the canonical issue is present in pile2

## Ground-truth audit

The 127 embedding@5 misses were manually reviewed.

Final labels:

| Tag | Count |
|---|---:|
| lexical | 26 |
| hard | 46 |
| bad_pair | 55 |

The 55 bad pairs included:

- broad area-level maintainer links
- catch-all issues collecting many reports
- pull-request-to-issue links
- testing and tracking links
- queries too vague to establish the same bug

This audit shows that GitHub’s duplicate graph is not identical to the project’s product definition.

The project asks:

> Do these issues describe the same underlying bug?

GitHub links may instead mean:

- related work
- same feature area
- same tracking issue
- same broad symptom
- same maintenance destination

## Adjusted evaluation denominator

Original recall@5:

```text
270/397 = 68.0%
```

After excluding the 55 manually rejected links:

```text
270/342 = 78.9%
```

Both values are useful:

- 68.0% measures agreement with the recovered GitHub link graph
- 78.9% measures recall against the manually defensible same-bug subset

## Category 1 contamination

The judge evaluation includes 200 issues not labeled `*duplicate`.

These are controls, not guaranteed negatives.

Absence of the label does not prove an issue has no duplicate. When the judge flags one, the pair must be manually adjudicated before it can be counted as a false positive.

This is why the top-five control flag rate:

```text
59/200 = 29.5%
```

is an upper bound rather than a final false-positive estimate.

## Data quality limitations

- Duplicate labels are incomplete.
- Maintainer links can represent broader relationships.
- Some linked reports are too vague to verify.
- Normalization can remove stack traces and screenshot-only evidence.
- The 3,236-issue pile2 corpus is not the entire repository history.
- The evaluation reflects the current dataset and definition of same underlying bug.
