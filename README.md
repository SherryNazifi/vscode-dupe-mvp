# vscode-dupe-mvp

An agent that reads a GitHub issue from the `microsoft/vscode` repo, searches over 3,000 others, and identifies the ones describing the same underlying bug.

## The problem

Duplicate issues rarely share wording. Two people hitting the same bug write "Copilot chat is not responding" and "requests fail silently after submit." Basic keyword matching can easily miss that these are describing the same issue.

Comparing every duplicate against every candidate is 800 × 3,236 = 2.6 million pairs, which sending them to an LLM is expensive.

Instead, the pipeline retrieves first and judges second:

1. Embeddings reduce the 2.6 million possible pairs to 4,000 likely candidates.
2. Only those 4,000 pairs are sent to the language model for a final decision.

## Data

The dataset is split into two piles pulled from the VS Code repository.

| Pile | Contents | Count |
| --- | --- | ---: |
| `pile1` | issues labeled `*duplicate` | 800 |
| `pile2` | the canonical issues those point to, plus 3,000 recent non-PR issues | 3,236 |

Ground truth came from two separate sources:

1. **Comment and body scraping** (`find_dupe_refs.py`), searches the body and comments of every pile1 issue for references such as: Duplicate of #12345

This method found 427 duplicate-to-canonical pairs.
2. **GraphQL `MarkedAsDuplicateEvent`** (`fetch_timeline.py`), the structured event GitHub records when a maintainer marks a duplicate. Found 57 pairs.

`merge_ground_truth.py` merges them, deduplicates by *unordered* pair so the two sources do not double-count the same link, drops self-references, and lets the timeline win when the two disagree on direction. A structured GitHub event is more trustworthy than a regex on comment text.

Result: **442 pairs**, of which **397 are checkable**, meaning the duplicate is in `pile1` and its canonical is in `pile2`.

> One important mistake in an earlier version was filtering for the label duplicate instead of *duplicate. The duplicate label is barely used and returned only 358 issues. The actual VS Code triage label is *duplicate, which has more than 29,000 issues. That one-character difference changed the ground truth from 8 usable pairs to 442. 

## Pipeline 

Arm A is the main production pipeline.

**1. Normalize** (`normalize.py`)
The normalization step removes issue-template content that is usually not helpful for finding duplicates, including: HTML comments, `<details>` blocks, fenced code, images, and version and OS lines. The output format is:

{
  "number": 123,
  "title": "Issue title",
  "document": "Issue title + cleaned issue body"
} 

The searchable document is created as: document = title + cleaned body
When normalization removes the entire body, the issue is not dropped. Its title is kept as the document instead.

**2. Embed** (`embed.py`)
All 4,036 documents through `text-embedding-3-small`, batched 500 at a time, truncated to 8,000 tokens. Both piles are stored inside one .npz file with a tag identifying whether each vector belongs to pile1 or pile2. This means the issues do not need to be embedded again every time retrieval is rerun.

**3. Retrieve** (`similarity.py`)
The vectors are first L2-normalized. The pipeline then calculates cosine similarity using one matrix multiplication:
v1 @ v2.T
This calculates all 2.6 million similarities between pile1 and pile2.
For each pile1 issue, the system keeps the five most similar issues from pile2.
The result is:
800 issues × 5 candidates = 4,000 candidate pairs

→ **4,000 candidate pairs.**

**4. Judge** (`judge.py`)
Each candidate pair is sent to gpt-5.4-mini in JSON mode. The model is asked one main question: Are these issues describing the same underlying bug, or are they only related to the same feature area? For every pair, the model returns:

{
  "verdict": true,
  "confident": 0.94,
  "evidence": "Explanation of the shared bug",
  "suggested_action": "close as duplicate"
}

The script is resumable, so if the run crashes halfway through, it can continue without paying again for the pairs that were already processed.

Out of the 4,000 pairs, the judge flagged:

