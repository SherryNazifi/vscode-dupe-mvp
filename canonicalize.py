import os, json, time
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError, APIConnectionError
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

MODEL = "gpt-5.4-mini"
PROGRESS_EVERY = 25
SLEEP_BETWEEN = 1.5          # ~40 req/min, well under the tier rate limit

INSTRUCTION = (
    "Given the github issue which is title + body find the underlying bug and "
    "state it one plain sentence that should have the problem and if "
    "identifiable the cause. Do not mention any formatting, code blocks, stack "
    "traces, error-message syntax, version numbers, OS, and the language the "
    "report was written in. So that different reports of the same underlying "
    "bug should produce almost the same statement no matter how their original "
    "repost looks like. The output should one be one sentence."
)

FILES = [
    ("norm-pile1.jsonl", "canonical-pile1.jsonl"),
    ("norm-pile2.jsonl", "canonical-pile2.jsonl"),
]


def load_records(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def already_done(path):
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    done.add(json.loads(line)["number"])
    return done


def canonicalize(document):
    delay = 5
    for attempt in range(12):          # ride out longer rate-limit bursts
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": INSTRUCTION},
                          {"role": "user", "content": document}],
            )
            return resp.choices[0].message.content.strip()
        except RateLimitError as e:
            wait = delay
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
    raise RuntimeError("exceeded retry budget for an issue")


grand_total = 0
grand_processed = 0

for infile, outfile in FILES:
    records = load_records(infile)
    done = already_done(outfile)
    todo = len(records) - len(done)
    grand_total += len(records)
    print(f"\n=== {infile} -> {outfile} : {len(records)} issues, "
          f"{len(done)} already done, {todo} to go ===")

    with open(outfile, "a") as out:
        for i, r in enumerate(records, 1):
            if r["number"] in done:
                continue
            document = (r.get("document") or r.get("title")
                        or f"issue {r['number']}").strip()
            canonical = canonicalize(document)
            record = dict(r)          # keep original norm fields
            record["canonical"] = canonical
            out.write(json.dumps(record) + "\n")
            out.flush()
            time.sleep(SLEEP_BETWEEN)
            grand_processed += 1
            if grand_processed % PROGRESS_EVERY == 0:
                print(f"  [{infile}] {i}/{len(records)}  "
                      f"(this run total: {grand_processed})")

# ---- final counts across both output files ----
print("\n=== Final counts ===")
grand_written = 0
for _, outfile in FILES:
    n = sum(1 for line in open(outfile) if line.strip())
    grand_written += n
    print(f"  {outfile}: {n}")
print(f"  total canonicalized: {grand_written} / {grand_total}")
