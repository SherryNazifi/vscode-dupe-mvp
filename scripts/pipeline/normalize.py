# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json
from normalize_core import clean_body, is_near_empty


def normalize_file(infile: str, outfile: str):
    written = 0
    near_empty = 0
    with open(infile) as fin, open(outfile, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            issue = json.loads(line)
            number = issue["number"]
            title = (issue.get("title") or "").strip()
            cleaned = clean_body(issue.get("body"))

            if is_near_empty(cleaned):
                # little/nothing left — keep the title, still keep the issue
                near_empty += 1
                document = title
            else:
                document = f"{title}\n\n{cleaned}" if title else cleaned

            record = {
                "number": number,
                "title": title,
                "document": document,
            }
            fout.write(json.dumps(record) + "\n")
            written += 1
    return written, near_empty


for src, dst in [("pile1.jsonl", "norm-pile1.jsonl"),
                 ("pile2.jsonl", "norm-pile2.jsonl")]:
    written, near_empty = normalize_file(src, dst)
    print(f"{dst}: {written} issues written  ({near_empty} empty/near-empty bodies -> kept title only)")
