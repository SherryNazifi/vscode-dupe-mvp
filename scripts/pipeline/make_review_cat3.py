# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json

# Build the category-3 (known_canonical_query) review set: the cases where
# retrieval DID surface the true canonical in the top 20, but the judge still
# failed it. Two failure modes:
#   picked_distractor - judge chose some other candidate
#   picked_none       - judge abstained despite the canonical being present
# These isolate judge error from retrieval error, since retrieval is known-good
# for every row here. Layout mirrors review-cat1-evaluation-top5.jsonl so the
# same review workflow applies.

CANDIDATES = "evaluation-candidates.jsonl"
JUDGED = "evaluation-top20.jsonl"
QUERY_DOCS = "norm-pile1.jsonl"     # the queried issues
CAND_DOCS = "norm-pile2.jsonl"      # the retrieval corpus
OUT_FILE = "review-cat3-evaluation-top20.jsonl"

URL = "https://github.com/microsoft/vscode/issues/{}"


def load_jsonl(path):
    out = []
    for line in open(path):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def load_docs(path):
    return {r["number"]: r for r in load_jsonl(path)}


docs = load_docs(QUERY_DOCS)
docs.update(load_docs(CAND_DOCS))

cands = {r["number"]: r for r in load_jsonl(CANDIDATES) if r["category"] == 3}
judged = {r["issue"]: r for r in load_jsonl(JUDGED) if r["category"] == 3}


def title_of(num):
    return (docs.get(num) or {}).get("title", "")


def doc_of(num):
    return (docs.get(num) or {}).get("document", "")


def rank_score(cand_row, num):
    for c in cand_row["candidates"]:
        if c["number"] == num:
            return c["rank"], c["score"]
    return None, None


rows = []
for num, cr in cands.items():
    if not cr["true_canonical_in_top20"]:
        continue                      # retrieval miss, not a judge failure
    jr = judged.get(num)
    if jr is None:
        continue
    truth = cr["true_canonical"]
    picked = jr["picked_canonical"]
    if picked in truth:
        continue                      # judge got it right
    mode = "picked_none" if picked is None else "picked_distractor"

    picked_rank, picked_score = rank_score(cr, picked) if picked else (None, None)
    # the best-ranked true canonical, i.e. what the judge should have picked
    tc = min(truth, key=lambda t: rank_score(cr, t)[0] or 999)
    tc_rank, tc_score = rank_score(cr, tc)

    rows.append({
        "issue": num,
        "issue_url": URL.format(num),
        "issue_title": cr["title"],
        "issue_doc": doc_of(num),
        "failure_mode": mode,
        # what the judge did
        "picked_canonical": picked,
        "picked_url": URL.format(picked) if picked else None,
        "picked_title": title_of(picked) if picked else None,
        "picked_doc": doc_of(picked) if picked else "",
        "picked_rank": picked_rank,
        "picked_score": picked_score,
        # what it should have done
        "true_canonical": tc,
        "true_canonical_all": truth,
        "true_canonical_url": URL.format(tc),
        "true_canonical_title": title_of(tc),
        "true_canonical_doc": doc_of(tc),
        "true_canonical_rank": tc_rank,
        "true_canonical_score": tc_score,
        "judge_confidence": jr.get("confidence"),
        "judge_evidence": jr.get("evidence"),
        # <-- you fill these in
        "human_verdict": "",
        "human_notes": "",
    })

# hardest first: judge most confident in a wrong answer
rows.sort(key=lambda r: -(r["judge_confidence"] or 0))

with open(OUT_FILE, "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

from collections import Counter
modes = Counter(r["failure_mode"] for r in rows)
print(f"Category 3 judge failures (true canonical was retrieved): {len(rows)}")
for m, n in modes.most_common():
    print(f"  {m}: {n}")
print(f"-> {OUT_FILE}  (fill \"human_verdict\" and \"human_notes\" on each line)")
