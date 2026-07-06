import os, json, time
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BASE = "https://api.github.com/repos/microsoft/vscode/issues"
OUTPUT = "pile2.jsonl"
RECENT_CAP = 3000  # a few thousand general recent issues


def wait_for_rate_limit(resp):
    remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
    reset_at = int(resp.headers.get("X-RateLimit-Reset", time.time()))
    if remaining == 0:
        wait = max(reset_at - int(time.time()), 0) + 2
        print(f"  Rate limit hit — sleeping {wait}s until reset...")
        time.sleep(wait)


def to_record(issue):
    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue.get("body"),
        "state": issue["state"],
        "labels": [lb["name"] for lb in issue.get("labels", [])],
        "author": issue["user"]["login"] if issue.get("user") else None,
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "closed_at": issue.get("closed_at"),
    }


# --- Numbers we already have in pile1 (don't refetch) ---
pile1_numbers = set()
with open("pile1.jsonl") as f:
    for line in f:
        line = line.strip()
        if line:
            pile1_numbers.add(json.loads(line)["number"])
print(f"pile1 has {len(pile1_numbers)} issues (will be skipped)")

# --- Canonical issue numbers from ground truth ---
canonical_numbers = set()
with open("ground_truth.jsonl") as f:
    for line in f:
        line = line.strip()
        if line:
            canonical_numbers.add(json.loads(line)["canonical"])
print(f"ground_truth references {len(canonical_numbers)} canonical issues: "
      f"{sorted(canonical_numbers)}")

seen = set(pile1_numbers)  # everything already collected or to skip
pile2_count = 0
pr_skipped = 0
dup_skipped = 0

with open(OUTPUT, "w") as out:
    # ---------- 1) Pull the canonical issues explicitly ----------
    print("\n=== Fetching canonical issues ===")
    for num in sorted(canonical_numbers):
        if num in seen:
            print(f"  #{num} already in pile1 — skip")
            dup_skipped += 1
            continue
        resp = requests.get(f"{BASE}/{num}", headers=HEADERS)
        wait_for_rate_limit(resp)
        if resp.status_code == 404:
            print(f"  #{num} not found (404) — skip")
            continue
        resp.raise_for_status()
        issue = resp.json()
        if "pull_request" in issue:
            print(f"  #{num} is a PR — skip")
            pr_skipped += 1
            seen.add(num)
            continue
        out.write(json.dumps(to_record(issue)) + "\n")
        seen.add(num)
        pile2_count += 1
        print(f"  #{num} added (canonical)")

    # ---------- 2) Pull a few thousand recent general issues ----------
    print(f"\n=== Fetching recent general issues (cap {RECENT_CAP}) ===")
    recent_added = 0
    page = 1
    while recent_added < RECENT_CAP:
        params = {
            "state": "all",
            "per_page": 100,
            "sort": "created",
            "direction": "desc",
            "page": page,
        }
        resp = requests.get(BASE, headers=HEADERS, params=params)
        wait_for_rate_limit(resp)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            print(f"Page {page}: no more results.")
            break

        page_added = 0
        for issue in items:
            if recent_added >= RECENT_CAP:
                break
            if "pull_request" in issue:
                pr_skipped += 1
                continue
            num = issue["number"]
            if num in seen:
                dup_skipped += 1
                continue
            out.write(json.dumps(to_record(issue)) + "\n")
            seen.add(num)
            pile2_count += 1
            recent_added += 1
            page_added += 1

        print(f"Page {page}: added {page_added} (recent total: {recent_added})")
        page += 1

print("\n=== Summary ===")
print(f"pile2 issues written : {pile2_count}")
print(f"PRs skipped          : {pr_skipped}")
print(f"duplicates skipped   : {dup_skipped}  (already in pile1 or pile2)")
print(f"Output -> {OUTPUT}")
