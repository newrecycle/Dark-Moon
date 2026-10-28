# Server-enforced evidence access — 28 October 2026

## Default response migration

Authenticated workspace responses, including legacy aliases, now go through an explicit fail-closed safe projection at the HTTP response boundary. Retain record IDs, associations, lifecycle state, numeric aggregates and ordering metadata. Exclude raw evidence, arbitrary titles/descriptions, URLs, source paths and source text, patch and validation probes, tool output, secrets, raw response/request bodies and unrecognized nested fields. Projection never mutates stored records or internal processing data. Default markdown content is withheld and JSON exports are projected. Full PDFs, raw logs/streams and remediation patches now require scoped grants; previously admin-accessible direct URLs may return 403. Existing PDF encryption/signing, PBKDF2 passwords, JWT/session revocation and encrypted credential vault are retained.

Source-file pickers no longer disclose arbitrary repository paths by default; an authorized source-selection workflow remains future work. Static launch-form catalogs and masked credential metadata remain, but repository paths and raw workspace records are excluded. Consumers needing full content must use the explicit reveal contract instead of depending on default detail/admin responses.

## Grant contract

POST /api/v1/evidence/grants takes JSON fields kind, id, and optional campaign_id. Only an administrator can mint. Kinds: finding, campaign, graph, report, report_pdf, remediation, patch, run, stream. The resource must exist and optional campaign scope must equal the recorded campaign association. HTTP 201 returns opaque grant, grant_id, expires_in (45 seconds), and exact kind/id/campaign binding. The stored journal contains only a SHA-256 grant digest, session/user identity and scope, not the secret. Up to 24 outstanding grants per session.

GET /api/v1/evidence/{kind}/{id}/reveal requires X-Darkmoon-Evidence-Grant and consumes the grant once. Wrong kind, ID, campaign, role, session, account, stale/expired, forged, revoked or replayed grants fail closed. Full PDF endpoints accept report_pdf grants, raw log detail accepts run grants, raw stream accepts stream grants and stops after expiry/session invalidation, and direct remediation patch requests accept patch grants. POST /api/v1/evidence/grants/{grant_id}/revoke with {} revokes an unused grant. Logout revokes session grants; existing JWT password-rotation and session revocation still apply.

## Browser semantics

Default finding detail is metadata only. Explicit administrator reveal obtains a fresh grant and displays escaped, untrusted evidence. Dialog close, refresh, logout or selection changes invalidate late responses and remove revealed content from the DOM. Focus alone is never server authorization. Once content is observed, downloaded or copied it cannot be retroactively revoked.

## Testing and exceptions

Use only synthetic canaries and owned-loopback HTTP fixtures. Verify canonical and legacy defaults, export protections, role matrix, scope, expiry/replay, concurrent claims, logout, SSE and raw log denial, browser stale-response safety, SDK and native consumer behavior. Operational system/provider config APIs outside the workspace route set, source-file selection and custom external integrations remain separate audits. No original commercial vendor-wire equivalence is asserted. Record CI results only when actually completed.
