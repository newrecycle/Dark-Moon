# Pinned audit implementation progress — 28 October 2026

Reference: the user's `darkmoon-pro-complete-audit-upload.zip`, vendor image
`ascit/opencode-darkmoon-pro@sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907`,
and the [static review](../2026-10-27/DARKMOON_AUDIT_REVIEW.md) committed in
7bcdf36. The original 27 October ledgers remain historical baseline observations.
This continuation records independent fork behavior separately.

## Typed evidence intake

[typed-contracts.json](typed-contracts.json) records 18 classes and 140 annotated
fields from nine selected original text interfaces, with source SHA-256 hashes
and line references. **125 defaults remain unknown** because the generated
stubs erase their values or contain unevaluated expressions. Optional annotations
do not establish defaults, requiredness or update semantics. Both patch/judge
prompt constants are fingerprinted by name, length and hash; their proprietary
text is not copied into the fork. No native modules or vendor code are executed.

Regenerate from the supplied archive:

```sh
python tools/pro-audit/extract_typed_contracts.py /path/to/darkmoon-pro-complete-audit-upload.zip \
  --output docs/pro-audit/2026-10-28/typed-contracts.json
```

## First P0 method/input increment

| Ledger row | Fork implementation | Verification level / remaining difference |
| --- | --- | --- |
| API01 | `POST /api/v1/auth/change-password` accepts exactly `current_password` and `new_password`; returns a fresh authenticated token and public user after rotation | Fork-tested from readable original request/response evidence. PBKDF2, 12–1024 character policy, role boundaries and old-session revocation remain stronger intentional behavior. No original runtime comparison. |
| API02 | Bodyless `DELETE /api/v1/run/{id}/stop` delegates to the existing queue cancellation; repeated cancellation is idempotent | Fork-tested method alias. Cancels this launcher's job, not independently spawned or external processes. Existing POST remains available. Original response envelope/process behavior unverified. |
| API03 | `PUT /api/v1/scheduler/{id}` supports partial updates of existing fork schedule fields with a mandatory current integer `version` | Fork-tested method/version contract. Does not replace omitted scope/timing. Original flat `scheduled_at`/`recurrence` payload translation and unknown default semantics remain open. Existing PATCH and calendar features remain available. |
| API11 / SEC01 | Negative tests cover anonymous, viewer, wrong-password, missing/malformed fields/IDs, stale versions, retained scope and concurrent password rotation | Fork-tested safeguards, not universal vendor envelope/auth equivalence. |

Password verification and hash rotation now occur inside one store transaction,
so simultaneous changes cannot both validate an old hash or reuse a revocation
version. The compatibility path issues its replacement token against that
specific rotation's version. A subsequent password rotation revokes it even if
session issuance completes later. The existing `/auth/password` endpoint keeps
its original `reauthenticate: true` response.

At the first P0 increment, the other ten static discrepancy rows remained open; see subsequent implementations below. Credential capabilities and
masked detail, finding history/PR linkage, active-run/log metadata, target
history, webhook detail/test behavior, and original wire snapshots require their
own explicit contracts. Supporting an exact method/path is insufficient to mark
any row **wire-verified**.

## Validation

Ten new HTTP tests exercise the three aliases and their authorization/error
paths, including concurrent password changes, a later rotation racing token
issuance, a genuinely bodyless DELETE, and exact schedule scope/timing
preservation. The complete MCP/community suite passed **318 tests and 17
subtests**. Hosted validation is tracked with the implementation commit; the
original vendor runtime has not been executed.

## Webhook detail/test increment — 28 October (untested)

| Contract | Fork implementation | Evidence boundary |
| --- | --- | --- |
| GET /api/v1/webhooks/{webhook_id} | Administrator-only safe detail serializer shared with collection; withheld vault IDs, signed secrets, URL path/query/fragment | Source implemented, no commercial response snapshot |
| POST /api/v1/webhooks/{webhook_id}/test | Administrator-only unique `webhook.test` admission, single-target signed retry queue, HTTP 202 accepted/delivery ID rather than outcome, 409 disabled/unavailable and 429 persisted throttle/queue bound | Source implemented; transport and native host untested |
| n8n integration | Validate HMAC and durable receipt claim; acknowledge test without workflow execution | Source implemented, native host deferred |

Earlier passing tests predate these changes. Schema, disabled/deleted behavior,
and deferred DNS/TLS/redirect/response-bound checks are recorded in
[webhook-receipts.md](../../handoff/webhook-receipts.md). Vendor-wire
equivalence is not established.

## Active-run discovery and bounded log browsing — 28 October integration increment

