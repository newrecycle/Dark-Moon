# Visual handoff implementation progress

Updated 27 October 2026. Branch `pro`. All 13 linked videos are acquired, and all 475 supplied two-second samples have been reviewed. See [observations and implementation list](uploaded-video-analysis.md) and [sample/hash coverage](uploaded-video-review.json). Acquisition is resolved; exact continuous-frame interaction parity remains unclaimed.

## Implemented graph behavior

- Manual tour with numbered steps, Back/Next, Finish and Explore freely. Steps follow actual assets with linked findings, with instantaneous camera reframing.
- Keyboard-accessible asset dropdown, explicitly linked finding buttons, empty asset state, inspector close and focus return.
- Asset type/address/endpoint/technology summary where available, severity counts, CVSS/category/status rows and expandable raw metadata.
- Manual asset selection or inspector close exits the tour, preventing a stale step card from describing a different selected asset.

## Remaining implementation

- G01: proposal indicators, in-inspector finding detail/Back and campaign-preserving proposal/report actions. Existing finding buttons open the existing detail dialog.
- G02: persisted evidence-backed attack paths. The current tour visits finding locations without manufacturing an exploitation chain.
- D02: closer responsive split-view styling, mobile inspector sheet and visual comparison at multiple viewports.
- Other functional work remains tracked in [the full backlog](pro-video-backlog.json), with new per-video observations in uploaded-video-analysis.md.

## Validation

Focused graph-controller checks pass for multi-step navigation, Finish, finding isolation, empty states, escaped metadata, CVSS zero handling, focus restoration and manual-selection/close tour exit. JavaScript syntax and whitespace checks pass.

[Hosted Chromium acceptance on the video-review commit](https://github.com/newrecycle/Dark-Moon/actions/runs/40576949394) passed. It covers all routes, model/profile discovery, provider/OAuth/API-key flows using offline fixtures, populated selectors, webhook/retest flows, evidence/XSS, filters, graph navigation, local remediation, PDF export, schedules, fake launcher queue and responsive layout. These fixture tests do not establish live external provider or host integration parity.

The [follow-up browser run](https://github.com/newrecycle/Dark-Moon/actions/runs/40577228611) also passed, including the tour-exit fix. Both jobs in [runtime CI](https://github.com/newrecycle/Dark-Moon/actions/runs/40577228744) passed: the actual branch Docker image build/native provider API contract and the owned-loopback analysis. This does not establish live external provider login or a full LLM-driven assessment.


## Follow-up audit

The audit of commits 7157bbc through 0d1f7bd found documentation traceability errors: uploaded-video-analysis.md assigned several integrations to the wrong ticket IDs, omitted I09/O01 from its integration/deployment summary, and used M01 (remediation) for posture metrics (I07). Those mappings are corrected. The older-demo inventory no longer claims its media is unavailable, and the backlog scope no longer says no production code changed.

Coverage totals in the manifest are 13 sources, 475 reviewed samples and 107 acquired storyboard sheets. The prior review remains a sampled visual pass: individual storyboard inspection, continuous playback/audio, short transitions, exact typography and hover/focus parity are not complete. Browser tests exercise behavior with fixtures; their screenshots were not retained by the workflow for a visual comparison. Native integration-host tests, live external login synchronization and headset tests remain unverified. These are outstanding validation tasks, not evidence that the corresponding features passed.

All 26 backlog tickets remain tracked. The graph increment does not complete G01/G02: in-inspector finding detail/Back, real proposal indicators and campaign-preserving report/proposal navigation, persisted evidence-backed paths, and responsive visual parity remain open. Calendar editing/recurrence, server-side redaction/reveal, onboarding, launch/console/report refinements and native integrations likewise must not be described as fully implemented from this increment.


## Finding inspector increment

Implemented in-panel finding detail with Back, endpoint/MITRE/description/remediation, real proposal indicators and campaign-preserving report/proposal actions. Finding selection rechecks the current campaign record; removed or unlinked findings have an explicit unavailable state. Stale asynchronous responses cannot overwrite a newly selected asset. Proposal review verifies the finding/campaign against current records. Focused controller checks cover linkage, absent proposals, deleted findings and response races; all 122 community tests pass.

Media follow-up is in progress: all 13 full audio/video streams decode without errors, and full-track base.en speech-recognition output has been reviewed (12 sources with speech; the older demo produced no detected speech). ASR is approximate and is not direct listening or proof of narrated claims. Individual storyboard inspection and rendered visual comparisons are being recorded in a subsequent checkpoint.


## Rendered UI and media checkpoint

See [full-track/storyboard/visual review](full-track-review.md). All 107 native storyboards are now individually inspected, all full tracks decode, and speech-recognition output from complete audio tracks has been reviewed. Direct continuous playback remains unclaimed. Desktop/mobile screenshots are stored with the comparison; the visual pass found and fixed the inherited finding-button flex/default-style defect. The tour now overlays the desktop map, mobile selection uses a bottom sheet, and report previews have keyboard section navigation. Local Chromium acceptance and focused controller checks pass for this increment. A real n8n 2.45.4 CLI read-only workflow also passed against our HTTP server; host trigger/editor parity is not claimed.
