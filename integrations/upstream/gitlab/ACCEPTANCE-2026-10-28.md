# GitLab generated component acceptance — 28 October 2026

Historical record: the Runner 15.11 harness and its helper scripts were retired
on 29 October after real CE/registered-Runner acceptance passed. Commands below
describe that earlier tree; current CI uses `test/server_acceptance.py`.

Scope: fork `newrecycle/Dark-Moon`, isolated implementation branch
`agent/gitlab-native-acceptance-20261028`. This record distinguishes
schema validity, actual historical Runner execution and **unperformed**
GitLab server ingestion. The repository does not ship a GitLab server,
a registered runner or a GitLab Ultimate entitlement.

## Observed hosted verification

GitHub Actions: https://github.com/newrecycle/Dark-Moon/actions/runs/40777630435

Both required jobs **passed** on isolated branch commit
`50b0a8a05432b26b89f87791c0d1f44759c3a6fa`:

- `generated-and-schema`: the regenerated YAML matched the shipped
  `templates/scan/template.yml` byte-for-byte; `check_schema_pin.py`
  pinned the mapper and vendored SAST schema at **15.2.5**;
  `unit_tests.py` reported **37 passed, 0 failed**; and
  `job_acceptance.py` exercised **21 generated-job cases** including
  authenticated launch failure, timeout, failed/stopped run, missing/malformed
  findings, wrong campaign ID, wrong counts/offending severity, inconsistent
  verdict/exit code, valid-empty, nonempty, and disabled SAST. The existing
  `tests/community/gitlab_contract.py` also completed successfully.
- `legacy-native-runner`: installed **GitLab Runner 15.11.1**, built the
  checkout's patched **`@darkmoon_ai/client@0.2.1-darkmoon.1`** with
  `npm ci` and `npm run build`, and executed the flattened **actual
  generated job script** via `gitlab-runner exec shell` with disposable,
  local OSS fixture data. `run_runner_e2e.sh` reported
  **32 passed, 0 failed** across blocking gate, nonblocking gate, passing
  nonempty and genuinely empty campaigns. Nonempty produced five Code Quality
  entries and five SAST vulnerabilities; valid empty produced zero for both.
  Generated SAST JSON passed the vendored schema check. No configured fixture
  license string was logged, and sensitive full reports were withheld.

The runner's local `exec shell` returned nonzero on the exit-2 gate even
when `allow_failure.exit_codes=[2]`: local execution does **not** evaluate
GitLab's server-side allowed-failure pipeline status. That is not a test
failure or proof of server semantics. No real assessment was run.

## Exact reproducible checks

From repository root after installing Python 3.12, PyYAML 6.0.3,
jsonschema 4.26.0, Node 20 and a disposable Runner 15.11.1 binary at
`integrations/upstream/gitlab/test/vendor/gitlab-runner`:

```bash
cd integrations/upstream/gitlab
cp templates/scan/template.yml /tmp/darkmoon-gitlab-shipped.yml
python3 build/render_template.py
cmp templates/scan/template.yml /tmp/darkmoon-gitlab-shipped.yml
python3 test/check_schema_pin.py
python3 test/unit_tests.py
python3 test/job_acceptance.py
cd ../../..
python3 tests/community/gitlab_contract.py
npm --prefix integrations/upstream/client ci
npm --prefix integrations/upstream/client run build
bash integrations/upstream/gitlab/test/run_runner_e2e.sh
```

The hosted workflow pins the legacy Runner version but does not publish,
register or contact any third-party GitLab runner. In the native job, tests
execute locally under the Runner shell executor; the generated YAML contains
`artifacts: when: always` and `artifacts: reports: sast/codequality`,
but a local runner cannot prove artifact **upload**.

## Boundaries and next host acceptance

**Schema:** PASS (15.2.5, including genuinely empty SAST).

**Historical Runner 15.11.1:** PASS (32 focused assertions, real patched
CLI + generated script, local fixture only). `gitlab-runner exec` is removed
from modern supported Runner releases; a modern registered-runner acceptance
still needs an **owned disposable GitLab server**.

**Artifact upload:** NOT VERIFIED. Requires a real GitLab pipeline/job and an
observed artifact response from its API. The generated job requests
`artifacts:when:always` and publishes both report types, but declarations
are not server observations.

**Server security ingestion:** NOT VERIFIED. Requires an owned disposable
supported GitLab instance with the Ultimate security feature available,
a project-scoped registered Runner and a **successful nonempty SAST-producing
job**. GitLab documents that failed jobs (including allowed-to-fail jobs)
upload report artifacts but do **not** ingest their security findings.
Use `fail-on: ""` for the nonblocking *successful* ingestion-acceptance run,
then test policy failure separately. Read-only
`test/verify_ingestion.py` requires explicit owned-host permission,
a localhost-bound instance, and a temporary read-only API token; it checks
job/pipeline identity, actual SAST artifact availability, and pipeline-scoped
Darkmoon vulnerability findings. No GitLab host/entitlement is available in
this execution environment, so it was **not executed**.

**Dependencies:** The hosted `npm ci` reported **8 audit advisories** for
the existing patched client dependency graph (3 moderate, 3 high,
2 critical). This review did not modify shared dependency locks.

No public catalog publication, runner registration with an unrelated
instance, external webhook, real assessment, deployment, or proprietary
vendor binary was performed.

## Modern-server continuation — 29 October

A new `modern-registered-runner` gate now creates its own loopback-bound
GitLab CE 19.5.1 container and registers Runner 19.5.0 using the supported
runner-authentication-token workflow. The real server interpolates the shipped
component; the shell Runner executes the standalone built patched CLI on
synthetic local data. Five independent pipelines cover success, empty results,
blocking gate, allowed exit 2 and a read error that must still fail the pipeline.
Job, pipeline, runner and commit identities, actual report download, private
artifact absence and trace secrecy are checked. The container, runner and
project are disposable; no existing GitLab instance is contacted.

This gate verifies artifact upload and pipeline semantics once observed passing;
it does not activate a paid trial or prove Ultimate vulnerability ingestion.
`verify_ingestion.py` now downloads `artifacts/gl-sast-report.json`, validates its
Darkmoon SAST identity and requires nonempty successful output and matching
scanner finding counts. The previous `artifacts?file_type=sast` archive request
was not sufficient proof of SAST JSON storage.
