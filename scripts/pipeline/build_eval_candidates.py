# Build evaluation-candidates.jsonl — 4 categories of evaluation issues.
#
#   1) 200 random vscode issues NOT labeled *duplicate/duplicate  (fresh fetch + embed)
#   2) 150 close-but-wrong canonicals: 50 pile1 queries x 3 distractors from their top-10
#   3) 100 pile1 queries with a known canonical (50 shared with cat 2)
#   4) 30 near-empty (normalized) pile2 issues, spread across body-length buckets
#
# Categories 1, 3, 4 each carry their top-20 embedding candidates (rank + score).
# Category 3 flags whether the true canonical is inside those 20.
#
# Network stages are cached so reruns don't re-hit GitHub / OpenAI.
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))

import os, json, time, random
import numpy as np
import requests
import tiktoken
from openai import OpenAI
from dotenv import load_dotenv
from normalize_core import make_document

load_dotenv()
random.seed(42)

CAT1_N          = 200
CAT1_POOL_PAGES = 12          # recent issue pages to draw the cat-1 pool from
CAT2_QUERIES    = 50
CAT2_PER_QUERY  = 3
CAT3_N          = 100
CAT4_N          = 30
TOP_N           = 20
EMBED_MODEL     = "text-embedding-3-small"
MAX_TOKENS      = 8000

CAT1_RAW  = "_eval_cat1_raw.jsonl"     # cached fetched issues (raw)
CAT1_NORM = "norm-eval-cat1.jsonl"     # normalized cat-1 docs (like norm-pile*.jsonl)
CAT1_EMB  = "_eval_cat1_emb.npz"       # cached embeddings for cat-1 issues
OUTFILE   = "evaluation-candidates.jsonl"

# --- load pile embeddings ----------------------------------------------------
d = np.load("embeddings_armA.npz", allow_pickle=True)
emb   = d["embeddings"].astype(np.float32)
nums  = d["numbers"]
piles = d["piles"]
emb  /= np.linalg.norm(emb, axis=1, keepdims=True)
idx_of  = {int(n): i for i, n in enumerate(nums)}
p2_nums = [int(n) for n, p in zip(nums, piles) if p == "pile2"]
p2_idx  = np.array([idx_of[n] for n in p2_nums])
p2_mat  = emb[p2_idx]
p1_set  = {int(n) for n, p in zip(nums, piles) if p == "pile1"}
p2_set  = set(p2_nums)

def top_candidates(vec, n=TOP_N, exclude=None):
    """Top-n pile2 issues for a normalized query vector. Returns [(rank, num, score)]."""
    sims = p2_mat @ vec
    order = np.argsort(-sims)
    out, rank = [], 0
    for i in order:
        num = p2_nums[i]
        if exclude is not None and num == exclude:
            continue
        rank += 1
        out.append((rank, num, float(sims[i])))
        if rank >= n:
            break
    return out

# --- ground truth: pile1 query -> true canonical (pile2) ---------------------
gt = [json.loads(l) for l in open("ground_truth.jsonl") if l.strip()]
canon_of = {}   # pile1_query -> set of true canonicals
for r in gt:
    a, b = r["issue"], r["canonical"]
    q  = a if a in p1_set else (b if b in p1_set else None)
    c  = b if b in p2_set else (a if a in p2_set else None)
    if q is None or c is None or q == c:
        continue
    canon_of.setdefault(q, set()).add(c)
queries_with_canon = sorted(canon_of)                     # 396 pile1 queries
print(f"pile1 queries with known canonical: {len(queries_with_canon)}")

# pile2 text lookup for titles/documents
norm_p2 = {json.loads(l)["number"]: json.loads(l)
           for l in open("norm-pile2.jsonl") if l.strip()}
norm_p1 = {json.loads(l)["number"]: json.loads(l)
           for l in open("norm-pile1.jsonl") if l.strip()}

