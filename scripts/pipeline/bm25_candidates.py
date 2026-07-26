# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json
import bm25s

TOP_K = 20


def load_tokenized(path):
    """Return (numbers, token_lists) preserving file order."""
    numbers, token_lists = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            numbers.append(rec["number"])
            token_lists.append(rec["tokens"])
    return numbers, token_lists


# --- build the BM25 index over pile2 using the pre-tokenized tokens ----------
pile2_numbers, pile2_tokens = load_tokenized("tokenized-pile2.jsonl")
retriever = bm25s.BM25()
retriever.index(pile2_tokens)          # tokens already prepared; no bm25s.tokenize

# --- query with each pile1 issue's own token list ----------------------------
pile1_numbers, pile1_tokens = load_tokenized("tokenized-pile1.jsonl")
k = min(TOP_K, len(pile2_numbers))

written = 0
with open("bm25-candidates.jsonl", "w") as fout:
    for p1_number, query_tokens in zip(pile1_numbers, pile1_tokens):
        # retrieve expects a batch of queries; wrap this one in a list
        idx, scores = retriever.retrieve([query_tokens], k=k)
        candidates = [
            {"number": pile2_numbers[int(j)], "score": float(s)}
            for j, s in zip(idx[0], scores[0])
        ]
        fout.write(json.dumps({
            "pile1_number": p1_number,
            "candidates": candidates,
        }) + "\n")
        written += 1

print(f"bm25-candidates.jsonl: {written} pile1 issues, top-{k} pile2 candidates each")
