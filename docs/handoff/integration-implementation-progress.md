# Integration implementation checkpoint — 28 October 2026

The user deferred tests to prioritize completing integration wiring. This batch
is an implementation checkpoint, not a green native acceptance claim. Python,
JavaScript/TSX, XML and JSON syntax were checked without executing assessments.
Kotlin, Java, Go and complete frontend builds still need the later pass.

## Client distribution

JetBrains previously invoked a CI command which does not implement its GUI
read grammar. The default now extracts a packaged bridge and the patched SDK
together. Jenkins similarly ships the patched portable CLI in its HPI and copies
it to the agent. Node 18+ is a runtime prerequisite. No npm installation runs
inside the editor or Jenkins step. Explicit custom commands remain possible.
Snapshot manifests and MIT/Zod licenses accompany both bundled runtimes. They
come from the fork SDK checkpoint 126f6daa, version 0.2.1-darkmoon.1.

## JetBrains

All bridge campaign-reference operations retain correlation rather than treating
run IDs as campaign IDs. Temporary `run:<id>` status records are not pinned.
Wrong identities, malformed output, interrupted transport and nonzero process
results fail explicitly. Process lifetime/output and stream frames are bounded;
raw stderr/stdout are withheld from errors.

Connection refresh clears stale cached state. Background findings and full
reads are bound to the selection and connection. Full evidence/report rendering
requires a confirmed trusted, focused, local window and expires within 60 seconds;
focus loss, panel hiding, credential changes and settings/selection changes revoke
it. Default panels retain metadata rather than evidence bodies. This does not
replace server-side authorization or retract already observed/copied values.
The pinned platform trust/remote APIs and behavior across the declared IDE range
remain to be compiled and exercised.

## Jenkins

The step requires an exact completed campaign record and a readable typed
findings array after launch. Fetched findings drive failure/unstable counts.
Malformed or missing data cannot be downgraded to an empty report. Configured but
unavailable credentials fail explicitly. Known generated files are cleared at
start; only named outputs are archived. Logs contain lifecycle metadata rather
than raw responses or command arguments. Shared SARIF withholds free-form
finding descriptions/remediation and URL credentials/query/fragment data.
Node prerequisites, HPI resource extraction, remote-agent paths and native Jenkins
execution need later verification.

## Grafana

The app's former starter pages are replaced with datasource-backed overview,
campaign, finding, target, trend, published-PR, local-proposal and retest views.
The app saves a datasource UID; URL/token settings belong to the actual datasource,
with encrypted credentials. Request subscriptions are cancelled on view changes.
Failures and unavailable counts remain distinct from valid empty results.

The backend prefers retained-workspace posture, with legacy overview fallback
only on 404. Health probes protected campaign data. Scalars cannot stringify
nested evidence; metadata proxy output is projected rather than forwarded.
Sparse trend series share sorted timestamps and nullable gaps. Proposal state
is separate from published PRs, and retests retain status even with no finding
rows. Nested datasource assets are packaged, and SDK Mage output belongs beside
the nested datasource manifest. Native compatibility and build correctness await
the later pass; no broad Grafana version claim is newly established here.

## Splunk

REST IDs now reach the HEC identity fields. Typed scalar projections and finite
numeric stats exclude nested payloads. Local proposals have a separate sourcetype;
unknown/running retests are not labelled completed. REST failures stop the batch.
HEC needs successful HTTP plus `code: 0`; redirect forwarding and unsupported
indexer-ACK claims are rejected. Retries/snapshot forwarding remain potentially
duplicate; content fingerprints are not an exactly-once guarantee.

The alert action resolves an allowlisted host to one authenticated saved target
before a retest. It reports launch acceptance rather than completion. Quota state
uses a process lock and atomic replacement. This fork does not implement direct
`format=splunk_hec` webhook delivery: its API now rejects unsupported formats,
and docs direct users to the authenticated forwarder.

## Webhook inspection and synthetic test deliveries (source-only)

Listing and administrator-only webhook detail share a safe projection that
redacts signing-vault references and URL paths, queries and fragments.
Registration still returns generated secrets once. Explicit per-hook test
admission queues a unique synthetic event using the signed retry worker,
with transactional throttling and queue bounds. n8n validates and admits
test receipts but does not execute a workflow. HTTP 202 means accepted,
not delivered. See [webhook-receipts.md](webhook-receipts.md) for schema,
disabled-hook behavior and deferred security checks. No tests ran.

