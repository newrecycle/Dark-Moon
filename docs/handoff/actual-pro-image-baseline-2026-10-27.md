# Actual commercial Pro image baseline — 2026-10-27

**Purpose:** reference implementation evidence for [fork parity ledger](actual-pro-parity-ledger-2026-10-27.md) and [exact API crosswalk](actual-pro-endpoint-crosswalk-2026-10-27.md). This document describes original commercial Pro, **not** capabilities claimed by the `newrecycle/Dark-Moon:pro` fork. No vendor source/binaries are copied into this repository.

**Post-extraction update:** [Comprehensive static audit and 126-test/Ghidra coverage](../pro-audit/README.md) is now available. The native `.pyi` modules identify **Nuitka**, and all 32 module files were processed by Ghidra (46,276/46,290 individual function attempts succeeded). These are low-level decompiler outcomes, **not recovery of exact Python algorithms**; no vendor runtime behavior was verified. The previous documented API crosswalk and 28-item parity ledger remain relevant.

## Verified provenance and evidence level

- Image: `ascit/opencode-darkmoon-pro@sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907`, built 2026-10-27T19:45:03Z; image created 2026-10-27T20:13:21Z.
- Original app paths: `/opt/darkmoon/mcp/server/api/`, `/opt/darkmoon/mcp/server/src/remediation/`, `/opt/darkmoon/mcp/server/tests/`, `/opt/darkmoon/dashboard/`.
- **B**: readable original Python source `api_server.py`, `routes_auth.py`. **I**: compiled CPython native module + generated `.pyi` signatures. **U**: compiled Angular JS/CSS/HTML. **T**: packaged source tests (not executed). **F**: fork implementation. **X**: actual runtime HTTP/device behavior (**unverified**).
- Original distribution contains **15 mounted FastAPI router groups**, **52 decorated method/path declarations including aliases**, **23 compiled API extensions**, **nine compiled remediation extensions**, **114 Angular JavaScript bundles**, and **13 Angular page routes**. No `.map` files were found in the shipped dashboard assets.
- These are *file/contract* observations. Claims of working runtime behavior require a separate authenticated, safely authorized live test, which was **not** conducted.

| Domain | Original Pro shipped evidence | Verification limit |
| --- | --- | --- |
| API | FastAPI mounts `projects`, `targets`, `campaigns`, `vulnerabilities`, `dashboard`, `run`, `scheduler`, `auth`, `credentials`, `pull-requests`, `system`, `webhooks`, `events`, `retest`, `metrics` under `/api/v1` | B/I: exact decorators; no live response schema verified |
| UI | Root/dashboard, login, change-password, new-campaign, scheduler, history, projects, project/:id, campaign/:id, report/:id, vulnerability/:id, infra/:id, pull-request/:id | U: compiled Angular routing; no original TypeScript source/maps |
| Graph | Compiled Three/WebGL and `immersive-vr` WebXR request code | U, not physical headset verification |
| Reporting | Compiled client calls pdfMake `createPdf().download()` | U, **does not prove** vendor-signed/encrypted PDF |
| Streams | Run-specific `/run/{id}/stream`, global `/events/stream`, event-bus/reconciliation stubs | I/U, not proven auth, replay or order |
| Scheduler | `GET/POST /scheduler/`; `GET/PUT/DELETE /scheduler/{id}` | I, not crash/restart timing |
| Remediation | `models`, `codemap`, `patcher`, `sandbox`, `validators`, `scm`, `pipeline`, `cli` + launcher modules; source tests | I/T; compiled implementation not executed |
| Remediation workflow | Source ranking, exact JSON edit matching, optional LLM generation, separate review/confidence, before/after exploit+normal probes, Docker sandbox, SCM PR linkage | I/T; expected behavior, not independently verified success |
| Integrations | Native backend routers include retests, webhook operations, events, metrics; not all are exposed in Angular navigation | I/U; backend-only until matching UI proven |

## Critical differences not to copy blindly

The shipped original `routes_auth.py` uses plain SHA-256 for passwords, includes fallback signing/admin configuration, and `api_server.py` configures permissive CORS; the original auth guard exposes configurable write authorization. Our independent fork uses PBKDF2, authenticated reads, role controls, revocation, scoped secrets, stronger report protection and operator-controlled publishing. **Preserve the fork's protections** when adding compatibility aliases; commercial parity is not a reason to weaken them. Do not reproduce a default credential or commit authentication secrets.

Original Pro's Angular service uses raw `fetch()` for campaign launching in addition to authenticated Angular `HttpClient`; exact deployed auth behavior cannot be established statically. Original UI includes pdfMake browser export; the fork's signed/encrypted server PDF is an independent extension, not demonstrated vendor implementation.

## Unresolved evidence

Live Pro response bodies/status codes, original native `.so` implementation bodies, original Angular TypeScript/source maps, executed vendor remediation tests, WebXR headset behavior and actual commercial deployment security are not verified. The author-published [Juice Shop remediation dossier](https://github.com/ASCIT31/juice-shop/blob/master/docs/REMEDIATION_BENCHMARK.md) contains reported retests, not independent reproduction.

## Sources and updating rules

- User-provided pinned image inventories, SHA-256 manifest, extracted API `.pyi`/readable Python, Angular browser assets and packaged tests.
- Fork implementation: [REST dispatch](../../mcp/community/api.py), [HTTP/SSE server](../../mcp/community/server.py), [UI](../../mcp/community/static/), [remediation](../../mcp/community/remediation.py), [queue/scheduler](../../mcp/community/jobs.py).
- [Upstream author repository](https://github.com/ASCIT31/Dark-Moon) and [official SDK contract](https://github.com/ASCIT31/darkmoon-client/blob/master/CONTRACT.md).

For another image, record the exact digest, extracted-file hashes, evidence grade, and changed contract. Update crosswalk/ledger only with attributable evidence. **Neither a public product claim nor a green fork unit test proves live Pro parity.**
