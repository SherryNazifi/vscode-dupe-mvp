# --- resolve data/ paths relative to repo root ---
import os as _os
_root = _os.path.dirname(_os.path.abspath(__file__))
while not _os.path.isdir(_os.path.join(_root, "data")) and _root != _os.path.dirname(_root):
    _root = _os.path.dirname(_root)
_os.chdir(_os.path.join(_root, "data"))
import json, os
from collections import Counter
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["GITHUB_TOKEN"]
NUM = 304865
OUTFILE = "timeline_304865.json"

# Same header that already worked for the REST timeline endpoint
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

url = f"https://api.github.com/repos/microsoft/vscode/issues/{NUM}/timeline"

events = []
page = 1
while True:
    resp = requests.get(url, headers=HEADERS, params={"per_page": 100, "page": page})
    resp.raise_for_status()
    batch = resp.json()
    events.extend(batch)
    if len(batch) < 100:
        break
    page += 1

# Write the entire raw response, pretty-printed
with open(OUTFILE, "w") as f:
    json.dump(events, f, indent=2)

# Summary count of each distinct event type
counts = Counter(ev.get("event") for ev in events)
print(f"Issue #{NUM}: {len(events)} total timeline items")
print(f"Raw response written to {OUTFILE}\n")
print("Event type counts:")
for etype, n in counts.most_common():
    print(f"  {etype!s:<28} {n}")
