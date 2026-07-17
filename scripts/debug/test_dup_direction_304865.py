# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json, os
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Query BOTH the assumed-duplicate (#304865) and its canonical (#304866)
# to see which timeline actually carries the MarkedAsDuplicateEvent.
QUERY = """
query($number: Int!) {
  repository(owner: "microsoft", name: "vscode") {
    issue(number: $number) {
      number
      timelineItems(first: 50, itemTypes: [MARKED_AS_DUPLICATE_EVENT, UNMARKED_AS_DUPLICATE_EVENT]) {
        nodes {
          __typename
          ... on MarkedAsDuplicateEvent {
            duplicate { ... on Issue { number } ... on PullRequest { number } }
            canonical { ... on Issue { number } ... on PullRequest { number } }
          }
          ... on UnmarkedAsDuplicateEvent {
            duplicate { ... on Issue { number } ... on PullRequest { number } }
            canonical { ... on Issue { number } ... on PullRequest { number } }
          }
        }
      }
    }
  }
}
"""

for num in [304865, 304866]:
    resp = requests.post("https://api.github.com/graphql",
                         json={"query": QUERY, "variables": {"number": num}},
                         headers=HEADERS)
    data = resp.json()
    nodes = data["data"]["repository"]["issue"]["timelineItems"]["nodes"]
    print(f"\n=== querying #{num} ===")
    print(f"  dup/unmark events on this timeline: {len(nodes)}")
    print(json.dumps(nodes, indent=2))
