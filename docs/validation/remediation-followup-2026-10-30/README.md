# Remediation and fork SSE follow-up — 30 October 2026

Started from `pro` at `91d8ee5`. `AGENTS.md` was absent from the checkout and
its ancestor directories. The worker read both current handoff documents before
running acceptance. These are local observations, not new hosted workflow runs.

## Automatic review: UNAVAILABLE, still OPEN

Managed environment readiness was current, with no secrets, runtime-variable
bindings or outbound identities. All six `DARKMOON_REMEDIATION_*` endpoint,
model and credential variables were unset. The enforced HTTP policy permits
package/Git hosts but no model-provider host; VPN is not configured and there
are no TCP grants. No endpoint or credential was invented or borrowed.

```sh
PYTHONPATH=mcp .venv/bin/python tests/community/remediation_model_native.py --configured-models
```

Exit **3**; exact stdout is retained in `configured-model-preflight.txt`.
No model call, generated fix, positive verdict or negative-control verdict was
obtained. This does not close automatic model/Docker/forge acceptance. Supply
explicitly selected capable endpoint/model configurations and their own required
credentials, with permitted network access, then follow the existing runbook.

The next native gates also have no available prerequisites: no supplied licensed
Splunk host/credentials, licensed GitLab Ultimate instance, physical headset,
Grafana signing account or activated commercial reference. No license or terms
were acquired/accepted and no unavailable native gate is labeled passed.
The linked commercial matrix's fork SSE rotation gap was actionable instead.

## Actual operator-reviewed Docker and HTTPS forge: PASS

Python environment: existing Python 3.11.17 `.venv` with installed analysis
dependencies. Docker 28.4.0, local managed daemon, `vfs`, Linux amd64.

```sh
docker build --file tools/lab/Dockerfile --tag darkmoon-ui-lab .
umask 022
PYTHONPATH=mcp .venv/bin/python tests/community/remediation_native.py
```

Both commands exited **0**. The built lab image was
`sha256:3606c3b5d42934cc45f5ad7416be8f776d6c25bf9cd46e8bd9d7a735c88f6772`.
Gitea used the unchanged 1.24.6 rootless manifest pin in `native_forge.py`.
The exact successful stdout is retained in `native-remediation.json`:

- Valid parameter-binding fix: all three before/after probes passed, including
  both SQLi variants, normal behavior, UID 65534, read-only root and no network.
- Unsafe fix: `validation_failed`; intentionally absent image: `unreproduced`,
  infrastructure error recorded, no patch applied.
- Real push/PR/readback: trusted HTTPS, exact head, open/unmerged PR, idempotency,
  original source unchanged, no external repository. Disposable forge removed.
- `model_inference:false`: an operator-supplied fix, not automatic approval.

The first run exited **1** before any edit/publication: inherited umask 077 made
the synthetic worktree unreadable to container UID 65534 (`cp: cannot stat
'/source/.': Permission denied`, then `ModuleNotFoundError: No module named
'app'`). All three before probes failed; production returned `unreproduced` and
`Original source failed reproduction/regression gates; no patch applied`.
Rerunning with umask 022 made the synthetic files readable. Explicitly private
fixture parents/control/output directories remained private. The container UID,
read-only mount/root, no-network, capabilities and verdict/probe gates were
unchanged. The failed attempt is not counted as acceptance.

## Fork SSE rotation regression

The stream previously reused its old byte offset after reopening a new file,
skipping a shorter replacement entirely and losing the prefix of a longer one.
It also clamped an offset beyond a truncated file to EOF. New HTTP regressions
failed before the change in all three cases; append and symlink denial passed.

A connection now tracks device/inode from `fstat` on the actual safely opened
file. It resets to zero on replacement or an observed size below the consumed
offset. Existing bounds and unsafe-file denials remain in place. The identity
is connection-local, never returned in responses. Reconnects start from the
current file's beginning and require a fresh evidence grant.

This cannot recover unread bytes from a removed file, transient rotations missed
between polls, or same-inode truncate-and-regrow to the previous size or larger
between polls. It adds no durable run replay cursor or vendor-wire claim. The
existing 8,192-byte reads and 30-poll connection lifetime remain unchanged.

## Verification of the final source changes

- Before the fix: `PYTHONPATH=mcp .venv/bin/python -m pytest
  tests/community/test_run_discovery.py -q` exited **1**: three subcase failures
  (`replace_shorter`, `replace_longer`, `truncate`), 13 passed, one subtest passed.
- Focused final tests: `PYTHONPATH=mcp .venv/bin/python -m pytest
  tests/community/test_run_discovery.py tests/community/test_evidence_access.py
  tests/community/test_core_contract_boundaries.py -q` exited **0**:
  **35 passed, 43 subtests passed**.
- Full final backend suite: `PYTHONPATH=mcp .venv/bin/python -m pytest
  mcp/tests tests/community -q` exited **0**:
  **511 passed, 301 subtests passed** in 100.14 seconds.
- All seven Tests-workflow Node scripts (`campaign_binding`, `graph_navigation`,
  `finding_query`, `resource_routes`, `campaign_window`, `run_paging`,
  `xr_lifecycle`) exited **0**; `node --check` passed for every
  `mcp/community/static/*.js` file.
- `git diff --check` passed. No new hosted workflow outcome is claimed here.

Real loopback/socket/Docker commands required sandbox access beyond the default
command sandbox; they succeeded with that access. The model/network blocker
above describes actual configured infrastructure, separately from sandbox
permissions. No production verdict, confidence threshold or probe expectation
was altered.
