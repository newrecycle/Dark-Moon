# Recorded posture and reviewed cross-assessment identity

The dashboard supports current assessment-start windows and recorded aggregate
observations. These are different contracts. UTC windows select assessments by
start time, with current triage; as-of selects the latest explicitly recorded
observation at or before a requested time. No state before recording, between
observations, or from an absent vendor runtime is invented.

Administrators click **Record current posture** in Overview. Viewers can read
recorded metadata but cannot create observations. API:

- POST /api/v1/dashboard/posture/captures with an empty JSON object: admin-only,
  returns an observation ID and UTC timestamp.
- GET /api/v1/dashboard/posture/captures: newest 100 IDs/timestamps, exact total.
- GET /api/v1/dashboard/posture?as_of=TIME: authenticated read; cannot combine
  with from/to. Missing earlier observations return 404; future timestamps and
  malformed/repeated inputs reject. URL-encode the timestamp, especially `+`.

The UI preserves window filters through finding, project, campaign and proposal
drill-downs and Back. Historical aggregate drill-downs are disabled: opening a
current record would not reproduce the saved cohort. Historical observations
are explicitly **observed_cross_file_state**, not an atomic snapshot across
independent assessment files. Captures contain only the typed safe posture
projection, not evidence, names/hosts, credentials, source or report bodies.
Each payload/identity/time has a checksum; this detects accidental corruption,
not malicious modification by an owner who can recompute checksums.

## Reviewed deduplication

Finding triage includes an optional `tracking_id`. Use the same ID only after
operator review establishes the same issue across assessments. Groups are
qualified by exact target ID. Reused finding IDs, matching titles, endpoints or
LLM guesses are never automatically treated as equivalent. Totals separately
report tracked records, distinct tracked groups and untracked records; an
untracked record is not proof of a distinct vulnerability. Clearing the field
removes the assignment. Status-only older clients preserve existing assignments.
Updates use the existing crash-recoverable finding snapshot protocol.

## Storage and retention

Observations are in the existing private control SQLite database, collection
posture_history. Manual capture only; no unbounded background recording. Limits:
4096 observations, 64 MiB total, 2 MiB per posture. Capacity refuses new captures;
no observation is automatically deleted. Full control backups include history.

Run from a checkout with the acceptance runbook's virtual environment. Use a
private operator-owned destination; existing files are never overwritten:

```bash
PYTHONPATH=mcp .venv/bin/python -m community.posture_history \
  --state-dir /absolute/private/community \
  --archive-before 2027-01-01T00:00:00Z --output /absolute/private/posture.jsonl
```

This deletes zero rows. Add `--prune` only to explicitly remove rows after their
lossless archive and parent directory have been fsynced. A crash before database
commit leaves the original rows. Partial/failed files are not reused implicitly.
Restore verifies the complete archive and capacity before atomic insertion;
matching IDs are idempotent, conflicting data refuses the transaction:

```bash
PYTHONPATH=mcp .venv/bin/python -m community.posture_history \
  --state-dir /absolute/private/community --restore /absolute/private/posture.jsonl
```

## Reproduction

```bash
node tests/community/campaign_window.cjs
PYTHONPATH=mcp .venv/bin/python -m pytest \
  tests/community/test_posture.py tests/community/test_posture_history.py \
  tests/community/test_finding_query.py tests/community/test_evidence_access.py -q
```

Real SQLite tests cover saved-vs-current state, admin/viewer access, absent/future
history, capacity, archive/prune/restore/idempotency, corruption refusal and exact
target-qualified identity groups. Browser acceptance exercises window controls,
scoped links and Back, explicit recording, and disabled historical drill-downs.
