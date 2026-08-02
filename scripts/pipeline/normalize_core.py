"""Shared issue-text normalization.

Single source of truth for turning a raw GitHub issue (title + body) into the
cleaned `document` string that gets embedded and judged. Imported by
normalize.py, build_eval_candidates.py and judge_eval_top20.py.

Pure functions and constants only — no I/O, no chdir, nothing runs at import.
"""
import re

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

NEAR_EMPTY_THRESHOLD = 10   # non-whitespace chars below which the body is dropped


def clean_body(body: str) -> str:
    """Strip scaffolding (comments, code, images, tags, version lines) from a body."""
    if not body:
        return ""
    text = body
    text = RE_HTML_COMMENT.sub("", text)
    text = RE_DETAILS.sub("", text)
    text = RE_CODE_FENCE.sub("", text)
    text = RE_IMG_MD.sub("", text)
    text = RE_HTML_TAG.sub("", text)          # strip bare tags first (e.g. <b>Bug</b> -> Bug)
    text = RE_VERSION_LINE.sub("", text)      # so version-line patterns match clean text
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_near_empty(cleaned: str) -> bool:
    """True when the cleaned body has too little content to keep."""
    return len(cleaned.replace(" ", "").replace("\n", "")) < NEAR_EMPTY_THRESHOLD


def make_document(title: str, body: str) -> str:
    """Cleaned `title + body` document; falls back to title-only when near-empty."""
    title = (title or "").strip()
    cleaned = clean_body(body)
    if is_near_empty(cleaned):
        return title
    return f"{title}\n\n{cleaned}" if title else cleaned