# =============================================================================
# CATEGORY 1 — fetch 200 non-duplicate issues, embed, top-20
# =============================================================================
HEADERS = {
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BASE = "https://api.github.com/repos/microsoft/vscode/issues"

def wait_for_rate_limit(resp):
    if int(resp.headers.get("X-RateLimit-Remaining", 1)) == 0:
        reset = int(resp.headers.get("X-RateLimit-Reset", time.time()))
        wait = max(reset - int(time.time()), 0) + 2
        print(f"  rate limit hit — sleeping {wait}s"); time.sleep(wait)

def is_duplicate_labeled(issue):
    return any("duplicate" in (lb["name"] or "").lower() for lb in issue.get("labels", []))

if not _os.path.exists(CAT1_RAW):
    print("\n=== CAT1: fetching non-duplicate issue pool from GitHub ===")
    pool = []
    for page in range(1, CAT1_POOL_PAGES + 1):
        params = {"state": "all", "per_page": 100, "sort": "created",
                  "direction": "desc", "page": page}
        resp = requests.get(BASE, headers=HEADERS, params=params)
        wait_for_rate_limit(resp)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        kept = 0
        for it in items:
            if "pull_request" in it:               # skip PRs
                continue
            if is_duplicate_labeled(it):            # skip *duplicate / duplicate
                continue
            num = it["number"]
            if num in p1_set or num in p2_set:      # keep them fresh / unseen
                continue
            pool.append({"number": num, "title": it["title"], "body": it.get("body"),
                         "labels": [lb["name"] for lb in it.get("labels", [])]})
            kept += 1
        print(f"  page {page}: +{kept} (pool {len(pool)})")
    if len(pool) < CAT1_N:
        raise SystemExit(f"pool too small ({len(pool)}) — raise CAT1_POOL_PAGES")
    sample = random.sample(pool, CAT1_N)
    with open(CAT1_RAW, "w") as f:
        for r in sample:
            f.write(json.dumps(r) + "\n")
    print(f"  sampled {CAT1_N} -> {CAT1_RAW}")

cat1 = [json.loads(l) for l in open(CAT1_RAW) if l.strip()]

# normalize cat-1 to a persisted file, same {number, title, document} schema as
# norm-pile*.jsonl — this is the exact text that gets embedded and later judged.
with open(CAT1_NORM, "w") as f:
    for r in cat1:
        title = (r.get("title") or "").strip()
        document = make_document(r["title"], r["body"]) or f"issue {r['number']}"
        f.write(json.dumps({"number": r["number"], "title": title,
                            "document": document}, ensure_ascii=False) + "\n")
print(f"normalized cat-1 -> {CAT1_NORM}")
cat1_docs = [json.loads(l) for l in open(CAT1_NORM) if l.strip()]

# embed cat-1 documents (cached)
ENC = tiktoken.get_encoding("cl100k_base")
def truncate(text):
    toks = ENC.encode(text)
    return text if len(toks) <= MAX_TOKENS else ENC.decode(toks[:MAX_TOKENS])

if _os.path.exists(CAT1_EMB):
    cat1_vecs = np.load(CAT1_EMB)["embeddings"].astype(np.float32)
else:
    print("\n=== CAT1: embedding 200 issues via OpenAI ===")
    client = OpenAI()
    docs = [truncate(r["document"]) for r in cat1_docs]
    resp = client.embeddings.create(model=EMBED_MODEL, input=docs)
    cat1_vecs = np.array([e.embedding for e in resp.data], dtype=np.float32)
    np.savez(CAT1_EMB, embeddings=cat1_vecs)
    print(f"  embedded {len(docs)} -> {CAT1_EMB}")
cat1_vecs = cat1_vecs / np.linalg.norm(cat1_vecs, axis=1, keepdims=True)

# =============================================================================
# CATEGORY 2 & 3 — pile1 query sampling (50 shared)
# =============================================================================
cat2_queries = random.sample(queries_with_canon, CAT2_QUERIES)               # 50
remaining    = [q for q in queries_with_canon if q not in set(cat2_queries)]
cat3_queries = cat2_queries + random.sample(remaining, CAT3_N - CAT2_QUERIES)  # 100 (50 shared)

# =============================================================================
# CATEGORY 4 — near-empty pile2 issues, spread across body-length buckets
# =============================================================================
def norm_body(rec):
    doc = rec.get("document", "") or ""; t = rec.get("title", "") or ""
    return (doc[len(t):].strip() if doc.startswith(t) else doc).strip()

near_empty = [n for n, rec in norm_p2.items() if len(norm_body(rec).split()) <= 5]
def bucket(c):
    return "0" if c == 0 else ("4-10" if c <= 10 else ("11-25" if c <= 25 else ">25"))
by_bucket = {}
for n in near_empty:
    by_bucket.setdefault(bucket(len(norm_body(norm_p2[n]))), []).append(n)
# target spread across the buckets that actually exist
targets = {"0": 10, "4-10": 1, "11-25": 10, ">25": 9}
cat4_nums = []
for b, want in targets.items():
    avail = by_bucket.get(b, [])
    cat4_nums += random.sample(avail, min(want, len(avail)))
# top up to 30 if any bucket was short
if len(cat4_nums) < CAT4_N:
    rest = [n for n in near_empty if n not in set(cat4_nums)]
    cat4_nums += random.sample(rest, CAT4_N - len(cat4_nums))
print(f"near-empty pool {len(near_empty)}; cat4 buckets: "
      f"{ {b: len(v) for b, v in by_bucket.items()} }")

# =============================================================================
# WRITE
# =============================================================================
def cand_records(cands):
    return [{"rank": r, "number": n, "score": round(s, 6)} for r, n, s in cands]

records = []

# ---- category 1 ----
for r, vec in zip(cat1, cat1_vecs):
    cands = top_candidates(vec, exclude=r["number"])
    records.append({
        "number": r["number"], "category": 1,
        "category_name": "non_duplicate_control",
        "title": r["title"], "labels": r["labels"],
        "candidates": cand_records(cands),
    })

# ---- category 2 ---- (distractors: top-10, drop true canonical, sample 3)
for q in cat2_queries:
    truth = canon_of[q]
    top10 = top_candidates(emb[idx_of[q]], n=10)
    distractors = [(rk, n, s) for rk, n, s in top10 if n not in truth]
    picked = random.sample(distractors, min(CAT2_PER_QUERY, len(distractors)))
    for rk, n, s in picked:
        rec2 = norm_p2.get(n, {})
        records.append({
            "number": n, "category": 2,
            "category_name": "close_but_wrong_canonical",
            "title": rec2.get("title"),
            "source_pile1_query": q,
            "rank_for_source_query": rk,
            "score_for_source_query": round(s, 6),
        })

# ---- category 3 ---- (pile1 query, top-20, flag true canonical)
for q in cat3_queries:
    truth = canon_of[q]
    cands = top_candidates(emb[idx_of[q]])
    hit_rank = next((rk for rk, n, s in cands if n in truth), None)
    rec1 = norm_p1.get(q, {})
    records.append({
        "number": q, "category": 3,
        "category_name": "known_canonical_query",
        "title": rec1.get("title"),
        "true_canonical": sorted(truth),
        "true_canonical_in_top20": hit_rank is not None,
        "true_canonical_rank": hit_rank,
        "shared_with_category2": q in set(cat2_queries),
        "candidates": cand_records(cands),
    })

# ---- category 4 ---- (near-empty pile2, top-20)
for n in cat4_nums:
    rec = norm_p2[n]
    body = norm_body(rec)
    cands = top_candidates(emb[idx_of[n]], exclude=n)
    records.append({
        "number": n, "category": 4,
        "category_name": "near_empty",
        "title": rec.get("title"),
        "norm_body_chars": len(body),
        "length_bucket": bucket(len(body)),
        "candidates": cand_records(cands),
    })

with open(OUTFILE, "w") as f:
    for rec in records:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# --- summary ---
from collections import Counter
c = Counter(r["category"] for r in records)
print(f"\n=== {OUTFILE}: {len(records)} records ===")
for cat in (1, 2, 3, 4):
    print(f"  category {cat}: {c[cat]}")
cat3 = [r for r in records if r["category"] == 3]
hit = sum(r["true_canonical_in_top20"] for r in cat3)
print(f"  cat3 true canonical in top-20: {hit}/{len(cat3)}")
b = Counter(r["length_bucket"] for r in records if r["category"] == 4)
print(f"  cat4 length buckets: {dict(b)}")
