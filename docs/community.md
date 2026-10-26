# DarkMoon Community workspace

An independent GPLv3 implementation of the dashboard, API, visualization,
scheduler, report exports and local remediation workflow. It reads the existing
assessment data produced by current upstream MCP tools. It does not require DarkMoon
Pro, copy its implementation, or change the existing agent runtime.

The [feature audit](community-feature-audit.md) distinguishes paid packaging from
actual public-source removals and identifies the exact comparison commits.

## Start locally (Linux / WSL)

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r mcp/community/requirements.txt
DARKMOON_PYTHON="$PWD/.venv/bin/python" ./community.sh
```

Open `http://127.0.0.1:8780`. Read the access-token file at the path printed on
startup and enter its contents into the unlock form. The token is generated once
with private permissions and persists across restarts. The browser holds it only
in tab memory. A reload locks the workspace. Alternatively set
`DARKMOON_DASHBOARD_TOKEN` to a random token of at least 24 characters.

Install the complete community requirements before starting. ReportLab handles rendering,
cryptography protects stored credentials/state, PyJWT verifies sessions/OIDC, and
pyHanko/pypdf provide actual digital signatures and AES-256 PDF encryption.

By default the workspace reads `./darkmoon-settings`, matching current upstream's
OpenCode data bind mount, and uses `./reports` for reports. To use another existing workspace:

```bash
DARKMOON_DATA_DIR=/path/to/darkmoon-settings ./community.sh --port 8780
```

The dashboard must run as an account that can read/write that shared directory.
Launching assessments also requires the **existing** Docker/Compose agent stack
to be installed and configured (`./install.sh`). Starting the dashboard does not
start a pentest. An explicit New assessment action or an enabled, due schedule
starts one. Assessment commands use `./darkmoon.sh` from the repository root.

For another locally installed runtime, configure its launcher as an argv array:

```bash
export DARKMOON_LAUNCH_ARGV='["/absolute/path/to/assessment-wrapper"]'
./community.sh
```

The final argv element is the complete scope prompt. The wrapper must honor the
existing campaign id in its context. The default prompt tells the agents to push
all findings to that campaign and finalize it, rather than initialize a second
one. The preserved LLM orchestrator's compliance still depends on its behavior;
verify campaign linkage on the first live assessment.

The queue executes one task at a time, limits stored launcher output to 8 MiB,
and defaults to a two-hour deadline (`--job-timeout`). A zero exit from the
launcher is recorded separately from assessment completion. If the agent did
not finalize the campaign, it becomes `awaiting_review`, not `completed`.

Cancellation terminates the host launcher process group. A Docker exec client
or external runtime can leave work running on its server after disconnect; check
that agent session before rerunning. A restarted dashboard marks interrupted
jobs honestly and does not automatically rerun them.

One daemon owns each state directory. Interval schedules store timezone-aware
UTC timestamps; the browser displays your local time. After downtime, a missed
occurrence is run once, not once for every missed interval. An unfinished job
from the same schedule prevents overlap. A crash between persisting the next
occurrence and enqueueing can skip that occurrence; the scheduler favors avoiding
duplicate assessments over promising exactly-once external effects.

## API

The extended Pro-style route families, account setup, security profiles and
source provenance are documented in [the feature coverage matrix](pro-feature-matrix.md).
Campaign/project/target list routes use the official client envelope `{ "data": [...] }`.
Campaign detail includes both `data` and the original community detail fields.

All data, mutation, event and metrics routes require:

```text
Authorization: Bearer YOUR_TOKEN
```

The static UI and minimal `/healthz` endpoint are public. Host validation rejects
DNS-rebinding names; cross-origin requests are disabled. It binds loopback by
default. For a reverse proxy, use TLS and add the proxy's hostname with
`--allow-host dashboard.example.com`. Do not put the bearer token in a URL.

