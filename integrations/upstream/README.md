# Public integration source imports

These are MIT-licensed source imports, with original copyright/license files.
[SOURCES.json](SOURCES.json) records exact commits, exclusions and modifications.
Eight imports are unmodified; the n8n webhook receiver is adapted to require
HMAC v2, a fresh timestamp and persisted event-id replay suppression.

| Directory | Implementation | Verification here |
|---|---|---|
| `client` | Official TypeScript SDK and `darkmoon-ci` CLI | Build; 75 tests; direct HTTP contract test. |
| `action` | GitHub Action and nested reusable workflow | Typecheck, build and 27 tests; its legacy SDK also tested against our API. |
| `gitlab` | CI Catalog component and SAST/Code-Quality mapper | 15 offline mapper/schema checks. |
| `jenkins` | Pipeline plugin, SARIF adapter and Warnings-NG integration | Source/provenance checked; Maven/HPI and Jenkins host tests not run. |
| `vscode` | Campaign/finding/report views and launch/status extension | Typecheck, build and 8 Node data-layer tests; Electron host tests not run. |
| `jetbrains` | IntelliJ plugin, Kotlin client and Node bridge | Source/provenance checked; Gradle and IDE host tests not run. |
| `n8n` | Campaign/finding/retest/metric/webhook nodes and trigger | Build; 25 checks; compiled webhook signature/replay test. |
| `grafana` | Go datasource, Grafana app and dashboards | Source/provenance checked; Go build and live Grafana host not run. |
| `splunk` | Splunk app, guarded alert action and safe-field HEC forwarder | 7 offline security checks and 6 local mock-HTTP checks; live Splunk not run. |

Nothing in these directories is installed, published or activated by importing
it. Nested workflow files do not change this repository's root CI. Auxiliary CI
and promotional screenshots are omitted as recorded in the manifest. The Action's
checked-in distribution bundle is omitted; rebuild it from source. Upstream
vendored SDK tarballs and the Gradle wrapper are retained byte-for-byte.

Use each package's README for native packaging/installation. Point its Pro HTTP
backend at the reconstructed workspace URL and obtain an authenticated session
through `/api/v1/auth/login`. The server reports `edition=community` honestly;
some legacy clients issue an informational warning while using the supported
HTTP contract. A one-hour JWT must be refreshed for long-running installations.
Do not make read routes public to accommodate a client without login support.
API PR views are read-only, and these imports do not enable publication.

The imported client versions differ: `client` is `@darkmoon_ai/client` 0.2.0;
Action and VS Code pin a vendored `@darkmoon/client` 0.1.0. Both were exercised
against our service for their common read operations. Full native/live wire
compatibility beyond the tested contracts is not asserted. For Splunk HEC, use
the supplied safe-field REST/export forwarder; the reconstructed webhook service
emits Darkmoon-format signed events, not native `splunk_hec` envelopes.

Additional repeatable local checks, after installing dependencies:

```bash
npm ci --ignore-scripts --prefix integrations/upstream/action
npm run all --prefix integrations/upstream/action
npm ci --ignore-scripts --prefix integrations/upstream/vscode
npm run typecheck --prefix integrations/upstream/vscode
npm run compile --prefix integrations/upstream/vscode
npm run compile-tests --prefix integrations/upstream/vscode
integrations/upstream/vscode/node_modules/.bin/mocha integrations/upstream/vscode/out/test/node/datalayer.test.js
.venv/bin/python integrations/upstream/gitlab/test/unit_tests.py
.venv/bin/python integrations/upstream/splunk/test/test_alert_action.py
.venv/bin/python integrations/upstream/splunk/test/test_mock_launch.py
```

Core setup, feature behavior and deployment limits:
[community guide](../../docs/community.md),
[coverage matrix](../../docs/pro-feature-matrix.md),
[validation record](../../docs/community-validation.md).
