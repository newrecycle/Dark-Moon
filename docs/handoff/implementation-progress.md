# Visual handoff implementation progress

Updated 27 October 2026. Branch `pro`. This is the current state; ticket baseline statuses refer to the older 630e090 baseline.

## Implemented in the video-driven increments

- Manual graph tour with Back/Next/Finish and Explore freely, derived from actual assets with explicitly linked findings. Manual selection/close exits the tour. The desktop card sits inside the map; mobile controls remain in flow.
- Keyboard asset selector, type/address/endpoint/technology summaries, per-asset severity totals, readable finding cards with CVSS/category/status/MITRE, expandable raw metadata and close/focus restoration.
- In-inspector finding detail and Back, current-record linkage checks, unavailable/deleted finding states and protection from stale asynchronous responses. Proposal badges require real same-campaign records. Proposal review verifies finding/campaign ownership; report actions retain campaign identity.
- Mobile asset inspector sheet and screenshot-driven card styling fixes. Fixture screenshots and a structural comparison are in [the full-track review](full-track-review.md); browser CI retains screenshots.
- Report preview section navigation focuses the actual section/finding heading and keeps report content literal.
- Guided initial administrator setup after private recovery-token unlock: username, password confirmation, normal account session, cleared form secrets and provider-settings handoff. Recovery-session and OIDC paths remain available. Reviewed [desktop](visual-review/first-use.webp) and [mobile](visual-review/first-use-mobile.webp) captures use empty password fields. Initial creation checks for existing users inside the store transaction; six simultaneous requests create exactly one administrator.
- Native n8n credential Test now validates protected API access for token and password modes. It previously tested only public API reachability. Both action/trigger nodes expose the test. The development Compose lab loads the normal package so n8n retains credential-test bindings.

## Media coverage

All 13 original video/audio pairs decode end to end. All 107 storyboard sheets have been individually visually inspected, supplementing the original 475 two-second samples and four full-resolution Pro frames. Complete audio tracks were transcribed with faster-whisper base.en and all generated speech segments were reviewed; 12 sources yielded speech and the older demo did not. Twenty additional high-threshold transition frames were inspected.

This is full-track machine-transcription and visual sample/storyboard review. Direct continuous audiovisual playback, direct listening and inspection of every encoded frame remain incomplete. ASR can misrecognize technical words and timings. Narrated claims and the read-only demo are not proof of live execution. Exact fonts, brief states and headset interactions remain unverified. See [method and per-sheet hashes](full-track-review.json).

## Validation

- **125 community tests passed**, including initial setup authentication, password handling and concurrent requests. Focused graph-controller checks cover multi-step navigation, Finish, linkage isolation, proposal context, deleted findings, stale responses, empty states, CVSS zero and focus.
- Local Chromium acceptance passed, including initial setup, settings/provider fixtures, graph panel/Back, responsive inspector, report navigation, remediation and exports. Model OAuth fixture flows are distinct from real provider-account verification.
- [Hosted browser on the responsive/report checkpoint](https://github.com/newrecycle/Dark-Moon/actions/runs/40604535323) and [its actual Docker/provider + owned-loopback run](https://github.com/newrecycle/Dark-Moon/actions/runs/40604535342) passed. [Follow-up browser](https://github.com/newrecycle/Dark-Moon/actions/runs/40605263580) also passed.
- **[Real native n8n host CI passed](https://github.com/newrecycle/Dark-Moon/actions/runs/40605263744)**: n8n 2.45.4 encrypted credential import, package loading, workflow execution, campaign-filtered finding output, downstream safe metadata and editor credential tests accepting valid/rejecting invalid token/password values. See [recorded contract](../validation/n8n-native-host-20261027.json).
- Imported SDK contract and n8n HMAC/replay tests pass. Native OpenCode 1.19.4 catalog/config readback and disposable key storage checks pass. No operator provider credentials are configured; real subscription login and inference entitlement remain unverified. The local environment has no Docker engine; hosted image results are separate evidence.

## Remaining implementation and validation

- **G02:** persisted evidence-backed attack paths, edge/evidence validation and technical step detail. The finding-location tour does not claim an exploitation chain.
- **D01/D02/I07:** dashboard hierarchy/metrics with exact denominators, broader page styling, full-window graph and exact visual comparisons. Current screenshots establish reviewed layouts at two viewports, not pixel parity.
- **C01/C02/F01/F02/R01:** campaign grouping/scope and live-console refinements, persistent filters/sort/paging, richer impact/fix disposition, report roadmap and further export states.
- **P01:** complete server-side redacted projection, controlled reveal/expiry and end-to-end absence checks. The safe integration feed is already restricted; the authenticated workspace still has raw evidence views.
- **S01:** calendar editing, one-time/recurring rules, timezones/DST and history beyond existing interval scheduling.
- **I01–I09/O01/G03:** remaining native host versions, trigger restart lifecycle, GitLab/Jenkins/IDE/Grafana/Splunk hosts, deployment/readiness adaptation and headset tests. n8n workflow/credential success does not establish all integration parity. Cloud deployment, external delivery and remediation publication have not been exercised.

All 26 tickets remain in [the backlog](pro-video-backlog.json). No ticket is complete merely because its source video was acquired. Earlier handoff mapping errors were corrected in 7bca2c4; the current mappings include SDK I09, deployment O01 and posture I07.
