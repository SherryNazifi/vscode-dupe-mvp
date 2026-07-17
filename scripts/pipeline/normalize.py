# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json, re

# --- Regexes for stripping scaffolding ---------------------------------------
RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
RE_DETAILS      = re.compile(r"<details\b.*?</details>", re.DOTALL | re.IGNORECASE)
RE_CODE_FENCE   = re.compile(r"```.*?```", re.DOTALL)          # fenced code blocks
RE_HTML_TAG     = re.compile(r"<[^>]+>")                        # any leftover tag
RE_IMG_MD       = re.compile(r"!\[[^\]]*\]\([^)]*\)")           # markdown images

# Version / environment / template lines (whole-line, case-insensitive)
VERSION_LINE_PATTERNS = [
    r"type:\s*bug", r"type:\s*feature", r"type:\s*performance",
    r"extension version:",
    r"vs\s*code version:", r"vscode version:",
    r"os version:",
    r"modes:",
    r"^version:", r"^commit:", r"^date:", r"^electron:",
    r"^chromium:", r"^node\.?js:", r"^v8:", r"^sandboxed:",
    r"^remote:", r"^os:", r"^cpus:", r"^memory:",
    r"does this issue occur when all extensions are disabled",
    r"steps to reproduce:?$",
]
RE_VERSION_LINE = re.compile(
    r"^\s*(?:" + "|".join(VERSION_LINE_PATTERNS) + r").*$",
    re.IGNORECASE | re.MULTILINE,
)

NEAR_EMPTY_THRESHOLD = 10   # non-whitespace chars


def clean_body(body: str) -> str:
    if not body:
        return ""
    text = body
    text = RE_HTML_COMMENT.sub("", text)
    text = RE_DETAILS.sub("", text)
    text = RE_CODE_FENCE.sub("", text)
    text = RE_IMG_MD.sub("", text)
    text = RE_HTML_TAG.sub("", text)          # strip bare tags first (e.g. <b>Bug</b> -> Bug)
    text = RE_VERSION_LINE.sub("", text)      # so version-line patterns match clean text
    # collapse excess whitespace / blank lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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

            if len(cleaned.replace(" ", "").replace("\n", "")) < NEAR_EMPTY_THRESHOLD:
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
