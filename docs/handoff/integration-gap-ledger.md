# Systematic integration continuation

> **New actual-Pro baseline (2026-10-27):** [image reference](actual-pro-image-baseline-2026-10-27.md), [52-route crosswalk](actual-pro-endpoint-crosswalk-2026-10-27.md) and [implementation parity backlog](actual-pro-parity-ledger-2026-10-27.md). This pre-existing ledger tracks **integration host validation**, not measured parity with the vendor binary.

The new [commercial Pro static audit](../pro-audit/README.md) is a separate source for API/Angular/remediation coverage; it does not supersede integration-host tests or establish commercial runtime behavior. This ledger remains the source for native integration-host follow-up.

Scope: finish integration gaps sequentially, test against this fork, push tested
checkpoints to `pro`, and continue searching until remaining gaps are either
resolved or require a concrete unavailable capability. No PR, external message,
cloud deployment, or real assessment of a third-party target is authorized by
these tests. All test launches use disposable offline/owned-loopback fixtures.

The preceding dashboard checkpoint is `babdc39`. Its browser, both regression
gates, Docker/provider, owned-loopback and real n8n host checks passed.

## Current audit

| Integration | Baseline evidence | Concrete gaps / next validation |
| --- | --- | --- |
| n8n | Package 25 checks, 12 adversarial contracts, HMAC tests and native host lifecycle pass in offline run 40646332504 | Exact identity; atomic campaign-qualified cursors; allowlisted output; encrypted signing secret; transactional producer-backed replay admission. Real polling, credential tests, restart, duplicate suppression and asynchronous deactivation cleanup verified in Docker --network none. Original commercial producer receipt-extension support remains unverified. |
| SDK / CLI | Patched local snapshot: lint, types, build, 98 tests plus built CLI adversarial checks | Exact launch/run/root-session correlation; authenticated reads, body/idle-stream deadlines, typed identity/schema failures, no redirect forwarding. Failed/stopped campaigns produce CLI error 1; stale zero counts cannot hide fetched findings. Patched archive is now consumed by the Action and VS Code; actual fork HTTP checks pass. |
| GitHub Action | Patched snapshot; build, types, 30 tests and executed bundled-action checks pass | Failed/stopped assessments and findings-read errors fail closed; counts derive from fetched findings. Real toolkit outputs and SARIF verified for high/empty/failed/auth/malformed cases over owned HTTP; no comments posted. Hosted runner rerun pending. |
| GitLab | Schema pin 15.2.5; strict mapper and exact generated YAML script cases pass locally | Run identity, findings-read, parse and mapping errors become exit 1 and failed-scan SAST diagnostics; exit 2 remains the optional nonblocking gate. Real GitLab runner/server and report ingestion still need a configured disposable host. |
| VS Code | Updated client; types/build and all 12 data-layer/real-adapter tests pass | Removed developer-home path and silent skip. 19 Node data/grant tests pass; scoped expiring trusted-local reveal, fresh reads, metadata-only default bodies and refresh race/failure protection implemented. Offline native VS Code 1.106.3 acceptance pending. |
| JetBrains | Portable required bridge/SDK fixtures and offline native harness added; CI pending | JDK 21 runtime plus declared JDK 17 compilation toolchain; pinned IntelliJ 2025.2.6.2. Baseline inspection found synthetic run IDs pinned as campaign IDs, raw subprocess error text, stale asynchronous panel reads and no enforced trusted-local reveal expiry. These remain next corrections; a green baseline alone will not close them. |
| Jenkins | Source/tests and isolated Docker host recipe located; not yet run | Build HPI and run Jenkins harness/host cases for fail vs unstable precedence, empty results and scanner errors. Local Docker/Maven are absent; hosted CI is available. |
| Grafana | Native Go/plugin/frontend test inventory located; not yet run | Run datasource and dashboard contracts, verify safe projections/denominators, then disposable Grafana plugin/host requests. Local Go/Docker are absent; hosted CI is available. |
| Splunk | All 7 guard checks and 6 loopback mock-HTTP checks pass | Audit forwarder field types and state/error behavior; validate HEC mapping without external traffic. Native proprietary host/license prerequisites remain unverified. |

## Review order and completion rule

For each integration, inspect launch identity, authorization/transport errors,
result/gate semantics, sensitive-output boundaries, durable restart/retry state,
and the actual consumer host. Existing green unit tests are baseline evidence,
not proof of an untested host. An unavailable credential, license acceptance or
native capability is recorded explicitly rather than silently skipped or called
complete. Once a fix passes its relevant checks, update provenance and this
ledger, push the checkpoint, and proceed to the next item.

## 28 October audit intake

The user supplied the pinned commercial audit ZIP and commits 84c9d36/7bcdf36.
The [review](../pro-audit/2026-10-27/DARKMOON_AUDIT_REVIEW.md) identifies 13 static
API discrepancies, 126 original packaged test functions, 52 route declarations
(including aliases), and Nuitka-generated native interfaces. No original runtime
response snapshots are present. Preserve the difference between static evidence,
fork-tested behavior and original wire verification. The 76 generated acceptance
rows are plans, not executed tests. The review's P0 method/path contracts are next,
followed by credential/history/run/webhook projections and the remaining native
host/IDE gaps. Existing fork security and independent extensions remain required.

