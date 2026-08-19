# Taxonomy

Four independent taxonomies used when reviewing judged duplicate pairs.

- **Taxonomy 1** — what kind of issue it is.
- **Taxonomy 2** — what the true relationship between the pair is.
- **Taxonomy 3** — why the judge made a real mistake.
- **Taxonomy 4** — when the problem is actually the ground-truth label, not the judge.

The key rule is: **one label per taxonomy**, and **Taxonomy 4 replaces Taxonomy 3** when the
"error" comes from bad ground truth.

## Taxonomy 1: Issue type

| Category | What qualifies | Example from the data |
|---|---|---|
| Defect report | The issue describes a specific observed behavior that is incorrect or failing and provides enough information to compare it with another defect report. | #301988 — extension installation fails for all extensions on VS Code 1.111.0, with version information, reproduction steps, and error text. |
| Feature request | The issue asks for new or changed functionality rather than reporting existing functionality that is malfunctioning. | #327733 — asks for browser element attachments to be combined into one item. |
| Non-defect artifact | The issue is primarily a test plan, tracking/meta issue, PR, or other coordination artifact rather than a report of a specific defect. | #327411 — a TPI test plan for Agent Host Copilot terminal output streaming. |
| Insufficient content | The issue does not provide enough information about the observed behavior or conditions to identify a specific defect reliably. | #327762 — only reports that VS Code is "unable to update", without enough detail to identify the failure. |

## Taxonomy 2: Pair relationship

| Category | What qualifies | Example from the data |
|---|---|---|
| Same defect | Both reports describe the same failing behavior under compatible conditions and should be treated as duplicates. | #328330 → #321882 — both report that the Local harness in the Agents window lacks the expected tools on the first message and gains them on subsequent messages. |
| Same symptom, different cause | The reports describe the same or very similar visible symptom, but a materially different trigger or cause indicates separate defects. | #293117 → #321132 — both involve menus rendering behind other UI, but one is tied to the experimental dark theme while the other concerns webview/panel z-order. |
| Same component, different defect | The reports concern the same feature or subsystem but describe different failing behaviors. | #327839 → #325032 — both concern Report Issue, but one says the menu item is missing while the other says it exists but generates a URL that is too long. |
| Opposite symptom | The reports concern the same feature or state but describe inverse or contradictory failures. | #327643 → #321049 — one reports terminals persisting when they should not, while the other reports terminals being destroyed when they should persist. |

## Taxonomy 3: Judge failure mode

### Over-calling failures

| Category | What qualifies | Example from the data |
|---|---|---|
| Component/vocabulary overmatch | The judge predicts a duplicate because the reports share a component, terminology, or broad topic while failing to distinguish the actual requested or failing behavior. | #327733 → #320888 — both concern browser element attachments, but one asks for attachments to be combined while the other reports unwanted context being added. |
| Symptom overmatch | The judge predicts a duplicate because the visible symptoms are similar while ignoring a materially different trigger or cause. | #293117 → #321132 — both involve menus appearing behind UI, but the conditions producing the symptom differ. |
| Contradictory-behavior overmatch | The judge predicts a duplicate despite the reports describing opposite or incompatible behaviors. | #327643 → #321049 — one reports persistence while the other reports destruction. |
| Unjudgeable-input overmatch | The judge commits to a duplicate despite one or both issues being a feature request, non-defect artifact, or too underspecified for reliable comparison. | #327762 → #322858 — both are extremely vague update complaints, yet the judge commits to a duplicate instead of abstaining. |

### Under-calling failures

| Category | What qualifies | Example from the data |
|---|---|---|
| Detail asymmetry | The judge rejects a true duplicate because one report contains substantially more diagnostic information than the other and treats the missing detail as evidence of a different defect. | #299107 → #293151 — one report diagnoses an uppercase-matching bug while the other only says the filter is not working. |
| Instance-vs-general | The judge rejects a true duplicate because one report describes a specific manifestation of the defect while the other describes the same defect more generally. | #285777 → #187338 — the query describes the keyring issue under Niri while the canonical describes the broader Linux desktop-environment keyring-detection problem. |
| Environment-as-defect | The judge rejects a true duplicate because it treats incidental differences in OS, desktop environment, version, or similar context as evidence of different defects. | #301988 → #301011 — both describe extension installation failures in VS Code 1.111.0, but the judge distinguishes them partly because one is Windows and the other macOS. |
| Reporter-hypothesis-as-defect | The judge rejects a true duplicate because the reporters propose different suspected causes even though the observed failing behavior is the same. | #307039 → #305240 — both report the same "Stopping Extension Hosts" failure, but the reports speculate about different causes. |

## Taxonomy 4: Ground-truth defect

| Category | What qualifies | Example from the data |
|---|---|---|
| Bucket sibling | The judge selects a different member of the same duplicate class instead of the exact member named as the ground-truth canonical. | #325093 → #325092, GT #325086 — all three describe essentially the same Python terminal/input behavior, so the selected issue is a valid sibling of the labeled canonical. |
| GT wrong | The issue labeled as the ground-truth canonical does not actually describe the same underlying defect as the query. | #301001 → GT #301011 — the query concerns .VSIXPackage filename recognition while the labeled canonical concerns corrupted or unreadable VSIX/ZIP downloads. |
| Pick better than GT | The judge selects a candidate that is a more direct or specific match to the query than the issue supplied as the ground truth. | #320557 — the judge selected the specific black-block terminal rendering issue while the GT points to a broader font-rendering thread. |
