import json

# Merge the two duplicate-link sources into one deduped ground_truth.jsonl:
#   - ground_truth.jsonl : timeline pairs (from fetch_timeline.py) {issue, canonical}
#   - matched_dupes.json : comment/body pairs (from find_dupe_refs.py) {issue, original}
# Dedup by UNORDERED pair so reverse-direction overlaps collapse. Timeline is
# authoritative on direction when the two sources disagree (conflict flagged).

GT_FILE = "ground_truth.jsonl"


def load_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


timeline = load_jsonl(GT_FILE)                       # {issue, canonical, source:"timeline"}
with open("matched_dupes.json") as f:
    comments = json.load(f)                          # {issue, original, source:"comment"}

# normalize to {issue(dup), canonical, source}
records = [{"issue": r["issue"], "canonical": r["canonical"], "source": "timeline"}
          for r in timeline]
records += [{"issue": r["issue"], "canonical": r["original"], "source": "comment"}
           for r in comments]

merged = {}   # frozenset({a,b}) -> record
for r in records:
    if r["issue"] == r["canonical"]:   # drop self-references (noise)
        continue
    key = frozenset({r["issue"], r["canonical"]})
    if key not in merged:
        merged[key] = dict(r)
        continue
    existing = merged[key]
    same_direction = (existing["issue"] == r["issue"] and
                      existing["canonical"] == r["canonical"])
    # timeline wins direction
    if existing["source"] == "timeline":
        winner = existing
    elif r["source"] == "timeline":
        winner = dict(r)
    else:
        winner = existing
    merged[key] = winner
    srcs = set()
    for x in (existing, r):
        srcs.update(x.get("source", "").replace("+", ",").split(","))
    srcs.discard("")
    winner["source"] = "+".join(sorted(srcs))
    if not same_direction:
        winner["conflict"] = True

out = sorted(merged.values(), key=lambda r: r["issue"], reverse=True)
with open(GT_FILE, "w") as f:
    for r in out:
        f.write(json.dumps(r) + "\n")

print(f"Merged ground truth: {len(out)} unique pairs "
      f"({len(timeline)} timeline + {len(comments)} comment, deduped)")
from collections import Counter
for s, n in Counter(r["source"] for r in out).most_common():
    print(f"  {s}: {n}")
