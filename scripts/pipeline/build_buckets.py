# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json
from collections import Counter, defaultdict

# Turn the pairwise ground truth into duplicate BUCKETS.
#
# Each edge {issue, canonical} is undirected; every connected component is one
# bucket, so A->B and B->C put A, B and C together. This is the equivalence-class
# representation the review kept asking for: scoring against a single named
# canonical marks a judge wrong for picking any other valid member of the class.
#
# Master selection, in order:
#   1. the member named as `canonical` most often within the bucket
#   2. tie -> the one backed by a GitHub timeline event (MarkedAsDuplicateEvent)
#      rather than only a body/comment regex match
#   3. still tied -> lowest issue number (oldest), for determinism
# The reason is recorded per bucket.

# Usage: build_buckets.py [ground_truth.jsonl]
# Output names derive from the input, so the full and bad-pair-filtered variants
# can coexist:
#   ground_truth.jsonl        -> buckets.jsonl / reverse_map.jsonl
#   ground_truth_clean.jsonl  -> buckets_clean.jsonl / reverse_map_clean.jsonl
import sys

GT_FILE = sys.argv[1] if len(sys.argv) > 1 else "ground_truth.jsonl"
_suffix = "_clean" if "clean" in _os.path.basename(GT_FILE) else ""
DOCS = ("norm-pile1.jsonl", "norm-pile2.jsonl")
BUCKETS_FILE = f"buckets{_suffix}.jsonl"
REVERSE_FILE = f"reverse_map{_suffix}.jsonl"

TIMELINE_SOURCES = ("timeline", "comment+timeline")

# Manual master overrides, keyed by a MEMBER issue number rather than a bucket id
# (bucket ids are positional and shift when the edge set changes). Use when the
# automatic rules produce an arbitrary answer — typically a wide tie where every
# candidate has the same assignment count.
#
#   member issue -> (master issue, reason)
MASTER_OVERRIDES = {
    301802: (301011,
             "manual override: maintainer's designated canonical. The automatic "
             "rules could not reach it — a 9-way tie at 2 canonical assignments "
             "made the pick arbitrary, and #301011 is not the winner by "
             "assignment count in either edge set (1 in the full ground truth, 0 "
             "after bad-pair filtering). Maintainer choice takes precedence over "
             "link-frequency heuristics"),
}


def load_jsonl(path):
    return [json.loads(l) for l in open(path) if l.strip()]


# --- union-find ---------------------------------------------------------------
parent = {}


def find(x):
    parent.setdefault(x, x)
    root = x
    while parent[root] != root:
        root = parent[root]
    while parent[x] != root:          # path compression
        parent[x], x = root, parent[x]
    return root


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra


edges = load_jsonl(GT_FILE)
for e in edges:
    union(e["issue"], e["canonical"])

# --- group members by component ----------------------------------------------
components = defaultdict(set)
for node in list(parent):
    components[find(node)].add(node)

# how often each issue was named canonical, and by which sources
canon_count = Counter()
canon_sources = defaultdict(set)
for e in edges:
    canon_count[e["canonical"]] += 1
    canon_sources[e["canonical"]].add(e.get("source", ""))

docs = {}
for path in DOCS:
    for r in load_jsonl(path):
        docs.setdefault(r["number"], r)


def title_of(num):
    return (docs.get(num) or {}).get("title", "")


def pick_master(members):
    """Return (master, reason)."""
    for member, (master, reason) in MASTER_OVERRIDES.items():
        if member in members:
            if master not in members:
                raise SystemExit(
                    f"override master #{master} is not in the bucket containing "
                    f"#{member}; members: {sorted(members)}")
            return master, reason

    counts = {m: canon_count.get(m, 0) for m in members}
    top = max(counts.values())
    if top == 0:
        # no member was ever named canonical (cannot happen for a real edge, but
        # keep the branch honest rather than crashing)
        master = min(members)
        return master, "no member was ever named canonical; picked lowest issue number"

    tied = sorted([m for m, c in counts.items() if c == top])
    if len(tied) == 1:
        return tied[0], (f"named canonical {top} time(s), more than any other member "
                         f"of the bucket")

    timeline_backed = [m for m in tied
                       if any(s in TIMELINE_SOURCES for s in canon_sources[m])]
    if len(timeline_backed) == 1:
        return timeline_backed[0], (
            f"tied at {top} canonical assignment(s) with "
            f"{', '.join('#' + str(t) for t in tied if t != timeline_backed[0])}; "
            f"broke tie on GitHub timeline event over comment/body regex")
    if len(timeline_backed) > 1:
        master = min(timeline_backed)
        return master, (
            f"tied at {top} canonical assignment(s) among "
            f"{', '.join('#' + str(t) for t in timeline_backed)}, all timeline-backed; "
            f"broke tie on lowest issue number")
    master = tied[0]
    return master, (
        f"tied at {top} canonical assignment(s) among "
        f"{', '.join('#' + str(t) for t in tied)}, none timeline-backed; "
        f"broke tie on lowest issue number")


buckets = []
for i, root in enumerate(sorted(components, key=lambda r: min(components[r])), 1):
    members = sorted(components[root])
    master, reason = pick_master(members)
    buckets.append({
        "bucket_id": f"B{i:04d}",
        "size": len(members),
        "members": members,
        "master": master,
        "master_title": title_of(master),
        "master_reason": reason,
        "master_canonical_count": canon_count.get(master, 0),
        "master_sources": sorted(canon_sources.get(master, [])),
    })

with open(BUCKETS_FILE, "w") as f:
    for b in buckets:
        f.write(json.dumps(b, ensure_ascii=False) + "\n")

with open(REVERSE_FILE, "w") as f:
    for b in buckets:
        for m in b["members"]:
            f.write(json.dumps({
                "issue": m,
                "bucket_id": b["bucket_id"],
                "is_master": m == b["master"],
            }, ensure_ascii=False) + "\n")

# --- report -------------------------------------------------------------------
in_bucket = {m for b in buckets for m in b["members"]}
print(f"{len(edges)} edges -> {len(buckets)} buckets covering {len(in_bucket)} issues")
sizes = Counter(b["size"] for b in buckets)
print("bucket size distribution: " +
      ", ".join(f"{s}:{n}" for s, n in sorted(sizes.items())))

print("\nTop 5 largest buckets:")
for b in sorted(buckets, key=lambda b: (-b["size"], b["bucket_id"]))[:5]:
    print(f"\n  {b['bucket_id']}  size={b['size']}  master #{b['master']}")
    print(f"    reason: {b['master_reason']}")
    for m in b["members"]:
        mark = "*" if m == b["master"] else " "
        print(f"    {mark} #{m}  {title_of(m)[:78]}")

pile_nums = set()
for path in DOCS:
    pile_nums |= {r["number"] for r in load_jsonl(path)}
orphans = pile_nums - in_bucket
print(f"\npile1+pile2 unique issues: {len(pile_nums)}")
print(f"  in a bucket    : {len(pile_nums & in_bucket)}")
print(f"  in no bucket   : {len(orphans)} "
      f"({100 * len(orphans) / len(pile_nums):.1f}%)")
print(f"\n-> {BUCKETS_FILE}, {REVERSE_FILE}")
