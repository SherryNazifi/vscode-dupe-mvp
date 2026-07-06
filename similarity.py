import json
import numpy as np

TOP_K = 5
d = np.load("embeddings.npz", allow_pickle=True)
emb    = d["embeddings"].astype(np.float32)
nums   = d["numbers"]
piles  = d["piles"]

# --- split by pile tag ---
m1 = piles == "pile1"
m2 = piles == "pile2"
v1, n1 = emb[m1], nums[m1]
v2, n2 = emb[m2], nums[m2]
print(f"pile1: {v1.shape[0]} vectors   pile2: {v2.shape[0]} vectors")

# --- L2-normalize so dot product == cosine similarity ---
v1 /= np.linalg.norm(v1, axis=1, keepdims=True)
v2 /= np.linalg.norm(v2, axis=1, keepdims=True)

# --- cosine similarity: (pile1 x pile2) matrix ---
sims = v1 @ v2.T                       # shape (358, 3004)

# --- top-K pile2 per pile1 vector ---
k = min(TOP_K, v2.shape[0])
# argpartition for the k largest, then sort those k descending
idx_part = np.argpartition(-sims, kth=k - 1, axis=1)[:, :k]
rows = np.arange(sims.shape[0])[:, None]
part_scores = sims[rows, idx_part]
order = np.argsort(-part_scores, axis=1)
top_idx = idx_part[rows, order]        # (358, k) column indices into pile2

pairs = 0
with open("candidates.jsonl", "w") as out:
    for i in range(sims.shape[0]):
        for j in top_idx[i]:
            record = {
                "pile1_number": int(n1[i]),
                "pile2_number": int(n2[j]),
                "score": float(sims[i, j]),
            }
            out.write(json.dumps(record) + "\n")
            pairs += 1

print(f"Total candidate pairs written: {pairs}  -> candidates.jsonl")
