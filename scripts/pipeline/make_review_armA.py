# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json, random

random.seed(42)   # reproducible sample

# Target band mix for the 40-pair review (arm A judged pairs).
# low is capped by availability; any shortfall spills into medium so high stays fixed.
TARGET_HIGH = 25
TARGET_MED  = 10
TARGET_LOW  = 5
JUDGED = "judged_armA.jsonl"
OUT    = "review_armA.jsonl"


def load_docs(path):
    d = {}
    for line in open(path):
        line = line.strip()
        if line:
            r = json.loads(line)
            d[r["number"]] = r.get("document") or r.get("title") or ""
    return d


docs1 = load_docs("norm-pile1.jsonl")
docs2 = load_docs("norm-pile2.jsonl")

yes = []
for line in open(JUDGED):
    line = line.strip()
    if line:
        r = json.loads(line)
        if r["verdict"] == "yes" and r.get("confident") is not None:
            yes.append(r)


def band(c):
    c = float(c)
    if c >= 0.8: return "high"
    if c >= 0.5: return "medium"
    return "low"


buckets = {"high": [], "medium": [], "low": []}
for r in yes:
    buckets[band(r["confident"])].append(r)

take_low  = min(TARGET_LOW, len(buckets["low"]))
# spill low shortfall into medium; keep high fixed at TARGET_HIGH
med_target = TARGET_MED + (TARGET_LOW - take_low)
take_med  = min(med_target, len(buckets["medium"]))
take_high = (TARGET_HIGH + TARGET_MED + TARGET_LOW) - take_low - take_med
take_high = min(take_high, len(buckets["high"]))

picks = (random.sample(buckets["high"], take_high)
         + random.sample(buckets["medium"], take_med)
         + random.sample(buckets["low"], take_low))
random.shuffle(picks)   # mix bands so review isn't ordered by confidence

with open(OUT, "w") as out:
    for i, r in enumerate(picks, 1):
        p1, p2 = r["pile1_number"], r["pile2_number"]
        rec = {
            "idx": i,
            "pile1_number": p1,
            "pile2_number": p2,
            "score": r.get("score"),
            "confident": r["confident"],
            "band": band(r["confident"]),
            "model_verdict": r["verdict"],
            "evidence": r.get("evidence"),
            "pile1_document": docs1.get(p1, ""),
            "pile2_document": docs2.get(p2, ""),
            "my_verdict": "",          # <-- you fill: "yes" / "no"
        }
        out.write(json.dumps(rec) + "\n")

print(f"Selected {len(picks)} YES pairs  "
      f"(high={take_high}, medium={take_med}, low={take_low})")
print(f"-> {OUT}  (fill each line's \"my_verdict\": \"yes\"/\"no\")")
