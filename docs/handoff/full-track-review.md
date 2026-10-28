# Full-track, storyboard and rendered UI follow-up

27 October 2026, branch `pro`. Exact sheet hashes and per-source audio/decode coverage: [full-track-review.json](full-track-review.json).

## What was actually reviewed

All 13 original audio/video pairs decoded end to end with FFmpeg and no decode errors. Complete mono 16 kHz audio tracks were processed with faster-whisper 1.2.1, base.en int8, VAD and beam size 5. All resulting speech segments were read in chronological order. Twelve sources yielded speech; the older demo yielded none. This is full-track machine-transcription review, not direct listening. Technical names and ASR timestamps can be inaccurate, and no-speech detection does not prove silence.

All **107 native storyboard sheets** were individually displayed and visually inspected, including their opening/closing/title frames: Pro 9, cloud 7, GitHub 8, GitLab 7, Jenkins 8, VS Code 7, JetBrains 7, n8n 7, Grafana 7, Splunk 7, SDK 6, OSS 13, older demo 14. These supplement the prior 475 two-second samples. A scene-change pass across every original yielded 20 additional inspected high-threshold transitions, mostly title changes and older-demo notifications. It is insensitive to gradual fades and small controls.

Direct continuous audiovisual playback and visual inspection of every encoded frame remain incomplete. Small thumbnail text does not establish exact settings. Narration describes intended behavior; it does not independently prove execution or compatibility.

## Findings carried into implementation

- Pro narration links password setup, scoped launch, live console, finding evidence/impact, reviewable fix, executive-to-technical report/PDF and infrastructure navigation. The example path describes internet access, weak login, database controls and file exposure. These are example relationships, not four mandatory steps for arbitrary campaigns.
- Full-track narration reinforces that cloud deployment/readiness is CLI-driven, CI gates are recomputed from finding severity, and Jenkins separates failure from unstable policy. These remain native-host contracts.
- Grafana and Splunk explicitly use safe metadata without evidence/report bodies. The SDK defaults evidence to null. IDE reveal requires an explicit local action. The n8n recording describes credential confirmation and downstream finding data; mere public API reachability is insufficient evidence of authenticated access.
- The older demo shows accumulating target notifications beside agent execution. No additional Pro web page or spoken requirements were found from the current review methods.

## Rendered visual comparison

Local Chromium 153 rendered our actual application and disposable HTTP fixture at 1440×1000 and 390×844. The reference graph at Pro 128/136 seconds was inspected at full resolution; it has a large map, right-hand asset inspector, severity totals, finding cards and a lower-left manual tour. The comparison is structural: different fixture data, viewport and graph implementation make a pixel-difference score misleading.

| Observed gap | Change and verification |
|---|---|
| Finding selection opened a separate dialog immediately | In-inspector detail/Back now retains the asset; full evidence remains available through a separate action. Missing/deleted linkage and stale-response races are checked. |
| Proposal badges could have been copied as decoration | Badges appear only for actual proposal records in the same campaign; review verifies current campaign/finding ownership. |
| Finding buttons inherited a flex row and default gray button background | Screenshot review caught squeezed text that functional tests had missed. Explicit vertical cards restore readable severity/CVSS/title/category rows. |
| Tour appeared below the map | Desktop card now sits in the lower-left map area; on small screens it stays in document flow. |
| Inspector crowded the mobile layout | Selected assets use a bounded, scrollable bottom sheet with a visible close action. |
| Long report preview lacked section navigation | Section buttons focus and scroll to the actual heading, including finding headings, without interpreting report text as HTML. |

Reviewed fixture captures: [asset inspector](visual-review/surface-inspector.webp), [finding detail](visual-review/surface-finding.webp), [tour](visual-review/surface-tour.webp), [mobile inspector](visual-review/surface-mobile.webp), [report navigation](visual-review/report-navigation.webp). They contain synthetic data. Browser CI now retains fixture screenshots for later comparisons.

Our page still differs from the recording's full-window map, exact typography, node styling/topology and some spacing. Real evidence-backed path records, headset operation and exact animation/hover parity remain open. Screenshot similarity does not establish those features.

## Runtime and integration evidence

The full browser suite and focused graph controller pass locally. The imported official SDK passes against our real HTTP handler with the fake scan launcher; the n8n HMAC/replay suite passes. An actual n8n 2.45.4 CLI workflow has also loaded the custom node, imported encrypted disposable credentials, read campaign-filtered findings from our HTTP server and passed safe metadata into a downstream node. The real editor credential-test API subsequently passed valid/invalid token/password cases; [host CI](https://github.com/newrecycle/Dark-Moon/actions/runs/40605263744) repeats this. Trigger-host lifecycle, restarts, broader editor interactions and third-party delivery remain separate checks.

[Native OpenCode follow-up](../validation/native-provider-followup-20261027.json) passes native 1.19.4 catalog, authentication rejection, model/small-model readback and disposable key write/delete. Local Docker remains unavailable; the previously successful hosted image run is separate evidence. No provider account credentials are configured, so real subscription login and inference entitlement are unverified.
