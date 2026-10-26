# Provider and Docker validation — 26 October 2026

This validation supplements the isolated unit/browser suite. It never starts a
target assessment, performs inference, or logs in to an unspecified account.

| Check performed in the coding environment | Actual result |
|---|---|
| Docker Compose 5.6.1: base configuration | Passed using the real Compose executable. |
| Compose: authenticated bridge and hardened bridge | Passed merge/validation, loopback binding and read-only policy checks. |
| OpenRouter public `/api/v1/models` | Passed; 466 models returned at validation time. No key or inference entitlement verified. |
| Installed OpenCode 1.19.4 binary: health, Basic-auth rejection, provider catalog, auth API | Native HTTP calls succeeded, including disposable API-key PUT/DELETE. 232 catalog providers; the isolated invocation advertised zero OAuth method providers. No real account OAuth was performed. |
| Same binary: model PATCH followed by GET | Initial project `/config` PATCH **failed** readback. Updating the shared default through `/global/config` **passed** effective `/config` readback for both model settings. The WebUI uses that endpoint and still detects unverified activation. |
| Local Docker image build/boot | **Blocked**: no usable daemon/socket; no process capabilities and a read-only cgroup mount. Docker client installation alone is not an engine test. |
| Actual Docker image in GitHub CI | **Passed** build and boot; all three Compose renders, native health/auth/catalog/login-method discovery, effective model/small-model readback and disposable API-key PUT/DELETE passed. |
| WebUI HTTP API connected to real isolated OpenCode 1.19.4 | **Passed** live catalog, named profile creation, live apply/readback, profile check and deletion retaining the active model. No account login or inference. |
| Community suite | 108 tests passed, including real loopback model HTTP requests, profile lifecycle and stale native readback handling. |
| Browser acceptance | Passed the full dashboard flow, including model discovery/failure preservation, profile edit/duplicate/check/delete, bridge health, existing login/model workflows and report downloads. |
| Existing MCP/invariant gates | 117 MCP tests and the repository no-regression gate passed. |

The machine-readable local result is
[provider-local-20261026.json](validation/provider-local-20261026.json). Its failed
and blocked statuses are intentional evidence, not successful Docker/account
validation. The installed upstream binary is separate from DarkMoon's branded
fork image; their results must not be conflated.
The successful native retest is recorded separately in
[provider-global-config-20261026.json](validation/provider-global-config-20261026.json).

## Actual image validation in CI

The `Community runtime validation` workflow builds `Dockerfile.opencode` on a
Docker-capable GitHub runner. The build pins ASCIT31/opencode source to
`77b3b46788623317115ae920cf0072e54aa2643c` (package manager `bun@1.3.11`) instead
of silently changing when the fork's dev branch moves. The source revision can
be overridden explicitly with the `OPENCODE_REF` build argument.

The job then boots only an isolated OpenCode container, with a random temporary
server password and no operator credentials or host data volumes. It probes
health, unauthenticated rejection, real provider/model/auth-method discovery,
model config write/readback and disposable API-key write/delete. No images are
published and no assessment, PR, cloud deployment or inference request is made.
The container is removed on exit. JSON results and its credential-free logs are
retained as workflow artifacts.

The [successful image run](https://github.com/newrecycle/Dark-Moon/actions/runs/40370000911)
tested commit `64a156f99255aea2cfb1a9dc49a7ee3dda4078b7`. Both the image build and
every requested runtime check passed. Its native catalog contained 232 providers;
three providers advertised login methods. Both effective model settings matched
the shared-default update. The exact JSON report is preserved in
[docker-provider-ci-20261026.json](validation/docker-provider-ci-20261026.json),
and the run's `community-runtime-evidence` artifact includes the original JSON
and container logs. This establishes actual image/API validation, not real-account
OAuth or inference entitlement.

The [initial image run](https://github.com/newrecycle/Dark-Moon/actions/runs/40363087162)
built and booted the actual branded image successfully. It discovered 232 providers
and three providers advertising login methods, and passed Basic-auth rejection and
disposable API-key write/delete. It failed model readback via the project config
endpoint, reproducing the native-binary issue. Inspection of the pinned source
found `Config.update()` writes project `config.json`, while project loading uses
`opencode.json`/`opencode.jsonc`. Shared defaults now use `/global/config`, followed
by effective `/config` readback, which also catches project overrides. The native
retest and actual image rerun passed.

The initial runner also rejected the Compose invocation. The probe now resolves
its required env file in a disposable project directory, avoiding dependence on
the newer `--no-env-resolution` flag and any operator env file. All three Compose
configurations passed the local retest with this invocation.

The additional live WebUI adapter check launched the actual dashboard HTTP handler
and a stock OpenCode 1.19.4 child process in disposable directories. It created a
profile through the WebUI API, applied it, confirmed the effective active model
through the synchronized catalog, checked the profile, and deleted it while
confirming the active model remained selected. This uses a real native process,
separate from the browser suite's deterministic native-server fixture. Its result
is [webui-native-adapter-20261026.json](validation/webui-native-adapter-20261026.json).

To repeat on a Docker host:

```bash
docker build --file Dockerfile.opencode --tag darkmoon-community-validation .
python3 tools/validate-community-runtime.py --docker-image darkmoon-community-validation --output runtime-validation.json
```

For a separately installed native binary and optional public catalog check:

```bash
python3 tools/validate-community-runtime.py --opencode-binary /path/to/opencode --public-catalog --output native-validation.json
```

Exit status is 0 for all requested checks passing, 1 for a failure, and 2 when
checks are blocked. Native binary validation uses a disposable home/config/data
and Git directory. It strips common provider key/config overrides from that
child environment. The public catalog check is opt-in.

Real subscription OAuth and inference validation still need an operator-selected
provider/account. No such credentials or live operator endpoint were configured
in this environment. Public model-list access and local HTTP fixtures do not
stand in for those account checks.
