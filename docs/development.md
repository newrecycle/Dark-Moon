# Start here: development and acceptance

This fork's independently implemented workspace lives in `mcp/community/`.
Read [the current task map](handoff/api-task-progress.json) for open acceptance
and bounded refactor tasks. Implementation, offline regression, owned native
workflow acceptance and reference equivalence are separate evidence levels.
Historical dated reports keep their original claims and limitations.

## Fresh checkout

Use Python 3.12 (3.11 also runs the backend gate), Git and Node 24. Docker and
OpenSSL are needed only for native gates; a model endpoint is optional.

```sh
git clone --branch pro https://github.com/newrecycle/Dark-Moon.git
cd Dark-Moon
python3 tools/acceptance/bootstrap.py python
PYTHONPATH=mcp .venv/bin/python -m pytest mcp/tests tests/community -q
python3 tools/acceptance/audit.py
```

`requirements-dev.txt` is shared by setup and backend CI. It includes the two
production requirement files without duplicating their package declarations.
The bootstrap preserves proxy/CA environment configuration; network access and
package availability remain prerequisites. Do not disable TLS to install tools.

For SDK/integration work, install locked packages with
`python3 tools/acceptance/bootstrap.py node`. This can be large and runs package
lifecycle scripts. Build/test only the integration you change, following its
README. Browser acceptance uses the Node Playwright package: follow
`.github/workflows/community-browser.yml` for its isolated Node install and
`CODEX_PRIMARY_RUNTIME_NODE_MODULES` setting. The optional `bootstrap.py browser`
installs Python Playwright and Chromium for Python/manual browser inspection;
it does not install the Node package required by the existing `.cjs` harnesses.

## Repository map

| Path | Responsibility |
|---|---|
| `mcp/community/api.py`, `server.py`, `service.py` | API dispatch, HTTP/auth boundaries, application services |
| `mcp/api/live_push.py`, `json_storage.py` | Normal campaign/finding producers and persistent data |
| `mcp/community/remediation.py`, `publish.py` | Scoped proposals, real probes and explicit publication |
| `mcp/community/static/` | Browser workspace |
| `integrations/upstream/` | SDK and independent packaged consumers |
| `tests/community/`, `mcp/tests/` | Regression and explicitly invoked native/browser harnesses |
| `tools/acceptance/` | Focused fresh captures, setup and deterministic hygiene audit |
| `docs/handoff/api-task-progress.json` | Current queue, checkpoints and bounded follow-ups |

## Validation levels

1. Backend gate: the pytest command above. Tests use synthetic fixtures; this
   makes no configured-model requests and is not reference runtime acceptance.
2. Pure browser logic: run the Node scripts listed in `.github/workflows/tests.yml`.
3. Browser interactions: use `.github/workflows/community-browser.yml` and
   `tests/community/browser_acceptance.cjs`; retain owned screenshots privately.
4. Native operator edits: build `tools/lab/Dockerfile` as `darkmoon-ui-lab`, then
   run `capture.py --only native-publication --out /private/new-native-run`.
   This reuses production remediation, real offline Docker probes, real disposable
   HTTPS Gitea publication and actual fork HTTP projection. No model calls.
5. Configured-model acceptance: explicitly run `--only configured-model` after
   configuring the variables in [the model runbook](handoff/remediation-model-forge-acceptance.md).
   Typically three requests (generation, review, unfixed negative review); up to
   five with the default second attempt after failed probes. Review rejection is
   never changed into approval. Do not run this automatically per commit.
6. Reference capture: see [the runnable capture guide](../tools/acceptance/README.md).
   Only requested open gaps are selected; existing successful evidence is not
   replayed by default. A bounded SSE observation is not a completed stream.

Exit 3 means unavailable, 1 means failed, 0 means the selected checks completed.
None means global parity. A missing model, license, device or successful engine
run remains an explicit blocker. The agent editing this repository is not the
application's configured generation/review endpoint.

## Current handoff and history

The code checkpoint `359850b` includes recurring interval preservation, latest-two
campaign-total trends, non-root source staging, wrong-password401, and real
publication metadata/probe kinds. These were pushed after the older dated
checkpoints. The task map records the follow-up and fresh tooling verification.
Some earlier private evidence is unavailable in a restored workspace: do not
claim its raw captures/hashes were recovered or that an uninspected suite passed.
Fresh captures are new observations with source/provenance manifests.

For the private handoff archive, use its separate setup guide and supplied private
inputs. They are intentionally absent from this repository. Never copy the ZIP,
installer, runtime credentials, raw captures or proprietary assets into Git.

## Latest tooling verification — 1 November 2026

Backend gate:570 tests and382 subtests passed. Capture tooling:17 focused tests
passed after final reporting/deduplication changes. All seven pure-browser
checks and production JavaScript syntax checks passed. Actual paired scheduler,
populated history and bounded event/SSE captures completed; actual Docker/Gitea
publication and HTTP projection passed. These are scoped observations, not full
reference acceptance. The configured provider model-list request was blocked by
the environment proxy403 before inference. Enable authorized provider access
before the first model acceptance; do not retry on every commit.

The audit retained24 exact duplicate groups used by independent package paths,
licenses or fixture formats. Shared capture manifest and synthetic cohort logic
are centralized, and this guide/task map replace conflicting current-status
pointers without deleting historical reports.
