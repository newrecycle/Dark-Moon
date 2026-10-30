# Commercial API parity: runnable acceptance and evidence register

Updated 29 October 2026. Start with [current status](current-pro-status.md).
This runbook is for a new worker starting with no conversation history.

## What is and is not closed

The 13 discrepancies in the dated static CSV have fork implementations. They
are not 13 currently missing routes. **None of the 52 original declarations is
vendor-wire verified.** Authentic commercial responses have not been captured;
the user has no vendor license and does not intend to acquire one. Treat vendor
execution as unavailable. Do not bypass activation. Continue useful fork/static
checks and leave the vendor column unavailable rather than fabricating fixtures.

Pinned reference image:
`ascit/opencode-darkmoon-pro@sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907`.
[Original 52 declarations](actual-pro-endpoint-crosswalk-2026-10-27.md),
[typed contracts](../pro-audit/2026-10-28/typed-contracts.json), and
[static audit](../pro-audit/2026-10-27/DARKMOON_AUDIT_REVIEW.md) are the reference.
Do not count slash aliases as separate business capabilities.

## Fresh checkout and fork regression commands

Use Linux, Python 3.11, Node 24 and Git. Run from the checkout root:

```bash
git clone --branch pro --single-branch https://github.com/newrecycle/Dark-Moon.git
cd Dark-Moon
git rev-parse HEAD
python3.11 -m venv .venv
.venv/bin/python -m pip install pytest PyYAML -r mcp/requirements.txt -r mcp/community/requirements.txt
PYTHONPATH=mcp .venv/bin/python -m pytest mcp/tests tests/community -q
npm ci --ignore-scripts --prefix integrations/upstream/client
npm run lint --prefix integrations/upstream/client
npm run typecheck --prefix integrations/upstream/client
npm test --prefix integrations/upstream/client
npm run build --prefix integrations/upstream/client
DARKMOON_TEST_PYTHON="$PWD/.venv/bin/python" node tests/community/sdk_fork_http.cjs
```

Check package.json if a script was renamed. These exercise disposable fixture
storage/loopback, not a vendor engine. Native browser acceptance is owned by
community-browser.yml; consult its exact install/run steps for Playwright.
Do not point these test fixtures at an existing operator data directory.

## Required comparison matrix

For every row execute: valid populated and valid empty responses; anonymous,
viewer, analyst, administrator and revoked/expired-session requests; malformed,
blank, repeated and unknown parameters; unknown identity and wrong-campaign
identity; success and failure body/status/headers. Record intentional stronger
fork denials explicitly. Never weaken authentication to make a comparison pass.
The declaration numbers below cover all 52 reference rows.

