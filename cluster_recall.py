import json
import numpy as np
from sklearn.cluster import KMeans

SEED = 42
KS = [20, 50, 100, 200, 400]

# --- load arm A embeddings ---
d = np.load("embeddings_armA.npz", allow_pickle=True)
emb   = d["embeddings"].astype(np.float32)
nums  = d["numbers"]
piles = d["piles"]

# L2-normalize once -> dot product == cosine similarity
norm = emb / np.linalg.norm(emb, axis=1, keepdims=True)

# index maps
idx_of = {int(n): i for i, n in enumerate(nums)}
pile_of = {int(n): p for n, p in zip(nums, piles)}

pile1_nums = {int(n) for n, p in zip(nums, piles) if p == "pile1"}
pile2_nums = {int(n) for n, p in zip(nums, piles) if p == "pile2"}

# --- checkable ground-truth pairs: dup in pile1, canonical in pile2 ---
gt = [json.loads(l) for l in open("ground_truth.jsonl") if l.strip()]
checkable = []          # (p1_dup, p2_canonical)
for r in gt:
    a, b = r["issue"], r["canonical"]
    p1 = a if a in pile1_nums else (b if b in pile1_nums else None)
    p2 = b if b in pile2_nums else (a if a in pile2_nums else None)
    if p1 is None or p2 is None or p1 == p2:
        continue
    checkable.append((p1, p2))
n_checkable = len(checkable)

print(f"checkable ground-truth pairs: {n_checkable}\n")

rows = []
for k in KS:
    km = KMeans(n_clusters=k, random_state=SEED, n_init=10)
    labels = km.fit_predict(norm)
    label_of = {int(n): int(labels[idx_of[int(n)]]) for n in nums}

    # cluster -> list of pile2 issue numbers
    cluster_pile2 = {}
    for n in pile2_nums:
        cluster_pile2.setdefault(label_of[n], []).append(n)

    co_cluster = 0
    hits = 0
    for p1, p2 in checkable:
        c1 = label_of[p1]
        if label_of[p2] == c1:
            co_cluster += 1
        # rank pile2 members of p1's cluster by cosine, take top-5
        members = cluster_pile2.get(c1, [])
        if not members:
            continue
        v = norm[idx_of[p1]]
        member_idx = np.array([idx_of[m] for m in members])
        sims = norm[member_idx] @ v
        top = member_idx[np.argsort(-sims)[:5]]
        top_nums = {int(nums[i]) for i in top}
        if p2 in top_nums:
            hits += 1

    rows.append((k, co_cluster, hits))

# --- table ---
print(f"{'k':>5} | {'same-cluster':>12} | {'recall@5':>18}")
print("-" * 42)
for k, co, hits in rows:
    print(f"{k:>5} | {co:>4}/{n_checkable} ({co/n_checkable*100:4.1f}%) | "
          f"{hits:>3}/{n_checkable} ({hits/n_checkable*100:4.1f}%)")
