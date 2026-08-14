# Dark-Moon configuration scopes

Dark-Moon runs as a **single `darkmoon` container**. The toolbox and the MCP
server are baked into the same image; the MCP auto-starts on container boot and
exposes `http://127.0.0.1:8000/mcp` (Streamable HTTP). The LLM brain (Hermes)
runs outside the container and is the only thing that talks to the MCP — there is
no OpenCode brain, no `docker-proxy` sidecar, and no separate `darkmoon-mcp`
service.

## Production Compose

`docker-compose.yml` (x86_64, image `newrecycle/darkmoon:local`) and
`docker-compose-dev.yml` (ARM64, builds the `Dockerfile` locally) each define
exactly one service: `darkmoon`. On container start, `conf/bootstrap.py` seeds or
migrates the persistent agents, renders the provider selected by `install.sh`,
and writes the auth/agent state. The MCP runs **inside** the container with
`DARKMOON_EXEC_MODE=local`, so it executes tools as local subprocesses — the
container never mounts `/var/run/docker.sock`.

Reference: `conf/bootstrap.py`, `conf/opencode-config.py` (the agent-config
renderer, now Hermes-agnostic).

## Hermes MCP entrypoint

Hermes reaches the MCP at `http://localhost:8000/mcp`. The MCP server key is
`darkmoon`, so the tools are exposed to Hermes as `darkmoon_*` (e.g.
`darkmoon_health_check`, `darkmoon_execute_command`, `darkmoon_list_workflows`).
On the wire the server registers bare names (`health_check`, `execute_command`,
`list_workflows`, ...) — the `darkmoon_` prefix is applied by the Hermes
server-key integration, not by the server itself.

## Standalone MCP development

Running the MCP from the `mcp/` directory uses the local Python module directly
(`python -m src.http_server` or `python -m src.healthcheck`). This is only for
local development/diagnostics; the production boundary is always the baked-in
image.

These scopes intentionally share the same single-container, local-exec design —
the MCP process always lives with the toolbox, never as a separate service.