| Declarations | Surface / required scenarios | Fork test starting points | Vendor evidence |
|---|---|---|---|
| 1–4 | Projects/targets list/detail, linkage, empty/orphan records, deterministic ordering | test_pro_features.py; test_evidence_access.py | Unavailable |
| 5 | Target evolution, tied/undated campaigns, retained-snapshot vs event history | test_finding_lifecycle.py | Unavailable |
| 6–10, 12–13 | Campaign/finding details, graph/report readiness, evidence metadata; redacted default vs scoped reveal | test_evidence_access.py; test_attack_paths.py; test_report_roadmap.py | Unavailable |
| 11 | History target filter, limits/offset/snapshot sequence, corruption, stable event identity | test_finding_lifecycle.py; test_finding_history_durable.py | Unavailable |
| 14 | Overview totals, missing/null values, denominator/cohort definitions | test_posture.py; test_pro_features.py | Unavailable |
| 15 | Launch flat input fields, credential references, target scope, idempotency and distinct run/campaign IDs | test_pro_contract_aliases.py; test_campaign_identity.py; test_credential_access.py | Unavailable |
| 16 | Run SSE names/envelopes, heartbeat, terminal/error, disconnect/reconnect, raw grant expiry and log rotation | test_run_discovery.py; test_evidence_access.py; test_core_contract_boundaries.py | Unavailable; rotation matrix incomplete |
| 17–20 | DELETE stop idempotency, queued/running/cancelling/terminal states; active/log paging; missing/unsafe files | test_run_discovery.py; test_run_discovery_scale.py | Unavailable |
| 21–25 | Slash aliases, flat create/update, PUT version conflict, recurrence/default/timezone/DST, deletion and overlap | test_scheduler_compatibility.py; test_calendar_scheduling.py | Unavailable; vendor defaults unknown |
| 26–29 | Login errors, password change validation/revocation, me, logout; role and session transitions | test_pro_contract_aliases.py; test_community.py | Unavailable |
| 30–35 | Provider catalog, capability filter, structured fields, masked CRUD, ownership/grants/revocation | test_credential_discovery.py; test_credential_access.py | Unavailable; provider field semantics unknown |
| 36–38 | Exact finding-to-PR/proposal lookup, many-to-many links, publication state and safe URL shape | test_finding_lifecycle.py; test_core_contract_boundaries.py | Unavailable |
| 39–40 | System info/update-status: absent stamps, registry errors, no implicit deployment | test_pro_features.py; test_community.py | Unavailable |
| 41–47 | Webhook aliases/filter/detail/create/delete/test; 202 admission vs delivery; retry/HMAC/SSRF/replay | test_webhook_delivery_contract.py; test_webhook_receipts.py; test_webhook_tls_loopback.py | Unavailable |
| 48 | Global SSE sequence, known/unknown/evicted cursors, restart checkpoint, retention and webhook atomicity | test_events_durable.py; test_core_contract_boundaries.py | Unavailable |
| 49–51 | Retest aliases, original/new campaign identity, failed/stopped/running/empty comparison; not_observed never fixed | test_pro_features.py; sdk_fork_http.cjs | Unavailable |
| 52 | Metrics UTC boundaries/buckets, missing values, zero denominators, alignment and query rejection | test_posture.py; Grafana backend/frontend tests | Unavailable |

All Python paths in the table are under tests/community/. A listed file is a
starting point, not a claim that every comparison scenario already has a test.
Run a focused file with `PYTHONPATH=mcp .venv/bin/python -m pytest tests/community/FILE -q`.

## How to capture authentic responses if an authorized reference becomes available

This is conditional guidance, not a request to obtain a license. Use a disposable
operator-owned reference workspace matching the pinned digest, with synthetic
campaigns, findings, source and credentials. Record image digest, server build,
role, setup steps and fixture IDs before each case. Keep reference and fork
storage separate. Do not run mutation/launch/webhook cases against production.

For read-only smoke capture, set API_BASE to an explicitly configured host
(including /api/v1), TOKEN to a synthetic fixture account bearer token, then:

```bash
umask 077
mkdir -p /tmp/darkmoon-parity-private
curl --silent --show-error --max-time 30 --max-redirs 0 \
  --header "Authorization: Bearer $TOKEN" \
  --dump-header /tmp/darkmoon-parity-private/headers.txt \
  --output /tmp/darkmoon-parity-private/body.json \
  "$API_BASE/system/info"
```

Do not enable shell tracing, print tokens, follow redirects or commit raw captures.
For each matrix scenario capture both systems' method/path/query, sanitized
request JSON, status, content type, body/schema, relevant cache/auth headers,
and ordered SSE frames. Map generated IDs/timestamps consistently while retaining
null-vs-missing distinctions, ordering, types, error fields and state transitions.
For auth/cookie headers retain scheme/flags only, never credential values.
Use explicit bounded SSE capture duration and record timeout vs terminal event.
Route names and type stubs alone cannot supply response snapshots.

