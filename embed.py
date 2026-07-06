import os, json
import numpy as np
import tiktoken
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

MODEL = "text-embedding-3-small"
BATCH_SIZE = 500                 # inputs per request -> few requests total
MAX_TOKENS = 8000                # safely under the model's 8192-token hard limit
OUTFILE = "embeddings.npz"

# Reads OPENAI_API_KEY from the environment automatically
client = OpenAI()
ENC = tiktoken.get_encoding("cl100k_base")   # encoding used by text-embedding-3-*


def truncate_tokens(text):
    toks = ENC.encode(text)
    if len(toks) <= MAX_TOKENS:
        return text
    return ENC.decode(toks[:MAX_TOKENS])


def load_pile(path, pile_tag):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            doc = (r.get("document") or r.get("title") or "").strip()
            if not doc:
                doc = f"issue {r['number']}"        # never send an empty string
            rows.append((r["number"], pile_tag, truncate_tokens(doc)))
    return rows


# ---- Gather both piles into one combined list ----
rows = load_pile("norm-pile1.jsonl", "pile1") + load_pile("norm-pile2.jsonl", "pile2")
print(f"Loaded {len(rows)} documents "
      f"(pile1 + pile2), embedding in batches of {BATCH_SIZE}")

numbers = np.array([n for n, _, _ in rows], dtype=np.int64)
piles   = np.array([p for _, p, _ in rows])
texts   = [t for _, _, t in rows]

# ---- Embed in batches ----
vectors = []
for start in range(0, len(texts), BATCH_SIZE):
    batch = texts[start:start + BATCH_SIZE]
    resp = client.embeddings.create(model=MODEL, input=batch)
    # API preserves input order
    vectors.extend(d.embedding for d in resp.data)
    print(f"  embedded {min(start + BATCH_SIZE, len(texts))}/{len(texts)}")

embeddings = np.array(vectors, dtype=np.float32)
assert embeddings.shape[0] == len(rows), "vector/row count mismatch"

# ---- Save in a reloadable format (no re-embedding needed) ----
np.savez(OUTFILE, embeddings=embeddings, numbers=numbers,
         piles=piles, model=np.array(MODEL))

print(f"\nSaved {embeddings.shape[0]} vectors of dim {embeddings.shape[1]} -> {OUTFILE}")
print(f"  pile1: {(piles == 'pile1').sum()}   pile2: {(piles == 'pile2').sum()}")
print("Reload with:  d = np.load('embeddings.npz'); "
      "d['embeddings'], d['numbers'], d['piles']")
