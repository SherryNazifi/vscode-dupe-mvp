# vscode-dupe-mvp



An agent that reads a GitHub issue, searches over 3,000 others, and identifies issues describing the same underlying bug.



## The experiment



I tested three retrieval approaches using Recall@5 against 442 known duplicate pairs. Of those, 397 were checkable because the duplicate was in `pile1` and its canonical issue was in `pile2`.

* The canonicalization prompt explicitly told the model to discard error strings.
  That likely contributed to Arm B's lower recall by removing some of the most
  useful matching signals. The prompt was:

    "Given the github issue which is title + body find the underlying bug and 
    state it one plain sentence that should have the problem and if 
    identifiable the cause. Do not mention any formatting, code blocks, stack 
    traces, error-message syntax, version numbers, OS, and the language the 
    report was written in. So that different reports of the same underlying 
    bug should produce almost the same statement no matter how their original 
    repost looks like. The output should one be one sentence."



| Arm               | Retrieval method                                         |            Recall@5 |
| ----------------- | -------------------------------------------------------- | ------------------: |
| **A: raw text**   | Embed cleaned title and body, then search all of `pile2` | **68.0%** (270/397) |
| **B: canonical**  | Convert each issue into one bug sentence, then embed it  |     61.0% (242/397) |
| **C: clustering** | Search only inside the nearest k-means cluster           |         Best: 55.9% |
| **D: canonical + clustering** | Canonical sentences, searched inside the nearest cluster |         Best: 46.6% |



Clustering results:



|   k | A same cluster | A Recall@5 | B same cluster | B Recall@5 |
| --: | -------------: | ---------: | -------------: | ---------: |
|  20 |          61.2% |      49.6% |          58.7% |      44.1% |
|  50 |          59.4% |      54.4% |          52.1% |      44.8% |
| 100 |          57.2% |      53.4% |          52.1% |      46.6% |
| 200 |          58.7% |      55.9% |          46.9% |      43.8% |
| 400 |          56.9% |      55.4% |          48.1% |      46.1% |



Raw normalized text performed best. Canonicalization removed useful details such as component names and error strings. Clustering also reduced recall because many true duplicate pairs were assigned to different clusters.



## What it produced



Example duplicate recommendations:



| Pair              | Confidence | Suggested action   | Why                                                         |
| ----------------- | ---------: | ------------------ | ----------------------------------------------------------- |
| #313638 → #313639 |      0.999 | close as duplicate | identical title, description, version, and commit hash      |
| #304056 → #304057 |      0.999 | close as duplicate | identical reproduction steps and symptom                    |
| #294142 → #294141 |      0.999 | close as duplicate | identical issue body about inline suggestions covering code |
| #325093 → #325086 |       0.99 | close as duplicate | same Python `input()` terminal bug                          |



Each prediction contains:



* verdict

* confidence

* evidence

* suggested action



stored in `judged_armA.jsonl`.



The filter also caught a high-confidence failure:



| Pair              | Confidence | Why it was flagged                            | Why it was removed                                                             |
| ----------------- | ---------: | --------------------------------------------- | ------------------------------------------------------------------------------ |
| #305541 → #305540 |       0.98 | both bodies contain the same meaningless word | each normalized document contains only one word, so there is no bug to compare |



This shows why duplicate filtering needs to consider content quality, not only confidence.



## The numbers



| Stage                             |                                   Count |
| --------------------------------- | --------------------------------------: |
| Issues ingested                   | **4,036** (800 `pile1` + 3,236 `pile2`) |
| Ground-truth duplicate pairs      |                 **442** (397 checkable) |
| Candidate pairs (top-5 retrieval) |                               **4,000** |
| LLM-flagged duplicates            |                                 **860** |
| Candidates after filtering        |                                 **774** |
| Best retrieval Recall@5           |                               **68.0%** |
| Earlier human-review agreement    |                         **78% overall** |
| Earlier high-confidence agreement |                         **94%** (16/17) |



