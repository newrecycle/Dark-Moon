# VS Code packaged native-host verification — 28 October 2026

## Scope and isolation

This verification concerns **only** `integrations/upstream/vscode/**`, the disposable VS Code host driver in `tests/community/vscode_host.cjs` and its Xvfb/Docker recipe, the VS Code CI workflow, and this note. No JetBrains files, credential/API server implementation or real assessment launcher were changed. Work began from `origin/pro` at `f1408942d7b89ed52c66015d370132b7fa59eb64` on the isolated `agent/vscode-native-acceptance-20261028` branch. The execution environment could not resolve github.com for a local cloned worktree; GitHub's isolated branch/tree updates and Actions fresh checkout were used instead. The final commit should be based on the *then-latest* `pro` tree, preserving intervening changes.

No root/subtree `AGENTS.md` files were present in the inspected repository tree. Existing handoff ownership indicated Jenkins had a separate claimed workstream; no Jenkins or JetBrains files were changed.

## Actual tested artifact and toolchain

- Extension `darkmoon-vscode` version **0.1.3**; bundled fork SDK `@darkmoon/client` version **0.2.1-darkmoon.1**.
- **VS Code 1.106.3** Stable linux-x64, downloaded by `@vscode/test-electron` during the controlled Docker build.
- **Node.js 24** via `node:24-bookworm`, declared TypeScript/esbuild tooling from the committed `package-lock.json`.
- `vsce package --no-dependencies` builds `/workspace/darkmoon.vsix` with production `dist/extension.js`. The VSIX is extracted to `/workspace/vscode-package/extension`; that extracted **packaged** extension is the VS Code extension-development/activation path, while external compiled tests run through `--extensionTestsPath`. A development-source-only green test is not substituted for packaged acceptance.
- All execution occurs inside `docker run --network none`; only pinned build dependencies/editor downloads use build-time network. No real targets, model/provider calls, webhook notifications, deployments or external services were exercised by the tests. `--disable-workspace-trust` is forbidden and not used. Workspace trust is enabled and the empty local workspace must actually satisfy the trusted-local reveal gate.

## Exact repeatable commands

From the repository root with a Docker engine:

```sh
docker build --progress=plain -f tests/community/Dockerfile.vscode-host -t darkmoon-vscode-host .
docker run --rm --network none --entrypoint sh darkmoon-vscode-host -c \
  'cd integrations/upstream/vscode && node node_modules/mocha/bin/mocha.js --reporter dot out/test/node/*.test.js'
timeout --signal=TERM --kill-after=10s 240s \
  docker run --rm --init --network none --memory=3g --shm-size=512m --pids-limit=512 darkmoon-vscode-host
```

Docker image build executes, in order:

```sh
npm ci --prefix integrations/upstream/vscode --ignore-scripts --no-audit --no-fund
npm --prefix integrations/upstream/vscode run typecheck
npm --prefix integrations/upstream/vscode run compile-tests
npm --prefix integrations/upstream/vscode run compile
cd integrations/upstream/vscode
node_modules/.bin/vsce package --no-dependencies -o /workspace/darkmoon.vsix
unzip -q /workspace/darkmoon.vsix -d /workspace/vscode-package
```

The host entry script `tests/community/launch_vscode_host.sh` starts `Xvfb :98` without TCP, enforces a 10-second Unix-socket readiness gate, and traps display-child cleanup. The Node driver uses a private temporary settings/extensions directory, a 150-second native deadline with a 5-second termination grace, detached process-group termination, a hard finish even if grandchildren inherit stdout, and temporary-state deletion. A separate 240-second outer deadline protects Docker-level failures. CI job limit: 15 minutes. Never pass credential values as process arguments. Raw editor stdout/stderr is hashed and counted, not forwarded to CI; the native suite records only status, counts, and source-controlled failing test titles, **never** assertion messages or secrets.

## Observed results

[Community native VS Code acceptance (run 40778113910)](https://github.com/newrecycle/Dark-Moon/actions/runs/40778113910): **SUCCESS** on the isolated feature branch. The hosted log records:

- TypeScript `typecheck`, `compile-tests` and production `compile`, VSIX packaging/extraction: **pass**.
- Separate plain Node data-layer, real SDK-adapter, identity and reveal-grant contracts: **26 passing**.
- Native extension-host suite, actual packaged extension under pinned VS Code: **35 started, 35 passed, 0 failed**, editor exit code 0. Browser/display startup and editor shutdown completed. No tests were skipped or replaced by Node-only coverage.

The previous [run 40647818948](https://github.com/newrecycle/Dark-Moon/actions/runs/40647818948) successfully built the editor but was cancelled after a silent `xvfb-run`-wrapped native invocation. A first bounded attempt [40776423933](https://github.com/newrecycle/Dark-Moon/actions/runs/40776423933) reproduced a silent outer deadline. Replacing the wrapper with explicit Xvfb startup resolved the missing-startup diagnostic. The first native suite then ran in seconds with one failing **Growth CTA test isolation** case (33/34 pass); the safe-failure-label run [40777664456](https://github.com/newrecycle/Dark-Moon/actions/runs/40777664456) identified it without exposing raw errors. The native fixture globally suppresses unsolicited CTA; its positive test now explicitly clears that opt-out and enables the setting for the test, while the opt-out guard remains tested. The final packaged suite passed 35/35.

## Defects and coverage

- Replaced opaque test-host startup with bounded, actionable display/extension-stage diagnostics and cleanup; separate Node suite is no longer incorrectly presented as extension-host execution.
- Exercised actual extension activation/command registration, campaign/finding/report view providers, exact campaign relationships, fixture data and capability degradation, default report preview, forged reveal URI denial, trusted-local full-content grants, TTL expiry, refresh revocation, and stale pending responses. Native view provider tests use a recording WebviewView (not a DOM pixel-equivalence harness).
- Prevented the real-client adapter from substituting an independent `runId` or `pending` placeholder for a missing campaign identity; invalid/absent campaign identity fails closed.
- Generic launch and client-loader errors no longer echo untrusted subprocess/transport exceptions; base URL warnings reject embedded userinfo/query/fragments and no longer repeat potentially credential-bearing invalid URL strings.
- Default campaign, finding and report-list metadata now runs through the fork's redaction net; default detailed finding/report evidence remains protected by explicit scope, focused trusted-local checks and expiring revocable grants.
- Native tests and offline grant tests cover resource/client/revision/focus/trust expiry and revocation semantics. Missing findings, changed campaigns, failed refreshes, in-flight client replacement and empty/unavailable states are exercised by existing/new suites.

## Boundaries

This is a **Linux VS Code 1.106.3** packaged-host acceptance claim, not validation of every supported editor version or Windows/macOS/remote extension-host behavior. Native execution opens an empty local workspace; actual user-facing untrusted-folder confirmation dialogs and focus transitions are not simulated at OS GUI level (grant authorization logic is tested with controlled state). The WebviewView recording double verifies extension-provider HTML/message contracts but not browser pixel rendering. The existing redaction net handles known secret formats; no regex scrubber proves arbitrary free-form content free of unknown secrets. No real Pro credentials, licensed commercial runtime, external REST server or live assessment were run. Native CI success is specific to the above commit and environment; subsequent `pro` workflows must be reported from their own observed results.