| Method | Route | Result |
|---|---|---|
| GET | `/api/v1/capabilities` | Community feature contract; publishing=false |
| GET | `/api/v1/overview` | Current project, target, campaign, finding and job snapshot |
| GET | `/api/v1/projects`, `/targets`, `/campaigns`, `/findings` | Existing stored records |
| POST | `/api/v1/campaigns` | Queue an assessment; returns HTTP 202 with job id |
| GET | `/api/v1/campaigns/{id}` | Campaign with target, findings and infrastructure |
| GET | `/api/v1/campaigns/{id}/findings` | Full finding records |
| GET | `/api/v1/campaigns/{id}/graph` | Nodes, recorded edges and finding associations |
| GET | `/api/v1/campaigns/{id}/report.md`, `.pdf`, `.json` | Fresh deterministic exports |
| PATCH | `/api/v1/campaigns/{id}/findings/{finding}` | Operator status triage, separate from validation |
| GET | `/api/v1/jobs`, `/jobs/{id}`, `/jobs/{id}/log` | Queue state / bounded log |
| POST | `/api/v1/jobs/{id}/cancel` | Request cancellation |
| GET, POST | `/api/v1/schedules` | Read/create durable recurring assessments |
| PATCH, DELETE | `/api/v1/schedules/{id}` | Pause/resume with `{ "enabled": false/true }`, or delete |
| GET, POST | `/api/v1/remediations` | Read local proposals / queue a local fix |
| GET | `/api/v1/remediations/{id}/patch` | Download the saved local patch |
| GET | `/api/v1/integrations/findings` | Allowlisted metadata without evidence/host/title |
| GET | `/api/v1/events` | SSE revision events, not a copy of all assessment evidence |
| GET | `/metrics` | Prometheus severity counts, campaign count and queue size |

Example assessment body:

```json
{"name":"Staging review","target":"https://staging.example.com","focus":"sqli,xss,idor","exclude":"dos","severity":"critical,high","noise":"moderate"}
```

Use an `Idempotency-Key` header when retrying assessment creation. Reusing a key
with the same body returns the existing job; a different launch spec is rejected.
Schedule bodies add `interval_seconds` (60 to 31,622,400), `enabled` (boolean)
and `next_run` (timezone-aware ISO timestamp). Example:
`"next_run":"2026-11-01T18:00:00Z"`.

## Infrastructure visualization

The map supports drag-to-orbit, scroll-to-zoom and node selection. Nodes come
from `dashboard_push_infra_node`; edges come from explicit parent ids and
connections. Findings link through their existing `node_id` field. The UI does
not manufacture an attack path from unrelated findings.

WebXR is offered when `navigator.xr` reports immersive VR support. It requires a
compatible headset/browser and a secure context (localhost or HTTPS). The VR
view renders the same nodes/edges; it is a basic spatial view, not the full Pro
orbital tour or a guarantee of headset compatibility.

## Local remediation

From a confirmed/exploited finding, select **Prepare local fix**, give the path
to the target's source repository on the dashboard host, and supply exact-match
edits or opt into the configured model. Validation is an explicit checkbox.
The job runs in the same bounded queue as assessments.

The CLI provides the same pipeline:

```bash
export DARKMOON_DATA_DIR="$PWD/darkmoon-settings"
PYTHONPATH=mcp python3 -m community.remediation \
  --repo /path/to/application --campaign-id camp_... \
  --finding-id vuln_... --edits /path/to/edits.json
```

`edits.json` is an array:

```json
[{"path":"src/search.py","old":"exact vulnerable source","new":"replacement source"}]
```

The target must be a clean local Git working tree. The pipeline creates a new
local branch and an isolated worktree under
`darkmoon-settings/community/remediation/rem_.../source`. It validates every
search before writing a file, rejects traversal/symlinks and changes to validation
configuration, and caps patch scope. The original working tree and HEAD stay
untouched. The proposal is an **uncommitted diff** in its new worktree plus
`fix.patch` and `result.json`; review it before committing or applying it.

To request defensive edits from an OpenAI-compatible model:

```bash
export DARKMOON_REMEDIATION_BASE_URL=http://127.0.0.1:1234/v1
export DARKMOON_REMEDIATION_MODEL=your-model
# Set DARKMOON_REMEDIATION_API_KEY only if that endpoint requires it.
PYTHONPATH=mcp python3 -m community.remediation \
  --repo /path/to/application --campaign-id camp_... --finding-id vuln_... \
  --generate --file src/search.py --file src/database.py --validate
```