→ **860 flagged as duplicates.**

**5. Filter** (`filter_candidates.py`)
The judge output is filtered using two rules:

1. Remove pairs with confidence below 0.8.
2. Remove pairs where either document contains fewer than 25 non-whitespace characters.

These rules handle different failure modes.

The confidence threshold removes pairs where the model itself is uncertain.

The document-length filter removes pairs where the model sounds confident despite having almost no evidence.

For example, issue #305541 was matched with #305540 at 0.98 confidence because both normalized documents contained the same single meaningless word.

A confidence filter alone would not catch that. The system also needs to check whether the documents contain enough actual information to support the decision.

After filtering, the final output contains:

→ **774 recommendations.**

The system only recommends duplicates. A human still makes the final decision about closing an issue.

## Does it work

The retrieval stage is evaluated using Recall@5 against the 397 checkable ground-truth pairs.
Recall@5 asks:
For each known duplicate, did its actual canonical issue appear anywhere in the five candidates retrieved by the system?
This evaluates retrieval separately from the LLM judge.

That separation matters because if the correct canonical issue never enters the top five, the judge never gets a chance to identify it.

| Arm | Retrieval method | Recall@5 |
| --- | --- | ---: |
| **A: raw text** | embed cleaned title + body, search all of `pile2` | **68.0%** (270/397) |
| B: canonical | rewrite each issue as one bug sentence, then embed | 61.0% (242/397) |
| C: clustering | search only inside the nearest k-means cluster | 55.9% best |
| D: canonical + clustering | both of the above | 46.6% best |



### Arm B: canonicalization

Before embedding, each issue was rewritten into a single sentence stating the underlying bug, on the theory that two reports of the same bug would collapse to nearly identical sentences. For example, two differently written reports could both become something like:
Copilot Chat fails to return a response after the user submits a message. The prompt explicitly told the model to discard code blocks, stack traces, error strings, version numbers, and OS.

I think the instruction was the mistake. Error strings are exactly what makes two reports of one bug recognizable. The prompt threw away the signal it was supposed to preserve. Recall dropped 7 points, so this arm was never sent to gpt-5.4-mini to get judged.

### Arm C: clustering

Arm C used k-means clustering over all 4,036 embedding vectors.
The random seed was fixed at 42.
For each pile1 issue, the system searched only among pile2 issues in the same cluster.

| k | pairs in same cluster | Recall@5 |
| ---: | ---: | ---: |
| 20 | 61.2% | 49.6% |
| 50 | 59.4% | 54.4% |
| 100 | 57.2% | 53.4% |
| 200 | 58.7% | **55.9%** |
| 400 | 56.9% | 55.4% |

Across the different values of k, only around 60% of true duplicate pairs were placed in the same cluster at all. That means around 40% of the correct answers became impossible to retrieve before similarity ranking even started. Clustering introduces a hard ceiling on recall. I was wondering on using HNSW approximate nearest-neighbor search. So that there wouldn't be a hard clusters and if an issues is not in a cluster, it can still get compared. Partitioning the dataset into clusters removed too many valid candidates.

### Arm D

Arm D used the canonicalized vectors from Arm B inside the cluster-based retrieval system from Arm C.

This combined the weaknesses of both approaches:

Canonicalization removed useful technical details.
Clustering made many true matches unreachable.

The best Recall@5 was:

46.6% at k = 100

## What it produces

| Pair | Confidence | Action | Why |
| --- | ---: | --- | --- |
| #313638 → #313639 | 0.999 | close as duplicate | identical title, body, version, commit hash |
| #304056 → #304057 | 0.999 | close as duplicate | identical repro steps and symptom |
| #294142 → #294141 | 0.999 | close as duplicate | identical body about inline suggestions covering code |
| #325093 → #325086 | 0.99 | close as duplicate | same Python `input()` terminal bug |

The complete output is stored in:

judged_armA.jsonl

