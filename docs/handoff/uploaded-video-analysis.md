# Uploaded video design and functionality review

27 October 2026. Implementation baseline: `9b507a1980d64518dcb4ac7a03c601451efdf8f4`, branch `pro`.

## Coverage and interpretation

The uploaded 143,700,312-byte archive contains all 13 linked videos, 475 two-second samples and 107 native storyboard sheets. All 635 supplied file hashes matched. Every supplied sample was inspected in chronological contact sheets; the Pro-tour frames at 46, 120, 128 and 136 seconds were additionally inspected at full resolution. The native storyboard sheets were acquired and hash-verified, but not individually visually reviewed. See [exact coverage and hashes](uploaded-video-review.json).

This resolves the acquisition blocker. It is a sampled visual review, not continuous playback, audio review or inspection of every encoded frame. Small text in contact sheets is not treated as transcribed configuration. Exact typography, animation timing, hover/focus interactions, intermediate states shorter than two seconds and headset behavior remain unverified. The original media stays in the uploaded archive; this repository stores analysis and evidence references.

A material distinction: the Pro recording visibly displays a read-only demo banner. Screens and links are evidence of presentation and navigation; they do not establish that the demonstrated scan, PR, deployment or integration actions were executed live. Blue/purple backgrounds, large numbered chapter titles and annotation cards belong to the edited tutorial presentation, not the web application.

## Per-video observations and implementation mapping

| Source | Reviewed sample timeline | Observed screens and behavior | Implementation requirements |
|---|---|---|---|
| Pro tour | 0–142s, every 2s | 12–18s install terminal; 20–22s sign-in; 24–36s dashboard totals, severity cards, campaign history and risky targets; 38–48s target/program with expandable scope, attack strategy, authentication and settings; 50–56s run scope summary and output; 58–68s findings list; 70–80s GitHub PR page; 82–96s report sections; 98–102s PDF viewer; 106–136s map/tour/inspector | D01/D02, A01, C01/C02, F01/F02, R01, G01/G02. Preserve campaign identity across screens. The banner prevents interpreting launch controls as verified live execution. |
| Cloud deployment | 0–52s | 10–24s terminal deploy command/progress; 26–32s doctor diagnostics; 34–46s findings table | I08: provider/profile/region and readable provision/health results. There is no observed web cloud wizard; such a wizard is a proposed adaptation. |
| GitHub Actions | 0–62s | 4–10s failed workflow result; 12–24s workflow YAML; 26–30s fail severities and SARIF callouts; 34–44s launch/wait/gate log; 46–54s finding totals and failed gate | I01: severity gate, summary and SARIF outputs. Distinguish scan completion, findings and policy failure. Host UI is GitHub's, not a DarkMoon page. |
| GitLab | 0–60s | 4–10s merge request findings; 12–22s CI YAML; 24–28s fail policy/allow-failure callouts; 30–40s job log and exit 2; 42–52s findings and blocked pipeline | I02: Code Quality/security outputs, explicit policy exit semantics and MR feedback. |
| Jenkins | 0–64s | 4–8s failed job; 12–22s plugin/pipeline context; 26–30s fail/unstable thresholds; 32–44s console; 46–50s issue chart/table; 54–56s archived job links | I03: separate unstable/fail choices, Warnings-NG findings and report artifacts. |
| VS Code | 0–60s | 4–8s findings view; 12–16s command palette setup; 18–22s data directory/fixture settings; 24–28s campaigns tree; 32–36s filter/search/sort; 38–46s finding detail/redaction; 48–52s local reveal view | I04/P01: campaign tree, sortable/filterable finding table, readable evidence and explicit reveal state. Fixture data must be visibly distinct from live findings. |
| JetBrains | 0–52s | 4–8s findings table; 12–14s install options; 18–22s data directory/fixtures; 24–28s search/filter/sort; 30–38s detail with redaction banner; 42–44s revealed state | I04/P01: same data contract, native host panels and explicit reveal state. |
| n8n | 0–52s | 4–8s connected workflow; 12–14s community node; 16–20s credential/test callouts; 22–26s resource/operation selectors; 28–32s trigger event selector; 36–44s execution JSON/table output | I05: populated operation/event selectors, credential test, execution output and event-triggered actions. Reuse backend-supported events rather than copying labels without routes. |
| Grafana | 0–52s | 4–8s posture dashboard; 12–14s import/datasource instructions; 18–22s totals/rate; 24–32s metadata findings table; 34–38s campaign/risk panels; 40–44s MITRE bars/drill-down | M01/I06: denominators for rates, severity counts, campaign tables and technique drill-down with metadata-only exports. |
| Splunk | 0–52s | 4–8s SOC overview; 12–14s app/HEC; 16–20s safe metadata ingestion; 24–28s totals/charts; 30–34s findings; 36–40s MITRE; 42–46s campaigns/retest affordance | M01/I06: HEC mapping, SOC filters, metadata-only findings and authorized retest handoff. |
| SDK/CLI | 0–50s | 4–8s policy exit; 12–14s package installation; 18–20s edition detection; 24–32s summary/findings; 34–38s JSON with redacted evidence; 40–44s fail-on/exit handling | I07/P01: edition/capability discovery, redacted contract and distinct policy/infrastructure errors. |
| OSS context | 0–108s | Installation/provider choices, CLI target entry, scan phases, technology fingerprint, evidence and result summary | Context for existing runtime only. Does not demonstrate additional Pro web UI. |
| Older demo | 0–118s | Juice Shop alongside agent terminal, growing challenge notifications and later result text | Contextual evidence of target/agent progress presentation; not a separate Pro dashboard or proof of current controls. |

