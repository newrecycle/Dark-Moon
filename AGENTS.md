# Working in this repository

Read [the development guide](docs/development.md), then the machine-readable
[acceptance task map](docs/handoff/api-task-progress.json). Dated reports describe
their own revisions; they are not current missing-feature lists.

- Backend/API: `mcp/community/`; normal data producers: `mcp/api/`.
- Browser implementation: `mcp/community/static/`; consumers: `integrations/upstream/`.
- Regression tests: `mcp/tests/`, `tests/community/`; live capture tools:
  `tools/acceptance/`. Use existing native fixtures instead of copying pipelines.
- Install development dependencies with `python3 tools/acceptance/bootstrap.py python`.
  Run `PYTHONPATH=mcp .venv/bin/python -m pytest mcp/tests tests/community -q`.
  Relevant native/browser gates are documented in the development guide.
- Preserve authentication/revocation, evidence grants, target scope, TLS checks,
  model review thresholds and real probe/publication gates. A route/status match
  or synthetic fixture is not full reference acceptance.
- Keep all capture output, private inputs, credentials and model responses outside
  Git. Use a new private output directory per run. Do not fabricate missing
  historical evidence, inject successful verdicts, or overwrite failed results.
- Model acceptance is opt-in, never part of normal unit tests or default capture.
  Use explicitly configured production endpoints; record missing prerequisites
  as unavailable. Never infer a model configuration from the coding agent.
- Run `python3 tools/acceptance/audit.py` after staging changes. Exact duplicate
  fixtures/assets/licenses often serve independent package paths: check consumers
  before removing them. Keep each refactor within its task-map scope.
- Before pushing, inspect the current branch/upstream and remote head. A restored
  workspace may use `work` while `origin/pro` is the intended target. Never force
  push or silently overwrite concurrent remote work.
