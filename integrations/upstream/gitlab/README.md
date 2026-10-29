# Darkmoon — GitLab CI/CD Component

> **📦 Marketplace status:** Live on the [GitLab CI/CD Catalog](https://gitlab.com/explore/catalog/Dark-Moon-X/darkmoon-scan).


## ⭐ Darkmoon ecosystem

Darkmoon is open-source — **a star really helps us grow.** [![Star the Darkmoon core](https://img.shields.io/github/stars/ASCIT31/Dark-Moon?style=social&label=Star%20Darkmoon)](https://github.com/ASCIT31/Dark-Moon)

🌐 **Website:** [dark-moon.org](https://dark-moon.org) · 📚 **Docs:** [docs.dark-moon.org](https://docs.dark-moon.org) · ⭐ **Star the core:** [github.com/ASCIT31/Dark-Moon](https://github.com/ASCIT31/Dark-Moon)

**Install the integrations, right where you work:**

| Platform | Get it |
|---|---|
| VS Code | [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Darkmoon.darkmoon-vscode) |
| GitHub Actions | [GitHub Marketplace](https://github.com/marketplace/actions/darkmoon-pentest) |
| GitLab CI/CD | [CI/CD Catalog](https://gitlab.com/explore/catalog/Dark-Moon-X/darkmoon-scan) |
| Jenkins | [Download the .hpi](https://github.com/ASCIT31/darkmoon-jenkins/releases) |
| Client & CLI | [npm: @darkmoon_ai/client](https://www.npmjs.com/package/@darkmoon_ai/client) |


## Screenshots

Produced by running the **real component job** on a genuine `gitlab-runner`
(historical Runner 15.11 fixture flow; retired in favor of the modern registered-Runner gate) against the synthetic **Demo Shop** campaign
(`demo-shop.local`). The reports are the actual `gl-code-quality-report.json` /
`gl-sast-report.json` artifacts (schema-validated in CI).

**CI job log** — real `gitlab-runner 15.11.1` output: the CLI launches → waits →
completes, the mapper emits both reports, and the findings gate fails the job
(exit 2):

![GitLab CI job log](https://raw.githubusercontent.com/ASCIT31/darkmoon-gitlab/master/docs/screenshots/gitlab-job-log.png)

**Code Quality** — a local render of the **real** `gl-code-quality-report.json`
artifact, shown the way it populates the merge-request **Code Quality** widget
and the pipeline **Code Quality** tab (the live MR widget needs a GitLab
instance):

![Code Quality report](https://raw.githubusercontent.com/ASCIT31/darkmoon-gitlab/master/docs/screenshots/gitlab-code-quality.png)

> The component wraps the portable `darkmoon-ci` CLI. It does not embed the
> scanning engine. See [`CONTRACT.md`](CONTRACT.md) for the exact CLI + JSON
> interface it consumes.

## Quick start

```yaml
include:
  - component: $CI_SERVER_FQDN/<your-namespace>/darkmoon/scan@1.0.0
    inputs:
      target: "https://staging.example.com"
      fail-on: high        # fail the job on a High+ finding
```

Replace `<your-namespace>` with the group/subgroup that hosts this project on
your GitLab instance (the component path is `<namespace>/darkmoon/scan`, i.e.
`<project-path>/<component-name>`). Pin `@<version>` to a released tag.

### Secrets

Set these as **masked + protected** CI/CD variables (Settings → CI/CD →
Variables). They are read from the environment; the component never places them
on the command line and never prints them.

| Mode | Required variables |
|------|--------------------|
| OSS  | `DARKMOON_LICENSE_KEY`, `OPENROUTER_PROVIDER`, `OPENCODE_MODEL`, `OPENROUTER_API_KEY` |
| Pro  | `DARKMOON_PRO_TOKEN` (or `DARKMOON_PRO_USER` + `DARKMOON_PRO_PASS`) + the `pro-url` input (or `DARKMOON_PRO_URL`) |

### Non-blocking (report but don't fail the pipeline)

```yaml
include:
  - component: $CI_SERVER_FQDN/<your-namespace>/darkmoon/scan@1.0.0
    inputs:
      target: "https://staging.example.com"
      fail-on: "critical,high"
      allow_failure_exit_codes: [2]   # tolerate the findings gate; real errors still fail
```

The findings gate is CLI exit code **2**. The default `allow_failure_exit_codes`
(`[250]`, a code the CLI never emits) makes the job **block**. Listing `2` makes
the gate non-blocking while genuine tool/usage errors (exit `1`) still fail the
pipeline. **GitLab does not ingest SAST findings from a failed job, including
a nonblocking (allowed-to-fail) job.** To check GitLab security ingestion for
nonempty findings, use `fail-on: ""` (mapped to the patched CLI's explicit
`none` policy), then perform a separate blocking gate in another job if needed.
All `artifacts:reports` files are still uploaded when a job fails, but an
uploaded SAST artifact is not proof of ingested findings.

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `target` | *(required)* | Target URL/host. `focus`/`severity` are folded in as `FOCUS=`/`SEVERITY=`. |
| `mode` | `auto` | `auto` (Pro if URL/token present, else OSS), `oss`, or `pro`. |
| `pro-url` | `""` | Darkmoon Pro REST API base URL (`--pro-url`; env `DARKMOON_PRO_URL`). |
| `focus` | `""` | Comma-separated attack focus, folded into the target as `FOCUS=`. |
| `severity` | `""` | Max severity cap, folded into the target as `SEVERITY=`. |
| `fail-on` | `critical,high` | Comma-separated **set** of severities that fail the build. Empty = never fail on findings. |
| `timeout` | `""` | Hard timeout (seconds) for the run (`--timeout`). |
| `oss-data-dir` | `""` | OSS data dir with `campaigns/` + `vulnerabilities/` (`--oss-data-dir`). |
| `oss-reports-dir` | `""` | OSS reports dir (`--oss-reports-dir`). |
| `oss-script` | `""` | Path to `darkmoon.sh` (`--oss-script`). |
| `sast-report` | `true` | Also emit `gl-sast-report.json`. |
| `expose-full-report` | `false` | Attach the full (redacted) report + normalized findings JSON as internal artifacts. |
| `artifacts-expire-in` | `1 week` | Artifact expiry. |
| `allow_failure_exit_codes` | `[250]` | Exit codes tolerated by the job. `[2]` = non-blocking gate. |
| `bootstrap-url` | `""` | If `darkmoon-ci` is absent, download & run this installer first. |
| `image` | `node:20-slim` | Image for docker-executor runners (shell runners ignore it). |
| `stage` | `test` | Stage for the job (must exist in the pipeline). |
| `job-name` | `darkmoon_scan` | Name of the generated job. |

## Outputs

- **Code Quality** — `gl-code-quality-report.json`
  (`artifacts:reports:codequality`). One entry per finding, mapped to the
  CodeClimate fields GitLab requires (`description`, `check_name`, `fingerprint`,
  `severity`, `location.path`, `location.lines.begin`).
- **SAST** — `gl-sast-report.json` (`artifacts:reports:sast`), conforming to the
  GitLab `security-report-schemas` SAST schema (validated in CI against the live
  schema; see `test/`). The MR SAST widget requires **Ultimate**.
- **Internal artifacts** (only when `expose-full-report: true`) — the full
  markdown report and native findings JSON, under `output-dir/`.

### What appears where (privacy)

Only a **redaction-safe summary** of each finding is placed on shared surfaces
(the MR/pipeline widgets). Full detail and raw evidence stay in the internal
report artifact, which is off by default. See `CONTRACT.md` §4.

## Runner requirements

`darkmoon-ci` is a Node CLI (Node ≥ 18); `python3` (≥ 3.8) is used for the report
mapping. The job image must provide **both**. `node:20-slim` (the default) ships
Node but **not** python3 — add it (`apt-get install -y python3`) or use a custom
image that bundles `darkmoon-ci` + `python3`. The job fails fast with a clear
message if either is missing.

- **Pro mode**: a runner with the CLI + `python3` and network access to the Pro
  REST API.
- **OSS mode**: `darkmoon-ci` drives the local Darkmoon Docker engine, so use a
  runner with Docker access (a **shell** executor on a Docker host, or
  Docker-in-Docker), and point `oss-data-dir`/`oss-reports-dir`/`oss-script` at
  the engine's mounted data.

> **OSS concurrency (important).** OSS runs share one on-disk data directory and
> the client correlates the new campaign by snapshot-diff + session-id + mtime.
> Run **one Darkmoon container / compose-project per CI job** (do not fan out
> parallel OSS jobs against the same data dir) or campaigns can be mis-attributed.
> The client emits a collision warning when it detects this; Pro mode is not
> affected. See `CONTRACT.md` §3.

### Installing the CLI on the runner

```bash
# For this fork's acceptance, use the patched CLI in this checkout:
cd integrations/upstream/client
npm ci && npm run build
# Point a disposable runner PATH wrapper at dist/cli/darkmoon-ci.cjs.
# Do not silently substitute an unverified upstream npm package.
```

## Severity mapping

| Darkmoon | Code Quality | SAST |
|----------|--------------|------|
| critical | `blocker`  | `Critical` |
| high     | `critical` | `High` |
| medium   | `major`    | `Medium` |
| low      | `minor`    | `Low` |
| info     | `info`     | `Info` |

## Development & tests

```bash
python3 build/render_template.py      # regenerate templates/scan/template.yml from src/
python3 test/unit_tests.py            # redaction (§4) + degradation (§2.4) + severity maps
python3 test/check_schema_pin.py      # guard against SAST schema drift
python3 test/job_acceptance.py        # generated job error/identity matrix
# CI builds the bundled CLI and runs test/server_acceptance.py with a disposable CE server.
```

`templates/scan/template.yml` is generated: it embeds `src/darkmoon_gitlab_report.py`
(base64) so the component is self-contained YAML. Edit `src/` and the `.yml.in`
skeleton, then re-render.

## Publishing to the CI/CD Catalog (human-only)

1. Make this a **public** project on your GitLab instance and set a project
   description.
2. Enable it as a catalog project (Settings → General → Visibility → *CI/CD
   Catalog project*).
3. Tag a **semantic version** and create a release with the `release` keyword
   (see this repo's own `.gitlab-ci.yml`). The pipeline for the tag publishes the
   component version to the catalog.

## License

MIT — see [`LICENSE`](LICENSE).

## 🎥 Video tutorial

[![Watch the Darkmoon + GitLab CI/CD tutorial on YouTube](https://img.youtube.com/vi/ui7NHD41cMM/maxresdefault.jpg)](https://youtu.be/ui7NHD41cMM)

▶ **[Watch the full Darkmoon + GitLab CI/CD tutorial on YouTube](https://youtu.be/ui7NHD41cMM)** — real setup, end to end.

## Darkmoon ecosystem

Darkmoon is an open-source, AI-powered penetration testing platform. It runs a full autonomous assessment and this integration brings the results into your GitLab CI/CD workflow.

- ⭐ **Flagship (star it):** https://github.com/ASCIT31/Dark-Moon
- 📚 **Docs:** https://docs.dark-moon.org
- 🌐 **Website:** https://dark-moon.org
- 🔗 **Related integrations:** [GitHub Actions](https://github.com/ASCIT31/darkmoon-action) · [Jenkins](https://github.com/ASCIT31/darkmoon-jenkins) 

## Dark-Moon fork corrections

Findings-read, malformed-input and mapping failures produce exit 1. Invalid
input produces failure-status SAST diagnostics, rather than a successful empty
scan. Only exit 2 represents a findings gate and can be made nonblocking with
`allow_failure_exit_codes: [2]`. Free-form remediation is withheld from shared
reports alongside evidence and descriptions. Explicit valid empty arrays remain
valid. When SAST output is disabled, no synthetic successful SAST artifact is
created. See `CONTRACT.md` and the generated job-script acceptance test at
`../../../tests/community/gitlab_contract.py`. That test executes the shipped
script with owned protocol fixtures; it does not establish GitLab server/runner
or artifact-ingestion compatibility.

## Generated job, runner and server-ingestion acceptance (2026-10-28)

The integration ships a self-contained generated component. The authoritative
sources are `templates/scan/template.yml.in` and
`src/darkmoon_gitlab_report.py`; `build/render_template.py` regenerates
`templates/scan/template.yml`. The GitHub workflow
`.github/workflows/gitlab-integration-verification.yml` checks a byte-for-byte
re-render, the pinned SAST schema, the mapper, and the actual generated job script
under disposable CLI-protocol fixtures. These are **schema/OS shell checks**,
not proof of GitLab server ingestion.

The generated job now checks the second findings read against the actual CLI
`run` verdict's exact campaign identity, total findings count, per-severity
offending counts, fail policy and exit code. Any disagreement becomes exit 1,
with failure-state diagnostic JSON rather than a clean empty assessment.
Finding titles containing URLs, endpoint userinfo/query/fragment data and
unexpected identifier metadata are withheld from shared reports. Missing CLI
with Python available also emits failure-state reports. Scanner failures remain
exit 1; only a genuine findings gate is exit 2.

The native runner gate uses the **fork-patched** client at
`integrations/upstream/client` (version `0.2.1-darkmoon.1`) and an isolated
GitLab Runner **15.11.1**. This is a **legacy compatibility** check:
`gitlab-runner exec shell` is removed in supported modern runner versions;
local `exec` does not exercise server registration, artifact upload or report
ingestion. No runner is registered with a public service.

**Server ingestion requires a separate owned disposable GitLab instance,
a registered runner scoped to that test project, and a GitLab Ultimate
entitlement/feature availability to inspect project vulnerability findings.**
For an actual successful nonempty scan, run the generated component with
`fail-on: ""` on the owned test project and record its actual job/pipeline IDs.
`test/verify_ingestion.py` is an opt-in read-only localhost-only API verifier:
it confirms the job succeeded, GitLab stored the SAST report and the server's
pipeline-scoped vulnerability findings contain a Darkmoon SAST result. It must
never be pointed at an unrelated GitLab instance. A 403/404 or absent finding
is **not** treated as an empty success.

Run on the disposable GitLab host only:

```bash
export GITLAB_ACCEPTANCE_OWNED=yes
export GITLAB_ACCEPTANCE_URL=http://127.0.0.1:8929
export GITLAB_ACCEPTANCE_PROJECT_ID=<test-project-id>
export GITLAB_ACCEPTANCE_JOB_ID=<successful-job-id>
export GITLAB_ACCEPTANCE_PIPELINE_ID=<pipeline-id>
export GITLAB_ACCEPTANCE_TOKEN=<temporary-read-only-token>
python3 integrations/upstream/gitlab/test/verify_ingestion.py
```

Use the version's supported GitLab security-report ingestion contract and
verify the scanned project permits the SAST report type. The pinned JSON schema
alone cannot establish successful ingestion. Do not confuse an allowed-to-fail
gate, report upload, or runner-only execution with security dashboard findings.

See [the observed 28 October acceptance record](ACCEPTANCE-2026-10-28.md) for native Runner and schema results, plus the separate unverified GitLab server-ingestion boundary.
