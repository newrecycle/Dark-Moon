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

The [follow-up browser run](https://github.com/newrecycle/Dark-Moon/actions/runs/40577228611) also passed, including the tour-exit fix. Docker/provider and owned-loopback validation are tracked separately in [runtime CI](https://github.com/newrecycle/Dark-Moon/actions/runs/40577228744). Check those run conclusions for current status.