The 40 manually reviewed pairs from the earlier 358-issue run are stored in `review.jsonl`.



## What it does



The system embeds every issue, retrieves the five most similar candidates, and asks an LLM whether each pair describes the same underlying bug rather than merely belonging to the same feature area.



Using embeddings first reduces the search from roughly 2.6 million possible comparisons to just 4,000 LLM evaluations.



## Pipeline



The production path is **Arm A (raw normalized text)**. Arms B and C are retrieval experiments that branch after embedding and were evaluated separately.



1. `fetch_dupes.py` pulls `*duplicate`-labeled issues into `pile1.jsonl` (800 issues).

2. `find_dupe_refs.py` scrapes issue bodies and comments for duplicate references. `fetch_timeline.py` retrieves structured duplicate events through GitHub GraphQL, and `merge_ground_truth.py` merges both sources, removes duplicates and self-references, and produces `ground_truth.jsonl` (442 pairs, 397 checkable).

3. `fetch_pile2.py` builds the search corpus from canonical issues plus 3,000 recent non-PR issues, producing `pile2.jsonl` (3,236 issues).

4. `normalize.py` removes template boilerplate and builds `document = title + cleaned body`.

5. `embed.py` embeds all 4,036 normalized documents using `text-embedding-3-small`.

6. `similarity.py` computes cosine similarity and retrieves the top five `pile2` neighbors for every `pile1` issue, producing 4,000 candidate pairs.

7. `judge.py` evaluates each pair with `gpt-5.4-mini`, returning a verdict, confidence, evidence, and suggested action. It flags 860 pairs as duplicates.

8. `make_review.py` creates a 40-pair stratified sample for manual evaluation.

9. `filter_candidates.py` removes predictions below 0.8 confidence and near-empty documents, leaving 774 recommendations.



Retrieval experiments branch after embedding:



* **Arm B:** `canonicalize.py` → `embed_armB.py` → `similarity_armB.py`

* **Arm C:** `cluster_recall.py` → `cluster_recall_armB.py`



Neither experimental arm was used in the final pipeline because both achieved lower Recall@5 than Arm A.



## Key decisions



### Retrieve, then judge



A brute-force comparison would require roughly 800 × 3,236 ≈ 2.6 million issue pairs. Embeddings narrow the search to the five most promising candidates before the LLM performs the semantic reasoning.



### Evaluate the intended task



GitHub duplicate labels often connect issues with similar symptoms but different underlying bugs. Instead of treating those labels as ground truth, I manually reviewed a stratified sample using the narrower question:



> Do these issues describe the same underlying bug?



### Fix the evaluation before running it



The prompt and 0.8 confidence threshold were fixed before evaluation and were not adjusted afterward.



### Filter weak content



Pairs with fewer than 25 non-whitespace characters are removed because high textual similarity is not meaningful when neither issue contains enough information.



## What I found



* Raw normalized text produced the strongest retrieval recall.

* Canonicalization removed details that embeddings used effectively.

* Clustering reduced recall before ranking even started.

* In the earlier 358-issue run, human agreement increased with confidence: 94% for high-confidence predictions, 81% for medium-confidence predictions, and 29% for low-confidence predictions.

* GitHub often uses a broader duplicate definition than the model.



## Limitations



* The 94% high-confidence agreement result comes from the earlier 358-issue run and is based on only 17 examples.

* Manual evaluation has not yet been repeated on the current 800-issue dataset.

* The 442 ground-truth pairs represent only a subset of VS Code duplicates.

* The canonicalization prompt explicitly instructed the model to discard error strings, which likely contributed to Arm B's lower recall by removing useful retrieval signals.

* Text normalization is tailored to the VS Code issue template.

* The pipeline currently runs manually.

* The system produces recommendations only. A human still decides whether to close issues.



## What I'd do next



2. Support multiple matching modes, including exact same bug and same root cause.

3. Repeat the manual evaluation on the current dataset.

4. Explore hybrid retrieval that combines embeddings with lexical signals such as error strings.