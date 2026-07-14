import json, re, os, time
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Covers:
#   /duplicate https://github.com/microsoft/vscode/issues/N
#   duplicate of #N  or  duplicate of https://.../issues/N
#   dup #N  or  dup https://.../issues/N
#   close as dup ...
PATTERN = re.compile(
    r'(?:'
    r'/duplicate\s+https://github\.com/microsoft/vscode/issues/(\d+)'  # slash-command
    r'|'
    r'(?:duplicate\s+(?:of|issue\s+of)|close\s+as\s+dup(?:licate)?|dup(?:licate)?)'
    r'\s+(?:https://github\.com/microsoft/vscode/issues/(\d+)|#(\d+))'  # URL or #N
    r')',
    re.IGNORECASE,
)


def extract(text):
    m = PATTERN.search(text or "")
    if m:
        return int(next(g for g in m.groups() if g is not None))
    return None


def wait_if_needed(resp):
    remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
    reset_at = int(resp.headers.get("X-RateLimit-Reset", time.time()))
    if remaining == 0:
        wait = max(reset_at - int(time.time()), 0) + 2
        print(f"  Rate limit — sleeping {wait}s")
        time.sleep(wait)


with open("pile1.jsonl") as f:
    issues = [json.loads(l) for l in f]

matched = []
skipped = []

for idx, issue in enumerate(issues, 1):
    num = issue["number"]

    orig = extract(issue.get("body"))
    if orig and orig != num:          # ignore self-references (noise)
        matched.append({"issue": num, "original": orig, "source": "body"})
        print(f"[{idx}/{len(issues)}] #{num} body -> #{orig}")
        continue

    url = f"https://api.github.com/repos/microsoft/vscode/issues/{num}/comments"
    found = False
    page = 1
    while True:
        resp = requests.get(url, headers=HEADERS, params={"per_page": 100, "page": page})
        wait_if_needed(resp)
        resp.raise_for_status()
        comments = resp.json()
        for c in comments:
            orig = extract(c.get("body"))
            if orig and orig != num:          # ignore self-references (noise)
                matched.append({"issue": num, "original": orig, "source": "comment"})
                print(f"[{idx}/{len(issues)}] #{num} comment -> #{orig}")
                found = True
                break
        if found or len(comments) < 100:
            break
        page += 1

    if not found:
        skipped.append(num)

    if idx % 10 == 0:
        print(f"[{idx}/{len(issues)}] matched={len(matched)}  skipped={len(skipped)}")

print(f"\nMatched : {len(matched)}")
print(f"Skipped : {len(skipped)}  (no duplicate reference found in body or comments)")

with open("matched_dupes.json", "w") as f:
    json.dump(matched, f, indent=2)

with open("skipped_issues.json", "w") as f:
    json.dump(skipped, f, indent=2)

print("Results -> matched_dupes.json  /  skipped_issues.json")
