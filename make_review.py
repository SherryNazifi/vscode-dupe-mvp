import json, random

random.seed(42)   # reproducible sample

def load_docs(path):
    d={}
    for line in open(path):
        line=line.strip()
        if line:
            r=json.loads(line)
            d[r["number"]]=r.get("document") or r.get("title") or ""
    return d

docs1=load_docs("norm-pile1.jsonl")
docs2=load_docs("norm-pile2.jsonl")

# --- collect YES verdicts, band by confidence ---
yes=[]
for line in open("judged.jsonl"):
    line=line.strip()
    if not line: continue
    r=json.loads(line)
    if r["verdict"]=="yes" and r.get("confident") is not None:
        yes.append(r)

def band(c):
    c=float(c)
    if c>=0.8: return "high"
    if c>=0.5: return "medium"
    return "low"

buckets={"high":[], "medium":[], "low":[]}
for r in yes:
    buckets[band(r["confident"])].append(r)

# target ~1/3 each, but low is capped by availability (7); fill the rest into med/high
TARGET=40
take_low=min(len(buckets["low"]), TARGET//3)          # 7
remaining=TARGET-take_low                              # 33
take_med=min(len(buckets["medium"]), remaining//2)    # ~16
take_high=TARGET-take_low-take_med                    # rest

picks=(random.sample(buckets["low"], take_low)
       + random.sample(buckets["medium"], take_med)
       + random.sample(buckets["high"], take_high))
random.shuffle(picks)   # mix bands so review isn't ordered by confidence

# --- write review.jsonl + print readable ---
with open("review.jsonl","w") as out:
    for i,r in enumerate(picks,1):
        p1,p2=r["pile1_number"],r["pile2_number"]
        rec={
            "idx": i,
            "pile1_number": p1,
            "pile2_number": p2,
            "score": r.get("score"),
            "confident": r["confident"],
            "band": band(r["confident"]),
            "model_verdict": r["verdict"],
            "evidence": r.get("evidence"),
            "pile1_document": docs1.get(p1,""),
            "pile2_document": docs2.get(p2,""),
            "my_verdict": "",          # <-- you fill: "yes" / "no"
        }
        out.write(json.dumps(rec)+"\n")

# console: readable, docs truncated for scanning (full text is in review.jsonl)
def trunc(s,n=900):
    s=s.replace("\n"," ").strip()
    return s if len(s)<=n else s[:n]+" …"

print(f"Selected {len(picks)} YES pairs  "
      f"(low={take_low}, medium={take_med}, high={take_high})\n")
for i,r in enumerate(picks,1):
    p1,p2=r["pile1_number"],r["pile2_number"]
    print("="*90)
    print(f"[{i:>2}]  #{p1} (pile1)  vs  #{p2} (pile2)   "
          f"| model=YES  confident={r['confident']}  band={band(r['confident'])}  "
          f"embed={r.get('score'):.3f}")
    print(f"     evidence: {r.get('evidence')}")
    print(f"  --- PILE1 #{p1} ---\n     {trunc(docs1.get(p1,''))}")
    print(f"  --- PILE2 #{p2} ---\n     {trunc(docs2.get(p2,''))}")
    print(f"     my_verdict: ____")
print("="*90)
print("\nSaved -> review.jsonl  (edit each line's \"my_verdict\": \"yes\"/\"no\", then we can score agreement)")
