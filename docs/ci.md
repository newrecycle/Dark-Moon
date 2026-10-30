# CI ownership after cleanup — 29 October 2026

The repository has 15 workflows, reduced from 27. The cleanup removes repeated
execution and retired harnesses; it retains behavior, authorization, privacy,
crash recovery, real browser and supported native-host coverage.

| Workflow | Owns |
|---|---|
| tests.yml | Full MCP/community Python suite, dependency policy, campaign binding, pure graph/finding logic and dashboard JS syntax |
| community-browser.yml | Chromium UI, headless flags and the dedicated path revision/expiry/conflict component acceptance, sharing one browser install |
| community-sdk.yml | Built SDK/CLI, consumer archive provenance, Action, authenticated SDK-to-fork HTTP contracts |
| community-integrations.yml | Real isolated n8n host, package tests, signed receiver and replay contracts |
| community-runtime.yml | Actual image/provider API, owned-loopback analysis, real SQLi/Docker probes and disposable HTTPS Gitea publication; explicit manual model-positive gate |
| community-vscode.yml | Packaged native extension host |
| gitlab-integration-verification.yml | Generated template, mapper/schema/error matrix and modern CE/registered-Runner acceptance |
| grafana-integration-verification.yml | Go backend and frontend package checks |
| grafana-native-host.yml | Real Grafana 10.4.19/13.1 API and all-eight-view browser matrix |
| jenkins-native-verification.yml | Packaged HPI, bundled CLI, controller and remote agent |
| splunk-verification.yml | Linux/Windows offline contracts plus native prerequisites/unavailable-host checks |
| splunk-native-host.yml | Operator-supplied native Splunk host; manual only |
| dependency-validation.yml | Dependabot-specific ecosystem builds/resolution and read-only dependency change validation |
| integration-inventory.yml | Distribution/provenance and active support inventory |
| build-and-push.yml | Existing product image build/publication; unchanged |

`Tests / pytest regression gate` retains the existing job name and runs the full
Python suite once per push/PR, replacing repeated focused/full-suite jobs for
campaign isolation, credentials, findings/history, scheduling, evidence, run
logs, webhooks and dependency policy. Tests stay in their domain-specific files
for local focused use. The old webhook receiver job already ran inside the
retained offline n8n host image. The dedicated path browser test moved intact.

Also removed:

- Duplicate Splunk offline workflow; its unique native preflight checks moved to
  the remaining Linux job. Windows checks and the seven subprocess alert guards
  remain.
- Runner 15.11 `exec shell` CI job, script and three exclusive fixture helpers.
  The modern real-server/registered-Runner gate replaces that obsolete runtime;
  generated error/identity tests and pinned schemas remain.
- Obsolete `sdk_contract.cjs`, which expected unrestricted report content and a
  separate legacy package install. Unique capabilities, evidence metadata,
  analytics, webhook CRUD, retest and launch/SSE scenarios moved to the current
  SDK HTTP contract; archive/Action checks remain with their existing owners.
- A benchmark of the retired heap through a fake Store. Filter/tie/empty-page
  cases now query the real SQLite Store, including the paging ceiling. Actual
  indexed decoding/memory/crash tests remain in `test_control_storage.py`.
- The one-off public video-frame acquisition workflow. Its manual acquisition
  tool and existing reference artifacts remain available.

SDK and GitLab no longer both run the same mapper matrix. GitLab now also
triggers for shared client changes. Superseded backend/browser/GitLab runs are
cancelled per ref. Dated validation reports remain historical evidence; active
commands and native acceptance guidance point to retained harnesses.

Historical workflow-cleanup validation: 495 Python tests and 268 subtests; current SDK HTTP contract
(including the transferred scenarios); 78 Splunk tests and native preflight exit
3; 37 GitLab mapper checks and 21 generated-job scenarios; campaign/graph/finding
Node checks; all retained YAML and embedded Bash blocks parsed; actionlint 1.7.12
passed with only the known custom runner labels allowed. No product runtime code
changed. Native/browser execution remains in the retained hosted workflows.
