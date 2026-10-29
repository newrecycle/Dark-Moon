# Reconstructed Pro features on the independent `pro` branch

> **Updated commercial Pro static analysis:** [Audit report, native coverage, Angular inventory, test overlap and known gaps](pro-audit/README.md). This is static evidence, not a completed runtime parity test.
>
> **Actual commercial Pro image reference (2026-10-27):** [pinned package evidence](handoff/actual-pro-image-baseline-2026-10-27.md), [exact 52-endpoint crosswalk](handoff/actual-pro-endpoint-crosswalk-2026-10-27.md), and [prioritized parity ledger](handoff/actual-pro-parity-ledger-2026-10-27.md). This matrix describes the **independent fork**, not demonstrated commercial runtime parity. The vendor packaged backend/frontend and test contracts are available for inspection, but original TypeScript / compiled native Python source and live vendor HTTP results remain unverified. Maintain stronger fork security.

Base: **ASCIT31/Dark-Moon master `b52d4d73c325427e4d2fa5f3cbf87dd889cc6300`**.
The original reconstruction contains the feature changes only. Current `pro`
subsequently merged upstream through `2b65cad`. The UI/provider update intentionally
extends `conf/apply-settings.sh` to preserve shared logins and support saved
OAuth authentication; see [OpenCode/WebUI sync](opencode-webui.md). The previous fork's runtime,
models, agents, image rewrites, toolbox inventory, Hermes/browser experiments and
build/CI modifications are not imported. The original reconstruction left upstream runtime/configuration unchanged.
The later upstream merge and targeted authentication change above are part of
the current branch; agent prompts are not edited by the UI update.

The proprietary Pro application source is not among the public repositories
inspected. The user explicitly selected **reconstruction from documentation**.
Accordingly, this is independent GPLv3 code with compatibility derived from the
public SDK, not a claim that the original Pro application has been recovered.
All nine documented public integration repositories are actual MIT-licensed source
imports, pinned in [SOURCES.json](../integrations/upstream/SOURCES.json), with
their licenses preserved. Eight source imports are unmodified. The n8n receiver has one explicitly
recorded adaptation for HMAC v2, timestamp validation and replay deduplication;
caches, dependency installs and locally generated build products are not committed.
The Action distribution bundle is rebuilt from source; upstream SDK tarballs and
the required license notices are preserved. See the [import guide](../integrations/upstream/README.md).

## Feature coverage

