# vscode-dupe-mvp

An agent reads a GitHub issue, searches 3,000 others on its own, and decides which ones are the same underlying bug.

## What it produced

Real duplicate suggestions after the run. Each is a pile1 issue paired
with a pile2 issue the agent found on its own, with the model's confidence,
evidence, and suggested action:

| Pair | Confidence | Suggested action | Why |
|---|---|---|---|
| #303674 → #319783 | 0.97 | close as duplicate | identical error: "Chat took too long to get ready…" |
| #303281 → #322364 | 0.96 | close as duplicate | same exception "RangeError: Invalid string length"; B adds the chat-session serialization stack trace |
| #303450 → #322381 | 0.91 | close as duplicate | identical core error "Server error. Stream terminated" |
| #304531 → #323830 | 0.99 | close as duplicate | identical "Language model unavailable" with no differing detail |

Every one of the 533 flagged pairs has this same shape, with fields: verdict,
confidence (0–1), evidence, suggested action in `judged.jsonl`. The 437 that
survive filtering are in `candidates_filtered.jsonl`.

Note: I marked #303281 → #322364 as "no" during review — B has long reasoning of the cause, A is just the error string repeated. It is the only high-confidence pair I disagreed with while the model is arguably right.

And one of the issues that it got wrong was caught by the filter applied after the confidence treshold:

| Pair | Confidence | Why it's flagged | Why it's dropped |
|---|---|---|---|
| #304494 → #322709 | **0.99** | both issue bodies are just the word "error" — one in English, one in Vietnamese ("Lỗi") | after normalization each document is a single word; there's no bug to compare |

This is the case for filtering on *content*, not just confidence. The model was
99% sure because the two documents were near-identical — but they were
near-identical because both were empty. Confidence is calibrated conditional on
there being something to judge, but when both documents are one word, the score
measures textual similarity instead of judging by the bug similarity.

## The numbers

| Stage | Count |
|---|---|
| Issues ingested | **3,362** (358 duplicate-labeled `pile1` + 3,004 recent non-PR `pile2`) |
| Candidate pairs (top-5 embedding retrieval) | **1,790** |
| Flagged as duplicates by the LLM judge | **533** |
| Hand-judged by me across confidence bands | **40** |
| Agreement with the model — overall | **78%** |
| Agreement — high-confidence (≥0.8) verdicts | **94% (16/17)** |
| Survivors after filtering low-confidence + near-empty | **437** |

The 40 hand-judged pairs that contains my verdicts and notes next to the model's are
in `review.jsonl`. That's the file to open to see where human and model agreed
and where they didn't.

## What it does

It reads an issue from `microsoft/vscode`, then goes looking for its duplicates
without being told where to look. It embeds every candidate issue, retrieves the
handful that are semantically closest, and gives each of those pairs to an LLM
that judges whether they describe the *same underlying bug* and not just the same
feature area. Every judgment comes back as a verdict (yes/no), a confidence
score, the evidence it used, and a suggested action (close as duplicate, keep
separate, needs human review). Used embeddings to make it cheap to search the large space so that the LLM does the reasoning only on the promising candidates

## Pipeline

1. `fetch_dupes.py` — pulls every `duplicate`-labeled issue from vscode →
   `pile1.jsonl` (358 issues, PRs skipped).
2. `find_dupe_refs.py` — scrapes issue bodies + comments for "duplicate of #N"
   / `/duplicate` references. Found 6 canonical issues.
3. `fetch_timeline.py` — queries GitHub's GraphQL API to recover machine-recorded duplicate events and builds the ground-truth dataset. Found 3.
   Merged with the comment refs → **8-pair `ground_truth.jsonl`** (6 + 3 = 9,
   minus one pair found by both methods).
4. `fetch_pile2.py` — builds the candidate pool: every canonical from ground
   truth + 3,000 recent general issues.
5. `normalize.py` — removed HTML comments, `<details>` blocks, code fences,
   version/environment boilerplate. Builds `document = title + cleaned body`;
   keeps title-only if the body is empty. → `norm-pile1/2.jsonl`.
6. `embed.py` — embeds all 3,362 documents with OpenAI `text-embedding-3-small`
   (batched), traceable by issue number + pile tag → `embeddings.npz`.
7. `similarity.py` — cosine similarity, top-5 pile2 neighbors per pile1 issue →
   `candidates.jsonl` (1,790 pairs).
8. `judge.py` — one `gpt-5.4-mini` call per pair, JSON output
   (verdict / confident / evidence / suggested_action), resumable →
   `judged.jsonl`.
9. `make_review.py` — gets 40-pair sample across confidence bands for
   human review → `review.jsonl`.
10. `filter_candidates.py` — drops pairs below 0.8 confidence or with a near-empty document
    (<25 non-whitespace chars) → `candidates_filtered.jsonl` (533 → 437).


## Key decisions

- **Retrieve and then judge** Comparing all 358 × 3,004 possible issue pairs would require about 1 million comparisons. Instead, embeddings narrow the search to just 1,790 candidate pairs before the LLM is called, which reduces the cost.
- **Graded against my own judgment** GitHub duplicate labels turned out to be noisy. Several maintainer-labeled duplicates described similar symptoms but different underlying bugs.
Rather than treating GitHub labels as ground truth, I manually reviewed a stratified sample and compared the model against the actual question that is "Are these describing the same underlying bug?"
- **Confidence threshold not tuned after the result** The confidence threshold (0.8) and prompt were fixed before evaluation and never adjusted afterward to avoid overfitting to the review sample.


## What I found

- Model confidence is well calibrated when these is enough content to judge. Human-model agreement tracks the
  confidence band almost monotonically: 94% high, 81% medium, 29% low. 
- GitHub's definition of "duplicate" is often broader than "same underlying bug." The model consistently applied the narrower definition.

## Limitations

- Accidentally filtered using the duplicate label instead of VS Code's broader *duplicate maintainer label, so the evaluation only covers a small slice of duplicate issues.
- High-confidence evaluation is based on only 17 examples.
- Ground truth contains only 8 canonical duplicate pairs.
- Text normalization is specific to the VS Code issue template.
- Runs manually; no scheduled pipeline.
- Produces recommendations only. A human still decides whether to close issues.

## What I'd do next

1. Evaluate on richer customer support conversations instead of GitHub issues.
2. Support two modes: exact same bug, same root cause
