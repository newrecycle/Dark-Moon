# Community control-state storage — 29 October 2026

Community jobs, schedules, sessions, encrypted credential records, events, grants
and other control collections now use `community/control.sqlite3`. Campaigns,
findings, infrastructure and reports keep their existing storage. The separate
finding-history SQLite journal is unchanged.

## Upgrade and recovery

Stop the old dashboard daemon before starting this version. Only one daemon
should own a state directory. At first open, one SQLite transaction imports every
legacy `state.json` key and record, including nested data and scalar metadata.
The source remains intact with private permissions. Malformed JSON, duplicate
keys, non-finite values and non-object roots refuse migration; no empty-success
fallback is used. A changed legacy file after migration refuses access, including
on an already-open Store. Content fingerprints allow backups restored to another
filesystem without treating a changed inode as changed source content.

Back up the entire private community state directory and assessment data while
the daemon is stopped. Keep the credential encryption key with that backup:
copying encrypted database rows alone does not preserve access to secrets. For a
live database-only snapshot, use SQLite's backup API; copying just the main file
while WAL writers run is not a consistent backup. Restore with the daemon stopped
and preserve `state.json` if it was present at import. A SQLite backup remains
portable alongside identical legacy content.

Do not roll an old binary directly onto the original legacy file after new
writes: that file is a pre-upgrade checkpoint. For a reviewed rollback, stop the
daemon, retain a complete backup, export the current decoded state using
`Store(state_dir).read()` into a separate private `state.json`, and restore the
matching keys/logs/remediation files into a separate rollback directory. The old
source is never overwritten automatically. JSON exports contain sensitive control
metadata and encrypted credentials and require mode 0600.

## Behavior and limits

SQLite uses WAL, FULL synchronous commits, a 30-second busy timeout and private
files/directories. Callback updates remain atomic across collections and nested
mutations, but only accessed records are decoded and changed records rewritten.
Exceptions and process termination before commit roll back the whole transaction.
No-op reads/updates do not advance the persisted change revision.

Run discovery, count/filter/page operations, idempotency lookups, queue selection,
active capacity checks and schedule overlap checks use indexed queries. Count and
page selection share one read transaction. Overview embeds only 100 recent runs
with explicit total/has-more metadata; dedicated run/log endpoints provide the
rest. Pages remain `live_offset` across requests: concurrent source changes can
shift later pages. This is not an immutable multi-request snapshot contract.

SSE change hints use the control revision and assessment file metadata rather
than repeatedly decoding/hashing the entire workspace for each connection.
Fresh evidence grants still read current content. Workspace snapshots and the
background observation poll still load retained assessment records; this change
does not claim constant-memory analytics over all campaigns.

Local regression fixture: 8,000 historical jobs, offset 4,000, limit 25 decoded
exactly 25 records, with ~136 KiB traced peak and ~6 ms selection on the managed
host. One nested job mutation decoded one record; active count decoded none.
These are measured fixture results, not production throughput guarantees.
