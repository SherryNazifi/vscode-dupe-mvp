# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json
import numpy as np
import tiktoken
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Arm B: embed the canonical bug-statement sentences (not raw issue text),
# so different reports of the same bug — which canonicalize to near-identical
# sentences — should land close together in vector space.

MODEL = "text-embedding-3-small"
BATCH_SIZE = 500
MAX_TOKENS = 8000
OUTFILE = "embeddings_armB.npz"

client = OpenAI()
ENC = tiktoken.get_encoding("cl100k_base")


def truncate_tokens(text):
    toks = ENC.encode(text)
    return text if len(toks) <= MAX_TOKENS else ENC.decode(toks[:MAX_TOKENS])


def load_pile(path, pile_tag):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                # arm B embeds the canonical sentence
                text = (r.get("canonical") or r.get("document")
                        or r.get("title") or f"issue {r['number']}").strip()
                rows.append((r["number"], pile_tag, truncate_tokens(text)))
    return rows


rows = load_pile("canonical-pile1.jsonl", "pile1") + \
       load_pile("canonical-pile2.jsonl", "pile2")
print(f"Loaded {len(rows)} canonical sentences (pile1 + pile2), "
      f"embedding in batches of {BATCH_SIZE}")

numbers = np.array([n for n, _, _ in rows], dtype=np.int64)
piles   = np.array([p for _, p, _ in rows])
texts   = [t for _, _, t in rows]

vectors = []
for start in range(0, len(texts), BATCH_SIZE):
    batch = texts[start:start + BATCH_SIZE]
    resp = client.embeddings.create(model=MODEL, input=batch)
    vectors.extend(d.embedding for d in resp.data)
    print(f"  embedded {min(start + BATCH_SIZE, len(texts))}/{len(texts)}")

embeddings = np.array(vectors, dtype=np.float32)
assert embeddings.shape[0] == len(rows), "vector/row count mismatch"

np.savez(OUTFILE, embeddings=embeddings, numbers=numbers,
         piles=piles, model=np.array(MODEL))

print(f"\nSaved {embeddings.shape[0]} vectors of dim {embeddings.shape[1]} -> {OUTFILE}")
print(f"  pile1: {(piles == 'pile1').sum()}   pile2: {(piles == 'pile2').sum()}")
