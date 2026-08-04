# OpenCode 1.18.12 runtime architecture

Dark-Moon uses the official `ghcr.io/anomalyco/opencode:1.18.12` image without adding Dark-Moon binaries or a Docker socket to that container.

## Services

| Service | Responsibility | Docker socket |
|---|---|---|
| `opencode` | TUI, agent orchestration, provider requests, compatibility plugin | No |
| `opencode-bootstrap` | One-shot agent/workflow seeding, migration, provider rendering, and configuration validation | No |
| `darkmoon-mcp` | Streamable HTTP MCP server and controlled bridge into the toolbox | Yes |
| `darkmoon` | Security-tool toolbox | Yes, retained from the existing toolbox architecture |

`opencode` and `darkmoon-mcp` share an internal Compose network. Both also join the egress network because OpenCode must reach configured model providers and the MCP service may run workflows that require external connectivity. The MCP endpoint is not published to the host.

## Clean installation

`install.sh` writes `.opencode.env` with mode `0600`, prepares the persistent bind mounts, and starts the stack. Before OpenCode starts, `opencode-bootstrap`:

1. Seeds the canonical agents when the persistent agent directory is empty.
2. Migrates and validates existing persisted agents without replacing user prompt customizations.
3. Seeds the default workflow registry when the persistent workflow directory is empty.
4. Converts the provider selected by `install.sh` into an OpenCode provider/model configuration.
5. Writes `opencode.json`, `auth.json`, and `.darkmoon-bootstrap.json` with restrictive permissions.
6. Registers `http://darkmoon-mcp:8000/mcp` as a remote Streamable HTTP MCP server.
7. Enforces `default_agent: pentest` and `subagent_depth: 1`.

OpenCode starts only after the bootstrap exits successfully and the MCP protocol-level health check can initialize a client and list the required tools.

## Persistent data

A normal `./install.sh` reset removes and recreates all generated bind mounts:

- `data`
- `darkmoon-settings`
- `workflows`
- `reports`
- `sessions`
- `workspace`

Use `./install.sh --keep` to preserve all six directories and named Docker volumes. `./install.sh --init` only forces provider reconfiguration; it does not imply data preservation.

## CLI behavior

`darkmoon.sh` invokes the stock `opencode` binary directly. It does not assume Bash, Python, GNU `timeout`, or `darkmoon-cli` exist in the official OpenCode image.

- Normal prompts execute through `opencode run`.
- OpenCode flags are forwarded directly.
- Provider reachability is checked from the MCP sidecar.
- `--log <session_id>` starts `src.mcp_monitoring` inside the MCP sidecar.

Local provider URLs must be reachable from containers. The installer defaults Ollama and llama.cpp URLs to `host.docker.internal`; container-local `localhost` addresses are rejected by the wrapper preflight.

## Configuration compatibility

The `darkmoon-compat` plugin removes legacy Dark-Moon metadata from normalized agent configuration and provider-bound options. It preserves valid root-level OpenCode fields such as `tools`, `permission`, `steps`, and `maxSteps` while removing unsupported provider values at `chat.params`.

The plugin also forces one-level delegation:

- `pentest` may invoke a specialist through `task`.
- Specialists cannot invoke another subagent.
- Specialists can still be selected directly.

## Development and ARM64

`docker-compose-dev.yml` uses the same stock OpenCode, bootstrap, plugin, and MCP sidecar topology. Its only intended difference is building the toolbox image locally. This avoids maintaining a separate embedded-MCP or Docker-socket-enabled OpenCode path on ARM64.

## Verification scopes

The repository separates verification into distinct workflows:

- Configuration/bootstrap/plugin tests and static shell/Compose validation.
- A fast synthetic Docker/MCP/provider protocol fixture.
- A clean production-Compose test using the real toolbox image, actual wrapper, workflow discovery, persistence, and service restarts.
- A path-filtered and scheduled source-build fallback test for `Dockerfile.opencode`.

Restart tests prove that fresh OpenCode CLI processes reconnect after restarting the MCP sidecar or OpenCode container. They do not claim preservation of an in-flight request.
