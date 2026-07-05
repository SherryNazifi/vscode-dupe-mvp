import json, os, time
import requests

TOKEN = os.environ["GITHUB_TOKEN"]
OUTPUT = "ground_truth.jsonl"
GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# MarkedAsDuplicateEvent lives on the CANONICAL issue's timeline.
# duplicate.number  = the issue that was marked as a dup
# canonical.number  = the original (same as the issue we queried)
# So the pair we want is:  duplicate.number -> canonical.number
QUERY = """
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      timelineItems(
        first: 100
        after: $cursor
        itemTypes: [MARKED_AS_DUPLICATE_EVENT, UNMARKED_AS_DUPLICATE_EVENT]
      ) {
        pageInfo { hasNextPage endCursor }
        nodes {
          __typename
          ... on MarkedAsDuplicateEvent {
            duplicate  { ... on Issue { number } ... on PullRequest { number } }
            canonical  { ... on Issue { number } ... on PullRequest { number } }
          }
          ... on UnmarkedAsDuplicateEvent {
            duplicate  { ... on Issue { number } ... on PullRequest { number } }
            canonical  { ... on Issue { number } ... on PullRequest { number } }
          }
        }
      }
    }
  }
  rateLimit { remaining resetAt }
}
"""


def wait_if_needed(rate):
    if rate and rate.get("remaining", 1) == 0:
        from datetime import datetime
        reset_ts = datetime.fromisoformat(
            rate["resetAt"].replace("Z", "+00:00")
        ).timestamp()
        wait = max(int(reset_ts - time.time()), 0) + 2
        print(f"  GraphQL rate limit — sleeping {wait}s")
        time.sleep(wait)


def get_dup_events(owner, repo, number):
    events, cursor = [], None
    while True:
        resp = requests.post(GRAPHQL_URL, headers=HEADERS, json={
            "query": QUERY,
            "variables": {"owner": owner, "repo": repo,
                          "number": number, "cursor": cursor},
        })
        resp.raise_for_status()
        data = resp.json()
        wait_if_needed((data.get("data") or {}).get("rateLimit"))

        timeline = (
            (data.get("data") or {})
            .get("repository", {})
            .get("issue", {})
            .get("timelineItems", {})
        )
        events.extend(timeline.get("nodes") or [])
        page = timeline.get("pageInfo", {})
        if not page.get("hasNextPage"):
            break
        cursor = page["endCursor"]
    return events


with open("pile1.jsonl") as f:
    issues = [json.loads(l) for l in f]

matched = 0
skipped = 0

with open(OUTPUT, "w") as out:
    for idx, issue in enumerate(issues, 1):
        canonical_num = issue["number"]
        events = get_dup_events("microsoft", "vscode", canonical_num)

        # Track mark/unmark per duplicate issue (one canonical can have many dups)
        # marks[dup_num] = True/False (True = currently marked)
        marks: dict[int, bool] = {}
        for ev in events:
            dup_obj = ev.get("duplicate") or {}
            dup_num = dup_obj.get("number")
            if dup_num is None:
                continue
            if ev["__typename"] == "MarkedAsDuplicateEvent":
                marks[dup_num] = True
            elif ev["__typename"] == "UnmarkedAsDuplicateEvent":
                marks[dup_num] = False

        # Emit one record per still-marked duplicate
        still_marked = [dup for dup, active in marks.items() if active]
        if still_marked:
            for dup_num in still_marked:
                record = {
                    "source": "timeline",
                    "issue": dup_num,
                    "canonical": canonical_num,
                }
                out.write(json.dumps(record) + "\n")
                print(f"[{idx}/{len(issues)}] #{dup_num} (dup) -> #{canonical_num} (canonical)")
            matched += len(still_marked)
        else:
            skipped += 1

        if idx % 20 == 0:
            print(f"[{idx}/{len(issues)}] matched={matched}  skipped={skipped}")

print(f"\nMatched : {matched}  (dup -> canonical pairs written)")
print(f"Skipped : {skipped}  (no active MarkedAsDuplicateEvent on these canonicals)")
print(f"Results -> {OUTPUT}")
