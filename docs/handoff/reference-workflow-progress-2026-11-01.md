# API workflow acceptance checkpoint — 1 November 2026

The task map now includes fresh workflow observations for each existing task ID.
Full reference acceptance remains open. Sanitized synthetic fixtures and their
capture hashes are retained outside Git; proprietary assets and raw captures
are excluded from this repository.

Two confirmed compatibility increments are committed locally:

- `28e80f5` — JSON event polling with bounded pages, safe metadata and replay
  cursors that do not skip matching events. SSE behavior and explicit resync
  protection remain available.
- `3735193` — campaign-group metric series, calendar-day labels and zero counts
  aligned across observed buckets. Protected labels and strict UTC input
  validation remain intact.

The fresh run contains 1,935 HTTP observations (1,032 reference, 903 fork),
including requests to all 52 declarations on both runtimes. Coverage counts are
not acceptance pass rates. Three reference transport timeouts remain recorded
as timeouts. Harness parsing/probe corrections and earlier unsuccessful cohort
comparisons are retained with their limits; their results were not fabricated.

Observed workflow checkpoints:

| Area | Evidence | Remaining boundary |
|---|---|---|
| Authentication | Password changes, old password/token behavior, correctly signed expiry, role downgrade and account deletion | Reference retains some older claims; stronger fork revocation and current-role checks remain |
| Credentials | Compatible GitHub token-only create, read, rename, rotate and delete on both | Other provider field families and full ownership/consumer matrix |
| Webhooks | Verified TLS, signed success, 503 retry, normal synthetic finding-producer callback, actual-byte consumer replay/tamper/key/staleness negatives | Reference synchronous five-attempt failure differs from fork asynchronous backoff; fork failure exhaustion/restart not completed |
| Runs and events | Normal launch attempts; controlled process/log append, rotation, reconnect, stop, real token expiry and unused grant expiry after 46 seconds | Engine/model prerequisites prevent successful assessment acceptance; controlled log fixtures are not assessments |
| Scheduling and retests | Due whole-second one-shot dispatched once on fork; both native retest aliases attempted | Reference schedule did not dispatch during bounded observation; reference retests remained running and fork retests became incomplete |
| Metrics | Eight fixed interior-cohort comparisons match series values and point order when compared by label | Label ordering and reference date-boundary behavior differ; full trend/denominator matrix stays open |
| Browser and SDK | Chromium login/basic pages/mobile observations; built SDK completed 20 live read observations without call failures | Original routing differs; full interaction, visual and stateful consumer acceptance remains open |

Validation after both increments: **540 backend tests and 338 subtests passed**
(`PYTHONPATH=mcp .venv/bin/python -m pytest mcp/tests tests/community -q`).
Focused polling/replay checks passed 10 tests; metrics/API checks passed 49.
The configured-model acceptance preflight exited **3 (unavailable)** because no
production endpoint/model is configured. This does not close automatic model
approval, probes or forge publication. Hosted CI was not run and nothing was
pushed.

The machine-readable [task map](api-task-progress.json) records the checkpoint,
remaining work and local commits for all 28 existing task IDs. Historical dated
handoffs retain their original scope; this checkpoint adds subsequent evidence.
