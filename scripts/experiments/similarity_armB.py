# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json
import numpy as np

# Arm B: same top-5 pile1 -> pile2 cosine retrieval as arm A, but over the
# canonical-sentence embeddings instead of the raw-text embeddings.

TOP_K = 5
IN_FILE = "embeddings_armB.npz"
OUT_FILE = "candidates_armB.jsonl"

d = np.load(IN_FILE, allow_pickle=True)
emb   = d["embeddings"].astype(np.float32)
nums  = d["numbers"]
piles = d["piles"]

m1 = piles == "pile1"
m2 = piles == "pile2"
v1, n1 = emb[m1], nums[m1]
v2, n2 = emb[m2], nums[m2]
print(f"pile1: {v1.shape[0]} vectors   pile2: {v2.shape[0]} vectors")

# L2-normalize so dot product == cosine similarity
v1 /= np.linalg.norm(v1, axis=1, keepdims=True)
v2 /= np.linalg.norm(v2, axis=1, keepdims=True)

sims = v1 @ v2.T

k = min(TOP_K, v2.shape[0])
idx_part = np.argpartition(-sims, kth=k - 1, axis=1)[:, :k]
rows = np.arange(sims.shape[0])[:, None]
part_scores = sims[rows, idx_part]
order = np.argsort(-part_scores, axis=1)
top_idx = idx_part[rows, order]

pairs = 0
with open(OUT_FILE, "w") as out:
    for i in range(sims.shape[0]):
        for j in top_idx[i]:
            out.write(json.dumps({
                "pile1_number": int(n1[i]),
                "pile2_number": int(n2[j]),
                "score": float(sims[i, j]),
            }) + "\n")
            pairs += 1

print(f"Total candidate pairs written: {pairs}  -> {OUT_FILE}")
