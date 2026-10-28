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

## Deferred

Behavioral tests, Kotlin/Java/Go/full TypeScript builds, packaged native hosts and
consumer artifact checks remain for the requested later verification pass.
Previous VS Code driver follow-ups and a Kotlin boundary test remain in the
working tree for that pass. The vendor wire contract is still static evidence;
no original licensed runtime was executed. Credentials/provider ownership and
field adapters, remaining static route discrepancies and global evidence access
policy remain in their existing audit ledgers.
