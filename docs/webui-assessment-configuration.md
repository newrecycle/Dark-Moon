# Document-backed WebUI assessment configuration

The upstream README, full scope reference, n8n guide, remediation guide and
linked benchmark/n8n repositories were read on 26 October 2026. Exact file blob
revisions are recorded in [assessment-catalog-sources.json](assessment-catalog-sources.json).
The catalog is bundled locally; opening a form does not fetch remote instructions.

## Launch behavior

- Presets cover custom, web, API/GraphQL, HackerOne and local lab engagements.
  They fill testing choices, never authorization or an assessment target.
- Noise uses the documented `stealth`, `low`, `moderate` values.
- Severity is one maximum assessment cap. It is different from an integration's
  minimum reporting threshold. Multiple caps and the former unsupported `high`
  noise option are rejected with a validation error.
- Focus/exclusions include authentication bypass, JWT, deserialization, GraphQL,
  HTML injection and the `H1` shortcut, with additional custom token fields.
- Program, additional assets, exclusions, rules and safe-harbor applicability
  are serialized as `PROGRAM`, `TARGETS`, `OUT`, `RULES`, `SAFE_HARBOR` flags,
  alongside the existing campaign context. API-prefixed additional assets remain
  subject to the target allowlist. Secrets still use vault references and the
  local privacy gateway. Remediation is handled locally; no publishing flag is emitted.
- A literal scope preview shows the nonsecret fields before submission.
- Integration setup links all nine upstream integrations, explains account/JWT
  setup and container networking, and distinguishes local proposals from PRs.

## Owned lab analysis

`tools/analyze-community-lab.py` starts an owned ephemeral loopback HTTP service
and a minimal disposable Docker toolbox. Real `BaseWorkflow.execute_step` calls
execute curl through the existing `DarkmoonDockerClient`. The script measures
browser hardening headers, reflection of an inert HTML element, and an HTTP 401
negative authentication control. Only findings demonstrated by measured responses
are pushed through DarkMoon's native campaign/finding/finalization functions.

The same stored campaign is then read through the WebUI HTTP handler, including
its options endpoint and Markdown/PDF exports. JSON campaign/finding records,
requests, responses and reports are retained by the `owned-lab-analysis` CI job.
Control-state keys and access tokens are excluded from the uploaded artifact.

This is a deterministic workflow/toolbox analysis, not a full LLM-orchestrated
pentest. It does not assert JavaScript execution, import benchmark findings as
local results, scan third-party targets, call a model, or publish a remediation.
The UI and report identify the lab origin explicitly.
Captured HTTP responses prompted a readable evidence view: terminal color codes
and carriage-return formatting are normalized for display, while the original
evidence remains available as raw JSON and in exports. Markup in evidence is
rendered as literal text, never executed by the dashboard.

Repeat on a Linux Docker host from the repository root, using a fresh output path:

```bash
docker build --file tools/lab/Dockerfile --tag darkmoon-ui-lab .
PYTHONPATH=mcp .venv/bin/python tools/analyze-community-lab.py --output-dir /tmp/darkmoon-owned-analysis
```

Install `mcp/requirements.txt` and `mcp/community/requirements.txt` in that venv
first. CI build/probe results determine actual analysis status; the presence of
this script alone is not evidence of a successful run.

The [completed analysis and replay instructions](validation/owned-lab-20261026/README.md)
preserve the actual CI campaign, its two measured findings and native report.
The source revision and artifact digest are recorded there. Browser acceptance
also passed with readable evidence, scope presets and integration setup; the
actual captured CI dataset was independently opened in Chromium and inspected.
