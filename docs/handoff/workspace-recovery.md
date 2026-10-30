# Offline complete workspace backup and safe restore

Run from a checkout with the parity runbook's environment. Linux/WSL filesystem
and SQLite are used; no cloud service, license, model or external notification.

1. Stop the dashboard **and** MCP/engine/other processes writing these roots.
   The daemon lock checks the dashboard; it cannot attest to external writers.
2. Supply the actual data, community control, and reports roots. Reports may be
   a separate mounted directory. Keep the destination outside all source roots.
3. Create an exclusive private snapshot; existing destinations are never reused.

```bash
PYTHONPATH=mcp .venv/bin/python -m community.backup create \
  --data-dir /absolute/data --state-dir /absolute/data/community \
  --reports-dir /absolute/reports --destination /absolute/backups/checkpoint \
  --writers-stopped
PYTHONPATH=mcp .venv/bin/python -m community.backup verify /absolute/backups/checkpoint
PYTHONPATH=mcp .venv/bin/python -m community.backup restore /absolute/backups/checkpoint \
  --destination /absolute/restored-workspace
```

These are command templates, not paths to guess. New restored roots are
restored-workspace/data, restored-workspace/state and restored-workspace/reports.
Inspect restore-report.json before switching a stopped service to those roots.
If preserving original source/worktree absolute paths matters, restore files to
the reviewed original mount layout while every writer remains stopped; opaque
Git proposal/repository paths are never silently rewritten to another project.

## Guarantees and recovery policy

SQLite online-backup semantics include committed WAL records. Databases receive
integrity checks; every saved regular file has a SHA-256 manifest entry. Symlinks
and special files refuse copying. Before/after inventories detect source changes.
An interrupted copy never publishes a complete destination. This is an **offline
quiescent writer contract**, not a live atomic snapshot across independent files.
The directory is mode 0700 and includes keys and private evidence: keep it private.
Checksums detect accidental damage, not a malicious owner changing the manifest.

Finding-history source binding is checked before copying and before publishing.
Restore rebinds its inode-based legacy marker only after matching archived bytes
have been verified; no reimport, event replacement or invented history occurs.
Restored history reads retain original event IDs. Posture history and archive
metadata live inside the copied control database.

Restore verifies into a private staging directory, then:

- clears sessions and evidence grants; rotates the file-based recovery token;
- interrupts restored queued/running jobs and retests;
- pauses schedules and webhook subscriptions, and fails pending deliveries;
- discards short-lived run snapshots; preserves records, credential encryption
  keys, event/receipt history and proposal evidence for explicit review.

No restored job, assessment or notification is automatically replayed. An
operator-configured DARKMOON_DASHBOARD_TOKEN environment override is outside the
archive: configure a fresh value rather than reusing an old recovery credential.
Review users, credential grants and post-backup revocations before exposing a
restored service. A backup reflects its capture point, not later access changes.

Test/reproduce:

```bash
PYTHONPATH=mcp .venv/bin/python -m pytest \
  tests/community/test_workspace_backup.py tests/community/test_control_storage.py -q
```

The tests use actual files and SQLite: complete restore, encrypted credential
resolution with restored keys, history IDs/legacy rebind, event records, paused
operational state, cleared sessions, active-daemon refusal, source mutation,
corruption and overwrite refusal. They start no assessments or deliveries.
