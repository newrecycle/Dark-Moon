# OpenCode configuration scopes

Dark-Moon supports three explicit OpenCode/MCP deployment scopes.

## Production Compose

`opencode-bootstrap` runs `conf/bootstrap.py` before stock OpenCode starts. It seeds or migrates the persistent agents, renders the provider selected by `install.sh`, writes `opencode.json` and `auth.json` with mode `0600`, and registers the `darkmoon-mcp` sidecar as a remote Streamable HTTP MCP server.

Reference: `conf/opencode.production.json`.

## Audited source-image fallback

`Dockerfile.opencode` retains the embedded stdio MCP runtime for development and source-build diagnostics. Its generated configuration uses the local command `/usr/local/bin/darkmoon-mcp`.

Reference: `conf/opencode.json`.

## Standalone MCP development

Running OpenCode from the `mcp/` directory can use the local Python module directly.

Reference: `mcp/opencode.json`.

These files intentionally use different MCP transports. Production must use the sidecar URL; the local configurations exist only where the MCP process is present in the same runtime environment as OpenCode.
