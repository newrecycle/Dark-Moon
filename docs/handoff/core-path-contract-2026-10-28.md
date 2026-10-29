> **Historical baseline:** This document preserves evidence at its stated revision. For current completion/open status use [current Pro status](current-pro-status.md) and [runnable commercial API acceptance](commercial-api-parity.md). Earlier missing-route, JSON-only storage, host-pending and no-path-edit claims may be superseded.

# Core paths and contract continuation — 28 October 2026

Owner: coordinating ChatGPT worker, prompts 8 and 9. Prompts 1–7 and JetBrains
removal belong to the other assigned workers. This increment preserves the
server-side evidence boundary that landed during implementation. It does not
claim completion of all visual, remediation or commercial-runtime parity work.

## Recorded path revisions

| Operation | Contract |
| --- | --- |
| Create | Existing `POST /api/v1/campaigns/{cid}/paths`; first revision is version 1. |
| Edit | `PUT /api/v1/campaigns/{cid}/paths/{id}` with exactly title, steps, reviewed:true and current positive integer version. Stale versions return HTTP 409. |
| History | `GET /api/v1/campaigns/{cid}/paths/{id}/revisions`; ordered immutable reviews, exact total, current_version and deleted marker when authorized for content. |
| Delete | Existing DELETE removes the current path from playback and retains its immutable reviews. History remains accessible by exact campaign/path IDs. |

All path routes reject query overrides. Existing workspace role guards apply:
viewers can read minimized metadata but cannot mutate. Review text is withheld
by default by the shared evidence policy. An administrator can explicitly mint
and consume a **graph** grant for the exact campaign in the
`X-Darkmoon-Evidence-Grant` header on a path route. Each read/write consumes a new
one-use grant; permission to mutate is independent of permission to reveal.
The existing evidence graph reveal supplies the full current graph for review.

Current records stay in `attack_paths`; review snapshots are in
`attack_path_revisions`, keyed by path ID and version in the same Store
transaction. The original creator remains recorded_by; edits add reviewed_by
and updated_at. Returned records cannot mutate retained snapshots. Legacy paths
read as version 1, and their first edit/deletion records the original review.
A path stops at 100 immutable revisions, and each campaign has an 8 MiB
retained-review payload budget measured as compact UTF-8 JSON. Nothing is
evicted to allow another edit. A rejected save leaves both current and historic
records unchanged; deleting an already-retained current review needs no new
budget. This does not bound the whole control-state file/RSS across campaigns
or provide an archive/retention policy. Existing 100-path-per-campaign and 32-step limits remain.

Each save validates same-campaign findings, supported statuses, current evidence,
asset linkage and contiguous nonrepeated directed observed connections. A fresh
explicit review can establish a new evidence fingerprint after evidence changes;
older revisions retain the original fingerprint and rationale. This is review
history, not reconstructed historical evidence bodies. Input graph reads and the
Store commit remain separate; mutation races in the underlying finding/graph
store are not claimed transactionally isolated. Every playback step revalidates
current references and stops if the selected revision changed.

The path UI adds edit/history and preserves a draft on stale-save rejection.
Its explicit graph/path review reveal lasts at most 45 client seconds. View,
path selection, focus loss and visibility loss clear the review; in-flight
responses are rejected after expiry/session/control changes. Default path labels
fall back to opaque IDs. This supplements the server's grants and cannot retract
content already observed or copied. Historical reviews cannot be played as a
past exploitation chain. Automated observation producers and headset support
remain outside this increment.

## API/event and remediation contract increment

The static 52-route and typed-interface ledgers remain reference baselines.
Later compatibility records already implement scheduler flat adapters,
credential discovery, finding lifecycle, webhook tests and bounded run/history
reads; those are not reimplemented here. This increment adds fork boundary
regressions, not original vendor response snapshots.

- Finding lifecycle observation uses `(campaign_id, finding_id)` instead of a
  bare finding ID, preventing one campaign's reused ID from suppressing or
  misattributing another's new/status events.
- Event emission admits bounded scalar metadata only; nested free-form values
  and unsupported fields do not enter events/deliveries. Event names are bounded
  and cannot inject SSE lines. This is not a universal semantic validation of
  arbitrary strings placed in otherwise valid metadata fields.
- Known persisted SSE sequence/ID cursors replay later safe events in order.
  Observation baselines still reset on process restart. The retained event log
  is bounded at 1000; evicted/unknown cursor gap detection, durable observation
  recovery and full adversarial streaming/rotation remain open.
- Reproduction plans validate every probe command, name, timeout and expectation
  before probe execution. Exit-code expectations are real integers 0–255;
  contains/not_contains are bounded nonempty strings and unknown expectation
  keys reject. Timed-out, infrastructure-error or malformed results cannot pass.
