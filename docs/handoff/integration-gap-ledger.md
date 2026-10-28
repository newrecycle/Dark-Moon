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
| n8n | Package build and 25 existing checks pass; native n8n 2.45.4 host previously passed | Fix explicit launch correlation, partial-poll cursor loss, campaign-qualified finding identity, safe event projection, local-proposal vs PR events, failed cleanup retention. New adversarial contract tests pass locally. Native trigger activation/restart/persistence validation in progress. Local host execution was blocked by automatic review after n8n attempted vendor API traffic. Both host tests now require OS-level network isolation and CI runs them with Docker --network none; optional banners/whats-new/license refresh are also disabled. Signing secrets move from exportable static data to encrypted credentials; actual HTTP rejection status is set explicitly. |
| SDK / CLI | Lint, types, build and all 75 tests pass | HTTP backend ignores returned campaign identity and retains an unsafe campaign-set fallback. Review interrupted run/auth/malformed response behavior and cross-consumer version compatibility. |
| GitHub Action | Build and all 27 tests pass | Add disposable real workflow contract, verify tool-error vs finding gate outcomes, safe summaries/SARIF/artifacts, and inherited client correlation. No comments will be posted. |
| GitLab | Schema pin 15.2.5 and all 15 mapper assertions pass | Mapper silently turns malformed/missing findings into clean empty reports. Audit template exit handling and test strict error propagation; native runner still unverified. |
| VS Code | Types/build and 8 data-layer tests pass | Four real-adapter tests silently skip because they reference an upstream developer's absolute home path. Fix portable fixture resolution and run actual extension-host tests. |
| JetBrains | Source/test inventory located; not yet run in this continuation | Run client/plugin tests and host fixtures; current local Java is 17. The native build's declared JDK/runtime requirements must be respected. |
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
