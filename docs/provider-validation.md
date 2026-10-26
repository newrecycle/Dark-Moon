# Provider and Docker validation — 26 October 2026

This validation supplements the isolated unit/browser suite. It never starts a
target assessment, performs inference, or logs in to an unspecified account.

| Check performed in the coding environment | Actual result |
|---|---|
| Docker Compose 5.6.1: base configuration | Passed using the real Compose executable. |
| Compose: authenticated bridge and hardened bridge | Passed merge/validation, loopback binding and read-only policy checks. |
| OpenRouter public `/api/v1/models` | Passed; 466 models returned at validation time. No key or inference entitlement verified. |
| Installed OpenCode 1.19.4 binary: health, Basic-auth rejection, provider catalog, auth API | Native HTTP calls succeeded, including disposable API-key PUT/DELETE. 232 catalog providers; the isolated invocation advertised zero OAuth method providers. No real account OAuth was performed. |
| Same binary: model PATCH followed by GET | **Failed**: PATCH accepted the model settings but GET did not confirm them. The WebUI now detects this and reports unverified live activation with restart required. |
| Local Docker image build/boot | **Blocked**: no usable daemon/socket; no process capabilities and a read-only cgroup mount. Docker client installation alone is not an engine test. |
| Community suite | 108 tests passed, including real loopback model HTTP requests, profile lifecycle and stale native readback handling. |
| Browser acceptance | Passed the full dashboard flow, including model discovery/failure preservation, profile edit/duplicate/check/delete, bridge health, existing login/model workflows and report downloads. |
| Existing MCP/invariant gates | 117 MCP tests and the repository no-regression gate passed. |

The machine-readable local result is
[provider-local-20261026.json](validation/provider-local-20261026.json). Its failed
and blocked statuses are intentional evidence, not successful Docker/account
validation. The installed upstream binary is separate from DarkMoon's branded
fork image; their results must not be conflated.

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
retained as workflow artifacts. The workflow's actual run result will determine
image validation status; adding this workflow does not itself establish a pass.

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
