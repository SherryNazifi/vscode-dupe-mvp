# Recall@5 for: Arm A (embedding), BM25, RRF fusion, Oracle (emb@5 ∪ bm25@5).
# All evaluated against the same 397 checkable ground-truth pairs.
import os, json
import numpy as np

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
K = 5

# --- embeddings (Arm A) ---
d = np.load(os.path.join(DATA, "embeddings_armA.npz"), allow_pickle=True)
emb   = d["embeddings"].astype(np.float32)
nums  = d["numbers"]
piles = d["piles"]
emb /= np.linalg.norm(emb, axis=1, keepdims=True)
idx_of = {int(n): i for i, n in enumerate(nums)}
pile1  = {int(n) for n, p in zip(nums, piles) if p == "pile1"}
pile2  = {int(n) for n, p in zip(nums, piles) if p == "pile2"}
p2_nums = [int(n) for n, p in zip(nums, piles) if p == "pile2"]
p2_idx  = np.array([idx_of[n] for n in p2_nums])
p2_mat  = emb[p2_idx]

# --- checkable ground truth ---
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

# --- embedding top-K per pile1 ---
emb_top = {}
for p1 in {p for p, _ in checkable}:
    sims = p2_mat @ emb[idx_of[p1]]
    emb_top[p1] = {p2_nums[i] for i in np.argsort(-sims)[:K]}

def load_topk(fname, key):
    out = {}
    for l in open(os.path.join(DATA, fname)):
        if not l.strip():
            continue
        r = json.loads(l)
        out[r["pile1_number"]] = [c["number"] for c in r["candidates"][:K]]
    return out

bm25_top = load_topk("bm25-candidates.jsonl", "score")
rrf_top  = load_topk("rrf-result.jsonl", "rrf_score")

def recall(getter):
    hits = 0
    for p1, p2 in checkable:
        if p2 in getter(p1):
            hits += 1
    return hits

r_emb    = recall(lambda p1: emb_top.get(p1, set()))
r_bm25   = recall(lambda p1: set(bm25_top.get(p1, [])))
r_rrf    = recall(lambda p1: set(rrf_top.get(p1, [])))
r_oracle = recall(lambda p1: emb_top.get(p1, set()) | set(bm25_top.get(p1, [])))

print(f"checkable pairs: {n}\n")
print(f"{'method':<28} {'recall@5':>16}")
print("-" * 46)
for name, h in [("Arm A (embedding)", r_emb),
                ("BM25", r_bm25),
                ("RRF fusion", r_rrf),
                ("Oracle (emb@5 ∪ bm25@5)", r_oracle)]:
    print(f"{name:<28} {h:>4}/{n} ({h/n*100:4.1f}%)")
