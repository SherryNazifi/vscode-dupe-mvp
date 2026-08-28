"""Bucket-aware scoring for retrieval and the category 3 judge.

Scores the same runs two ways:

  strict   only the bucket's designated master counts as correct
  lenient  any member of the true canonical's bucket counts as correct

The gap between them is the cost of single-canonical ground truth: it is the
share of decisions that are defensible duplicate calls but get marked wrong
because they name a sibling instead of the one issue the label happens to hold.

Metrics produced:
  retrieval recall@5   strict / lenient
  retrieval recall@20  strict / lenient
  judge accuracy k=5   strict / lenient
  judge accuracy k=20  strict / lenient

Strict and lenient are reported with SEPARATE denominators on purpose. A row can
be unscoreable strictly (the master is not in the retrieval corpus, so it could
never be found or picked) while still scoreable leniently (some other bucket
member is in the corpus).

Definitions used, stated explicitly because they drive every number:
  target bucket   the bucket containing the query's true canonical
  strict hit      the target bucket's designated master is in top-k / was picked
  lenient hit     some issue in top-k / the picked issue is a member of the
                  target bucket, excluding the query issue itself (a self-match
                  is not evidence of anything)

Usage:
  score_bucket_metrics.py
  score_bucket_metrics.py --judge-k5 evaluation-top5-v2.jsonl --label "gated run"

Re-run after prompt or input-gate changes and compare the same eight numbers.
"""
# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))

import argparse
import json
from collections import Counter

CATEGORY = 3


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reverse-map", default="reverse_map_clean.jsonl")
    p.add_argument("--buckets", default="buckets_clean.jsonl")
    p.add_argument("--candidates", default="evaluation-candidates.jsonl",
                   help="retrieval candidates; top-k is sliced from each row")
    p.add_argument("--judge-k5", default="evaluation-top5.jsonl")
    p.add_argument("--judge-k20", default="evaluation-top20.jsonl")
    p.add_argument("--corpus", default="norm-pile2.jsonl",
                   help="issues that retrieval can actually return")
    p.add_argument("--label", default="current run",
                   help="name for this run, printed in the header")
    return p.parse_args()


def pct(num, den):
    return f"{100 * num / den:5.1f}%" if den else "  n/a "