| Documented surface | Implementation | Verification / boundary |
|---|---|---|
| Live web dashboard | Campaigns, findings, evidence, projects, severity/category analytics, historical logs and responsive views | Desktop/mobile browser flow with literal malicious-looking evidence and no script execution. |
| Multi-target campaign parameters | Additional targets, out-of-scope assets, focus/exclusions, severity, noise, engagement rules, report format | Typed scope serialization; target allowlist covers additional hosts and prevents CIDR expansion outside allowed networks. |
| Accounts and authentication | PBKDF2 passwords, signed short-lived JWTs, explicit admin/analyst/viewer permissions, session revocation and password rotation | Real login/revocation and read-only enforcement tests. No weak default admin password is created. |
| SSO / OIDC | HTTPS discovery, authorization code + PKCE, browser-bound state cookie, nonce, issuer/audience/authorized-party checks and verified RSA/EC ID tokens | Signed-token test with fake provider transport. Authelia or another real IdP still requires deployment configuration/testing. |
| Encrypted credential store | Fernet-sealed secrets; public list/write responses contain masked metadata and opaque references | Plaintext absent from saved state and list responses. Root key and state files are private. |
| Authenticated target assessments | Separate target login/token references; local Docker stdin sends secrets to the **existing upstream privacy socket**, then only placeholders enter assessment argv | Fake-transport tests prove no secret in argv and fail-closed behavior if masking fails. Requires the running persistent upstream MCP socket; no plaintext fallback. |
| LLM provider management | Local, cloud and Anthropic profiles, encrypted API-key references, explicit `.opencode.env` application | Profile/apply tests use temporary repositories. Applying a profile updates shared files without erasing other logins; the optional authenticated native bridge applies changes live. Without it, restart OpenCode explicitly. Native OAuth is delegated to OpenCode. |
| REST API and capability discovery | All 15 documented route families: projects, targets, campaigns, vulnerabilities, dashboard, run, scheduler, auth, credentials, pull-requests, system, webhooks, events, retest, metrics | Actual official SDK against our HTTP server, plus HTTP permission/contract tests. `edition=community` is reported honestly. No PR-write or merge API exists. |
| Safe external integration data | Evidence-free vulnerability lists, evidence counts/booleans, safe PR validation summaries, aggregate metrics | Metadata tests exclude evidence, commands, target hosts and secrets from integration feeds. Full local administrator report/detail routes remain separate. |
| Live streaming | Run output SSE, terminal events, event journal, monotonically increasing cursors and replay by cursor | Real SSE over local HTTP with a fake assessment launcher; no real scan. |
| Webhooks | Event filters, legacy body-HMAC compatibility, stronger timestamp/id/body HMAC v2, bounded retries and delivery history | Receiver helper verifies signature, timestamp and replay id. HTTPS delivery pins approved DNS resolution and rejects private addresses unless explicitly allowed. No external delivery was performed. |
| Scheduler | One-shot dates and durable recurring intervals; pause/resume/delete; restart catch-up; per-schedule overlap prevention | Fake-clock and browser lifecycle tests. Exactly-once external side effects are not promised across crashes. |
| Retests | Queue a reassessment while preserving exclusions, rules and saved authentication; correlate original/new campaigns, compare findings and expose verdict summaries | Absence remains `not_observed`. A validated local proposal does not prove deployment or a fix on the assessed target, and never upgrades this verdict to `fixed`. |
| Project evolution charts | Per-project history, severity/category/status totals and timeseries | Browser analytics canvas and deterministic aggregation tests; changes in assessment scope still require interpretation. |
| Infrastructure / VR | 3D orbit/zoom, node-type exposure rings, per-node severity/counts, finding inspection, MITRE-labelled finding-location tour and WebXR | Browser canvas verified. Headset testing remains required. Recorded relationships are preserved; a location tour is not falsely described as a proven exploit chain. |
| Reports | Safe formatted Markdown preview; Markdown/JSON/PDF exports; HackerOne and Bugcrowd submission dossiers; operator-defined custom templates | Complete deterministic evidence exports and format tests. Templates use substitution, never code execution. |
| Signed/encrypted PDFs | Actual AES-256 PDF encryption **before** an embedded CMS signature, using operator PKCS#12 signing identity | Real decrypt + signature validation: intact, valid and trusted by the explicitly supplied test certificate. Self-signed operator certificates do not imply public CA trust. |
| Defensive remediation | Exact structured edits, source ranking, opt-in model generation, independent scope judge/confidence gate, isolated worktrees, before/after exploit/variant/normal probes and bounded retries | Local Git integration; mocked model/container validation; rejected proposals stay rejected. A failed baseline never counts as a fixed issue. |
| Campaign remediation automation | Opt-in completion hook queues confirmed findings, skips existing proposals, accepts local source or an explicit read-only HTTPS source checkout | Fake transport/queue tests; real source repositories, model and Docker image need operator validation. A fresh proposal repository without source is recorded `source_required`, never a fabricated code fix. |
| Remediation review / PR publishing | Read-only proposal/PR views, patch downloads; separately gated GitHub/GitLab/Gitea publication with saved credential refs or environment credentials | No automatic publishing. Both `--execute` and `DARKMOON_ALLOW_PUBLISH=1` are required. Only fake publication transports were exercised; no push, PR or merge occurred. |
| Sealed privacy state | Opt-in `community.guarded_mcp` delegates to unmodified upstream tools with an AES-GCM sealed persistent privacy vault | Restart and concurrent-instance tests preserve placeholders without plaintext files. Operator keys replace vendor licence-derived keys. |
| Rehydration audit | HMAC-chained metadata-only journal, category counts and integrity checks | Secret-denial behavior and journal tampering tested. It records local rehydrations; it cannot prove every possible network egress path. |
| Runtime hardening / guard | Optional read-only Compose overlay, cap drop/no-new-privileges, resource/log limits; operator-signed hash baseline and persistent compromise marker; periodic checks block new runs | Integrity tamper/reseal tests and static overlay review. No Docker daemon was available for an image boot test. Docker-socket access remains a powerful trust boundary. |
| Diagnostics / repair | Dependency/path/permission diagnostics; explicit repair of owned state directories and key permissions | Does not clear compromise markers, change vendor images, or install packages silently. |
| Image updates | Build/digest comparison and explicit read-only Docker Hub lookup; UI check button | Registry transport mocked; no automatic image pull or deployment. |
| CI/CD and integrations | Imported official client/CLI, GitHub Action/reusable workflow, GitLab component, Jenkins plugin, VS Code extension, n8n nodes, Grafana app and Splunk app/forwarder; existing lightweight JSONL/Prometheus examples | Client 75 tests; n8n 25 checks + receiver test; Action 27 tests; GitLab 15 checks; Splunk 13 offline/mock checks; VS Code build + 8 Node tests; direct current/legacy SDK-to-our-server flows. Native Grafana/Jenkins and live extension hosts require their environments. |
| Cloud / bare-metal deployment | Source bundle, checksum-verified bootstrap, AWS/GCP/Azure/OVH plans and explicit execution; same workspace can run on existing Linux/WSL hosts | Generated plans/cloud-init tested without provisioning. Source hosting and LLM secret configuration remain explicit operator steps; no unattended vendor appliance equivalence is claimed. |