This file contains the model's verdict for all 4,000 candidate pairs.

The filtered recommendations are stored in:

candidates_filtered_armA.jsonl

This file contains the 774 pairs that passed the confidence and document-quality filters.

### Human review

To evaluate the model's judgments, 40 pairs were manually reviewed and compared against the model's verdict.

The sample was stratified by confidence:

25 high-confidence pairs
12 medium-confidence pairs
3 low-confidence pairs

The labels are stored in:

review_armA.jsonl

All of the following numbers come from the current *duplicate run.

| Band | Agreement |
| --- | ---: |
| high (>= 0.8) | 23/25 = 92% |
| medium (0.5 - 0.8) | 10/12 = 83% |
| low (< 0.5) | 0/3 = 0% |
| **overall** | **33/40 = 82.5%** |

Agreement tracks confidence. When the model was sure it was almost always right, and when it wasn't sure it was wrong every single time. This suggests that the confidence score is useful as a filtering signal.

**What the disagreements looked like**

**Every disagreement went the same direction.** The model said yes, the human said no. There were no cases in this sample where the human identified a duplicate that the model had rejected. The judge's main failure mode is therefore over-matching rather than missing duplicates.

**The two high-confidence misses have the same shape:** one issue is detailed, the other is vague, and the model fills in what the vague one probably means. #5 (confidence 0.91) matched "REMOVE THIS PLEASE" against "STOP THE AI SUGGESTIONS PLEASE." Only one of them mentions AI. #20 (0.91) matched a real, specific bug against a bare template and matched on the detailed side alone. The model infers intent from the rich side and glosses over the underspecified one.

The rest are the familiar absence-of-evidence gap. The entire low band (#7, #10, #36) is blank issue templates, and the model's own evidence field admits it: "effectively empty placeholders, no concrete evidence," correctly hedged at 0.08 to 0.14 confidence.

**The filter catches most of this.** 5 of the 7 disagreements involve a near-empty document and get dropped by `filter_candidates.py` before a human sees them, leaving only #5 and #20. On the pairs that actually ship, agreement is 92%. That is the number describing the product rather than the model. It is close to the high-confidence-band result because the filtered output mostly contains that same type of pair.

## Key decisions

**Retrieve, then judge.** Embeddings are cheap and approximate, LLM calls are expensive and precise. Spend the cheap one on 2.6 million and the expensive one on 4,000.

**Do not trust the label as ground truth.** GitHub's `*duplicate` often links issues with similar symptoms and different root causes. So the judge was asked the narrower question, same underlying bug, and a stratified sample was hand-labeled to see whether the model's answer matched a human's.

**Fix the evaluation before running it.** The prompt and the 0.8 threshold were set before any results were seen and were not tuned afterward. The 92% high-band agreement is a result of that threshold, not a justification found for it later.

**Measure retrieval separately from judgment.** Recall@5 isolates the retrieval stage. If the answer is not in the top 5, the judge's accuracy is irrelevant.

## Limitations

- **The low band is directional, not solid.** The low-confidence sample is too small to support a strong conclusion. Only three low-confidence pairs were available, so 0/3 shows a pattern but is not a reliable measurement. The high- and medium-confidence bands are more meaningful because they contain 25 and 12 examples.
- 442 ground-truth pairs are a subset of real vscode duplicates, not all of them. Recall is measured against what could be recovered, not against truth.
- Normalization is hand-tuned to the vscode issue template and will not transfer to another repo without rework.
- The pipeline runs as a sequence of manual script invocations.
- The judge can over-match when one issue is detailed and the other is vague.

## Next

1. Push the judge toward abstaining when one side of a pair is underspecified, since that is where both high-confidence misses came from.
2. Hybrid retrieval: combine embeddings with lexical matching on error strings, Arm B showed how important those details are by performing worse when they were removed.
3. Support distinct matching modes: exact same bug versus same root cause.