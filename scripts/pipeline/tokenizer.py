# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json, re

# --- Regexes for the shared tokenizer ----------------------------------------
# 1. Split on case changes:
#    lower/digit -> upper boundary (runtimeHint -> runtime Hint)
RE_CASE_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
#    acronym -> word boundary (HTTPServer -> HTTP Server)
RE_ACRONYM_BOUNDARY = re.compile(r"([A-Z]+)([A-Z][a-z])")
# 2 & 4. Underscores and any punctuation/whitespace are token separators.
RE_SEPARATOR = re.compile(r"[^A-Za-z0-9]+")

MIN_TOKEN_LEN = 2


def tokenize(text: str) -> list:
    """Shared tokenizer for both piles. Cleanup, in order:
    1. split on case changes (runtimeHint -> runtime Hint)
    2. split on underscores (runtime_hint -> runtime hint)
    3. case-fold so Terminal/TERMINAL/terminal collapse together
    4. strip punctuation (conpty. -> conpty, terminal: -> terminal)
    then drop tokens shorter than 2 characters and purely-numeric tokens.
    """
    if not text:
        return []
    # 1. split on case changes (needs original casing, so do this first)
    s = RE_CASE_BOUNDARY.sub(r"\1 \2", text)
    s = RE_ACRONYM_BOUNDARY.sub(r"\1 \2", s)
    # 2 & 4. underscores and punctuation both act as separators
    parts = RE_SEPARATOR.split(s)
    # 3. case-fold, then drop short and purely-numeric tokens
    return [p.lower() for p in parts if len(p) >= MIN_TOKEN_LEN and not p.isdigit()]


def tokenize_file(infile: str, outfile: str):
    written = 0
    with open(infile) as fin, open(outfile, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            issue = json.loads(line)
            record = {
                "number": issue["number"],
                "title": issue.get("title", ""),
                "tokens": tokenize(issue.get("document", "")),
            }
            fout.write(json.dumps(record) + "\n")
            written += 1
    return written


for src, dst in [("norm-pile1.jsonl", "tokenized-pile1.jsonl"),
                 ("norm-pile2.jsonl", "tokenized-pile2.jsonl")]:
    written = tokenize_file(src, dst)
    print(f"{dst}: {written} issues tokenized")