Author independently sanitized fixtures under tests/community/fixtures/parity/
only after review. Give each fixture reference digest, capture date, scenario,
role, setup/reset recipe and SHA-256 of its private raw capture. Keep raw evidence
private. A new comparator must assert documented semantic equivalence per case,
with explicit allowances for stronger fork security. Do not simply strip every
difference or replay fork responses as vendor fixtures. Reference capture and
a fixture-based comparator are **not yet implemented** because the source
responses do not exist.

## Closure and ongoing updates

A row closes only when a new worker can reproduce its synthetic setup, run the
fork checks, and inspect authentic reference fixtures plus exact differences.
Keep four separate statuses: implemented / fork-tested / vendor-compared /
intentional divergence. Record commit SHA, command, exit code, case count and
CI run URL. Missing reference access leaves vendor-compared unavailable even
when every fork check passes. Native integration acceptance is a separate claim.

| Checkpoint | Observed outcome | Remaining |
|---|---|---|
| 9ee85be | 495 Python tests / 268 subtests locally; all seven triggered hosted workflows passed | All authentic vendor comparisons; scenarios above need explicit fixture reconciliation |
| Documentation reconciliation | Current index and historical notices created; runnable matrix covers declarations 1–52 | No vendor execution or new runtime test claimed by this documentation change |

### Shared SDK ambiguity correction

OSS snapshot discovery now rejects multiple new campaigns without pinning a
result. SDK lint/typecheck/build and 100 tests passed locally. Consumer archives
were rebuilt together; authenticated HTTP remains a separate exact-identity path.
A single unrelated campaign can still satisfy the legacy singleton heuristic:
explicit producer binding remains open and this is not marked full closure.

### Scoped source-browser checkpoint

Fork extension: administrator one-use source grants and configured-root listing
implemented. Twelve evidence HTTP tests passed, including a real disposable Git
repository, no unauthorized probe, replay/role/scope/config removal and tracked
symlink exclusion. Browser assertions added; hosted execution pending. This does
not change the 52 vendor declarations or close commercial wire comparison.

### Native remediation acceptance

The retained runtime workflow now executes tests/community/remediation_native.py
using the actual production Docker Sandbox and prebuilt tools/lab image. It checks
validated, regression-failing and unavailable-image outcomes, unmodified source,
non-root/read-only/network-isolated probes, and unpublished local results.
Reproduce with `docker build -f tools/lab/Dockerfile -t darkmoon-ui-lab .` then
`PYTHONPATH=mcp .venv/bin/python tests/community/remediation_native.py`. Exit 3
means unavailable. Hosted result pending. No model inference or forge publication
is included; those remain explicit outstanding workflow stages.

### Observed integrated backend result

After source-browser implementation: `PYTHONPATH=mcp /tmp/dm-current-venv/bin/python
-m pytest mcp/tests tests/community -q` passed **496 tests and 268 subtests**
locally. SDK/consumer provenance now also asserts the lockfile SHA-512 matches
its archive. An initial hosted SDK run exposed stale lock integrity and the
inventory rejected a retired-integration mention; both were corrected in the
subsequent checkpoint. Do not label those failed runs successful.

### Resource navigation checkpoint

Added strict metadata-only hash links `#campaign/ID` and
`#vulnerability/ID?campaign_id=CAMPAIGN_ID`. The campaign-qualified finding route
never guesses a campaign. Links contain no grants or revealed bodies; loading,
missing/access-error and reload/Back browser scenarios are included. Pure route
checks run with `node tests/community/resource_routes.cjs` in the retained Tests
gate. Browser execution remains pending for this checkpoint. This closes two
navigation surfaces, not all 13 original Angular routes or visual parity.

### Observed native remediation result

The owned-lab-analysis job in runtime run 40946712274 passed, including the new
production Docker remediation harness before owned-loopback analysis. Actual
containers exercised validated, validation_failed and infrastructure-error
unreproduced outcomes. No model inference or forge write was performed. The
separate image/provider job was still running at this observation.

### Date-window posture increment