Commercial licence activation, hardware-bound licence enforcement and vendor
anti-debugging restrictions are not recreated. They are distribution controls,
not additional assessment capability, and no vendor activation check is bypassed.
Our replacement guard and encryption remain under the installation owner's
control. No claim of original-Pro binary, UI, API or security certification parity
is made beyond the contracts and behaviors explicitly tested here.

## Accounts, SSO and encrypted credentials

Unlock with the existing workspace token, then use **Settings & accounts** to
create accounts. For unattended deployment, set `DARKMOON_ADMIN_USERNAME` and
`DARKMOON_ADMIN_PASSWORD` before first startup. The password must be at least 12
characters. It is hashed, not stored. JWTs last one hour and are revocable.

For OIDC set:

```text
DARKMOON_OIDC_ISSUER=https://your-issuer
DARKMOON_OIDC_CLIENT_ID=darkmoon-frontend
DARKMOON_OIDC_CLIENT_SECRET=your-confidential-client-secret-if-required
DARKMOON_OIDC_REDIRECT_URI=https://your-workspace/callback
DARKMOON_OIDC_ADMIN_SUBS=explicit-subject-id,another-admin-subject
DARKMOON_OIDC_ANALYST_SUBS=explicit-analyst-subject
```

Subjects not explicitly assigned are viewers. Email addresses and display names
never decide privilege. The IdP and redirect must be deployed/configured by the
operator; the code does not connect to an unspecified IdP or create an external
account during startup.

Use **Credentials** for secrets. Supply `assessment_credential_id` (with its
username metadata) and/or `assessment_token_id` for target authentication;
`credential_id` is the separate SCM credential for source access/publication.
The queue resolves them locally. Target secrets must be representable as single
tokens by the upstream scope parser; unsupported forms fail closed.

## Protected reports and privacy state

Initialize an operator signing identity, or configure your own trusted PKCS#12
chain through `DARKMOON_SIGNING_P12`:

