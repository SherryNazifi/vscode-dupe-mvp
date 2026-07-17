# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json

# Filter the LLM's YES verdicts down to high-confidence, non-empty duplicates.
# Two filters, each catching a different failure mode:
#   1. confidence >= CONF_MIN  — drop the pairs the model itself was unsure about
#   2. neither document near-empty — drop pairs where there's no real content to
#      judge (e.g. "error" vs "bug"); the model can be very confident on these
#      precisely because both docs are empty, so confidence alone won't catch them.

CONF_MIN = 0.8
NEAR_EMPTY_CHARS = 25          # non-whitespace chars below this = near-empty
JUDGED_FILE = "judged_armA.jsonl"
OUT_FILE = "candidates_filtered_armA.jsonl"


def load_docs(path):
    d = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                d[r["number"]] = r.get("document") or r.get("title") or ""
    return d


def near_empty(txt):
    return len("".join((txt or "").split())) < NEAR_EMPTY_CHARS


docs1 = load_docs("norm-pile1.jsonl")
docs2 = load_docs("norm-pile2.jsonl")

yes = []
with open(JUDGED_FILE) as f:
    for line in f:
        line = line.strip()
        if line:
            r = json.loads(line)
            if r["verdict"] == "yes":
                yes.append(r)

kept = []
drop_conf = 0
drop_empty = 0
for r in yes:
    fails_conf = (r.get("confident") or 0) < CONF_MIN
    fails_empty = near_empty(docs1.get(r["pile1_number"], "")) or \
                  near_empty(docs2.get(r["pile2_number"], ""))
    if fails_conf:
        drop_conf += 1
    if fails_empty:
        drop_empty += 1        # reasons overlap; a pair can fail both
    if fails_conf or fails_empty:
        continue
    kept.append(r)

with open(OUT_FILE, "w") as out:
    for r in kept:
        out.write(json.dumps(r) + "\n")

print(f"YES verdicts total          : {len(yes)}")
print(f"Dropped: confidence < {CONF_MIN}   : {drop_conf}")
print(f"Dropped: a doc near-empty   : {drop_empty}   (overlap counted in both)")
print(f"Surviving high-conf, non-empty duplicates: {len(kept)}")
print(f"-> {OUT_FILE}")
