# DarkMoon Pro — uploaded audit evidence review

Evidence: user-uploaded `darkmoon-pro-complete-audit-upload.zip` (analysis snapshot), pinned vendor image `ascit/opencode-darkmoon-pro@sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907`, fork snapshot `newrecycle/Dark-Moon` branch `pro` at `84c9d360df5eefc059ed26eae4d6a1fc97c4603e`. All findings below are **static** unless explicitly stated otherwise.

## 1. Extraction audit

- ZIP: **1,888 directory entries**, ~588 MB uncompressed, ~169 MB compressed; contains original `raw/api`, `raw/remediation`, `raw/tests`, 114 compiled Angular JS bundles and corresponding readable/AST indexes, 32 Ghidra outputs and the fork checkout. Some files, such as nested packages, are duplicates of indexed work.
- API: **52 route decorators**, including trailing-slash aliases. These are not 52 unique business operations.
- Angular: **114/114 Babel-parsed and Prettier-formatted**, 34 `app-*` component selectors statically extracted from Babel bindings. The general-purpose component index reports `components: []` and `events: []`: a **parser/indexer incompleteness**, not proof the components or events are absent.
- Babel AST: **1,567,150 syntactic AST nodes**, with 1,328 generic `get/post/...` call-site hits, 92 candidate event nodes, 68 validation hits, 60 routing hits. These are *not* deduplicated business HTTP actions or complete workflows; the scan also counts third-party library code.
- Native: **32 of 32** `.so` modules have Ghidra output; **46,290 attempted Ghidra function decompilations, 46,276 successes, 14 failures** across 10 modules. That is **99.970% of enumerated native functions**, not 99.970% of original algorithms recovered. The output is dominated by compiled CPython/runtime scaffolding.
- The native `.pyi` files explicitly identify **Nuitka** as their generator; do not label the modules Cython without separate evidence.
- Original tests: **126 `test_*` functions in 10 packaged test files**. The generated `contracts/test-expectations.json` incorrectly counts **127** because it also includes the API handler `api/routes_webhooks.pyi::test_webhook` as a test. Six test files are byte-identical in fork `mcp/tests`, one differs (`test_live_push_fixes.py`), and three same-name test files are absent there (`test_remediation_backend.py`, `test_remediation_toolkit.py`, `test_run_db_resolver.py`). Their functionality may have separate fork tests; this is **file-overlap evidence**, not a full coverage verdict.
- Generated acceptance-test matrix: **52 API + 13 UI + 11 remediation = 76 rows**, with generic requirements and **no executed vendor comparison**. The uploaded archive has no runtime/browser capture outputs.
- The Ghidra stage is recorded as PASS in `audit.log` after earlier invocation errors; the successful run took approximately 456 seconds. PASS means the analyzer finished, **not** that every function decompiled.

## 2. High-confidence API gaps against the pinned fork

The following are sourced from original `raw/api/routes_*.pyi`, original `contracts/api-decorators.json`, and fork `mcp/community/api.py`. Exact response schemas, authorization outcomes, defaults, and errors remain unverified without an authorized vendor instance.

| Original | Fork behavior seen in code | Classification |
|---|---|---|
| `POST /api/v1/auth/change-password` | `POST /api/v1/auth/password` | path mismatch |
| `GET /api/v1/credentials/providers` | `none in credentials dispatcher` | missing |
| `GET /api/v1/credentials/{cred_id}` | `none in credentials dispatcher` | missing |
| `GET /api/v1/targets/{target_id}/evolution` | `GET /api/v1/targets/{target_id}/analytics` | path mismatch |
| `GET /api/v1/vulnerabilities/history` | `none (history may be parsed as an ID)` | missing |
| `GET /api/v1/pull-requests/finding/{vuln_id}` | `GET /api/v1/pull-requests/{pr_id}` | missing |
| `GET /api/v1/run/active` | `none (active may be parsed as an ID)` | missing |
| `GET /api/v1/run/logs` | `only /run/logs/{run_id}` | missing |
| `DELETE /api/v1/run/{run_id}/stop` | `POST /api/v1/run/{run_id}/stop` | method mismatch |
| `PUT /api/v1/scheduler/{schedule_id}` | `PATCH /api/v1/scheduler/{schedule_id}` | method mismatch |
| `GET /api/v1/webhooks/{webhook_id}` | `GET /api/v1/webhooks` | missing |
| `POST /api/v1/webhooks/{webhook_id}/test` | `none` | missing |
| `GET /api/v1/credentials?capability=...` | `GET /api/v1/credentials (query appears unused)` | query mismatch |