def main():
    args = parse_args()

    reverse = load_jsonl(args.reverse_map)
    bucket_of = {r["issue"]: r["bucket_id"] for r in reverse}
    members_of = {}
    for r in reverse:
        members_of.setdefault(r["bucket_id"], set()).add(r["issue"])
    master_of = {r["bucket_id"]: r["issue"] for r in reverse if r["is_master"]}

    corpus = {r["number"] for r in load_jsonl(args.corpus)}
    records = [r for r in load_jsonl(args.candidates) if r["category"] == CATEGORY]
    judge = {
        5: {r["issue"]: r for r in load_jsonl(args.judge_k5)
            if r["category"] == CATEGORY},
        20: {r["issue"]: r for r in load_jsonl(args.judge_k20)
             if r["category"] == CATEGORY},
    }

    # ---- sanity checks on the mapping itself --------------------------------
    problems = []
    for bid, mem in members_of.items():
        if bid not in master_of:
            problems.append(f"bucket {bid} has no designated master")
        elif master_of[bid] not in mem:
            problems.append(f"bucket {bid} master #{master_of[bid]} is not a member")
    multi_master = [bid for bid, n in
                    Counter(r["bucket_id"] for r in reverse if r["is_master"]).items()
                    if n > 1]
    for bid in multi_master:
        problems.append(f"bucket {bid} has more than one master")

    # ---- classify every row once --------------------------------------------
    # rows[i] = dict with everything scoring needs, or an exclusion reason
    rows, excluded = [], Counter()
    unmapped_canonicals, masters_outside_corpus, master_is_query = [], [], []
    master_is_canonical = 0

    for rec in records:
        q = rec["number"]
        truths = rec.get("true_canonical") or []
        if not truths:
            excluded["no true canonical recorded"] += 1
            continue

        mapped = [t for t in truths if t in bucket_of]
        if not mapped:
            excluded["true canonical not in reverse map (edge audited out)"] += 1
            unmapped_canonicals.extend(truths)
            continue
        if len(mapped) < len(truths):
            unmapped_canonicals.extend(t for t in truths if t not in bucket_of)

        # target bucket(s): where the true canonical lives
        target_buckets = {bucket_of[t] for t in mapped}
        target_members = set()
        for b in target_buckets:
            target_members |= members_of[b]
        target_members.discard(q)          # a self-match proves nothing

        masters = {master_of[b] for b in target_buckets if b in master_of}
        if not masters:
            excluded["target bucket has no resolvable master"] += 1
            continue

        # A row is scoreable STRICTLY only if a master could appear at all.
        # Two separate ways that fails, tracked apart because they mean
        # different things:
        #   master IS the query   -> strict is undefined, not merely unavailable
        #   master not in corpus  -> retrieval could never return it
        masters_in_corpus = {m for m in masters if m in corpus and m != q}
        strict_ok = bool(masters_in_corpus)
        if not strict_ok:
            if any(m == q for m in masters):
                master_is_query.append(q)
            else:
                masters_outside_corpus.extend(sorted(masters))

        # ...and LENIENTLY only if some bucket member could appear.
        members_in_corpus = {m for m in target_members if m in corpus}
        lenient_ok = bool(members_in_corpus)

        if not strict_ok and not lenient_ok:
            excluded["no bucket member is in the retrieval corpus"] += 1
            continue

        if masters == set(mapped):
            master_is_canonical += 1

        rows.append({
            "query": q,
            "masters": masters_in_corpus,
            "members": members_in_corpus,
            "strict_scoreable": strict_ok,
            "lenient_scoreable": lenient_ok,
            "candidates": rec["candidates"],
        })

    # ---- score ---------------------------------------------------------------
    results = {}
    unresolved_picks = Counter()
    no_pick = Counter()

    # matched[metric] = (strict_hits, lenient_hits, den) over rows scoreable BOTH
    # ways, so the strict->lenient gap is a like-for-like comparison. The headline
    # table uses independent denominators as specified; percentages there are not
    # directly subtractable when the denominators differ.
    matched = {}

    for k in (5, 20):
        topk_hits_s = topk_hits_l = den_s = den_l = 0
        j_hits_s = j_hits_l = j_den_s = j_den_l = 0
        m_ret_s = m_ret_l = m_jud_s = m_jud_l = m_den = 0

        for row in rows:
            both = row["strict_scoreable"] and row["lenient_scoreable"]
            topk = {c["number"] for c in row["candidates"][:k]}
            hit_s = bool(row["masters"] & topk)
            hit_l = bool(row["members"] & topk)

            if row["strict_scoreable"]:
                den_s += 1
                topk_hits_s += hit_s
            if row["lenient_scoreable"]:
                den_l += 1
                topk_hits_l += hit_l
            if both:
                m_den += 1
                m_ret_s += hit_s
                m_ret_l += hit_l

            jr = judge[k].get(row["query"])
            if jr is None:
                no_pick[k] += 1
                continue
            picked = jr.get("picked_canonical")
            if picked is not None and picked not in bucket_of and picked not in corpus:
                # a pick we cannot resolve at all: counts as a miss, but flag it
                unresolved_picks[k] += 1

            jhit_s = picked is not None and picked in row["masters"]
            jhit_l = picked is not None and picked in row["members"]
            if row["strict_scoreable"]:
                j_den_s += 1
                j_hits_s += jhit_s
            if row["lenient_scoreable"]:
                j_den_l += 1
                j_hits_l += jhit_l
            if both:
                m_jud_s += jhit_s
                m_jud_l += jhit_l

        results[f"retrieval recall@{k}"] = ((topk_hits_s, den_s), (topk_hits_l, den_l))
        results[f"judge accuracy k={k}"] = ((j_hits_s, j_den_s), (j_hits_l, j_den_l))
        matched[f"retrieval recall@{k}"] = (m_ret_s, m_ret_l, m_den)
        matched[f"judge accuracy k={k}"] = (m_jud_s, m_jud_l, m_den)

    # ---- report --------------------------------------------------------------
    print(f"Bucket-aware scoring — {args.label}")
    print(f"  buckets   : {args.buckets} / {args.reverse_map} "
          f"({len(members_of)} buckets, {len(reverse)} members)")
    print(f"  candidates: {args.candidates}")
    print(f"  judge     : {args.judge_k5} (k=5), {args.judge_k20} (k=20)")
    print(f"  corpus    : {args.corpus} ({len(corpus)} issues)")

    print(f"\nRows: {len(records)} considered, {len(rows)} scoreable, "
          f"{sum(excluded.values())} excluded")
    for reason, n in excluded.most_common():
        print(f"  excluded {n:3d}  {reason}")
    n_strict = sum(1 for r in rows if r["strict_scoreable"])
    n_lenient = sum(1 for r in rows if r["lenient_scoreable"])
    print(f"  of the scoreable rows: {n_strict} strict-scoreable, "
          f"{n_lenient} lenient-scoreable")
    if n_strict != n_lenient:
        print(f"    ({n_lenient - n_strict} row(s) scoreable only leniently: the "
              f"master is outside the corpus but a sibling is in it)")

    order = ["retrieval recall@5", "retrieval recall@20",
             "judge accuracy k=5", "judge accuracy k=20"]

    print(f"\nIndependent denominators (a row is counted only where it is scoreable)")
    print(f"{'metric':<24}{'strict':>16}{'lenient':>16}{'gap':>10}")
    print("-" * 66)
    for name in order:
        (hs, ds), (hl, dl) = results[name]
        s, l = f"{hs}/{ds} {pct(hs, ds)}", f"{hl}/{dl} {pct(hl, dl)}"
        gap = (100 * hl / dl - 100 * hs / ds) if ds and dl else 0.0
        print(f"{name:<24}{s:>16}{l:>16}{gap:>9.1f}pp")
    if any(results[n][0][1] != results[n][1][1] for n in order):
        print("  note: denominators differ, so the gap column mixes a scoring change "
              "with a\n        population change and can go negative. Use the matched "
              "table below\n        to read the true strict->lenient effect.")

    print(f"\nMatched denominator (rows scoreable BOTH ways)")
    print(f"{'metric':<24}{'strict':>16}{'lenient':>16}{'gap':>10}")
    print("-" * 66)
    for name in order:
        hs, hl, den = matched[name]
        s, l = f"{hs}/{den} {pct(hs, den)}", f"{hl}/{den} {pct(hl, den)}"
        gap = (100 * hl / den - 100 * hs / den) if den else 0.0
        print(f"{name:<24}{s:>16}{l:>16}{gap:>9.1f}pp")

    print("\nSanity checks")
    if problems:
        for p in problems:
            print(f"  FAIL  {p}")
    else:
        print(f"  ok    every bucket has exactly one master and it is a member")
    if unmapped_canonicals:
        u = sorted(set(unmapped_canonicals))
        print(f"  note  {len(u)} true canonical(s) absent from the reverse map: "
              f"{u[:8]}{' ...' if len(u) > 8 else ''}")
    else:
        print("  ok    every true canonical resolves to a bucket")
    if masters_outside_corpus:
        u = sorted(set(masters_outside_corpus))
        print(f"  note  {len(u)} designated master(s) outside the corpus, so those "
              f"rows are lenient-only: {u[:8]}{' ...' if len(u) > 8 else ''}")
    else:
        print("  ok    every designated master is in the retrieval corpus")
    if master_is_query:
        print(f"  note  {len(master_is_query)} row(s) where the query IS its bucket's "
              f"master, so strict is undefined: {sorted(master_is_query)}")
    print(f"  info  master == true canonical on {master_is_canonical}/{len(rows)} "
          f"scoreable rows; strict scoring can only differ from canonical-based "
          f"scoring on the other {len(rows) - master_is_canonical}")

    # Lenient can only beat strict when a target bucket has MORE THAN ONE member
    # inside the retrieval corpus. If every bucket contributes exactly one
    # corpus-visible member, lenient is mathematically identical to strict and a
    # 0.0pp gap says nothing about the judge. Surface that up front.
    reach = Counter(len(r["members"]) for r in rows)
    multi = sum(n for size, n in reach.items() if size > 1)
    print(f"  info  target-bucket members inside the corpus: "
          f"{dict(sorted(reach.items()))}")
    if multi == 0:
        print("  WARN  every target bucket has exactly ONE member in the corpus, so\n"
              "        lenient scoring is identical to strict BY CONSTRUCTION and the\n"
              "        0.0pp gap is not a finding about the judge. Bucket siblings are\n"
              "        duplicates and live in pile1; only the canonical is in pile2.\n"
              "        To make lenient meaningful, the corpus must contain siblings.")
    else:
        print(f"  info  {multi} row(s) have >1 corpus-visible bucket member, so lenient "
              f"can diverge from strict there")
    for k in (5, 20):
        if no_pick[k]:
            print(f"  note  k={k}: {no_pick[k]} scoreable row(s) had no judge output")
        if unresolved_picks[k]:
            print(f"  WARN  k={k}: {unresolved_picks[k]} picked canonical(s) resolve "
                  f"to neither a bucket nor the corpus (scored as misses)")
    if not any(unresolved_picks.values()):
        print("  ok    every picked canonical resolves to a bucket or the corpus")


if __name__ == "__main__":
    main()