This **source-only integration increment** implements the fork's independent run
discovery contract; it does not establish original commercial Pro wire or
runtime equivalence. Existing SDK launch and status identities are unchanged.

| Route | Fork contract |
| --- | --- |
| `GET /api/v1/run/active` | `{data: PublicRun[], total, active_states: ["queued","running","cancelling"]}`. No query parameters. Only persisted `queued` and `running` records qualify. A running record with `cancel_requested` has public `state: "cancelling"` while its stored `status` stays `running`. Completed, failed, cancelled, interrupted and timed-out records are excluded. |
| `GET /api/v1/run/logs` | `{data: (PublicRun & LogMetadata)[], total, limit, offset, has_more, ordering: "created_at_desc,id_desc", content_policy: "metadata_only"}`. Optional exact `status`, `campaign_id`, `run_id`; `limit` 1–100 (default 25), `offset` 0–100000 (default 0). Status filters target the public `state` including `cancelling`. Descending `(created_at, id)` is deterministic for one dataset; offset pages are not a repeatable snapshot across concurrent queue changes. |
| `GET /api/v1/run/{run_id}` | `PublicRun & LogMetadata`, without the saved launch spec or execution details. Unknown run returns 404. |
| `GET /api/v1/run/logs/{run_id}` | `{data: LogEvent[], run_id, campaign_id, status, state, log_status, log_bytes, raw, truncated, content_policy}`. By default `data` contains only generated lifecycle metadata. Optional `lines` 1–200 (default 100). Explicit `raw=true` is administrator-only and returns at most the last 64 KiB, at most 200 lines and 512 characters per line. The first partial line is omitted when tail-truncated. |
| `GET /api/v1/run/{run_id}/stream` | Maintains SSE heartbeats, `run_completed`/`run_error` terminal frames and exact `run_id`/`campaign_id`. `output` frames are available only with administrator `?raw=true`, in bounded 8-KiB incremental reads; default/viewer stream emits lifecycle/heartbeat frames only. The default change is an intentional privacy restriction, not identical behavior to the earlier unguarded SSE output. |
| `POST/DELETE /api/v1/run/{run_id}/stop` | Same idempotent queue cancellation and exact job lookup; bodyless DELETE remains supported. Response now exposes only `PublicRun`. |

`PublicRun` is allowlisted: `id` and `run_id` are the actual queue
record ID, `campaign_id` is the separately persisted campaign ID (never
inferred from or substituted for the job ID), `status`, derived `state`,
`cancel_requested`, `kind`, optional lifecycle timestamps and related
schedule/proposal IDs, and optional integer exit code. Unknown queue statuses
are returned as `unknown`; arbitrary persisted status/error text is not
forwarded. No full `spec`, credential, environment, command argument, local
path, process error string or provider stdout is serialized.

`LogMetadata` has `log_status: available | missing | unavailable` and
`log_bytes` (null when unavailable). Known run with no log returns 200,
`log_status: missing` and no raw messages; unknown run returns 404.
Malformed/duplicate/unknown collection parameters and invalid requested ranges
return 400. Non-administrator `raw=true` returns 403. The collection never
includes raw log content. Authentication remains mandatory; viewer accounts
may read lifecycle metadata but not raw subprocess output, and retain no
mutation permission. No client-provided path is resolved. Reads enforce an
identifier-derived log location, reject symlinks and non-regular/multi-link
files, bound bytes/lines/line length, and never read whole files.

**Privacy limitation:** raw launcher logs are untrusted subprocess output and
may include credentials, tokens, sensitive targets, or other private text.
There is no claim that regex redaction can sanitize arbitrary output. Only an
administrator's explicit raw opt-in exposes a small unredacted window; the
default response and all collection views use structured lifecycle metadata.
The legacy `/api/v1/jobs/{id}`, `/api/v1/jobs/{id}/log`, launcher responses
and `/api/v1/overview` job records are restricted to the same boundary,
rather than leaking saved specs or unrestricted output.

The campaign-page consumer fetches `/run/active` and `/run/logs` with
50-record history pages, deduplicates active runs, keeps exact campaign/run
identities, exposes bounded previous/next navigation, and distinguishes loading,
valid emptiness, missing logs and failures. In-flight loads are discarded when
the view changes or a newer page request supersedes them. Per-run detail uses
structured lifecycle events; administrators can explicitly reveal a bounded
untrusted raw-output window. Stop uses the existing bodyless DELETE alias.

### Verification boundary for this increment

