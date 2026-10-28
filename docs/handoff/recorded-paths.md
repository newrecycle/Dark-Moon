# Recorded evidence-backed paths (G02)

The attack-surface view now supports persisted operator-reviewed paths. They
annotate existing directed connections with finding evidence and a review
rationale. The application validates references; it does not independently
prove that one exploit caused another.

## Record and inspect

Select an assessment, open **Record an evidence-backed path**, and add steps.
Each step selects an observed connection, a supporting finding on either of its
assets, and a rationale. Confirm the review checkbox to save. Containment alone
does not qualify. The next connection must start at the previous destination.

The separate **Tour recorded path** control highlights each connection and
selects its destination asset. Back, Next, Finish and Explore freely work with
the keyboard; Technical details links to the correct campaign's finding and
evidence. Camera changes are immediate, including with reduced motion enabled.
Selecting another asset, changing routes or locking cancels playback. Viewers
can inspect records but cannot create or delete them.

## API and persistence

- `GET /api/v1/campaigns/{id}/paths`: `{data, total}`.
- `POST` on the same route: `{title, reviewed: true, steps}`. Each step contains
  exactly `edge_id`, `finding_id`, and `rationale`.
- `DELETE /api/v1/campaigns/{id}/paths/{path_id}` removes only that campaign's
  path. This does not change findings, infrastructure or reports.
- Existing graph endpoints include stable edge IDs and `paths`. The regular
  infrastructure endpoint exposes the same enriched graph in its `data` field.

Titles support 160 characters, rationales 4000, paths 32 steps, and campaigns
100 path records. Supporting findings must belong to the campaign, explicitly
link to a connection endpoint, contain nonempty evidence, and have confirmed,
exploited, remediated or resolved status. Evidence is fingerprinted using its
canonical JSON; raw evidence is not copied into path state.

Records persist in the operator-owned control store. Every graph/list read and
each playback step checks current node, directed connection, finding, status
and evidence references. Changed evidence disables the old record until a new
review is saved. Stale records remain visible with their reason. Editing and
version history are future work; deleting an annotation is currently final.

## Validation

267 tests and 11 subtests pass, including campaign boundaries, role checks,
containment/observed-edge separation, ordering, reference deletion, evidence
mutation, restart persistence, input bounds and absence of copied raw evidence.
The graph-controller suite passes. Chromium acceptance exercises two-step
creation, persistence across navigation, literal markup, evidence links,
Back/Next/Finish/free exploration, manual-selection exit, deletion and stopping
when a supporting finding becomes false-positive. Desktop and 390px mobile
screenshots were inspected, including reduced-motion playback.

Tests use explicitly labelled fixture connections and evidence. No external
target scan, provider account login or paid inference is involved.