Only the explicitly selected files and the finding are supplied to that model.
Its key stays in the HTTP Authorization header, not the prompt or command line.
If the configured endpoint is external, that selected source/evidence is sent to
it; the dashboard does not silently inherit a cloud endpoint or disable the
existing assessment privacy gateway. No model is called without `--generate` /
the corresponding checked UI control.

### Reproduction plan

`--validate` requires a committed `.darkmoon/repro.json` in the target repository,
keyed by finding id or category. For example, a prebuilt Python image with an
application-specific probe script:

```json
{
  "sql_injection": {
    "image": "my-application-retest:reviewed",
    "probes": [
      {"name":"original exploit","kind":"exploit","argv":["python","probe.py","attack"],"before":{"exit_code":0,"contains":"VULNERABLE"},"after":{"exit_code":0,"contains":"BLOCKED"}},
      {"name":"encoding variant","kind":"variant","argv":["python","probe.py","variant"],"before":{"exit_code":0,"contains":"VULNERABLE"},"after":{"exit_code":0,"contains":"BLOCKED"}},
      {"name":"normal search","kind":"normal","argv":["python","probe.py","normal"],"before":{"exit_code":0,"contains":"EXPECTED_RESULT"},"after":{"exit_code":0,"contains":"EXPECTED_RESULT"}}
    ]
  }
}
```

The image must already exist locally and provide `sh`, `cp` and the probe runtime.
Each probe gets a disposable container with a private writable source copy, no
network, no capabilities, an unprivileged uid, memory/CPU/process/time limits and
no Docker socket. Install dependencies into the image beforehand; probes cannot
fetch them from the internet. Network-dependent exploit tests must be adapted
to start and probe the application inside that container, or use a separately
reviewed validation setup outside this pipeline. The image is a Docker container,
not a VM-grade boundary against hostile kernels.

Both phases use the same immutable probe definitions. At least one exploit and
one normal regression are mandatory. A timeout, missing image/engine or command
error cannot count as evidence of a fix. Dispositions:

| Status | Meaning |
|---|---|
| `proposed` | Local patch exists; validation was not requested. |
| `validated` | Every recorded baseline and post-fix probe passed its explicit expectations. Human review still required. |
| `unreproduced` | Baseline gates failed; no patch was applied. |
| `validation_failed` | Patch exists, but its retest failed or stopped. |
| `failed` | No usable proposal; see the saved error and job log. |

The dashboard, scheduler and remediation pipeline never push or create PRs.
Retesting does not silently change a finding's status to remediated. Operator
triage is explicitly recorded separately.

### Publication plan for later review

The separate publisher is inactive by default and is never invoked by a job.
It can prepare the intended Git push and forge request without modifying Git or
contacting the forge:

```bash
PYTHONPATH=mcp python3 -m community.publish --proposal-id rem_... \
  --destination https://github.com/YOUR_ACCOUNT/YOUR_TARGET_REPO --base main
```

Adapters cover GitHub, GitLab and Gitea. A proposed or incompletely validated fix
is marked draft (Gitea uses its configured WIP title-prefix convention, default
`WIP:`); a validated fix still requires human review and manual merge.
The planned PR includes gate outcomes and the explanation; raw evidence is kept
locally rather than uploaded automatically.

Actual publication is a separate future operator action requiring **both**
`--execute` and `DARKMOON_ALLOW_PUBLISH=1`, plus `DARKMOON_FORGE_TOKEN` in the
environment. No publication was performed during this work. Explicit execution
checks that the worktree still matches its recorded patch, commits that proposal
using the operator's Git identity, pushes its new branch without force, and
creates a review request. It never merges. The token is supplied through a
temporary fixed askpass helper/environment and an HTTP header, not Git URLs or
stored credentials. An ambiguous PR response stops for reconciliation rather
than retrying blindly. Enterprise GitHub hosts and other forge APIs need their
own adapters; do not assume universal compatibility.
Gitea also requires `DARKMOON_FORGE_USERNAME`; confirm its server's WIP prefix
configuration before publishing an unvalidated proposal.

