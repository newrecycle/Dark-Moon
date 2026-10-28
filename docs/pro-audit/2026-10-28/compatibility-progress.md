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

The other ten static discrepancy rows remain open. Credential capabilities and
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
