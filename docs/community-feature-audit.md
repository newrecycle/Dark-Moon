# Community feature audit - 26 October 2026

The active feature branch is now based directly on upstream master
`b52d4d73c325427e4d2fa5f3cbf87dd889cc6300` (fetched 26 October 2026).
Only feature commits are replayed. Old fork runtime/configuration/toolbox changes
are excluded. The original August-based result remains available locally on
`backup/community-features-before-master-20261026`.

The original historical comparison used our fork's `old` build (`c6df39e`,
17 August) and upstream `2b20a2c`. The historical deletion findings below refer
to that comparison. Current implementation coverage and remaining deployment
checks are in [pro-feature-matrix.md](pro-feature-matrix.md).

No original Pro server/UI source was available in the public repositories
inspected. The user selected independent reconstruction from documentation.
Actual MIT-licensed code from all nine documented public integration repositories is imported with preserved
licenses and exact source pins under `integrations/upstream/SOURCES.json`.

## What is actually paywalled?

Upstream's current README explicitly advertises the following as paid Pro
capabilities. A feature appearing in a Pro screenshot does **not** establish that
its implementation was previously shipped in the public repository.

| Capability | Evidence from our preserved build and upstream history | Community reconstruction in this branch |
|---|---|---|
| Web dashboard and REST API | Our build has a JSON store and MCP push tools, but no web server or dashboard application. Upstream explicitly says the dashboard is outside the OSS build. | Authenticated local UI and `/api/v1` API; shared project/target/campaign views; evidence detail and operator triage. |
| Finding detail, CVSS, ATT&CK and ISO mapping | The **data fields are already public** in `mcp/src/server.py:dashboard_push_finding`. Presenting them in a paid UI does not remove them from the CLI/MCP build. | Finding browser shows the existing fields and literal evidence. |
| Exportable reports | Deterministic **Markdown reporting already exists** in `mcp/api/live_push.py`. The web report viewer and PDF export are not in our baseline. | Download Markdown, JSON and embedded-font PDF from a selected campaign without finalizing or changing it. |
| Orbital infrastructure map / VR | Infrastructure nodes and parent relationships already exist. The browser/VR renderer is absent from the public source history inspected. | Orbit/zoom/select 3D canvas map; real recorded graph edges; per-node evidence; optional WebXR rendering. No invented attack chains. |
| Scheduled recurring assessments | No scheduler implementation in either public snapshot. | Durable interval schedules with scope flags, pause/resume/delete, restart catch-up and overlap prevention. |
| Finding-to-fix remediation | Upstream added Pro documentation, not remediation source. The docs describe sandbox checks and PR creation. | Structured-edit and opt-in model-generated fixes; local Git worktrees and patch files; before/after exploit, variant and normal probes in disposable containers. UI/CLI entry points and a separately gated publication command. |
| n8n / Grafana integrations backed by the Pro API | The current README labels n8n and Grafana Pro; other listed integrations also have OSS modes. Their external plugin implementations were not deleted from this repository. | Pinned official client/n8n/Grafana source imports, SDK-tested REST compatibility, plus lightweight n8n/Prometheus/JSONL examples. Undocumented native contracts and live Grafana deployment remain unverified. |
| Cloud provisioning | Current upstream docs require a Pro license for their deploy service. No equivalent cloud provisioner is in our earlier tree. | Source bundler, checksum-verified cloud-init and AWS/GCP/Azure/OVH CLI deployment plans. `--execute` is opt-in; agent-provider setup remains a separate step on the new VM. |

The user's instruction for this work is **no remote push and no PR creation**.
The dashboard and remediation pipeline prepare local proposals only. A separate
command can prepare a publication plan without mutation; actual publication
requires both a future `--execute` invocation and `DARKMOON_ALLOW_PUBLISH=1`.
It was tested with fake transports, not against a forge. No paid service, binary or license
validation has been modified or bypassed; the new code is independent GPLv3
source built around the public store.

## What did upstream remove?

The available Git history does **not** support the claim that the complete
dashboard, scheduler or remediation engine was removed from the build we had.
The evidence points to a separately distributed Pro implementation:

- [`e92fcf3` (29 April)](https://github.com/ASCIT31/Dark-Moon/commit/e92fcf3):
  removed **prompt references** to a dashboard API; its message expressly says
  there was no FastAPI/dashboard in that project. It did not delete a dashboard
  implementation.
- [`ddf3276` and `bc625df` (29 April)](https://github.com/ASCIT31/Dark-Moon/commit/ddf3276):
  restored the non-Cryptolens Dockerfile and removed an orphaned checker copy.
  These precede our August baseline; they are not a new October license gate.
- [`9ad46e6` (12 June)](https://github.com/ASCIT31/Dark-Moon/commit/9ad46e6):
  **added** the Pro findings-persistence pipeline to the community edition.
- [`a59517f` (3 August)](https://github.com/ASCIT31/Dark-Moon/commit/a59517f):
  honored a persistent report-directory override. This code remains public.
- [`3a780ca` (16 September)](https://github.com/ASCIT31/Dark-Moon/commit/3a780ca):
  added remediation/n8n documentation. No remediation implementation was added.
- [`b7e4e61` and `8791105` (21 September)](https://github.com/ASCIT31/Dark-Moon/commit/8791105):
  labeled remediation paid and explicitly separated OSS CLI and Pro showcases.
- [`bb55181` (21 September)](https://github.com/ASCIT31/Dark-Moon/commit/bb55181):
  removed dashboard/scheduler **images**, subsequently superseded by the Pro
  showcase. These were image removals, not application-code removals.
- [`7a31ce4` (25 September)](https://github.com/ASCIT31/Dark-Moon/commit/7a31ce4):
  labeled Pro-only surfaces in the documentation.
- [`98639cc` (28 September)](https://github.com/ASCIT31/Dark-Moon/commit/98639cc):
  added the Pro cloud-deployment promotion.

Actual post-baseline source deletions found in upstream include the obsolete
`mcp/.opencode/agents/pentest-web.md` duplicate (`5bdd43f`) and the misleading
`mcp/opencode.json` stub (`a5fc031`). Their commit messages explain registry and
configuration cleanup, not a paid replacement.

Our fork and upstream diverge at `6ccbdba`. Many compatibility tests, Docker
changes and runtime experiments are fork-only work. A direct tree diff showing
those files missing upstream is not evidence that the upstream author deleted
them. The feature-only rebase deliberately discards those fork-only changes and
uses current upstream runtime/configuration unchanged.

## Verification and limits

See [community.md](community.md) for operation and API contracts. The regression
suite covers HTTP authorization, path checks, queue deadlines, cancellation,
scheduling, parallel storage, local patch isolation and remediation validation
dispositions. Browser acceptance uses disposable fixture data, a fake assessment
launcher and a real local remediation subprocess; it performs no target scans.

Real LLM generation, real Docker retests, cloud provisioning, external integration
imports and headset rendering require those environments and were not live
tested here. Their code paths do not imply measured parity with DarkMoon Pro.
Machine-validated remediation means the supplied reproduction/regression probes
passed; it is not a claim that the target has no remaining vulnerabilities.

The old fork-only toolbox suite is not carried onto master. Current upstream
MCP tests pass; see the current validation record.

No push, PR, deployment, hosted-service upload or assessment of a real target was
performed during this reconstruction.