- Judge confidence excludes booleans/nonfinite/out-of-range numbers and requires
  a bounded explanation. Local proposals remain unpublished. Synthetic state
  cases cover validated, validation_failed, unreproduced and judge-rejected
  outcomes; a locally validated patch is not deployment or a live-target fix.

## Verification checkpoint

Local focused path/contract run: **27 tests and 35 subtests passed** on the
integrated evidence-policy baseline. A broader focused run covering existing
remediation, report-security and catalog tests also passed before the final
path grant additions. Exact final suite/hosted results belong in the observed
follow-up below, not inferred from these earlier counts.

`tests/community/path_revision_browser.cjs` mounts the real paths.js component
against the production HTTP handler and actual one-use grants. Only the shell
app.js is replaced with a small mount harness; CSP is retained. It tests
create/edit/history, stale drafts, revision-pinned playback, focus/expiry
clearing, escaping and two viewports. This is component acceptance, separate
from the full workspace browser suite. Screenshots are CI artifacts.

Local browser execution was blocked by an unavailable Chromium executable; the
normal Playwright download returned invalid/truncated archives. No proxy or TLS
bypass was attempted. The dedicated core-path-contract workflow installs its
hosted browser normally and must be observed before claiming browser success.

No real assessment, provider request, deployment, publication, notification or
proprietary binary runs in these tests. Remediation uses disposable local Git
repositories and an injected synthetic sandbox; this increment does not prove
native container exploitation or licensed Pro remediation equivalence.

### Observed local integrated result

On the integrated `80c7101` baseline plus this increment, the full
`mcp/tests` and `tests/community` run passed **459 tests and 248 subtests**
in 97.83 seconds. The focused path/event/guard suite passed **27 tests and
35 subtests**. Graph navigation, finding-query and campaign-binding Node checks
also passed. Earlier intermediate full runs exposed pre-redaction assertions;
subsequent upstream worker corrections were integrated before this green run.
The removed IDE integration's catalog assertion was corrected by its worker's
`446b65d`, which is preserved here. No unrelated test was disabled.

Path projection now preserves version metadata and dictionary-versus-list
response envelopes while retaining default rationale withholding. This is a
path-specific compatibility adjustment to the evidence worker's projection,
not an expansion of the general evidence allowlist.

### First observed hosted result and follow-up

Feature commit [31ca698](https://github.com/newrecycle/Dark-Moon/commit/31ca698fd9e237fee25402ec93e6968d003a8c61)
passed the dedicated [core path/event run 40779542775](https://github.com/newrecycle/Dark-Moon/actions/runs/40779542775):
27 Python tests and 35 subtests passed, and real Chromium component acceptance
passed create/edit/history, stale saves, revision-pinned playback, focus/expiry
clearing, escaping and responsive checks. Screenshots were retained as artifacts.

Its broad workspace browser run exposed an immediate disabled-button assertion
before the asynchronous review reveal completed. Worker commit eb703fc supplies the wait for the
actual enabled state and retains the assertion; its equivalent fix is preserved
without duplication in this follow-up. The isolated component had
already verified the same asynchronous flow using Playwright's action waits.

A local full run on the preceding integrated baseline passed 469 tests and 254
subtests. An exact 31ca698 rerun found 471 passed, 254 subtests and one failure
in the independently added proposal-canary fixture: it saved a record in the
control-state collection, while PR lookup reads actual remediation result files.
The owning worker fixed that fixture in 918dc46, which is integrated into this
follow-up. Neither failure is recorded as passing. Final full/hosted results
must be recorded after observing their corrected runs.

The follow-up adds the retained-review byte budget and atomic rejection test;
its focused path/contract suite passes 28 tests and 35 subtests locally.

### Latest observed local result and published follow-up

The post-fixture-fix local integrated run passed **473 tests and 254 subtests**
in 99.68 seconds. The retained-review budget test is included; the focused
path/contract run passed **28 tests and 35 subtests**. The published budget
follow-up is [98063e5](https://github.com/newrecycle/Dark-Moon/commit/98063e50059d6e6bb7901ab6261ea7c115d0f3ae).
The earlier real Chromium component success remains scoped to 31ca698.

At this entry, the follow-up's [core run 40780397752](https://github.com/newrecycle/Dark-Moon/actions/runs/40780397752),
[full backend run 40780397846](https://github.com/newrecycle/Dark-Moon/actions/runs/40780397846)
and [workspace browser run 40780397924](https://github.com/newrecycle/Dark-Moon/actions/runs/40780397924)
are queued. They are not reported as passing. Operator-reviewed path editing,
immutable revisions and conservative local contract gates are implemented;
automated observation producers, full visual parity, durable SSE observation/
evicted-cursor gap handling and licensed Pro/remediation runtime equivalence
remain open. Prompt 9 is an ongoing contract workstream, not a closed parity claim.
