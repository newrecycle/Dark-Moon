# Frame review and acquisition retry — 27 October 2026

**Result: partial visual progress.** No YouTube stream or storyboard was acquired. A publisher-supplied animated README reference was decoded and sampled successfully. Its graph, inspector and tour states can inform implementation; the full linked-video design audit remains incomplete.

## Acquisition outcomes

| Avenue | Actual result | Coverage consequence |
|---|---|---|
| Local public thumbnail, high-resolution storyboard and lower-resolution storyboard | Each returned 195-byte HTML “Site Unavailable,” not an image, despite HTTP 200. Decoding/content checks failed. | No storyboard or thumbnail evidence. |
| Local direct 360p video range request | HTTP 206, but the body was the same 195-byte HTML stub. | No stream evidence. |
| Normal public browser player for the Pro tour | Watch page and metadata loaded. Playback stayed at time 0 with `readyState=0`; the player remained black. Browser-native media download was canceled. No bot challenge was visible in that browser. | No decoded video frames. A loaded page is not a successful video review. |
| GitHub-hosted Ubuntu runner, public metadata/media acquisition | YouTube required sign-in to confirm the request was not a bot on the first source. The tool stopped further YouTube requests; the remaining 12 entries were skipped. No cookies, sign-in or bypass was attempted. | Zero video frames; workflow success means diagnostic completion only. |
| Existing publisher README animation | `docs/pics/infra-orbital.gif` decoded successfully: 1280×720, 182 frames, 50 ms per frame, 9.1 seconds. Reviewed 12 evenly spaced samples plus frame 87; inspected frames 0, 49, 87 and 99 at full size. | Bounded graph-animation evidence **A**. This is not acquired YouTube footage or a review of every animation frame. |

Hosted run: [40424885698](https://github.com/newrecycle/Dark-Moon/actions/runs/40424885698). Its short-lived artifact contained only a diagnostic manifest, with no contact sheets or video. ZIP SHA-256: `832d62f992940276024c89da5414e87612988b805be5a1ab3436a11ea8bf9cb4`. The sanitized persistent record is [video-acquisition-retry.json](video-acquisition-retry.json). The acquisition script is `tools/video-review/acquire_public_frames.py`; its workflow is `.github/workflows/video-reference-review.yml`. It is bounded, public-only and stops at a site bot restriction. The direct-video fallback applies when a storyboard is absent; a storyboard fetch/decode exception currently terminates that source rather than testing a stream fallback. That fallback was not reached in the hosted run.

## Animation provenance and sampled timeline

Reference: [infra-orbital.gif](../pics/infra-orbital.gif), linked by the publisher’s README. Git blob: `3182f7f9b2e471b1c41476a3435a22924b14ebb2`. SHA-256: `20c5c792d4cc81c5834bb2a25aed166560850bc61e4a9248cf8c1f0be473a549`. [Machine-readable frame record](animated-reference-review.json) lists the exact 13 reviewed frame indices and timestamps. No additional media copy is committed.

| Frames / sampled times | Observed state | Implementation implication |
|---|---|---|
| 0, 16, 33 / 0.00, 0.80, 1.65 s | Infrastructure Map with campaign return link, node/connection/severity counts, dark topology, right-side host inspector and an empty finding state. Lower-left tour says step 1/4 and offers Next. Camera framing changes between samples. | Preserve campaign context, distinguish an empty asset from an error, and keep summary counts tied to actual records. Do not infer the input gesture from camera motion. |
| 49, 66, 82, 87 / 2.45, 3.30, 4.10, 4.35 s | Web application selected; tour shows step 2/4, Back, Next, dot indicators and Technical details. Inspector shows asset identity/stack, severity chips, finding rows, CVSS and PR indicators. | Selection needs an asset-to-findings inspector and clear navigation. A narrative tour card can coexist with the asset inspector. |
| 99, 115, 132, 148, 165 / 4.95–8.25 s | Finding detail replaces the inspector list: Back/Vulnerability header, severity/CVSS, category, exploited status, MITRE, endpoint, description and remediation. View remediation (PR) and Open full report are visible. | Model list/detail navigation explicitly; maintain the selected asset and campaign for Back. Bind actions to existing proposal/report records. Button visibility alone does not establish successful external behavior. |
| 181 / 9.05 s | Tour returns to step 1/4 while vulnerability detail remains visible. | Keep tour and detail views usable together. This observation does not establish the original component/state architecture. |

## Design handoff

These are observed proportions and proposed behavior, not extracted CSS tokens or proof of Pro parity.

- At 1280×720, the graph occupies approximately x=0–940 and the inspector x=940–1280 (340 px). The tour card is approximately 430 px wide near the lower-left edge. Implement an adaptive split view; use a sheet on narrow screens and prevent the tour from covering navigation.
- The canvas is black, with dim unselected labels and dotted exposure rings; selected assets have a brighter label. Connections are red; nodes can have finding-count overlays and purple PR badges. Preserve text labels and keyboard selection so color and 3D positioning are not the only information channels.
- The graph header contains campaign context and aggregate node, connection and severity counts. Use measured backend records. Published sample values and paths are illustrative and must never populate a real campaign.
- The inspector needs close, asset identity/type/address/stack, severity totals and a finding list with severity, CVSS, title/category and linked-proposal indicators. Support long labels, scrolling, an empty state and focus return after close.
- Selecting a finding should open a detail panel with a Back action and preserve graph selection. Show endpoint, status, MITRE, description and remediation with readable wrapping. Resolve remediation/report actions to the selected finding; label unavailable destinations accurately. A PR badge does not authorize creating or publishing a PR.
- The tour needs current-step/total, Back/Next, step indicators, Technical details when supported, and Explore freely. The recording shows only steps 1 and 2 of 4. Derive our steps from real supported evidence; do not invent unseen publisher steps.
- Camera reframing is visible, but mouse/keyboard gestures, easing and timing are not established by the samples. Add reduced-motion behavior and keyboard alternatives. The animation does not establish headset controls or an evidence-backed kill chain.

Backlog updates: **G01** now specifies inspector/list/detail actions, **G02** specifies observed tour controls while retaining evidence-backed path requirements, and **D02** adds responsive split-view guidance. **V00 remains open/partial**.

## Verification and remaining review

Acceptance for implementation: select an asset → inspect only its linked findings → open one detail → return to the same asset/list → open its existing proposal or full report; step the tour forward/back and leave to free exploration; repeat with keyboard, reduced motion, an empty asset, missing proposal, long content and a narrow viewport. Graph topology must not manufacture exploitation evidence. These are implementation acceptance requirements, not tests already performed against Pro.

All 11 current Pro-related YouTube tutorials and the legacy demo still lack visual review. Existing captions remain useful functional evidence; the OSS tutorial remains contextual. Tour steps 3/4, hover/focus behavior, exact transitions, external destination behavior, other integration UIs and VR are unobserved. To close V00, review accessible publisher-provided recordings or captures across the full timelines and append timestamped evidence. Current site restrictions were respected; no access-control circumvention or further blocked-site retries are part of this handoff.