The network-disabled n8n run 40625693807 passed package/adversarial contracts,
the real action workflow/credential checks, native polling and persisted poll
cursor restart, HTTP 401 rejection and safe webhook output. The final webhook
restart failed: the test's shutdown timeout captured the mutable host variable
and could terminate a later host. The follow-up binds the timer to its own
process and clears it after exit. Final webhook restart/replay/deactivation
acceptance remains pending the rerun; it is not marked complete.

The first audit-driven implementation increment adds secure password-change,
run-stop DELETE and version-required scheduler PUT aliases. See the
[typed evidence and method/input contract](../pro-audit/2026-10-28/compatibility-progress.md).
API03's vendor flat schedule-payload adapter is still open, and none of the rows
are labeled vendor-wire verified. The other ten static discrepancy rows remain
in the systematic queue alongside the native integration-host work.

The shutdown-timer follow-up reached the final native replay assertion and
exposed an actual restart duplicate (two executions for one signed event).
Webhook receipt mutations in that pinned n8n path are therefore not accepted as
durable evidence. The next fix adds an authenticated, transactional producer
receipt journal, with no raw payloads, fail-closed admission, finite retention,
and no eviction of fresh entries at capacity. See [receipt contract](webhook-receipts.md).
Native replay/deactivation remains pending until the new offline host run passes.

Offline run 40645301696 passed producer-backed replay suppression across process
restart. Its remaining failure was an immediate post-deactivation registration
assertion. The pinned n8n 2.45.4 workflow service can enqueue unpublish via its
publication outbox, so the HTTP acknowledgment does not establish completed
cleanup. Acceptance now waits at most 15 seconds each for remote registration
deletion and route removal, retaining both required outcomes. The rerun remains
pending; no cleanup success is claimed from the acknowledgment alone. All other
applicable gates on 9d2833c passed.

Offline native n8n run **40646332504** completed successfully, including all
restart, producer-receipt replay and eventual deactivation outcomes. This closes
the pending lifecycle validation above. Patched SDK/Action/VS Code checkpoint
1ac3a8d also passed hosted SDK/CLI, consumer snapshot, bundled Action and real-fork
HTTP acceptance, both regression gates and browser acceptance. These are fork
results; no commercial Pro runtime was executed.

Native VS Code run 40647818948 built the editor/extension successfully but the
initial host invocation has not exited within the expected test duration. A driver
follow-up remains deferred in the working tree: direct cached-executable launch,
a 240-second deadline, startup/extension logs and removal of the helper's implicit
`--disable-workspace-trust`. Native success is still pending.

## Integration-first continuation (28 October)

User direction: **focus on integrations now; tests later**. Further test expansion,
native-host debugging and test execution were paused. The implementation batch
below is source-reviewed and syntax-checked where the local tools support it,
not type/build/native validated. Earlier passing evidence does not validate it.

| Consumer | Integration implementation | Later verification boundary |
| --- | --- | --- |
| JetBrains | Bundled bridge + patched SDK default; real OSS directory configuration; full reference forwarding, safe subprocess failures, bounded output/processes; trusted-local expiring reveal; selection/connection/credential binding | Kotlin compilation, platform API compatibility, packaging, UI and subprocess lifecycle |
| Jenkins | Bundled CLI on agent; exact completed campaign plus strict findings; fetched-result gates; constrained artifact/log/argument handling; safe SARIF | Maven/HPI build and Jenkins native step/artifact behavior |
| Grafana | Live datasource-backed app pages and config; posture/legacy adaptation; published PR vs local-proposal views; retest status; typed safe frames and aligned sparse trends; nested logo packaging | Frontend types/build, Go formatting/build, datasource/app/native host behavior |
| Splunk | Typed identity-preserving projections; strict REST/HEC errors; saved-target resolution for retests; no redirects; serialized quota state; local-proposal sourcetype | Mapping/transport/concurrency behavior and a permitted host |
| Action | Follow-up removes free-form bodies from JSON artifacts and URL query/fragment data from endpoint output | Artifact regression coverage |

Direct Splunk HEC webhook format was previously advertised although this fork's
dispatcher always emitted signed Darkmoon envelopes. Unsupported formats are
now rejected explicitly. The authenticated HEC forwarder is the supported path;
a separate HEC token is not replaced by a webhook signing secret.

See [implementation detail](integration-implementation-progress.md). Original
commercial wire parity, credential field/owner semantics, the broader static
API discrepancy backlog and server-wide evidence policy remain separate open
items. No vendor binaries, real assessments or external notifications ran.

## Webhook detail/test follow-up (28 October; source-only)

Administrator-only webhook inspection and explicit single-hook synthetic test
admission are implemented in the fork with safe serialization, persistent
throttling, bounded queue work and the existing signed delivery worker.
The n8n receiver retains transactional receipts but does not execute a
workflow for test events. See [webhook-receipts.md](webhook-receipts.md).
No new tests or external deliveries were run; no vendor-wire claim is made.
