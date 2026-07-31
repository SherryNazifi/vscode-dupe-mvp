# Full recall sweep + miss-rank analysis, against all checkable ground-truth pairs.
import os, json
from collections import Counter
import numpy as np

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")

d = np.load(os.path.join(DATA, "embeddings_armA.npz"), allow_pickle=True)
emb   = d["embeddings"].astype(np.float32)
nums  = d["numbers"]
piles = d["piles"]
emb /= np.linalg.norm(emb, axis=1, keepdims=True)
idx_of = {int(n): i for i, n in enumerate(nums)}
pile1  = {int(n) for n, p in zip(nums, piles) if p == "pile1"}
pile2  = {int(n) for n, p in zip(nums, piles) if p == "pile2"}
p2_nums = [int(n) for n, p in zip(nums, piles) if p == "pile2"]
p2_pos  = {num: i for i, num in enumerate(p2_nums)}
p2_mat  = emb[np.array([idx_of[n] for n in p2_nums])]

gt = [json.loads(l) for l in open(os.path.join(DATA, "ground_truth.jsonl")) if l.strip()]
checkable = []
for r in gt:
    a, b = r["issue"], r["canonical"]
    p1 = a if a in pile1 else (b if b in pile1 else None)
    p2 = b if b in pile2 else (a if a in pile2 else None)
    if p1 is None or p2 is None or p1 == p2:
        continue
    checkable.append((p1, p2))
n = len(checkable)

# --- embedding: full rank of the true canonical for each pair (1-indexed) ---
emb_rank = {}   # (p1,p2) -> rank of p2 among pile2 by cosine
emb_top20 = {}  # p1 -> set of top20 pile2 numbers
for p1 in {p for p, _ in checkable}:
    sims = p2_mat @ emb[idx_of[p1]]
    order = np.argsort(-sims)              # descending
    ranks = np.empty(len(order), dtype=int)
    ranks[order] = np.arange(1, len(order) + 1)
    emb_rank[p1] = ranks
    emb_top20[p1] = {p2_nums[i] for i in order[:20]}

def emb_recall(k):
    return sum(1 for p1, p2 in checkable if emb_rank[p1][p2_pos[p2]] <= k)

# --- bm25: top-20 candidates per pile1 (ranked order in file) ---
bm25 = {}
for l in open(os.path.join(DATA, "bm25-candidates.jsonl")):
    if not l.strip():
        continue
    r = json.loads(l)
    bm25[r["pile1_number"]] = [c["number"] for c in r["candidates"]]

def bm25_recall(k):
    return sum(1 for p1, p2 in checkable if p2 in set(bm25.get(p1, [])[:k]))

# --- ceiling: emb@20 ∪ bm25@20 ---
def ceiling_recall():
    h = 0
    for p1, p2 in checkable:
        if p2 in emb_top20.get(p1, set()) | set(bm25.get(p1, [])[:20]):
            h += 1
    return h

print(f"checkable pairs: {n}\n")
print("EMBEDDING")
for k in (1, 5, 10, 20, 50):
    h = emb_recall(k)
    print(f"  recall@{k:<3} {h:>3}/{n} ({h/n*100:5.1f}%)")
print("\nBM25")
for k in (5, 10, 20):
    h = bm25_recall(k)
    print(f"  recall@{k:<3} {h:>3}/{n} ({h/n*100:5.1f}%)")
h = ceiling_recall()
print(f"\nCEILING (emb@20 ∪ bm25@20)  {h}/{n} ({h/n*100:.1f}%)")

# --- rank distribution of canonical for pairs embedding MISSES at top-5 ---
missed = [(p1, p2, emb_rank[p1][p2_pos[p2]]) for p1, p2 in checkable
          if emb_rank[p1][p2_pos[p2]] > 5]
print(f"\nembedding top-5 misses: {len(missed)} pairs — where the canonical actually ranks:")
buckets = [("6-10", 6, 10), ("11-20", 11, 20), ("21-50", 21, 50),
           ("51-100", 51, 100), ("101-500", 101, 500), (">500", 501, 10**9)]
for label, lo, hi in buckets:
    c = sum(1 for *_, rk in missed if lo <= rk <= hi)
    bar = "#" * c
    print(f"  rank {label:<8} {c:>3}  {bar}")
ranks_only = sorted(rk for *_, rk in missed)
print(f"\n  median miss rank: {ranks_only[len(ranks_only)//2]}   "
      f"max: {ranks_only[-1]}")