```bash
export DARKMOON_DATA_DIR="$PWD/darkmoon-settings"
export DARKMOON_SIGNING_PASSWORD='YOUR_LONG_SIGNING_PASSWORD'
PYTHONPATH=mcp .venv/bin/python -m community.report_security init-signer --name 'Your installation operator'
```

Keep the signing password in the server environment. **Signed / encrypted PDF**
asks separately for a report password; it is not saved or put in a URL.
Custom report format uses the server's `DARKMOON_REPORT_TEMPLATE` text file and
the placeholders `$report`, `$campaign_name`, `$campaign_id` and `$target`.

For sealed privacy persistence, configure the MCP command to run
`python -m community.guarded_mcp` with this source package on `PYTHONPATH` instead
of `python -m src.server`. Set `DARKMOON_VAULT_STATE_DIR` to a private persisted
directory. The wrapper preserves the upstream tools and category policy; it adds
encrypted persistence and a metadata-only journal. This is opt-in and requires
an image/host containing the feature package; it is not silently injected into
an existing vendor image. Audit summary: `GET /api/v1/system/privacy-audit`.

## Integrity, updates and scope controls

```bash
PYTHONPATH=mcp .venv/bin/python -m community.integrity doctor
PYTHONPATH=mcp .venv/bin/python -m community.integrity doctor --repair
PYTHONPATH=mcp .venv/bin/python -m community.integrity seal
DARKMOON_GUARD_ENFORCE=1 DARKMOON_PYTHON="$PWD/.venv/bin/python" ./community.sh
```

Only seal after reviewing source and policy. A mismatch persists until explicitly
resealed; repair never clears it. Optional overlay:
`docker-compose.community-hardened.yml` (review image write paths before applying).
This source/Compose guard is independent of a vendor's opaque binary/hardware
licence guard; it is not a promise of protection against a host administrator.

Set `DARKMOON_TARGET_ALLOWLIST` to comma-separated hostname globs and/or CIDR
networks. Network targets must fit a configured network; a glob matching only
the CIDR's starting address is not enough. All API writes require authentication
even if an older Pro deployment allowed unauthenticated writes.

`GET /api/v1/system/update-status` uses supplied build stamps without network.
The UI's explicit check adds `?check=1` for Docker Hub metadata. Configure
`DARKMOON_IMAGE_NAME`, `DARKMOON_IMAGE_DIGEST` and/or `DARKMOON_IMAGE_BUILT_AT`
to identify the running image. Unknown information is returned as unknown.

## Public integration imports and compatibility

The imports preserve MIT licences and source pins. No third-party workflows are
installed or activated by copying these files. To reproduce the SDK checks:

```bash
npm ci --ignore-scripts --prefix integrations/upstream/client
npm run build --prefix integrations/upstream/client
npm test --prefix integrations/upstream/client
npm ci --ignore-scripts --prefix integrations/upstream/action
DARKMOON_TEST_PYTHON="$PWD/.venv/bin/python" node tests/community/sdk_fork_http.cjs
```

The direct contract test uses an authenticated JWT. The imported SDK's read-only
methods do not all initiate username/password login themselves: obtain a token
first rather than weakening the server's read authentication. The n8n node has
an explicit login flow. Existing Pro-only native integrations may still depend
on undocumented routes; do not infer full wire compatibility from the router
names alone.

Webhook receivers should use the v2 timestamp/id/body signature and retain a
seen-event-id set (`verify_delivery`), not only validate the backward-compatible
body-HMAC. The imported n8n receiver is adapted to require v2, a fresh timestamp and a
persisted bounded event-id cache in addition to its legacy body-HMAC. No outbound subscription was activated during this work.

Primary specifications:
[DarkMoon documentation](https://docs.dark-moon.org/),
[official client](https://github.com/ASCIT31/darkmoon-client),
[n8n source](https://github.com/ASCIT31/darkmoon-n8n),
[Grafana source](https://github.com/ASCIT31/darkmoon-grafana).
