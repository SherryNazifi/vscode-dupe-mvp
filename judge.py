import os, json, time
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError, APIConnectionError
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

MODEL = "gpt-5.4-mini"          # change here if the model id differs
CAND_FILE = "candidates.jsonl"
OUT_FILE = "judged_full.jsonl"
PROGRESS_EVERY = 25

SYSTEM = (
    "You are a triage assistant for the microsoft/vscode issue tracker. "
    "You are given two issue documents (title + body). Decide whether they describe "
    "the SAME underlying bug (a true duplicate), not merely the same feature area. "
    "Respond ONLY with a JSON object with exactly these fields:\n"
    '  "verdict": "yes" or "no",\n'
    '  "confident": a number from 0 to 1,\n'
    '  "evidence": a short string citing the concrete overlap or difference,\n'
    '  "suggested_action": a short string (e.g. "close as duplicate", "keep separate", "needs human review").'
)


def load_docs(path):
    docs = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                docs[r["number"]] = r.get("document") or r.get("title") or ""
    return docs


def load_pairs(path):
    pairs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def already_done(path):
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    done.add((r["pile1_number"], r["pile2_number"]))
    return done


def judge_pair(doc1, doc2):
    user = (
        f"ISSUE A (pile1):\n{doc1}\n\n"
        f"ISSUE B (pile2):\n{doc2}\n\n"
        "Are these the same underlying bug?"
    )
    # Retry with exponential backoff on rate limits / transient errors
    delay = 5
    for attempt in range(6):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": user}],
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except RateLimitError as e:
            wait = delay
            # honor Retry-After header if present
            ra = getattr(getattr(e, "response", None), "headers", {}) or {}
            if ra.get("retry-after"):
                wait = float(ra["retry-after"]) + 1
            print(f"    rate limited — sleeping {wait}s (attempt {attempt+1})")
            time.sleep(wait)
            delay = min(delay * 2, 120)
        except (APITimeoutError, APIConnectionError, APIError) as e:
            print(f"    transient API error ({type(e).__name__}) — sleeping {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 120)
    raise RuntimeError("exceeded retry budget for a pair")


docs1 = load_docs("norm-pile1.jsonl")
docs2 = load_docs("norm-pile2.jsonl")
pairs = load_pairs(CAND_FILE)
done = already_done(OUT_FILE)
total = len(pairs)
print(f"{total} candidate pairs, {len(done)} already judged, "
      f"{total - len(done)} to go")

processed = 0
with open(OUT_FILE, "a") as out:
    for i, p in enumerate(pairs, 1):
        key = (p["pile1_number"], p["pile2_number"])
        if key in done:
            continue
        result = judge_pair(docs1.get(key[0], ""), docs2.get(key[1], ""))
        record = {
            "pile1_number": key[0],
            "pile2_number": key[1],
            "score": p.get("score"),
            "verdict": str(result.get("verdict", "")).strip().lower(),
            "confident": result.get("confident"),
            "evidence": result.get("evidence"),
            "suggested_action": result.get("suggested_action"),
        }
        out.write(json.dumps(record) + "\n")
        out.flush()
        processed += 1
        if processed % PROGRESS_EVERY == 0:
            print(f"  judged {i}/{total} (this run: {processed})")

# ---- Final tally over the whole judged file ----
yes = 0
n = 0
with open(OUT_FILE) as f:
    for line in f:
        line = line.strip()
        if line:
            n += 1
            if json.loads(line)["verdict"] == "yes":
                yes += 1
print(f"\nDone. YES verdicts: {yes} / {n}")
