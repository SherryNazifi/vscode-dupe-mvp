import os
import json
import time
import requests

TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BASE_URL = "https://api.github.com/repos/microsoft/vscode/issues"
OUTPUT = "pile1.jsonl"
CAP = 800


def wait_for_rate_limit(response):
    remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
    reset_at = int(response.headers.get("X-RateLimit-Reset", time.time()))
    if remaining == 0:
        wait = max(reset_at - int(time.time()), 0) + 2
        print(f"  Rate limit hit — sleeping {wait}s until reset...")
        time.sleep(wait)


def fetch_issues():
    collected = 0
    page = 1

    with open(OUTPUT, "w") as out:
        while collected < CAP:
            params = {
                "labels": "duplicate",
                "state": "all",
                "per_page": 100,
                "sort": "created",
                "direction": "desc",
                "page": page,
            }
            resp = requests.get(BASE_URL, headers=HEADERS, params=params)
            wait_for_rate_limit(resp)
            resp.raise_for_status()

            items = resp.json()
            if not items:
                print(f"Page {page}: no more results.")
                break

            page_saved = 0
            for issue in items:
                if collected >= CAP:
                    break
                if "pull_request" in issue:
                    continue

                record = {
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
                out.write(json.dumps(record) + "\n")
                collected += 1
                page_saved += 1

            print(f"Page {page}: saved {page_saved} issues (total so far: {collected})")

            if len(items) < 100:
                print("Last page reached.")
                break

            page += 1

    print(f"\nDone. {collected} issues written to {OUTPUT}")


if __name__ == "__main__":
    fetch_issues()