These are compatibility observations, **not recommendations to weaken the fork's authentication, authorization, secure storage, request validation, or isolation**. In particular, original `DELETE /run/{id}/stop` and `PUT /scheduler/{id}` need carefully specified semantics before an alias is introduced. The fork has additional independent endpoints and may intentionally diverge.

## 3. Newly recoverable typed contracts and workflows

From original `.pyi` files (types observable, default **values** generally replaced with `...`):

- **CampaignRunRequest:** `target`, `program`, `targets`, `out_of_scope`, `exclude`, `focus`, `credentials`, `tokens`, `noise`, `severity`, `format`, `rules`, `safe_harbor`, `git_repo`, `credential_id`, `create_repo`, `remediate`.
- **ScheduledCampaignCreate/Update:** the above targeting/remediation fields plus `name`, `scheduled_at`, `recurrence`, `recurrence_interval`, `enabled`; create requires `target` and `scheduled_at`, while update makes them optional. `routes_scheduler.pyi` also exposes `_compute_next_run`, `_trigger_campaign`, `scheduler_loop` and prompt construction helpers.
- **CredentialCreate:** required `name`, `provider`; `fields` typed dictionary; update uses optional `name` and `fields`. Original GET list supports `capability` filtering.
- **WebhookCreate:** `url`, optional `events`, optional `secret`, `format`. Verification of delivery security, event filtering, and failure response remains open.
- **RetestRequest:** optional `target_id`, `campaign_id`, `finding_ids`, `safe_harbor`.
- **Remediation models:** `Finding`, `CodeLocation`, `Patch`, `GateResult`, `ValidationResult`, `PRResult`, `RemediationOutcome` specify typed fields including `ValidationResult.reproduced`, `gates`, and `confidence`, and PR provider/repo/url/branch/base/state/error.
- **Original remediation pipeline:** `ReproPlan` with exploit, variants, normal probes and optional test command; `RemediationConfig` with workspace, `max_attempts`, `min_confidence`, dry run, SCM and repository creation options; `file_repro_provider`, `remediate_finding`, `_open_pr`, `_link`; `Sandbox.build`, `start`, `restart_fresh`, `exec`, `http`, `cleanup`; `exploit_gate`, `regression_gate`, `compute_confidence`.
- **Original model prompts:** the Nuitka-generated `remediation/patcher.pyi` embeds distinct system prompt constants `_PATCH_SYSTEM` and `_JUDGE_SYSTEM`, specifying an exact substring edit contract (`find`/`replace`), root-cause analysis, and independent review JSON (`approved`, `reason`, `confidence`). The first-pass `remediation-prompts.json` fails to inventory both of these because its detection logic is incomplete. The fork uses independently written `old`/`new` edit schema and has its own adversarial judge with a static 0.75 acceptance threshold; no proof that this matches vendor thresholds.
- **Workflow comparison:** the fork uses offline prebuilt Docker images, independent before/after probes, and a local Git worktree; the original exposes sandbox image building/restart, explicit exploit and regression gates, confidence composition, and SCM PR creation. Some differences are intentional security boundaries, not bugs.

## 4. Recovered UI behaviors (static, concrete)

Source: formatted original `frontend/readable-js/main-FYH5V2MY.js` and compiled component bundles.