Implementation/source and documentation only: **no test execution, full build,
native host, licensed vendor process or assessment** was invoked. The earlier
passing test counts above describe their earlier compatibility increment, not
this one. Deferred cases: queued → running → cancelling → terminal transitions;
restart recovery and stopped runs; queue/remediation campaign/run identity
correlation; idempotent repeated stop and races; 8-MiB/oversized single-line
logs and concurrent file rotation; malformed/duplicate/overflow query values;
missing, unreadable, symlinked and replaced files; viewer/admin and
unauthenticated access; SSE disconnect and bounded raw reads; pagination with
concurrent inserts; browser stale requests; SDK launch/status polling; and
original-vendor response comparison if authorized access becomes possible.

## Scheduler flat-input adapter — 28 October 2026 (integration implementation only)

**Evidence and limits.** The committed typed contract
[`ScheduledCampaignCreate/Update`](typed-contracts.json) declares flat
`target`, `name`, `program`, `targets`, `out_of_scope`,
`exclude`, `focus`, `credentials`, `tokens`, `git_repo`,
`credential_id`, `create_repo`, `remediate`, `noise`,
`severity`, `format`, `rules`, `safe_harbor`,
`scheduled_at`, `recurrence`, `recurrence_interval` and `enabled`.
The readable UI review identifies one-time, daily, weekly and monthly
recurrence labels. The raw archive was catalogued in the earlier static review
but was not executable evidence; raw-byte access was unavailable in this
implementation session. No licensed-vendor runtime was invoked. Original
defaults, interval units beyond the daily/weekly/monthly labels, timezone
assumptions, null-as-clear behavior, error envelopes, and recurrence string
aliases are **unverified**.

**Accepted explicit mappings:**

| Flat input | Canonical handling |
| --- | --- |
| `target`, `targets`, `out_of_scope`, `exclude`, `focus`, `git_repo`, `credential_id`, `create_repo`, `remediate`, `noise`, `severity`, `format`, `safe_harbor` | Merge only present values into `spec`; pass through existing `launch_spec` validation. On edits, merge against the current persisted `spec` within the version-checked store transaction, retaining omitted target/scope/credentials. |
| `program` | Canonical `spec.name`; on create only, `name` also supplies `spec.name` if `program` is absent. On edits, `name` changes only the schedule display name, not the assessment program. |
| `name` | `display_name`; if both supplied, must equal canonical `display_name`. |
| `rules: string[]` | Nonempty text entries joined by `; ` for the existing prompt-text `spec.rules`; embedded semicolons/newlines rejected to prevent ambiguous flattening. |
| `credentials`, `tokens` | Rejected, including arrays. Inline secrets are forbidden; use saved `credential_id`. Saved credential IDs are validated on the compatibility create, preview and spec-changing edit paths and rechecked at launch. |
| `scheduled_at` | ISO-8601 timestamp with explicit UTC offset and whole-second precision; absolute instant is converted to `rule.start_local`. Creation without a canonical rule uses `UTC`; updates of a rule retain its named IANA timezone and derive the local time/fold from the timestamp. |
| `recurrence` | Only explicit `once`, `daily`, `weekly`, `monthly` map to existing calendar rule kinds. Original aliases, hourly and elapsed-interval values are not assumed. Fork-only interval rules remain available in the nested schema. |
| `recurrence_interval` | Strict integer 1–366 as `rule.every` for daily, weekly and monthly. For `once`, only 1 or omission is valid. A new recurring rule requires the interval explicitly; editing the same existing kind can retain its prior `every`. |
| `enabled` | Existing boolean field. For flat creation, required explicitly because the original default is unknown. On versioned partial edits, omission retains the current status. |

**Conflict and update rules.** An explicit null in a flat field is rejected,
rather than being treated as omitted, clearing a stored value or using a
default. Unsupported fields and recurrence values receive validation errors.
Mixing flat assessment fields with `spec` is allowed only when the normalized
values agree; mixing flat timing fields with `rule` is allowed only when they
produce the same normalized calendar rule. Without an explicit recurrence or an
existing/canonical calendar rule, `scheduled_at` is ambiguous and rejected.
Switching recurrence kind to daily/weekly/monthly requires an explicit
`recurrence_interval`; partial timestamp/interval edits of an existing
supported kind retain its other calendar dimensions. An existing fork
elapsed-interval rule is not silently converted from flat inputs. New
recurring flat timestamps must have UTC offset zero; named-zone local
recurrence must use the canonical `rule`, avoiding invented vendor DST
semantics. Changing to canonical timezone rules still uses the fork's DST gap,
fold and absent-month-day policies.

`PUT /api/v1/scheduler/{id}` still requires the current **integer**
`version`. Flat edits are resolved against the record inside the locked
store update after the stale-version comparison; no stale read/merge/write
window is introduced. `PATCH` and the intentional `{"enabled": boolean}`
legacy toggle remain. Canonical nested create/edit/preview clients, the
calendar editor, duplication, schedule history, one-shot execution claims,
overdue coalescing and duplicate-prevention paths are unchanged.