To remove a reviewed proposal later, first preserve any wanted diff, then use
`git -C /path/to/application worktree remove /path/to/proposal/source` (Git will
refuse dirty worktrees without an explicit force) and delete the associated local
branch with `git branch -d remediation/rem_...` when appropriate. The dashboard
does not silently delete proposal worktrees.

## Integrations

Import templates from `integrations/community/`:

- n8n: the inactive HTTP Request workflow needs a Header Auth credential with
  header `Authorization` and value `Bearer YOUR_TOKEN`. Adjust the hostname when
  n8n runs in a different container. No schedule is activated by importing it.
- Prometheus/Grafana: configure the bearer token file on the scraper, change the
  target address if necessary, and import the dashboard against that datasource.
- Splunk/other SIEM: generate an allowlisted JSONL snapshot for a local collector:

```bash
DARKMOON_DATA_DIR="$PWD/darkmoon-settings" PYTHONPATH=mcp python3 -m community.integrations \
  --url http://127.0.0.1:8780 --output /path/to/darkmoon-findings.jsonl
```

The exporter overwrites a snapshot; configure your collector to deduplicate by
finding id/status. It does not send messages or events to an external service.
These community routes are not an implementation of the proprietary Pro API.

## Cloud deployment preparation

The new provisioner supports AWS CLI, gcloud, Azure CLI and OVH's OpenStack CLI.
It creates a reviewable plan by default; only `--execute` invokes the cloud CLI.
It never pushes source or uploads the bundle. Ubuntu 24.04 amd64 with cloud-init
is the supported base for these templates.

```bash
PYTHONPATH=mcp python3 -m community.deploy bundle --output /tmp/darkmoon-source.tar.gz
# Host this reviewed archive at an HTTPS URL yourself. Keep its printed SHA-256.
# Fill a provider example from deploy/community/ with your existing resources.
PYTHONPATH=mcp python3 -m community.deploy plan --provider aws \
  --config /path/to/aws.json --source-url https://your-host/darkmoon-source.tar.gz \
  --sha256 YOUR_ARCHIVE_SHA256 --output-dir deploy-output
```

The bundle includes current source without `.git`, common credential files,
runtime data, images and caches. Review your archive for project-specific secrets
before hosting it; filename exclusions are not a universal secret scanner.

Cloud-init verifies the archive checksum, installs Docker/Compose and the Python
dashboard dependencies, and starts a systemd service bound to **127.0.0.1:8780**.
Use an SSH tunnel; it does not open the dashboard to the internet:

```bash
ssh -L 8780:127.0.0.1:8780 ubuntu@YOUR_VM
```

On the VM, configure the LLM and build the existing agent stack under the service
account with `sudo -u darkmoon -H bash -c 'cd /opt/darkmoon && ./install.sh'`.
The source bootstrap does not embed your LLM key in cloud user-data. This is
provisioning plus dashboard bootstrap, not an unattended, fully configured
pentest appliance. No cloud VM was created during development of this branch.

Provider command references:
[AWS run-instances](https://docs.aws.amazon.com/cli/latest/reference/ec2/run-instances.html),
[GCE cloud-init metadata](https://docs.cloud-init.io/en/latest/reference/datasources/gce.html),
[Azure custom data](https://learn.microsoft.com/azure/virtual-machines/linux/tutorial-automate-vm-deployment),
[OpenStack server create](https://docs.openstack.org/python-openstackclient/latest/cli/command-objects/server.html).

## Verify

```bash
PYTHONPATH=mcp python3 -m unittest discover -s tests/community -v
PYTHONPATH=mcp python3 -m pytest -q mcp/tests/test_privacy.py
node --check mcp/community/static/app.js
bash -n community.sh
# Optional: Playwright + installed Chromium, using disposable offline fixtures:
node tests/community/browser_acceptance.cjs
```

Set `CHROMIUM_EXECUTABLE` if Chromium is not in Playwright's cache, and
`DARKMOON_SCREENSHOTS` to choose the acceptance screenshot directory. No fixture
test calls a model, runs an actual assessment, provisions a cloud, pushes Git or
opens a PR. Real Docker/headset/cloud/provider integration tests remain separate
environment-dependent checks.
