# DarkMoon Pro video-to-implementation handoff

Baseline: `newrecycle/Dark-Moon`, branch `pro`, commit **630e0900a9b2f79a497b95bdb8a83dcda4ef9ab2**. Prepared 26 October 2026, America/Edmonton.

## Read this first

This is a functional handoff from **English captions for all 12 current official tutorials**, including one OSS contextual tutorial, plus direct inspection of four published Pro UI screenshots and a sampled frame review of the publisher’s 9.1-second infrastructure animation. **It is not a completed frame-by-frame video design audit.** Public video metadata/captions were accessible, but stream and storyboard downloads returned HTML “Site Unavailable” responses. They were verified as unusable rather than mistaken for video/image content. The older linked demo had metadata but no English caption track. YouTube animation, spacing, hover states, transition timing and unspoken controls remain unverified. The 27 October retry added bounded graph-animation evidence; see [frame review and acquisition outcomes](frame-review-retry.md). Ticket V00 is required to close that gap.

Evidence labels: **C** = reviewed caption/narration (a statement, not independent proof of a working feature); **S** = inspected published screenshot; **A** = inspected sampled frames from the publisher’s README animation (not YouTube footage); **B** = inspected baseline source; **P** = proposed implementation decision. No transcript or acquired video media is redistributed; the animated reference already exists in the repository. Narration is paraphrased; timestamp ranges link back to the originals.

Deliverables: this handoff, [source/coverage manifest](video-source-coverage.json), and [machine-readable backlog](pro-video-backlog.json). Captions’ SHA-256 hashes and video durations are recorded in the manifest. All current tutorial links from the official docs carousel and README were deduplicated; legacy `full.md` demo is tracked separately. This scope is bounded to those linked videos, not every upload on the channel.

## Constraints to carry into the next session

- Work on `pro`; do not re-import inherited master/runtime changes or overwrite agents, Docker installers or OpenCode defaults merely for appearance.
- Independent GPL implementation against public behavior; private Pro source is unavailable. Vendor activation, paid-license enforcement and hardware restrictions are outside this fork’s implementation goal. Preserve operator-owned security controls.
- This task prepares a handoff, not an instruction to launch pentests, provision clouds, publish remediation branches, send messages or create PRs. Keep the user’s no-PR constraint. Real external actions need their own authorized target/destination and reviewable result.
- Preserve the reviewed fixes: endpoint credential isolation, truthful retest verdicts, transactional scheduler updates, documented scope flags and raw-evidence preservation.
- Baseline verification from the preceding implementation task: 122 community tests, 117 MCP tests, Chromium acceptance, actual Docker/provider CI and owned-loopback analysis. These do not establish YouTube design parity, live integration-host parity, headset support or a full LLM-run assessment.

## Video inventory and functional observations (C unless stated)

