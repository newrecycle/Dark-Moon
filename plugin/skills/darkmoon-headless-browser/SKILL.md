---
name: darkmoon-headless-browser
description: Analyze authorized JavaScript-rendered sites, SPAs, client-side routes, browser network activity, and DOM sources/sinks through Dark-Moon's bounded Playwright workflow. Use when static HTTP crawling cannot observe rendered behavior.
allowed-tools: mcp__darkmoon__*
---

# Dark-Moon Headless Browser

Use the Dark-Moon MCP boundary for browser work. Load the existing
`headless-browser` persona through the MCP, then use only the structured browser
workflow. Do not execute a host browser or generate JavaScript for execution.

## Preconditions

1. The user must identify an authorized HTTP(S) target and scope.
2. Call `darkmoon_get_session` and retain its `session_id` for privacy-vault
   continuity.
3. Call `darkmoon_read_agent("headless-browser")` and adopt the returned persona
   as the operating rules for this specialist. Load it through MCP rather than
   host filesystem access.
4. Call `darkmoon_health_check`. The `playwright-chromium` runtime must be
   available; otherwise report that the Dark-Moon backend image needs upgrading.
5. Call `darkmoon_list_workflows` and require the `headless_browser` workflow
   with its `analyze` method. Never substitute an invented tool name.

## Operations

Call `darkmoon_run_workflow` with `workflow="headless_browser"`,
`method="analyze"`, the session ID, and one of these modes:

- `snapshot`: render one page and return bounded DOM metadata.
- `crawl`: follow rendered links sequentially within page/depth limits.
- `dom_sinks`: focus on client-side sources, sinks, and inline event handlers.
- `network`: summarize browser requests, responses, failures, and blocked egress.

Keep `same_origin=true` unless the user explicitly authorizes additional origins.
Start with `max_pages=3`, `max_depth=1`, `max_requests=200`, `timeout=60`, and
`settle_ms=1000`. Increase a bound only when evidence shows it is necessary,
never beyond the workflow's enforced ceiling. Enable `ignore_https_errors` only
for an explicitly authorized target with a known certificate problem.

Screenshots are optional artifacts. Request them only when visual evidence is
material; the workflow returns an artifact path rather than image bytes.

## Safety and privacy

- Pass the target only in the workflow's `url` parameter. Never place a target,
  credential, token, cookie, or protected placeholder in another field.
- The browser uses a fresh non-persistent context, blocks downloads and service
  workers, strips URL query values, suppresses headers/cookies/storage/bodies,
  and kills the whole process group at the deadline.
- Cross-origin traffic is blocked by default. Never disable that boundary merely
  to make a page render more completely.
- Never use `darkmoon_execute_command` to reproduce browser behavior with raw
  Node, Playwright, Lightpanda, or shell commands. The structured workflow is the
  only approved browser execution path.

## Reporting

Separate observed evidence from hypotheses. Report rendered URLs, status codes,
forms, DOM source/sink names, blocked requests, console summaries, and artifact
paths. Do not claim exploitability from a sink name alone; require a reproducible
source-to-sink flow or clearly mark it for manual validation. Preserve every
privacy placeholder exactly as returned by the MCP.

<!-- DARKMOON_BROWSER_CAPABILITIES_START -->
## Runtime browser capabilities (authoritative)

Call `darkmoon_list_workflows` before browser work; its `headless_browser.capabilities` object is the live contract and supersedes any earlier mode or limit list in this file.

Supported output modes:

- `snapshot` — Complete DOM snapshot with supporting telemetry; single-page unless link following is enabled.
- `crawl` — Follow links and return complete snapshots for multiple pages.
- `full` — Return every privacy-safe collector for the requested page set.
- `content` — Return rendered text, headings, and page identity.
- `metadata` — Return page identity, status, and headings only.
- `links` — Return discovered links and their rendered labels.
- `forms` — Return forms and input metadata without field values.
- `scripts` — Return external script inventory and source/sink indicators.
- `dom_sinks` — Focus on DOM sources, sinks, and inline event handlers.
- `network` — Return bounded request, response, and failure metadata.
- `console` — Return bounded, credential-scrubbed console messages.
- `accessibility` — Return a bounded semantic and interactive-element tree.
- `performance` — Return navigation, paint, and resource timing aggregates.
- `security` — Return privacy-safe browser security observations.
- `screenshot` — Capture viewport screenshots and minimal page metadata.

Set `follow_links=true` to traverse links with any mode. `crawl` enables traversal automatically, and `screenshot` enables screenshot capture automatically. Navigation waits support `commit`, `domcontentloaded`, `load`, `networkidle`.

Defaults are 10 pages, depth 3, 750 requests, 120 seconds, and 2000 ms settle time. Hard ceilings are 50 pages, depth 8, 2500 requests, 600 seconds, and 30000 ms settle time.

Browser output remains privacy-minimized: no request or response bodies, header values, cookies, browser storage, or form field values are returned.
<!-- DARKMOON_BROWSER_CAPABILITIES_END -->
