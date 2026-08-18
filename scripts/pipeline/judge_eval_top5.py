# Judge each evaluation issue against its top-5 candidates with gpt-5.4-mini.
# Identical to judge_eval_top20.py apart from TOP_K and the output file.
# Only categories 1, 3, 4 carry candidates. Resumable: appends to the output and
# skips any (category, number) already judged.
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))

import os, json, time, re
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError, APIConnectionError
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

MODEL     = "gpt-5.4-mini"
IN_FILE   = "evaluation-candidates.jsonl"
OUT_FILE  = "evaluation-top5.jsonl"
TOP_K     = 5
PROGRESS_EVERY = 20
QUERY_CHARS = 2500      # truncate long docs to control context/cost
CAND_CHARS  = 1200

PROMPT = (
    "For the given issue and the 5 candidate issues, find the true canonical if there "
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

# --- pick resolution ---------------------------------------------------------
# The model is asked for an issue NUMBER but occasionally returns the candidate's
# RANK instead (e.g. picked_canonical: 14 meaning "rank 14"). Left unvalidated
# that lands a bogus number in the output and scores a correct call as a miss.
# Resolve against the actual candidate list, in order of trustworthiness:
#   1. already a valid candidate number  -> use it
#   2. a #number in the evidence text that IS a candidate -> use that
#   3. a small int matching a rank        -> map rank to number
# Anything else is dropped to None and counted, rather than passed through.
def resolve_picked(raw, evidence, candidates):
    numbers = {c["number"] for c in candidates}
    by_rank = {c["rank"]: c["number"] for c in candidates}
    try:
        picked = int(raw) if raw not in (None, "", "None", "null") else None
    except (ValueError, TypeError):
        return None, "unparseable"
    if picked is None:
        return None, None
    if picked in numbers:
        return picked, None
    for m in re.findall(r"#(\d+)", evidence or ""):
        if int(m) in numbers:
            return int(m), "recovered_from_evidence"
    if picked in by_rank:
        return by_rank[picked], "recovered_from_rank"
    return None, "off_list_dropped"


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
repairs = 0
with open(OUT_FILE, "a") as out:
    for i, rec in enumerate(todo, 1):
        cat, num = rec["category"], rec["number"]
        shown = rec["candidates"][:TOP_K]
        result = judge(num, query_doc(rec), shown)

        verdict = str(result.get("verdict", "")).strip()
        evidence = result.get("evidence")
        # resolve against the TOP_K actually shown, not the full candidate list
        picked, repair = resolve_picked(
            result.get("picked_canonical"), evidence, shown)
        if repair:
            repairs += 1
            print(f"    #{num}: picked_canonical "
                  f"{result.get('picked_canonical')!r} -> {picked} ({repair})")

        record = {
            "issue": num,
            "category": cat,
            "category_name": rec.get("category_name"),
            "verdict": verdict,
            "picked_canonical": picked,
            "confidence": result.get("confidence"),
            "evidence": evidence,
        }
        if repair:
            record["pick_repair"] = repair
        # ground-truth cross-check for category 3
        if cat == 3:
            truth = set(rec.get("true_canonical", []))
            record["true_canonical"] = rec.get("true_canonical")
            record["picked_is_correct"] = picked in truth if picked is not None else False
            rank = rec.get("true_canonical_rank")
            record["true_canonical_in_top5"] = bool(rank) and rank <= TOP_K

        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()
        processed += 1
        if processed % PROGRESS_EVERY == 0:
            print(f"  judged {processed}/{len(todo)}  (last: #{num} cat{cat} -> {verdict})")

print(f"\nDone this run: {processed}. Total in {OUT_FILE}: {len(done) + processed}")
if repairs:
    print(f"Repaired {repairs} off-list picked_canonical value(s) — see pick_repair.")