An additive fork API selects campaign starts in explicit half-open UTC windows,
while retaining current triage semantics. Tests: posture + evidence suites,
27 passed / 6 subtests. See dashboard-posture.md for commands, strict query
rules and cohort definition. Historical as-of reconstruction, cross-campaign
identity deduplication and a cohort-aware UI remain open; no vendor comparison
or complete item-5 closure is claimed.

### Run-discovery keyset increment

Optional live keyset pages now avoid offset shifts from newer inserts; existing
offset clients retain their contract. Scale/storage focus: 14 passed and 110
subtests. Existing run/storage focus: 24 passed and 106 subtests before the new
case. See control-state-sqlite-2026-10-29.md for copyable requests and limits.
This does not claim frozen cross-request state or whole-system crash consistency.
The resource-link browser fixture initially attempted navigation while logged
out; it now explicitly authenticates before opening and after reload, preserving
the server's no-persisted-token policy. Its rerun remains pending.

### Graph/XR boundary increment

VR capability queries now tolerate policy/permission rejection without failing
the ordinary graph. Delayed capability replies cannot update detached controls;
start requests are deduplicated and a view abort ends its XR session. The browser
suite injects rejected XR capability promises while exercising the normal graph.
This validates unsupported-state behavior only; physical headset rendering,
controller input and independent exploitation proof remain unavailable.

### Explicit OSS producer binding (supersedes singleton gap for new launches)

New shared SDK launches request JSON output from their own process and validate
its root-session events before resolving an exact new non-subagent campaign.
Failed/identity-less/conflicting producers reject; a sole unrelated campaign is
not selected. Existing pinned bindings are rechecked against current records.
Custom launch templates must emit OpenCode JSON events. Legacy external handles
without producer fields retain compatibility semantics; callers should migrate
rather than treat legacy singleton discovery as strong attribution.

SDK `npm run ci` passed lint, types, **105 tests** and builds. New tests launch real
local Node producers, cover unrelated singleton/concurrent records, malformed
producer identity, nonzero exit, missing root and changed contradictory bindings.
Refreshed Action/VS Code archives and lock hashes pass client_snapshot.py. Built
SDK-to-fork authenticated HTTP contracts also passed. This tests trusted local
process attribution, not a vendor engine or cryptographic producer attestation.

The final integrated Python source before this SDK-only increment passed **499
tests and 278 subtests**. Browser run 40947738123 passed source grants, resource
links/reload/Back, policy-denied XR and dedicated path revision acceptance.

### Producer deadline and GitLab fixture compatibility follow-up

CLI --timeout now also bounds its OSS producer. Invalid deadlines reject before
spawn; a real stalled local child is terminated and cannot yield a campaign.
SDK lint/types/**106 tests**/build passed. Consumer archives and both lock hashes
were refreshed again and their provenance check passed.

The disposable GitLab engine now emits its own root-session JSON event and exact
campaign binding instead of relying on snapshot discovery. The actual built CLI
passed all five native fixture cases locally (passing, empty, blocking,
nonblocking, findings-read error), including exact campaign IDs and no private
canary output. Reproduce after SDK build:
`python integrations/upstream/gitlab/test/fixture_cli_acceptance.py`.
This runs before real CE/Runner acceptance in the existing native workflow.
The preceding hosted native VS Code and SDK runs passed on bc86713; native GitLab
must be taken from the follow-up revision because its producer fixture changed.

### Legacy identity closure

Unbound legacy OSS handles now reject automatic discovery, including a sole new
campaign. Callers must use new producer-bound launch handles or explicit known
campaign IDs. This removes the last timestamp/snapshot attribution heuristic.
The compatibility change is documented in the SDK README. SDK lint/types/build
and all 106 tests passed; both consumer archives and lock hashes were refreshed.
All five workflows on d6bd57f completed successfully, including modern GitLab
CE/Runner and native VS Code. Commercial wire evidence remains unavailable.