| Screen/component | Evidence from compiled code | Parity test |
|---|---|---|
| Login | Username/password required; blank submit sets `No credentials`; Angular auth service POSTs `/auth/login`. | Empty-field, wrong-credential, loading, redirect and error states. |
| Change password | `currentPassword` nonempty, `newPassword` >=8 chars, confirmation equality; success redirects to `/` after ~1500 ms; endpoint is `/auth/change-password`. | All boundary values, mismatch message, successful navigation, auth refresh. |
| New campaign | Compiles targeting and policy fields; semicolon-split rules, remediation switch, `git_repo`, `credential_id`, `create_repo`; launches/stops run via service. | Form defaults, comma/semicolon splits, toggle-dependent fields and cancellation. |
| Scheduler | One-time/daily/weekly/monthly recurrence labels; reset includes target, noise, severity, repository, credential, remediation switches; edit state is cleared. | Create/edit/delete/toggle and timezone/recurrence validation. |
| Credentials modal | Angular component `app-credentials-modal` exists, and compiled service calls providers, list/filter, get, create, update, delete. | Admin authorization, masking, errors, modal loading and CRUD. |
| Stream viewer | Renders Markdown and tool output; original component invokes `bypassSecurityTrustHtml` on parsed Markdown. | Verify sanitized/escaped markup in fork; **do not copy this vendor trust bypass**. |
| Project, campaign, vulnerability, reports, PRs | Components and route links are compiled and accessible as static templates. | Route-state matrix: loading, empty, error, populated, navigation, modal/subview, permissions. |

The generated index currently does **not** reconstruct a full component-to-template-to-event-to-state transition graph, despite parsing all bundles. Each Angular template's actual compiled definition and signal/action handlers must be inspected to close UI parity.

## 5. Original packaged tests as executable specifications

- Original/fork byte-identical: `test_privacy.py`, `test_session_privacy.py`, `test_port_scan_workflow.py`, `test_workflow_validator.py`, `test_workflow_privacy.py`, `test_tool_whitelist.py`.
- Changed: `test_live_push_fixes.py` — compare both versions' run robustness and crash/refresh assertions.
- No same-name fork test in `mcp/tests`: `test_remediation_backend.py` (23 functions), `test_remediation_toolkit.py` (21), `test_run_db_resolver.py` (6). Map their assertions to *existing* fork coverage before porting independent regression tests.
- The original tests explicitly cover unique substring replacement/path escapes, LLM JSON parsing, independent patch judgment, repository/PR operations, encrypted credential storage, secret masking, run DB selection and subagent event formatting. Those provide more actionable inputs and acceptance assertions than the generic generated 76-row matrix.

The machine-readable `original-test-function-crosswalk.csv` maps each of the 126 original packaged test-function names to same-name functions in the fork, when present. Matching names are not proof of passing tests or identical assertions.

## 6. Priority next implementation/verification queue

1. **P0:** Create *real method/path contract tests* for the 13 static discrepancies listed in the CSV and run them against the fork. Include role and error-path assertions; do not claim vendor body parity until reference runtime checks.
2. **P0:** Extract the original typed input schema and model constants (above) into machine-readable contracts; preserve unknown defaults as `unknown`, rather than inventing them.
3. **P0:** Build a remediation parity test suite from original `test_remediation_backend`, `test_remediation_toolkit` and `test_run_db_resolver`, with owned/no-network fixtures and explicit acceptance gates. Preserve fork sandbox restrictions.
4. **P1:** Improve JS analysis to segment by `ɵcmp({selectors,template,inputs,...})` and associated Angular class methods, then enumerate every handler/state/form/action with source offsets and confidence. Parsing success alone is insufficient.
5. **P1:** Investigate the **14 failed individual Ghidra functions** listed in `ghidra-function-coverage.csv`. Retry them separately if they are relevant to route/remediation semantics; do not rerun all 46k functions unnecessarily.
6. **P1:** Establish authorized vendor runtime response/error/authorization snapshots, and test controlled fixture workflows. No such results exist in this upload.
7. **P2:** Update the fork's committed parity ledger only after tests confirm each new behavior and explicitly document intentional security divergences.

## 7. Evidence inventory / trust limits

- `raw/api/*.pyi` and `raw/remediation/*.pyi` are type/function/class evidence, **not executable originals**.
- `ghidra/decompiled/*.c.txt` is decompiler-generated low-level pseudocode with function offsets; reconstructed C cannot be treated as guaranteed exact source-level logic.
- `frontend/readable-js/*.js` is formatted production JS, not original TypeScript or Angular templates.
- `frontend/babel-ast/*.json` and `frontend/component-and-interaction-index.json` contain lexical/AST hints, not full interaction verification.
- `fork-checkout/mcp/community/*` is the pinned independent fork state, not the vendor implementation.
- `stage-markers/*.done` indicate stages completed (not evidence that semantic parity or runtime correctness was established).

**No repository commit or push was performed in this review.**