| Topic / video | Length | Relevant intervals | Paraphrased observation |
|---|---:|---|---|
| [Pro tour](https://www.youtube.com/watch?v=zQE95bVLZgM) | 143 s | 00:20–00:24; 00:24–00:37; 00:37–00:58; 00:58–01:18; 01:21–01:28; 01:45–02:18 | First-use password setup, overview, scoped launches, console, finding evidence, reviewable fix, PDF and graph navigation. |
| [Cloud deployment](https://www.youtube.com/watch?v=2B_q_4IkE1A) | 54 s | 00:09–00:34; 00:34–00:47 | Cloud choices, provisioning progress, runtime diagnostics and opening the dashboard. |
| [GitHub Actions](https://www.youtube.com/watch?v=e67klNk79vg) | 64 s | 00:11–00:30; 00:30–00:54 | Action setup, severity-based gate calculation, job summaries and code-scanning output. |
| [GitLab](https://www.youtube.com/watch?v=ui7NHD41cMM) | 61 s | 00:11–00:29; 00:30–00:53 | CI component, configured gate thresholds, Code Quality/SAST outputs and merge-request feedback. |
| [Jenkins](https://www.youtube.com/watch?v=G0TgyGpVLZ8) | 65 s | 00:11–00:30; 00:32–00:57 | Plugin and pipeline step, separate failure/unstable policies, Warnings-NG and report archiving. |
| [VS Code](https://www.youtube.com/watch?v=GY7YOnYpteQ) | 61 s | 00:10–00:29; 00:31–00:52 | Source/fixture configuration, campaign tree, sortable findings, redacted details and explicit local reveal. |
| [JetBrains](https://www.youtube.com/watch?v=obUUrbTN3Jg) | 54 s | 00:11–00:21; 00:23–00:43 | Plugin configuration, sortable/filterable findings, evidence/remediation and confirmed local reveal. |
| [n8n](https://www.youtube.com/watch?v=3htg8kh7Dr8) | 53 s | 00:10–00:24; 00:28–00:43 | Community-node setup, connection test, campaigns/retests/metrics and event-driven downstream workflows. |
| [Grafana](https://www.youtube.com/watch?v=L7K-y0HPudk) | 54 s | 00:10–00:21; 00:23–00:43 | Datasource setup, posture metrics, metadata-only tables, distributions, risky targets and MITRE drill-down. |
| [Splunk](https://www.youtube.com/watch?v=8w2i8nEBdQQ) | 54 s | 00:10–00:19; 00:23–00:44 | HEC setup, metadata-only ingestion, SOC filters, MITRE coverage and retest action. |
| [SDK / CLI](https://www.youtube.com/watch?v=jMIMvV8yEK8) | 52 s | 00:10–00:21; 00:23–00:42 | Client setup, edition detection, severity summaries, redacted finding lists and policy exit codes. |
| [OSS context](https://www.youtube.com/watch?v=3Qv1luvW99E) | 109 s | 00:00–01:49 | Installation/model/CLI context; not treated as evidence of Pro UI behavior. |
| [Older demo](https://www.youtube.com/watch?v=1bFRVuMkZzY) | 120 s | Unavailable | Metadata obtained; no English captions and media unavailable. No content-derived requirements assigned. |

## Visual reference findings (S, not video frames)

Inspected repository images: `docs/pics/dashboard.png`, `docs/pics/vulnerability-1.png`, `docs/pics/scheduler.png`, `docs/pics/markdown-report-1.png`.

- Dashboard: black/near-black canvas, fixed left rail, outlined monochrome navigation icons, project list and bottom identity/online area. Main area uses uppercase display headings, four entity cards, four severity cards with count/percentage and colored shape, then dense recent-campaign and risky-target tables. History includes target/date/duration/risk/count/status. These are observed arrangements; exact fonts and numerical CSS tokens were not measured.
- Finding: large title, description, spacious characteristics panel with severity/category/endpoint/status/MITRE/ISO/CVSS rows. Evidence continues below. Keep our readable HTTP blocks and raw JSON rather than flattening evidence into decorative summaries.
- Scheduler: large sectioned edit panel with friendly name separate from program name, target, focus/exclusion controls, noise/severity/format, date/time, recurrence unit and every-N control. A schedule list exposes recurrence, run counts, state and action icons. This exceeds our interval-only create/pause/delete controls.
- Report: a large reading panel, top-level campaign/report heading, Markdown/PDF actions at the upper right, management summary before detailed issues, and clear horizontal section separators. This is a still-image observation, not a verified export interaction.
- Proposed design direction (P): reproduce the information hierarchy with our own components and accessible text labels. Keep the fork’s existing mint/purple identity unless the user chooses a closer visual theme. Do not copy screenshot counts, fake completion badges or illustrative attack paths into production data.

## Gap assessment against baseline (B)

`mcp/community/static/app.js` already implements overview, campaign/finding tables, readable escaped evidence, exports, cancellation, graph selection/tour and basic WebXR. `workspace.js` adds presets, provider/account/credential management, project charts, integrations, proposals and retests. `api.py`/`service.py` expose those features. `jobs.py` provides durable interval scheduling. `report_security.py` and `privacy_audit.py` implement real cryptographic operations. `publish.py` and `deploy.py` are separately gated CLIs, not full product flows. Imported integrations are present under `integrations/upstream`; presence/build tests are not proof of live product-host compatibility.

Highest gaps: server-side default-redacted views and controlled reveal; a richer live console; calendar/editable scheduling; genuine evidence-backed path playback; cross-linked proposal review; precise posture metrics; and real host verification of the imported integrations. First-use onboarding and report navigation need product completion rather than replacement of their existing backend foundations.

## Implementation backlog

Each acceptance statement below is required, not an optional QA suggestion. “Partial” means relevant code exists; inspect and extend it instead of rebuilding it blindly. File paths are relative to the repository root. No requirement claims unseen video controls.

### V00 — Resolve video visual coverage (P0)

Baseline: **Partial visual evidence; YouTube coverage blocked**. Evidence: A: 13 timestamped sampled animation frames; local CDN, browser and hosted YouTube attempts unsuccessful. See [retry record](frame-review-retry.md).

Collect accessible recordings for all 11 current Pro-related tutorials and the legacy demo. Record frame timestamps, viewport, interactions and states. Do not claim visual parity before this step. Use the animation observations as bounded graph requirements; do not substitute them for the linked YouTube recordings.

Implementation locations: `docs/handoff`.

Acceptance: Every source has a frame-review record or remains explicitly blocked.

### D01 — Dashboard information architecture (P1)

Baseline: **Partial**. Evidence: Pro 00:24–00:37; dashboard.png.

Add project/target/campaign/finding totals, severity proportions, duration-aware history and risky-target rows. Keep the fork’s evidence-first semantics.

Implementation locations: `mcp/community/static/app.js; service.py; operations.py`.

Acceptance: Zero-data and multi-project totals match records; risky rows navigate to the exact target/campaign.

### D02 — Consistent design system (P1)

Baseline: **Partial**. Evidence: Published screenshots; implementation proposal; A: 1280×720 graph reference.

Create shared page-header, stat-card, badge, table-toolbar, detail-section and form-section components using repo-native CSS. Maintain responsive keyboard-accessible navigation. At the reference viewport, the graph uses about 940 px and the inspector 340 px; adapt rather than hard-code this split. Keep the lower-left tour card clear of navigation and support a mobile inspector sheet.

Implementation locations: `mcp/community/static/app.css; app.js; workspace.js`.

Acceptance: Readable at 390 and 1440 px; focus visible; active sidebar state and severity text do not rely on color alone.

### A01 — First-use onboarding (P0)

Baseline: **Partial**. Evidence: Pro 00:20–00:24.

Add first-account setup using the private recovery token; prompt for a strong password and offer model/runtime readiness checks. Preserve OIDC and recovery access. Do not add vendor license checks.

Implementation locations: `mcp/community/auth.py; api.py; static/workspace.js`.

Acceptance: Concurrent setup creates one initial administrator; account data are never public; reload does not expose recovery credentials.

### C01 — Campaign launch completion (P1)

Baseline: **Partial**. Evidence: Pro 00:37–00:49; scheduler.png.

Preserve presets, native flag preview and vault references. Add distinct program vs schedule/display names, attack-strategy explanations and explicit remediation prerequisite status.

Implementation locations: `assessment_catalog.py; jobs.py; service.py; static/index.html`.

Acceptance: Rendered preview equals validated launch scope; severity cap remains distinct from integration failure thresholds.

### C02 — Live run console (P1)

Baseline: **Partial**. Evidence: Pro 00:49–00:58.

Promote run output to a dedicated campaign view with connection status, reconnect/resume position, bounded history and a cancel action whose scope is accurately stated.

Implementation locations: `server.py run_events; jobs.py; static/app.js`.

Acceptance: Reconnect loses no retained output and does not duplicate it; launcher exit and assessment finalization remain separate statuses.

### F01 — Finding search, filters and sort (P1)

Baseline: **Partial**. Evidence: VS Code 00:31–00:39; JetBrains 00:23–00:32.

Add severity/status/category/campaign/target filters plus stable sorting and pagination or virtualization. Preserve selections in navigation URLs.

Implementation locations: `api.py; static/app.js findingsTable`.

Acceptance: Stable ordering for ties; filters compose; empty results clear correctly; large datasets remain usable.

### F02 — Finding detail and fix linkage (P1)

Baseline: **Partial**. Evidence: Pro 01:02–01:18; vulnerability-1.png.

Add explicit impact, CVSS vector, related asset, remediation disposition and links to local proposal or recorded forge PR. Keep raw HTTP evidence and normalized reading views.

Implementation locations: `static/app.js showFinding; service.py; api.py`.

Acceptance: Only a finding’s own campaign/proposal is linked; absent impact/PR data show unknown or unavailable, never fabricated content.

### P01 — Default redaction and controlled reveal (P0)

Baseline: **Gap**. Evidence: VS Code 00:42–00:52; JetBrains 00:35–00:43.

Define a server-side redacted projection for findings, reports and logs. Add role-checked, explicit local reveal and expiry/audit behavior. Full raw response data must not already be in a supposedly redacted response.

Implementation locations: `auth.py; api.py; server.py; privacy_audit.py; static/app.js`.

Acceptance: Secret sentinels absent from default HTTP responses, SSE, DOM and client logs; reveal requires authorization and is revoked on lock.

### R01 — Report review experience (P1)

Baseline: **Partial**. Evidence: Pro 01:21–01:28; markdown-report-1.png.

Add executive/technical navigation, findings anchors, impact and remediation roadmap. Keep export formats consistent with stored evidence and distinguish unsigned, signed and encrypted outputs.

Implementation locations: `reports.py; report_security.py; static/workspace.js`.

Acceptance: Navigation reaches correct finding; long HTTP evidence wraps; signature/encryption validated independently; no unrecorded findings appear.

### G01 — Asset-to-finding-to-proposal navigation (P1)

Baseline: **Partial**. Evidence: Pro 01:45–02:18; A: infra-orbital.gif frames 0,49,87,99.

Make graph selection reveal asset identity, risk, measured connections, related findings and their proposals. Navigation must preserve campaign context. Add a closeable asset inspector with severity totals and finding rows (severity, CVSS, title/category, proposal indicator); selecting a finding opens its detail with Back, endpoint, MITRE, description, remediation, proposal and full-report actions.

Implementation locations: `service.py graph_for; static/app.js drawSurface`.

Acceptance: Selecting an asset yields exactly its node-linked findings; missing node linkage is displayed separately. Back restores the selected asset/list context; close and keyboard focus behave predictably; proposal/report links resolve to the selected finding and campaign, and unavailable actions explain their state.

### G02 — Evidence-backed attack-path tours (P1)

Baseline: **Gap**. Evidence: Pro 01:55–02:18; A: infra-orbital.gif sampled frames across 0–181, only tour steps 1/4 and 2/4 observed.

Introduce persisted observed path records with ordered node/edge references and evidence IDs. Add stepwise playback. Keep current finding-location tour separate when no verified path exists. Present a numbered tour card with Back/Next, step indicators, Technical details where relevant, and Explore freely. Reframe the camera with reduced-motion support. Do not invent unseen steps 3/4 or label illustrative topology as an observed attack path.

Implementation locations: `service.py; store.py; static/app.js`.

Acceptance: Unconnected nodes never become a kill chain; each tour step resolves to supporting evidence; invalid paths are rejected. Card, graph selection and inspector remain usable together; keyboard can move between steps and return to free exploration; reduced motion disables animated reframing.

### G03 — Immersive graph parity (P2)

Baseline: **Partial/unverified**. Evidence: Pro graph narration; precise VR interactions unverified.

Retain WebXR capability detection and provide keyboard/non-XR alternatives. Schedule headset testing of picking, locomotion, exit and labels; do not infer exact controls from unavailable video frames.

Implementation locations: `static/app.js startVR; browser_acceptance.cjs`.

Acceptance: Unsupported devices degrade gracefully; headset test evidence is required before claiming immersive parity.

### S01 — Calendar scheduling and editing (P1)

Baseline: **Gap beyond intervals**. Evidence: scheduler.png: direct still-image observation.

Add edit/duplicate/preview, one-time and calendar recurrence, every-N periods, named timezone and run history. Migrate existing interval schedules without changing their meaning.

Implementation locations: `jobs.py Scheduler; api.py; server.py; static/workspace.js`.

Acceptance: DST transition cases and monthly boundaries tested; pausing/deleting cannot resurrect schedules; concurrent edits preserve versioned state.

### M01 — Remediation review workspace (P1)

Baseline: **Partial**. Evidence: Pro 01:09–01:18; current fork review fixes.

Show branch/base, patch, scope judge, before/after checks, attempts, disposition and finding links. Describe local validation separately from deployed-target verification.

Implementation locations: `remediation.py; publish.py; api.py; static/workspace.js`.

Acceptance: Unreproduced/rejected/failed states remain visible; a validated local proposal never silently marks the target fixed.

### M02 — Operator-controlled publication UI (P2)

Baseline: **CLI only**. Evidence: Pro 01:09–01:18; implementation proposal.

If later requested, build a reviewable plan panel around the existing gated forge adapter. Bind approval to exact patch/destination/base; expose recorded PR read-only afterward.

Implementation locations: `publish.py; api.py; static/workspace.js`.

Acceptance: Tests use fake transports; no automatic push, PR or merge; explicit future operator authorization required for real publication.

### I01 — Integration connection wizard (P1)

Baseline: **Partial**. Evidence: n8n 00:10–00:24; SDK 00:10–00:21.

Provide installation-specific URL, auth method, connectivity test, role/scopes, transport choice and safe template downloads. Keep credentials out of exported workflow JSON.

Implementation locations: `assessment_catalog.py; integrations.py; static/workspace.js`.

Acceptance: No secret embedded in generated templates; localhost/container-network mistakes produce actionable errors; tests do not send external messages.

### I02 — n8n end-to-end verification (P1)

Baseline: **Imported; live host unverified**. Evidence: n8n 00:22–00:43.

Validate campaign launch/wait, findings, report, retest, metrics and event-trigger handling in a disposable n8n instance. Connect finding outcomes to safe downstream mappings.

Implementation locations: `integrations/upstream/n8n; operations.py; api.py`.

Acceptance: Persisted replay suppression and HMAC freshness tested across restart; no Slack/Jira/DefectDojo traffic without explicit configuration.

### I03 — GitHub CI experience (P1)

Baseline: **Imported; host parity unverified**. Evidence: GitHub 00:25–00:54.

Exercise configurable severity gates, summary tables, SARIF and artifacts against a disposable test workflow. Provide a copyable setup recipe in the WebUI.

Implementation locations: `integrations/upstream/action; client; static/workspace.js`.

Acceptance: Gate is recomputed from findings; infrastructure failure differs from a security-policy failure; reports contain safe fields.

### I04 — GitLab report contract (P1)

Baseline: **Imported; live host unverified**. Evidence: GitLab 00:24–00:53.

Validate component inputs, threshold defaults, Code Quality/SAST exports and merge-request result mapping. Provide a setup recipe without trying to merge anything.

Implementation locations: `integrations/upstream/gitlab`.

Acceptance: Report schemas and gate exit behavior match the pinned integration version; no external merge action.

### I05 — Jenkins failure vs unstable policy (P2)

Baseline: **Imported; host unverified**. Evidence: Jenkins 00:25–00:57.

Build/test HPI, pipeline step, separate fail/unstable policies, Warnings-NG publication and archived reports in an isolated Jenkins host.

Implementation locations: `integrations/upstream/jenkins`.

Acceptance: Threshold precedence and zero-findings behavior verified; a scanner error cannot masquerade as a clean scan.

### I06 — IDE data and reveal parity (P1)

Baseline: **Imported; hosts unverified**. Evidence: VS Code 00:17–00:52; JetBrains 00:17–00:43.

Validate data-directory and fixture modes, campaign tree, search/filter/sort and redacted detail panels in actual VS Code and JetBrains hosts.

Implementation locations: `integrations/upstream/vscode; jetbrains; client`.

Acceptance: Local reveal is explicit and authorized; remote workspaces cannot silently enable it; no real evidence is copied into fixture previews.

### I07 — Posture dashboard and metric definitions (P1)

Baseline: **Partial**. Evidence: Grafana 00:17–00:43.

Add exploited/confirmed counts, target risk, remediation disposition rates and MITRE breakdown with documented denominators and drill-down. Validate Grafana datasource/plugin separately.

Implementation locations: `operations.py; service.py; integrations/upstream/grafana`.

Acceptance: Rates have explicit cohorts and time windows; no local-validation rate is called deployed remediation; metadata feeds exclude evidence and report bodies.

### I08 — Splunk SOC flow (P2)

Baseline: **Imported; host unverified**. Evidence: Splunk 00:10–00:44.

Validate HEC ingestion, safe-field search dashboards, target/status/severity filters, MITRE aggregation and an authorized retest action.

Implementation locations: `integrations/upstream/splunk; integrations.py; operations.py`.

Acceptance: No evidence/secrets in HEC payloads; retest preserves original exclusions and authorization boundaries.

### I09 — SDK / CLI compatibility matrix (P1)

Baseline: **Partially tested**. Evidence: SDK 00:16–00:42.

Retest current and vendored clients against this fork, edition detection, summary/list operations, nullable evidence and severity-gate exit contracts.

Implementation locations: `integrations/upstream/client; tests/community/sdk_contract.cjs`.

Acceptance: Document supported versions; auth expiry, malformed responses and interrupted runs fail explicitly rather than reporting success.

### O01 — Deployment and readiness workspace (P2)

Baseline: **Plans/CLI only**. Evidence: Cloud 00:09–00:34; Pro 00:10–00:20.

Add cloud plan preview, instance requirements, progress/status and diagnostics results. Retain local model/provider selection and operator-owned integrity controls.

Implementation locations: `deploy.py; integrity.py; updates.py; static/workspace.js`.

Acceptance: No cloud resources or firewall changes on preview; never reuse vendor activation; deployment execution remains separately authorized.

## Contract and state decisions for implementers (P)

1. Use stable `project_id`, `target_id`, `campaign_id`, `finding_id`, `node_id` and `proposal_id` links. Do not associate fixes solely by finding id across campaigns. Maintain schema versions for persisted new records.
2. Add a schedule revision and transactional patch operation for full edits. Store timezone and calendar recurrence separately from legacy interval seconds. API/UI preview must use the same next-run calculation. Preserve claimed occurrences and document pause/delete semantics for an already-running job.
3. Expose graph paths as explicit records: id, campaign, ordered node/edge ids, evidence references, observation time and disposition. A UI animation is never evidence of reachability or exploitation.
4. Define response projections for redacted, metadata-only and full evidence. Browser masking alone does not protect data already delivered. Scope reveal grants, audit them without storing the revealed secret, expire them, and clear them on lock/reload. Keep test fixtures unmistakable.
5. Define remediation metrics before implementing cards. Keep proposed, locally validated, published and deployed-target-verified states distinct. Missing outcomes remain unknown; zero denominators render unavailable rather than a made-up percentage.
6. Add replayable event/run-output cursors and bounded history. Render structured messages with literal text and explicit progress/transport failure states. Preserve raw evidence in exports. Never infer completed assessment from launcher exit 0 alone.
7. Keep `GET /api/v1/pull-requests*` read-only. A future publication action must show exact patch, destination and base and preserve adapter safeguards. None of the integration videos authorizes automatic merging or sending notifications.
8. Keep setup recipes installation-specific. Port 8000/80 in upstream examples does not override our local 8780 deployment. Container localhost is not the host’s localhost. Credentials belong in the product vault or each integration’s credential store, not exported workflow templates.

## Execution order and review boundaries

- **Phase 0:** V00 evidence capture; validate this inventory against any subsequently available recordings. Record design frames and additional interactions before claiming exact parity. P01 threat model and response-projection design can proceed independently.
- **Phase 1:** P01, A01, D01/D02, F01/F02, C01/C02. Deliver one reviewed vertical workflow: sign in → configure authorized scope → launch → follow real progress → inspect redacted evidence → explicitly reveal where permitted → review report.
- **Phase 2:** S01, R01, G01/G02, M01, I07. Add calendar edits and trustworthy asset/finding/proposal navigation. Keep the graph usable without XR.
- **Phase 3:** I01–I09 and O01, using isolated host environments. Publishing UI M02 only if later requested; no deploy/push/send side effect during setup or tests.
- **Phase 4:** G03 headset validation and visual parity closure; rerun the full cross-device/host matrix. Every remaining unsupported state must be labelled in the UI and handoff status.

Use separate commits per vertical behavior, preserve old route contracts, and update the backlog status with concrete evidence. No broad rebase, blanket UI rewrite or dependency upgrade is required by this handoff.

## Verification matrix

| Area | Required checks |
|---|---|
| Data correctness | Empty state, multiple projects, duplicate finding ids across campaigns, missing metrics, archived/interrupted/incomplete records; no benchmark counts hardcoded into application state. |
| Auth/redaction | Anonymous, viewer, analyst, admin; expired sessions; local vs remote workspace; canary secrets absent from default responses, SSE, safe-field exporters, logs and workflow downloads. |
| Scheduling | Timezones, DST gap/fold, every-N periods, one-shot, monthly edge dates, overlap, restart and concurrent pause/edit/delete. Preserve the existing anti-resurrection regression tests. |
| Run console | Disconnect/reconnect, retained cursor, truncated logs, cancellation, child processes, separate launcher/campaign outcomes and stale results arriving after view changes. |
| Graph | Real node links, explicit observed edges, disconnected assets, unknown evidence, path ordering, keyboard selection, reduced-motion mode and unsupported XR. |
| Reports | Long request/response bodies, ANSI/carriage returns, literal script-like payloads, all export formats, signature verification and encrypted PDF decryption. |
| Remediation | Baseline reproduction failure, rejected judge, scope violation, retry exhaustion, local proposal not deployed, ambiguous forge response and mismatched destination/patch. No actual external write in test fixtures. |
| Integrations | Version-pinned client contract, live disposable product host, authentication expiry, rate limits, timeout, malformed response, replay attack, safe fields and CI-policy vs infrastructure-error outcomes. |
| Visual/accessibility | 390/768/1440 px, keyboard-only flows, visible focus, screen-reader labels, empty/loading/error states and long untrusted values. Compare only to genuinely reviewed reference frames/stills. |

## Open evidence gaps and continuation instructions

All 11 current Pro-related tutorials were reviewed through captions; OSS tutorial is contextual. The older demo cannot be content-reviewed from metadata alone. YouTube frame-level review remains blocked after local CDN, browser and hosted-runner retries. Four public screenshots and 13 sampled frames of the README animation now provide bounded visual references. The animation is not one of the linked YouTube tutorials. To close V00, supply accessible recordings/captures, then inspect the whole timeline and add timestamped differences; do not treat this handoff as proof that no additional controls exist.

Do not redistribute complete caption tracks or video files. Keep source URLs, timestamped paraphrases and source hashes. The implementer should begin by reading `video-source-coverage.json`, the current feature matrix and the regression tests; then inspect `pro` for changes after this baseline before editing.