## Newly resolved graph details

At 120s, step 3/4 selects the database and describes weak access controls. At 128s, step 4/4 selects exposed files and offers **Finish**. At 136s, free exploration shows an application inspector with type, address, technology, severity counts and per-finding severity/CVSS/category/PR badges. These replace the earlier uncertainty about tour steps 3/4. The displayed four-step story must not be hard-coded into arbitrary campaigns: actual finding relationships and supporting evidence must determine any attack path.

The graph uses a large canvas with a persistent right inspector, top campaign context and aggregate counts, a lower-left tour card, and a free-exploration action. Asset information leads, with raw metadata secondary. Selection should retain campaign context. A proposal indicator must refer to a real proposal; the recording's repeated PR badges are not production defaults.

## Implementation list and current increment

1. **Implemented in this increment (G01):** asset type/address/endpoint/technology summary where data exists; raw metadata moved to a disclosure; per-asset severity counts; finding rows show CVSS, category/status, title and MITRE. Values remain escaped and linked to the selected asset.
2. **Implemented in this increment (G02):** final manual tour step exposes Finish and returns focus to the tour launcher. Step count follows actual linked assets; no fabricated four-step path.
3. **Next G01:** in-inspector finding detail/Back and links to existing proposals/reports. Keep original evidence and campaign context; test missing proposal and deleted finding states.
4. **Next C01/C02:** align target/program/advanced field grouping, scope summary and live output hierarchy with 38–56s. Retain populated selectors and provider sync already implemented.
5. **Next F01/F02/R01:** table/detail navigation, explicit evidence-redaction/reveal contract, report navigation and export states; validate PDF generation independently of the demonstration.
6. **Next D01/D02/M01:** consistent dashboard hierarchy, risk denominators, responsive graph split view and metadata-only analytics with exact drill-down mapping.
7. **Integration tracks I01–I08:** verify each native-host behavior above using the imported integration code and live or isolated host tests. Documentation and build success alone do not establish compatibility.
8. **Still separate S01/G03:** editable calendar scheduling remains supported by earlier screenshot/documentation evidence; these samples add no headset interaction proof. Do not mark these done from video availability.

## Validation

The focused graph-controller suite exercises multi-step navigation, Finish, empty states, finding isolation, focus restoration, escaped metadata and CVSS zero handling. JavaScript syntax and whitespace checks are required. Hosted Chromium acceptance passed on commit 7157bbc; see implementation-progress.md for the run links. Follow-up assertions cover tour exit on manual asset selection/inspector close. Screenshot or full interaction parity is not claimed. Full demonstration videos are now available for denser follow-up inspection without reacquisition.