## Run discovery and bounded logs (source-only)

The run dispatcher now resolves literal `/run/active` and `/run/logs` ahead
of the generic run-ID route. Queue records use one allowlisted public
representation in detail, stop, overview and legacy job routes; run and campaign
IDs remain separate. Active discovery distinguishes queued, running and a
cancel-requested running state. Log-history queries validate filters and page
deterministically; raw subprocess content is absent from default/collection
responses. The only raw-output reads require explicit administrator opt-in and
are limited by bytes, lines and line length without following symlinks.

The campaign UI loads active runs and 50-record history pages independently
from the full workspace snapshot, distinguishes unavailable logs and empty
history, discards stale requests, and permits explicit bounded raw reveal to
administrators. SSE keeps heartbeat/terminal behavior with privileged opt-in
for its raw output frames. This is an intentional privacy boundary, not a
commercial Pro wire-parity claim. See the 28 October compatibility record for
route schemas, limit values, privacy caveats and deferred HTTP/browser cases.
No assessment, vendor binary, tests or build was run for this increment.

### Run/log verification follow-up

The later [focused offline verification workflow](../../.github/workflows/run-discovery-verification.yml)
passed [11 new run/log cases plus 10 existing compatibility cases](https://github.com/newrecycle/Dark-Moon/actions/runs/40664772710),
including Python module compilation and dashboard JavaScript parsing.
The [community browser acceptance](https://github.com/newrecycle/Dark-Moon/actions/runs/40664888578)
also passed with mocked run/log collection and detail behavior. This verifies
the fork's isolated API/UI contract, not commercial-vendor runtime parity,
native-client builds or adversarial streaming/rotation races. The older
scheduler invalid-input assertion was brought into alignment with a newer,
supported flat target update; no scheduler implementation was rewritten.

## Deferred

Behavioral tests, Kotlin/Java/Go/full TypeScript builds, packaged native hosts and
consumer artifact checks remain for the requested later verification pass.
Previous VS Code driver follow-ups and a Kotlin boundary test remain in the
working tree for that pass. The vendor wire contract is still static evidence;
no original licensed runtime was executed. Credentials/provider ownership and
field adapters, remaining static route discrepancies and global evidence access
policy remain in their existing audit ledgers.


## Finding lifecycle read continuation — 28 October 2026

API04, API05 and API08 now have additive authenticated read projections for
retained target campaigns, a newly recorded finding mutation journal and
exact finding-to-remediation links. The existing finding detail dialog
consumes the linked-record lookup; no additional vendor UI page was added.
The complete [dated response contracts and limitations](../pro-audit/2026-10-28/compatibility-progress.md)
specify pagination, strict validation, ordering and empty/error behavior.

The history journal records only new instrumented events from activation,
never reconstructed transitions. Target evolution reflects retained current
finding states by dated campaign, not past point-in-time risk. Local proposals
remain separate from published PR metadata. Tests, builds and licensed
vendor runtime checks remain deferred; no vendor wire parity or regression
freedom is asserted.


## Finding lifecycle verification follow-up — 28 October 2026

Implementation commit `9c8d6a8` now has dedicated offline HTTP/storage
tests ([commit `99dd9348`](https://github.com/newrecycle/Dark-Moon/commit/99dd93485b5d758e259dac0f1e526f5a07e2fa90)),
browser detail assertions and a focused repeatable CI gate
([commit `2295fcf0`](https://github.com/newrecycle/Dark-Moon/commit/2295fcf0e488ca117eb6101778ad9763f315e855)).
The [focused run](https://github.com/newrecycle/Dark-Moon/actions/runs/40665274418)
passed 10/10 tests; the [full community campaign suite](https://github.com/newrecycle/Dark-Moon/actions/runs/40665274332)
passed 403 tests and 66 subtests; the
[browser run](https://github.com/newrecycle/Dark-Moon/actions/runs/40665274368)
passed. These are independent-fork results, not original-vendor wire parity.
Historical backfill, crash-atomic snapshot/journal writes and native vendor
comparisons remain unsupported or unverified. Detailed cases and limitations
are in the [dated compatibility review](../pro-audit/2026-10-28/compatibility-progress.md).

## Combined delegated-feature review (28 October 2026)

The dated [compatibility review](../pro-audit/2026-10-28/compatibility-progress.md#consolidated-delegated-integration-review--28-october-2026) records the 38-commit review scope, concrete boundary fixes, known limitations and deferred verification. Source corrections cover strict credential and SSE query validation, initially-internal webhook signing keys and conservative PR URL classification. Earlier native/CI results were not re-executed during this integrations-first pass. The standalone Splunk agent branches were inspected but not merged; local uncommitted worker state was not available through the GitHub connection.

## Grafana lifecycle/time consumer follow-up — 28 October 2026

Source inspection after delegated review `b512f70` found a concrete producer/
consumer mismatch: running fork retests have `verdicts: []`, but the Grafana
adapter required `findings`. The adapter now renders lifecycle and exact
campaign/target/run references independently of comparisons, supports either
comparison alias with strict agreement, and preserves `current_finding_id`.
Missing completed results and malformed/foreign records fail explicitly.

Trend panel reads now forward Grafana's selected range and parse fork ISO-week
buckets. Findings retain campaign identity and nullable CVSS. App reads validate
column alignment and avoid silent substitution of unavailable datasource UIDs.
See the Grafana READMEs for the supported contract. No behavioral tests or builds
ran. Verification is handed to a separate worker as requested; Jenkins remains
in its previously claimed workstream.

## Bounded active-run discovery — 28 October 2026

`/run/active` now pages public metadata (default 50, maximum 100; offset ceiling
100000) instead of returning all active runs. The dashboard has independent
active/history pagers and live-page warnings. Both read paths use bounded
additional selection memory and preserve exact total counts and descending
identity-tied ordering. Full JSON-store loading remains; these are live offset
pages, not snapshot-isolated cursors. Source/syntax review only; post-commit
verification is delegated. See the dated compatibility record for limits and
remaining finding-journal scalability work.

## Bounded finding-history API reader — 28 October 2026

The history endpoint now uses bounded binary JSONL reads and a bounded sorted
page selection while checking all stored rows and preserving exact totals/order.
Offsets intentionally stop at 100000; lines at 65536 bytes. Invalid/incomplete
storage fails explicitly, and event writers enforce the same metadata/size
contract before append. Internal unpaged reads remain available, but the HTTP
route always pages. Full scans, lock duration, retention/indexing and separate
snapshot/journal writes remain limitations. Behavioral/resource verification is
delegated after this source/AST checkpoint.

## Grafana verification follow-up — 28 October 2026

Grafana's delegated behavioral verification now has an executed, passing
[offline Go/frontend CI gate](https://github.com/newrecycle/Dark-Moon/actions/runs/40725844906).
It uses the declared Go 1.26.3 and Node 22 toolchains, runs `gofmt` in CI,
`go test -race ./pkg/...`, `go build ./pkg/...`, `npm ci --ignore-scripts`,
`npm run typecheck`, `npm run test:ci -- --watch=false` and
`npm run build`. The new Go and React tests cover exactly scoped retest
references, completed-vs-running comparison requirements, UTC time ranges,
ISO week rollover and sparse null gaps, nullable CVSS, malformed frames,
datasource explicit selection and stale responses, plus redirect and evidence
metadata protections.

A native [Grafana 13.1 disposable-host acceptance gate](../../.github/workflows/grafana-native-host.yml)
is separately configured to build packaged Mage/webpack artifacts and query
a synthetic API via Grafana on an isolated Docker network. Initial native
harness runs revealed an obsolete image reference, an inaccessible
internal-network host port and an endpoint lookup mismatch. Those harness
issues were corrected without modifying other consumers. The latest
GitHub Actions run remains the authoritative native outcome; the passing
offline suite does not assert native Grafana success. No commercial Pro
binary, external provider, real scan, deployment or Jenkins work was run.

### Grafana native-host verification result — 28 October 2026

The [focused Go/frontend CI run 40725844906](https://github.com/newrecycle/Dark-Moon/actions/runs/40725844906)
passed Go race tests/build and frontend typecheck/Jest/webpack build. The
[disposable native Grafana 13.1 run 40727729155](https://github.com/newrecycle/Dark-Moon/actions/runs/40727729155)
also **passed** with the actual bundled Mage backend and frontend package:
Grafana registered the app/datasource, and its `/api/ds/query` HTTP interface
returned exact completed retest campaign/target/run references from the
synthetic fixture. See [full Grafana verification record](../pro-audit/2026-10-28/grafana-verification.md)
for commands, coverage, exposed defects, native harness corrections and
remaining version/vendor/browser limitations. Jenkins and unrelated integration
work were untouched.
