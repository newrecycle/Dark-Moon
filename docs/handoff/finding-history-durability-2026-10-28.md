# Finding history: embedded indexed ledger and recovery

Date: 2026-10-28. Scope: independent Dark-Moon Community fork; not commercial Pro wire equivalence.

## Architecture

The authoritative post-cutover store is `$DARKMOON_DATA_DIR/finding-history.sqlite3` (SQLite WAL, `synchronous=FULL`). An event holds its original generated `fh_...` ID, recorded UTC timestamp, exact campaign/target/finding IDs, and full validated JSON row. SQLite provides unique event IDs and one stable key per creation identity. Indexed readers order by `(recorded_at,id)`; unpaged internal readers return insertion order. Bounded reads issue `COUNT(*)` and `LIMIT/OFFSET` under one SQLite read transaction. They do not scan or lock the original JSONL. Offset 0–100000 and limit 1–500 remain enforced. Deep-offset reads remain proportional to offset (SQLite skips rows); exact `COUNT(*)` is not free.

Migration is an explicit, synchronous, fully validated transaction at first initialization. Every line of `finding-history.jsonl` must be valid, with a valid version-1 header. Existing event IDs, metadata, ordering, extension fields and activation timestamp are preserved, and no pre-activation snapshots are backfilled. Failed import rolls back entirely; no partial index becomes readable. The old JSONL remains untouched as evidence. Its device/inode/size/mtime fingerprint is checked on reads; an unexpected change fails closed, including after native writes. This is accidental-disagreement detection, not cryptographic tamper proof. Never manually edit the legacy file or use the test-only `DARKMOON_TEST_ALLOW_HISTORY_REIMPORT` flag in a live deployment.

## Mutation consistency and crash recovery

Only the instrumented live finding ingestion and operator triage paths gain the atomic event/intent protocol. Under a cross-process journal lock, the writer loads the current campaign finding snapshot, decides a mutation, and commits the history event plus a pending before/after snapshot intent in **one SQLite transaction**. After commit, it atomically replaces the legacy JSON snapshot and marks the intent applied. If interrupted between these boundaries, startup or the next reader/writer replays pending snapshots idempotently. Recovery checks the on-disk snapshot against the recorded *before* and *after* states; unexpected divergence raises a storage error rather than overwriting external edits. Duplicate creation deliveries do not create new finding events. Status changes are recorded only if actual status differs.

**Contract:** when an instrumented mutation has successfully returned, its history event and campaign finding snapshot are durable. After a crash, committed intents are rolled forward; uncommitted SQLite transactions roll back. During a crash window, direct readers of the raw JSON files may see a prior snapshot until recovery. Callers of the indexed history reader trigger recovery if necessary. Campaign aggregate stats, target risk labels, out-of-band direct JSON edits, webhook side effects, and jobs/queue storage are **not** in this transaction. These may require independent recalculation after a crash; do not describe them as crash-atomic with the finding event.

The failure-injection hook `DARKMOON_HISTORY_FAIL_AT` is for disposable test workers only; do not enable it in a service.

## Consistent pages

Without `snapshot_seq`, existing `GET /api/v1/vulnerabilities/history` queries retain their live-offset behavior, and new earlier-sorting rows may shift later pages. Each response now includes a numeric `snapshot_seq`, the highest committed event sequence at the read transaction. To obtain a stable event set, send that value as `snapshot_seq=<value>` on each subsequent page, preserving any target filter and ordering. Each bounded query then applies `seq<=snapshot_seq`; appends cannot alter that snapshot set. This is a fixed **set of event IDs**, not a frozen view of mutable finding snapshots. Timestamp/id ties remain deterministic; SQLite row IDs are immutable. The server clamps future sequence values to the current high-water mark. A snapshot cannot bridge explicit future destructive database restoration; retain backups for that.

## Operations (stop writers before restore, export-for-rollback or database relocation)

Set `DARKMOON_DATA_DIR` to the same persistent directory as the running service.

```sh
python tools/finding-history-admin.py --verify
python tools/finding-history-admin.py --recover
python tools/finding-history-admin.py --backup /secure/backup/history.sqlite3
python tools/finding-history-admin.py --archive /secure/archives/2026-10.json --before 2026-11-01T00:00:00Z
python tools/finding-history-admin.py --export-jsonl /secure/rollback/finding-history.jsonl
```

`--verify` executes SQLite integrity check and validates every indexed payload checksum/identity. It checks the retained original JSONL fingerprint. `--recover` completes pending committed snapshot intents; it does not invent events. `--backup` uses SQLite's online backup API and also copies the original JSONL, refusing overwrites. For a consistent *whole-system* restore, additionally back up the campaign snapshot directory and other relevant files while workers are stopped. `--archive` writes a lossless, SHA-256-described exported subset before an exclusive UTC timestamp into a new file and **deletes zero events**; archive creation fails if the destination already exists. There is **no automatic retention, expiry, compaction or deletion policy**. SQLite WAL checkpoints may run normally; do not delete `-wal`/`-shm` files manually during operations.

Recovery: stop the service; copy the directory and original legacy source for forensic preservation; run `--verify` and then `--recover`. If SQLite integrity or source consistency fails, restore the **matching database plus campaign snapshots and legacy source** from a known-good backup. Do not simply delete the index and reimport JSONL after new native events exist: that would silently lose post-cutover history. If rebuilding from a verified `--export-jsonl`, first stop writers, save full backups, confirm export count/IDs, and only then deploy/import it as the authoritative complete history. Version rollback to old JSONL-only code likewise requires an explicit `--export-jsonl` under maintenance mode: old code will not see post-cutover SQLite-only events otherwise.

## Validation and limits

Offline migration, repeated restart, corruption rollback, process-kill windows around commit/replace/applied markers, readers/writers, indexed ordering, target filters, bounded pages and snapshot-seq stability, source/index disagreement, archive boundaries and deep-page memory/latency are covered by `tests/community/test_finding_history_durable.py`, the prior bounded-history tests and lifecycle HTTP tests. Representative CI measurements must be recorded separately once observed: local/hosted-runner numbers are not universal service-level latency/RSS guarantees. The deep-page test reports traced Python allocations during read calls, not whole-process peak RSS.

**Remaining limitations:** SQLite exact counts and deep OFFSET still have work proportional to relevant row counts/offset, though pages no longer parse the full JSONL. First-time migration takes a full validated scan and a migration lock. JSON snapshots duplicate current finding data and cause per-mutation rewriting; SQLite pending intent size scales with the campaign snapshot. Full index integrity scans are explicit, not performed for every page; normal reads validate selected payload checksums. Metadata-only history does not include external writers or historical backfill. Queue and job storage remain unchanged and have a separate full-state-loading limitation; SQLite finding history does not optimize them. Independent fork test success cannot establish a licensed original-vendor response contract.
