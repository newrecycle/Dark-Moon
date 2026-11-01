# API compatibility continuation — 31 October 2026

Implementation continuation from `pro` at
`95f3c472a8c9b452dfd71793dbcf10eed7eecad8`. Read the
[current status](current-pro-status.md), [28-item parity ledger](actual-pro-parity-ledger-2026-10-27.md)
and [complete API acceptance matrix](commercial-api-parity.md) together.
Historical missing-route entries do not imply those handlers are still absent.
This increment changes independently implemented request/response behavior;
it does not close the complete reference acceptance matrix.

| Ledger item | Implementation in this increment | Remaining boundary |
|---|---|---|
| API03 / S01 | Omitted flat recurrence and literal `none` normalize to the existing one-shot calendar rule for create/preview; `none` also works in versioned updates. | Explicit boolean enablement, whole-second offset-aware timestamps, recurring interval validation, named-zone rules and optimistic concurrency remain required. Disabled-record acceptance is not proof of external execution semantics. |
| API06–07 / API11 | A narrow `provider: github`, `fields: {token: ...}` input form maps to the existing SCM-token adapter. Catalog metadata advertises this request alias. Rename-only updates preserve existing encrypted secrets. | This is not an arbitrary provider-field store, catalog equivalence, OAuth flow, PR publisher or provider entitlement check. Public credential metadata retains the fork contract and full masking. |
| API11 / API14 / F01 | Finding lists add `stats.by_severity`, `stats.by_category` and `stats.by_status` for the entire selected cohort before paging. | Existing composed filters, deterministic ordering and optional page bounds remain. Do not substitute reference paging/order behavior for those protections. |
| API14 / D01 | Overview adds metadata-only `recent_campaigns` and `targets_at_risk`, zero severity/status buckets and safe category counters. Default project/target totals include idle registered records. | Hostnames and evidence are withheld; scoped analytics retain their campaign cohort. These are current retained-state observations, not historical reconstruction or a cross-file transaction. |
| SEC01 / REM04 | Field translation and secret preservation occur inside the vault transaction and retain existing ownership, grants, adapter checks, revocation and role enforcement. Histogram keys use an explicit public vocabulary. | No stronger security control is relaxed to match a less restrictive deployment. |

## Credential input behavior

An authenticated administrator can submit:

```json
{"name":"Source token","provider":"github","fields":{"token":"SYNTHETIC-EXAMPLE-ONLY"}}
```

New records use the existing version-1 `scm_token` adapter. Default scope is
private, owned by the authenticated principal; eligibility is limited to
`source_checkout`. Explicit owner/scope/grants still pass the existing policy.
Administration of another owner's record does not grant permission to use it.

Only the token field is supported in this form. Unknown providers, extra nested
fields, wrong adapters and conflicting top-level/nested secrets are rejected
before persistence. Ordinary scalar-secret and explicitly typed inputs retain
their existing contracts. Provider-specific endpoint, username, cloud, OAuth
and other multi-field forms remain separate work.

PUT/PATCH with an omitted secret can rename an existing legacy record without
re-encryption. A token-field update of an existing GitHub-labeled legacy record
replaces its scalar secret without silently migrating its scope or adapter.
Explicit migration remains necessary. Typed updates preserve current owner,
scope, grants and irreversible revocation. Response/status and catalog schemas
are not declared fully reference-compatible by this request adapter.

## Statistics and overview behavior

Finding statistics describe all rows selected by the composed filters, including
when the requested page is empty. They do not describe only the returned page.
Default finding order, stable identity ties and bounds are unchanged.

Only explicitly public category/severity/status labels become histogram keys.
Unknown/free-form labels are counted under `unknown`; their text is not exposed
through dictionary keys. Counts remain nonnegative integers. Original stored
findings are unchanged.

Overview lists the five most recent retained campaigns with exact campaign and
target IDs, recorded date, active-finding risk and total finding count. Valid
calendar-only dates use UTC midnight solely as a deterministic display-order
key; the stored date is not rewritten or presented as an exact event time.
Unknown dates sort last, and identity breaks ties. Risk rows count current active
findings per target and sort by severity, count and identity. Resolved,
remediated, closed, fixed and false-positive findings do not inflate active risk.
Accepted risk remains exposure, following the existing posture policy.