**Deferred verification cases (not executed here):** create/preview/update
equivalence for all supported recurrence kinds; stale/concurrent PUT versions;
PATCH partial edit retaining scope and credential references; explicit null,
invalid/ambiguous recurrence and contradictory mixed schemas; naive/non-UTC
recurring timestamps; spring gap and fall fold; monthly missing dates;
overdue one-shot, disabled schedules and no catch-up loop; claim duplication
under concurrent ticks; legacy enabled-only toggle; existing canonical editor,
duplicate and history consumers. No full build, schedule execution, assessment
launch or regression test was performed. This adapter does not establish
licensed-vendor scheduling/runtime parity.

## Credential discovery increment — independent fork contract

Source implementation, review only (test authoring, test execution, builds and
native-host checks deferred at the user's request):

| API / consumer | Implemented fork behavior | Intentional difference / verification still needed |
| --- | --- | --- |
| `GET /api/v1/credentials/providers` | Administrator-only catalog of fork-native `generic`, `target-login`, `target-token`, `scm`, `api-key` suggested record labels, with explicit capability identifiers and field metadata. Routed before ID detail. | These are **not** verified vendor provider adapters, vendor schemas or supported vendor ownership models. Provider labels are descriptive; old/custom labels remain valid. Vendor response shape remains unknown. |
| `GET /api/v1/credentials/{credential_id}` | Administrator-only `{"data": ...}` of allowlisted `id`, `name`, `provider`, `username`, `created_at`, fixed masked `hint`, `set`, and computed `capabilities`. Unknown/internal IDs return 404. | No decrypted or sealed data, internal webhook signing credentials, or arbitrary persisted fields. External wire-envelope parity unverified. |
| `GET /api/v1/credentials?capability=...` | Administrator-only, ID-sorted, internal-excluding records with deterministic capability selection; duplicate/blank/unknown capability fails with 400 instead of widening results. Unfiltered list remains supported. | Fork-derived single-secret eligibility, not a guessed original provider-specific field adapter. |
| `GET /api/v1/options` | Viewer gets no credential choices; analyst/admin retain the existing masked `credentials` list and receive `credential_choices` keyed by capability. Workspace launch, profile and OpenCode selectors consume those specific arrays. | Analysts may select workspace credentials for authorized launches; credential discovery/detail/mutation endpoints remain administrator-only. No partial per-owner filtering. |
| Credential-consuming operations | `assessment_login` requires a nonempty username; `assessment_token`, `source_checkout` and `provider_api_key` require a sealed single secret. Shared eligibility checks protect launch, privacy-token injection, HTTPS checkout, remediation requests, provider profile/apply, model discovery, and OpenCode connect. | A usable reference is not a live provider test; no provider calls are made by discovery. Runtime-specific username/token syntactic constraints remain at their existing use sites. |

Credential catalog use-site meanings:

- `assessment_login`: username + secret injected through local privacy tokenization.
- `assessment_token`: single secret injected as a target API token through the same privacy boundary.
- `source_checkout`: single secret for read-only HTTPS Git askpass checkout (optional username).
- `provider_api_key`: single secret for an administrator-managed OpenCode/provider profile or connection.

Provider labels do not narrow use-site capability: old entries such as
`github`, `gitlab`, `gitea`, `aws` and native OpenCode names remain intact,
but labels alone do not assert that integrations work. A single-secret record
can match several use sites; only login use requires a username. Internal records
and records without a sealed secret cannot pass capability filtering. Saved
ciphertext and existing credential IDs are not migrated or re-encrypted. Webhook
signing keys remain internal and are excluded from discovery, detail, selectors
and new consumer eligibility checks; their private delivery resolution is not
changed.

**Access model:** one administrator-managed workspace vault, with analyst
selection exposure via `/options`, not per-user credential ownership. The
vendor's potential owner-scoped/provider-specific behavior is deliberately not
claimed or emulated. PBKDF2 local authentication, revocable JWT sessions, and
the API's current credential route admin gate are unchanged.

**Deferred verification:** HTTP status/envelope and role-matrix tests; blank,
duplicate, unknown filter and ID behavior; legacy custom-provider records; forged
fields and internal webhook credentials; selection of login credentials without
usernames; UI selector/metadata interaction; launch, remediation checkout and
OpenCode profile/connection behavior; concurrency, persistence and native-host
compatibility; authorized original-runtime comparison if ever available. This
increment has **not** been test-executed, built or vendor-wire-verified.
