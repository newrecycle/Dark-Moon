# Actual Pro vs our fork: systematic implementation ledger (2026-10-27)

**This ledger is a static comparison and prioritized work queue, not a claim of completed implementation or tests.** Original-reference evidence: [pinned Pro image baseline](actual-pro-image-baseline-2026-10-27.md), [all 52 original route declarations](actual-pro-endpoint-crosswalk-2026-10-27.md). Fork state inspected at `7c2bb758adc43ecb96e2761e6fbe9cc670cb04c3`: [REST implementation](../../mcp/community/api.py), [HTTP/SSE server](../../mcp/community/server.py), [UI](../../mcp/community/static/), [remediation](../../mcp/community/remediation.py), [queue/scheduler](../../mcp/community/jobs.py), [existing feature matrix](../pro-feature-matrix.md), [integration continuation](integration-gap-ledger.md).

Status: **D** observed difference; **N** no exact route found; **P** present/partial with no original wire-level proof; **E** intentional fork extension; **U** vendor/runtime evidence unavailable. All work rows remain **open**. Prior green fork tests do not establish Pro parity.

| ID | Priority | Reference difference | Status | Acceptance evidence required |
| --- | --- | --- | --- | --- |
| API01 | P0 | POST /auth/change-password vs fork /auth/password | D | Add safe alias and password/authorization tests; retain revocation |
| API02 | P0 | DELETE /run/{id}/stop vs fork POST | D | Add method alias with idempotency and role tests |
| API03 | P0 | PUT /scheduler/{id} vs fork PATCH | D | Verify replace/update semantics without losing version check |
| API04 | P1 | GET /targets/{id}/evolution vs fork /analytics | D | Add vendor-shaped evolution fixture and compatible alias |
| API05 | P1 | GET /vulnerabilities/history exact route missing | N | Build redacted ordered/paginated history projection |
| API06 | P1 | GET /credentials/providers exact route missing | N | Return masked provider catalog; no secrets |
| API07 | P1 | GET /credentials/{id} exact route missing | N | Authorization/ownership/masking response |
| API08 | P1 | GET /pull-requests/finding/{id} missing | N | Finding-scope PR lookup; distinguish local proposal from published PR |
| API09 | P1 | GET /run/active and GET /run/logs missing | N | Add safe list serializers/pagination and cross-role checks |
| API10 | P1 | GET /webhooks/{id} and POST /webhooks/{id}/test missing | N | Add authorized detail and safe mocked delivery; SSRF guard |
| API11 | P0 | 15 router names match but wire envelopes/auth not validated | P | Contract fixtures for headers/error codes/payloads across all routes |
| API12 | P1 | Global & per-run SSE exist but parity not tested | P | Sequence/event names/cursor/replay/secret-leak negative tests |
| API13 | P1 | Retest lifecycle/verdict names not fully compared | P | Do not treat not-observed as fixed; correlate campaigns |
| API14 | P1 | Metrics and finding evidence projections unverified | P | Projection, denominator, privacy and query conformance |
| UI01 | P0 | Original 13-route Angular vs independent fork SPA | D | Map pages, deep links/back/refresh, screenshots, responsive acceptance |
| UI02 | P1 | Original Angular source maps absent; compiled JS/CSS present | U | Use pinned browser reference; document visible-state comparisons |
| UI03 | P1 | Run/stop/log/stream UI uses different API semantics | D | Full authenticated flow and error/reconnect E2E |
| UI04 | P1 | Original WebGL/Three + immersive-vr; fork independent graph | P | Compare graph transitions and linkage; headset test for XR |
| UI05 | P2 | Original browser pdfMake; fork signed/encrypted server PDF | E | Keep fork security; label as extension, not vendor implementation |
| UI06 | P2 | Original backend retest/webhook/metrics not in apparent Angular navigation | U | Don't invent vendor UI pages without proven route or trace |
| REM01 | P0 | Original native codemap/patcher/validators/sandbox/scm/pipeline vs fork Python | P | State transition & error matrix from original typed interfaces/tests |
| REM02 | P0 | Exploit-before/after, variants and normal probes differ in details | P | Offline exploit repro, fixed/rejected and regression gates |
| REM03 | P0 | Judge/confidence and many-to-many finding ↔ PR linkage | P | Verify no auto-merge, reviewer consent and status projections |
| REM04 | P1 | Original credential store masked/encrypted; fork independently implemented | P | Cross-owner authorization and no-secret-in-log/event tests |
| REM05 | P1 | Original remediation native runtime cannot be verified from stubs | U | Owned lab + no-network container; no claims until execution |
| SEC01 | P0 | Original JWT/password/CORS fallbacks vs fork stronger security | E | Preserve PBKDF2, RBAC, revocation, scope and export protections |
| INT01 | P1 | SDK/n8n/CI/IDE/Grafana native host parity incomplete | P | Differentiate mocked, native-host and original-Pro responses |
| OPS01 | P1 | Original vendor image vs source-built independent community fork | U | Build/runtime/readiness validations; no licence-bypass or binary claims |

## Processing protocol

1. Pin the vendor image digest and precise `.py`/`.pyi`/Angular asset or original response supporting the claim. Separate native interface (not executed), original frontend behavior, fork implementation, and public marketing.
2. For the row being addressed, record original method/schema/event/state and fork result in an isolated fixture. Preserve error paths, role guards, data minimization, and no-secret leakage.
3. Implement the smallest compatible additive change; **do not replace or delete our independent improvements**, do not adopt weaker original authentication, and do not copy proprietary binaries or circumvent licensing.
4. Run unit, contract, browser and actual native host/integration tests relevant to the row. Real scan/remediation exercises only on owned disposable local targets; no third-party assessment.
5. Record commit SHA, test commands/outcomes, remaining failures and explicit vendor-runtime unknowns. Mark `wire-verified` only with genuine vendor HTTP response evidence; otherwise mark `fork-tested` separately.

**Suggested order:** API01–03 + API11 + SEC01, then API04–10 and API12–14, then UI01/03/02/04/05/06, then REM01–05, then INT01/OPS01. The existing [integration-gap ledger](integration-gap-ledger.md) remains the separate source for native integration-host tasks.

## Things not proven by extracted image

Original Angular TypeScript source, original native Python logic, live licensed Pro API behavior, commercial remediation success, VR hardware experience and production auth/security configuration have not been recovered/tested. Do not label these verified merely because their compiled modules or public product descriptions exist.
