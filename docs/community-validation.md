# Feature reconstruction and master rebase validation — 26 October 2026

Branch: `restore/community-features-20261026`.
Base: upstream master **`b52d4d73c325427e4d2fa5f3cbf87dd889cc6300`**, verified
against the remote master ref on 26 October 2026.

Only the feature commit was replayed onto this base; the earlier fork runtime,
configuration, toolbox and build changes were discarded. The prior result is
preserved locally as `backup/community-features-before-master-20261026`.
The private Pro application was not imported: the user selected independent
reconstruction. Actual public integration imports are pinned with MIT licenses
in [SOURCES.json](../integrations/upstream/SOURCES.json). See the
[coverage matrix](pro-feature-matrix.md) for implementation boundaries.

## Automated and visual checks

| Check | Result |
|---|---|
| Community unit/integration suite | **85 passed** with `unittest`. |
| Current upstream MCP suite | **117 passed** with `pytest`; no upstream test changes. |
| Imported official client | Build passed; **75 tests passed**. |
| Imported n8n nodes | Build passed; **25 checks passed**. |
| Imported GitHub Action | Typecheck, build and **27 tests passed**. |
| Imported GitLab report mapper | **15 checks passed**, including safe-field reports against the pinned schema. |
| Imported Splunk | **7 offline guard checks** and **6 local mock-HTTP checks passed**; no real Splunk server. |
| Imported VS Code extension | Typecheck, extension build, test compilation and **8 Node data-layer tests passed**. Electron extension-host tests not run. |
| Actual SDK against reconstructed HTTP service | JWT login, capability discovery, campaign/finding/report/evidence metadata, timeseries, webhooks, retest, queue and real SSE progress passed. The older Action/VS Code SDK also passed detect/campaign/finding/report checks. Assessment launcher and external delivery were fake/disabled. |
| Adapted n8n webhook receiver | Real compiled receiver accepted signed v2 delivery, suppressed replay, and rejected stale timestamps and forged event ids. |
| Chromium acceptance | Passed across all 12 dashboard routes, desktop 1440×1000 and mobile 390×844, without page errors. |
| PDF cryptography | Real AES-256 encrypted PDF decrypted successfully; embedded CMS signature was intact, valid and trusted under the explicitly trusted test certificate, with network fetching disabled. |
| PDF layout | Long-evidence PDF rendered with Poppler and inspected; embedded Vera fonts; no clipping or overlap. |
| Static checks | Python compilation, JavaScript parsing, shell parsing and first-party patch whitespace passed. Upstream Markdown line breaks/trailing whitespace and config EOFs were preserved in imported files. |
| Feature-only scope | Existing runtime/configuration paths unchanged; only `.gitignore`, README and the shared JSON storage adapter modify files already on master. |
| Import provenance | 513 selected upstream files from nine repositories checked against pinned Git blobs; only the documented n8n receiver adaptation differs. Build caches, installed dependencies and locally generated products excluded. The Action bundle is rebuilt from imported source; upstream SDK tarballs and the Gradle wrapper are preserved. |
| Clean-master patch | Complete binary-capable diff checked for application to a clean archive of the pinned master. |

The community suite exercises authorization and role restrictions, JWT revocation,
password hashing/rotation, signed OIDC claims with mocked IdP transport, encrypted
credentials, launch idempotency, network scope restrictions, secret-free argv,
concurrent storage and sealed vault state, integrity/audit tampering, queue
cancellation/recovery/deadlines, durable schedules, retest dispositions, signing,
model judge rejection, bounded remediation retries, isolated source worktrees,
metadata-only integration feeds and publication/deployment gates.

The browser flow covers filtering and script-like evidence, the 3D canvas,
project analytics, account and encrypted credential creation, diagnostics,
local remediation through a real subprocess, unchanged original source,
patch/PDF downloads, schedule lifecycle, fake campaign queue, responsive layout
and workspace locking. Screenshots were visually inspected. Fixtures are
explicit disposable test records, not production findings.

Publication uses fake Git/HTTP transports. Cloud tests inspect generated plans
and cloud-init without invoking a cloud CLI. LLM calls and Docker probe results
are mocked. HTTPS webhook delivery and image registry lookups are mocked.
A local proposal emits `remediation.updated`; `pr.opened` requires a recorded
publication. This test does not create a real PR.

## Reproduce

Install `mcp/community/requirements.txt`, current `mcp/requirements.txt`, `pytest`
and a compatible Node runtime in an isolated development environment. From the
repository root:

```bash
PYTHONPATH=mcp .venv/bin/python -m unittest discover -s tests/community -q
PYTHONPATH=mcp .venv/bin/python -m pytest -q mcp/tests
npm ci --ignore-scripts --prefix integrations/upstream/client
npm run build --prefix integrations/upstream/client
npm test --prefix integrations/upstream/client
npm ci --ignore-scripts --prefix integrations/upstream/n8n
npm run build --prefix integrations/upstream/n8n
npm test --prefix integrations/upstream/n8n
node tests/community/n8n_receiver.cjs
npm ci --ignore-scripts --prefix integrations/upstream/action
npm run all --prefix integrations/upstream/action
DARKMOON_PYTHON="$PWD/.venv/bin/python" node tests/community/sdk_contract.cjs
DARKMOON_PYTHON="$PWD/.venv/bin/python" CHROMIUM_EXECUTABLE=/path/to/chrome-headless-shell node tests/community/browser_acceptance.cjs
```

Additional import checks and the native build limits are listed in
[the import guide](../integrations/upstream/README.md). Browser acceptance loads Playwright from `CODEX_PRIMARY_RUNTIME_NODE_MODULES`
in this environment; use an equivalent Playwright installation elsewhere.

## Environment-dependent checks

- Build/run the Docker/Compose agent stack; check current image write paths under
  the optional hardened overlay, local privacy-socket credential flow, campaign
  linkage, cancellation and guarded MCP launch in the actual deployed image.
- Run reproduction/variant/regression probes with a real reviewed Docker image
  and defensive generation/judging against the configured model endpoint.
- Configure and test a real OIDC provider, TLS reverse proxy, production signing
  chain and the operator's backup/rotation/recovery procedures.
- Build the Grafana Go backend, Jenkins HPI and JetBrains plugin, and perform a live Grafana import, external n8n
  delivery, cloud provisioning or forge publication only in their environments
  and when separately authorized. Go, Maven and Docker were unavailable here; the Gradle/IDE builds were not attempted.
- Verify immersive WebXR with a compatible headset.

No real target assessment, cloud resource creation, hosted-service upload,
external webhook delivery, Git push or PR creation occurred. Both Git remote
push URLs remain disabled. The old fork-only toolbox test failures are not part
of this master-based result.
