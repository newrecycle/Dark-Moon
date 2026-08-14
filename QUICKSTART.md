# Dark-Moon — Quickstart (prepared for use)

The production image **`newrecycle/darkmoon:latest`** has been built from the
current source. It includes:
- the verified toolbox version pinning (impacket pinned to commit `4c09897a…`,
  bloodhound wrappers, cmseek `v.1.1.3` tag, etc.),
- the `verify_toolbox.py` / `build_manifest.py` / `run_tests.py` fixes,
- the `port_scan.py` fix (naabu host parsing + result dedup).

> Runtime note: `docker-compose.yml` bind-mounts `./workflows` into the
> container (`…/src/tools/workflows/:rw`), so edits to
> `mcp/src/tools/workflows/*.py` take effect without rebuilding the image.

## Config (already in place)
- `.opencode.env` — LLM provider credentials (git-ignored; never commit).
- `mcp/.env` — MCP server defaults (container name, timeouts, paths).
- Bind-mount directories present: `shared/`, `reports/`, `sessions/`,
  `darkmoon-settings/`, `workflows/`.

No top-level `.env` is required — Compose defaults `DARKMOON_UID`/`GID` to `1000`.

## Launch
```bash
docker compose up -d
```
Starts the `darkmoon` toolbox container (name `darkmoon`) and the `opencode`
MCP host. On first run Compose builds the `opencode` image if it is missing.
The MCP server connects to the toolbox container by the name `darkmoon`.

> This was NOT started automatically as part of preparation — `docker compose up`
> creates/replaces the live stack, so run it when you are ready.

## Verify the stack is healthy
Once up, the MCP server exposes `health_check`, `list_workflows`,
`list_allowed_tools`, `check_tool`, `execute_command`, and `run_workflow`.
From the OpenCode host (or any MCP client pointed at the server) call e.g.
`health_check()` or run a workflow:
```json
run_workflow("port_scan", "scan_ports", {"target": "127.0.0.1", "top_ports": 100})
```
The `port_scan` workflow now reports HTTP services found by `httpx` on open
ports (previously always 0 due to a naabu `ip`/`host` field mismatch).

## Verification status from this session
- Manifest audit: 64 exact / 1 accepted floating (`lightpanda`, nightly).
- Static regression suite: 11/11 groups, 13/13 atomic checks.
- Runtime verification (phase8): 65/65 records PASS.
- MCP server tools exercised via the live server: health, workflows,
  allow-list, `check_tool`, `execute_command`, and `run_workflow` (port_scan).
- `port_scan` httpx step fixed and re-validated end-to-end.
