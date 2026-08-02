# Judge each evaluation issue against its top-20 candidates with gpt-5.4-mini.
# Only categories 1, 3, 4 carry candidates. Resumable: appends to the output and
# skips any (category, number) already judged.
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))

import os, json, time
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError, APIConnectionError
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

MODEL     = "gpt-5.4-mini"
IN_FILE   = "evaluation-candidates.jsonl"
OUT_FILE  = "evaluation-top20.jsonl"
PROGRESS_EVERY = 20
QUERY_CHARS = 2500      # truncate long docs to control context/cost
CAND_CHARS  = 1200

PROMPT = (
    "For the given issue and the 20 candidate issues, find the true canonical if there "
    "are any. The judgement should be based on if they are the same underlying bug and "
    "not solely in the same category. For example just because both issues are talking "
    'about "terminal" doesn\'t mean that they are the same bug, unless they are talking '
    "about a specific bug in terminal. The output should be a single json object. With "
    "categories: issue, verdict (put duplicate if a same underlying bug was found, put "
    "None if there are no found canonicals, You should pick None over a weak confidence. "
    "Put insufficient information for when the judgement can't be made solely with the "
    "given content, not when there is content for both issues but they don't match), "
    "picked_canonical number (if any), confidence score (from 0 to 1) and a short evidence."
)

# --- document sources --------------------------------------------------------
def load_docs(path):
    out = {}
    for line in open(path):
        line = line.strip()
        if line:
            r = json.loads(line)
            out[r["number"]] = r.get("document") or r.get("title") or ""
    return out

p2_docs   = load_docs("norm-pile2.jsonl")      # candidates + cat-4 queries
p1_docs   = load_docs("norm-pile1.jsonl")      # cat-3 queries
cat1_docs = load_docs("norm-eval-cat1.jsonl")  # cat-1 queries (normalized by the builder)

def query_doc(rec):
    cat, num = rec["category"], rec["number"]
    if cat == 1:
        return cat1_docs.get(num, rec.get("title", ""))
    if cat == 3:
        return p1_docs.get(num, rec.get("title", ""))
    if cat == 4:
        return p2_docs.get(num, rec.get("title", ""))
    return rec.get("title", "")

# --- model call with retry ---------------------------------------------------
def judge(issue_num, issue_doc, candidates):
    lines = [f"ISSUE #{issue_num}:", issue_doc[:QUERY_CHARS], "", "CANDIDATES:"]
    for c in candidates:
        cnum = c["number"]
        lines.append(f"--- candidate #{cnum} (rank {c['rank']}):")
        lines.append((p2_docs.get(cnum, "") or "")[:CAND_CHARS])
    user = (PROMPT + "\n\n" + "\n".join(lines) +
            "\n\nReturn a single JSON object with fields: issue, verdict, "
            "picked_canonical, confidence, evidence. picked_canonical must be one of "
            "the candidate numbers above or null.")
    delay = 5
    for attempt in range(6):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": user}],
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except RateLimitError as e:
            wait = delay
            ra = getattr(getattr(e, "response", None), "headers", {}) or {}
            if ra.get("retry-after"):
                wait = float(ra["retry-after"]) + 1
            print(f"    rate limited — sleeping {wait}s (attempt {attempt+1})")
            time.sleep(wait); delay = min(delay * 2, 120)
        except (APITimeoutError, APIConnectionError, APIError) as e:
            print(f"    transient error ({type(e).__name__}) — sleeping {delay}s")
            time.sleep(delay); delay = min(delay * 2, 120)
    raise RuntimeError(f"exceeded retry budget for issue {issue_num}")

# --- resume ------------------------------------------------------------------
def already_done(path):
    done = set()
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line:
                r = json.loads(line)
                done.add((r["category"], r["issue"]))
    return done

records = [json.loads(l) for l in open(IN_FILE) if l.strip()]
tasks = [r for r in records if r.get("candidates")]        # cat 1,3,4 only
done = already_done(OUT_FILE)
todo = [r for r in tasks if (r["category"], r["number"]) not in done]
print(f"{len(tasks)} judgeable issues (cat 1/3/4), {len(done)} done, {len(todo)} to go")

processed = 0
with open(OUT_FILE, "a") as out:
    for i, rec in enumerate(todo, 1):
        cat, num = rec["category"], rec["number"]
        result = judge(num, query_doc(rec), rec["candidates"])

        verdict = str(result.get("verdict", "")).strip()
        picked = result.get("picked_canonical")
        try:
            picked = int(picked) if picked not in (None, "", "None", "null") else None
        except (ValueError, TypeError):
            picked = None

        record = {
            "issue": num,
            "category": cat,
            "category_name": rec.get("category_name"),
            "verdict": verdict,
            "picked_canonical": picked,
            "confidence": result.get("confidence"),
            "evidence": result.get("evidence"),
        }
        # ground-truth cross-check for category 3
        if cat == 3:
            truth = set(rec.get("true_canonical", []))
            record["true_canonical"] = rec.get("true_canonical")
            record["picked_is_correct"] = picked in truth if picked is not None else False
            record["true_canonical_in_top20"] = rec.get("true_canonical_in_top20")

        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()
        processed += 1
        if processed % PROGRESS_EVERY == 0:
            print(f"  judged {processed}/{len(todo)}  (last: #{num} cat{cat} -> {verdict})")

print(f"\nDone this run: {processed}. Total in {OUT_FILE}: {len(done) + processed}")