The complete 52-declaration scenario matrix, valid-run SSE/replay, reference
webhook delivery/retry, scan-dependent retests, remediation, original UI and
licensed/native-host requirements remain open to their own acceptance evidence.
Neither matching route names nor a green fork regression run closes those items.

## Verification

The increment adds independently authored synthetic HTTP and storage checks in
`test_api_overview.py`, `test_credential_access.py`, `test_finding_query.py` and
`test_scheduler_compatibility.py`. They cover filtered totals, empty/idle data,
exact scoped identities, date-only ordering, protected-text histogram keys,
private credential use, role denials, malformed/conflicting forms, immutable
revocation, concurrent rename/rotation, one-shot claims and stale versions.

Run the complete backend gate from the checkout root:

```sh
PYTHONPATH=mcp .venv/bin/python -m pytest mcp/tests tests/community -q
```

Run the seven Node scripts and static syntax checks listed in
`.github/workflows/tests.yml`. Build the shared SDK before running
`DARKMOON_TEST_PYTHON="$PWD/.venv/bin/python" node tests/community/sdk_fork_http.cjs`.
The existing browser gate commands are in `community-browser.yml`; an installed
Chromium may be selected with `CHROMIUM_EXECUTABLE` if the available Playwright
package expects another browser revision. Fork/browser/SDK results must be
recorded separately from reference comparison and native-host acceptance.

Initial local result at code checkpoint `92c7190`: **527 backend tests and
319 subtests passed** in 127.91 seconds. All seven Tests-workflow Node scripts
and static JavaScript syntax checks passed. The unchanged SDK source built and
its actual authenticated fork-HTTP acceptance passed. Installed Chromium 154
passed both prescribed headless flag sets, full desktop/mobile application
acceptance and the production path-component checks; the final date-only
ordering correction is covered by the final backend run. No hosted CI result,
new model approval or native/licensed-host acceptance is claimed.

## Further local task checkpoints

Each tested implementation item is committed locally for eventual squash. See
[the machine-readable task map](api-task-progress.json) for exact commit IDs and
remaining acceptance. No push is implied by a local checkpoint.

- API04 adds the `campaigns` evolution series (`date`, severity `stats`,
  `total_vulns`, `overall_risk`) alongside the existing typed projection. Host
  names remain withheld; no trend formula is guessed from insufficient samples.
- API05 adds a `history` campaign-snapshot collection while preserving the
  genuine `data` mutation journal. Snapshot and event totals/pages remain separate;
  `snapshot_seq` applies only to the journal. Snapshot pages use the existing
  limit/offset independently, with `history_total`, `history_has_more` and
  `history_next_offset`. Each campaign exposes at most 500 finding metadata rows,
  with explicit total/truncation fields. Titles/evidence remain withheld. Reading
  pre-existing findings creates no fabricated journal events. Campaign metadata
  and selected finding files are still read; this is not an indexed snapshot
  store or a cross-file transaction.
- API08 returns an empty collection for an authenticated, unqualified lookup of
  an unknown finding's PRs. Explicit campaign existence/scope checks and identifier
  validation remain. This establishes no populated publication workflow result.
- API14 metrics now handle absent/invalid dates without server errors, use UTC for
  calendar-only dates, require aware bounds, and reject repeated/blank/unknown
  query parameters. Inclusive end bounds and equal-bound point windows remain
  supported for existing clients. Unrecognized series labels aggregate under
  `unknown` instead of exposing free text. ISO UTC bucket output is retained.

Current campaign snapshots are not event history, and a local model/SDK/browser
pass is not a complete reference workflow pass. Runtime-dependent rows stay open.

### Integrated verification after the further checkpoints

The final local backend run passed **534 tests and 330 subtests** in 132.34
seconds. Built SDK-to-fork HTTP acceptance and the full Chromium application
checks passed. The browser reload assertion initially raced the debounced
finding-query update; the test now waits for the expected persisted query before
capturing its URL, retaining all existing restoration assertions. That correction
has its own local commit. No hosted CI or fresh reference workflow execution is
claimed by these local results.
