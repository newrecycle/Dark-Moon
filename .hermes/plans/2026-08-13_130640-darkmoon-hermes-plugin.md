# Convert Dark-Moon into a Hermes Agent Plugin — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Package the Dark-Moon MCP + agent prompts as a portable **Agent Plugins v1** package so a Hermes user can `hermes plugins install` it, enable it, and get the `darkmoon_*` security tools + a pentest skill inside any Hermes session.

**Architecture:** Dark-Moon today is a standalone stack (`darkmoon.sh` → OpenCode → Dark-Moon MCP → Docker toolbox). We do NOT rewrite that stack. Instead we add a thin `plugin/` package that ships (a) a `plugin.json` manifest, (b) an `mcp.json` that points Hermes at the Dark-Moon MCP over **streamable-http** (the MCP already exposes `mcp/src/http_server.py` on `:8000`), and (c) a `skills/darkmoon-pentest/SKILL.md` that teaches Hermes how to drive the tools and bring up the Docker backend. The Docker toolbox + `docker-proxy` are still required and are started by a helper script the skill invokes; the plugin is a client of that backend, not a replacement for it.

**Tech Stack:** Hermes Agent portable plugin format (`plugin.json` / `mcp.json` schema `https://agent-plugins.org/schemas/1.0.0/*`), FastMCP `streamable-http` transport (already in `mcp/src/http_server.py`), Docker Compose v2, Python 3.12. Validation via `hermes plugins doctor` and `python -m unittest`.

---

## Current context / assumptions

- Verified in repo:
  - MCP tools are already namespaced `darkmoon_*` (AGENTS.md invariant + tests).
  - `mcp/src/http_server.py` runs `mcp.run(transport="http", host=$DARKMOON_MCP_HOST, port=$DARKMOON_MCP_PORT|8000)` — an HTTP/streamable endpoint already exists.
  - `mcp/src/server.py` builds `FastMCP("Darkmoon CyberSecurity")`; privacy gateway is server-side (model never sees real IPs/creds). This boundary MUST stay server-side after packaging.
  - `darkmoon-settings/` is live runtime state and gitignored; `conf/agents/*.md` is canonical source; `conf/plugins/darkmoon-compat.js` is an **OpenCode** plugin (unrelated to Hermes plugins — do not confuse the two).
- Verified in Hermes runtime (`~/.hermes/hermes-agent/hermes_cli/agent_plugins.py`):
  - Portable manifest is `plugin.json`, `$schema` MUST equal `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`.
  - `name` regex `^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$`, length 1–64.
  - MCP config is a separate `mcp.json`, `$schema` == `.../mcp.schema.json`, top-level keys exactly `{$schema, mcpServers}`.
  - Supported MCP types: `stdio` and `streamable-http`. `sse` is explicitly rejected. Remote non-loopback URL MUST be https; http allowed only for `localhost`/loopback.
  - Skills live under `skills/<name>/SKILL.md`; frontmatter `name` MUST equal the directory name and match `^(?!.*--)[a-z0-9]+(?:-[a-z0-9]+)*$`; `description` 1–1024 chars.
  - Portable packages install **disabled** by default (`hermes plugins install` → then `hermes plugins enable <name>`).

**Assumption to confirm with user (see Open Questions):** transport choice — `streamable-http` (recommended; MCP already serves it) vs `stdio` (would require the MCP to run with the Docker socket reachable from the stdio child, which conflicts with the docker-proxy security boundary).

---

## Target layout (all under `plugin/`)

```
plugin/
  plugin.json                      # v1 manifest
  mcp.json                         # v1 mcpServers (streamable-http)
  skills/
    darkmoon-pentest/
      SKILL.md                     # frontmatter name: darkmoon-pentest
      references/
        bringup.md                 # how to start the Docker backend
        tool-catalog.md            # darkmoon_* tools + privacy rules
  scripts/
    darkmoon-up.sh                 # idempotent: bring up docker-compose + mcp, print URL
    darkmoon-down.sh               # stop backend (optional convenience)
  README.md                        # install/enable/use for end users
```

Nothing in `conf/`, `mcp/src/`, `docker-compose*.yml`, or `install.sh` is modified — the plugin is a client + docs wrapper around the existing stack. This keeps the plugin portable and avoids breaking the pinned OpenCode pipeline.

---

## Proposed approach

1. **Transport = `streamable-http`.** Point `mcp.json`'s `mcpServers.darkmoon` at the already-existing HTTP endpoint (`DARKMOON_MCP_HOST`/`DARKMOON_MCP_PORT`, default `localhost:8000`). This avoids the Docker-socket-in-stdio-child conflict and reuses the privacy gateway unchanged.
2. **Backend bring-up stays in Docker Compose.** The skill's `references/bringup.md` documents running `./install.sh` / `docker compose -f docker-compose.yml up -d` then launching the MCP (`python -m src.http_server` inside the `darkmoon-mcp` container, or via `darkmoon.sh`). `scripts/darkmoon-up.sh` wraps this so the user has one command; it prints the URL the plugin's `mcp.json` expects.
3. **Skill teaches the agent the contract:** only call `darkmoon_*` tools, never hand-write IPs/creds (use `IP_PRIVATE_001` placeholders in prompts/reports), bring the backend up first, and treat the MCP as the sole execution boundary.
4. **No new Python in `mcp/src` is required** — only the new `plugin/` wrapper. Keeps the existing `mcp` `requirements.lock`/`uv` workflow intact.

---

## Step-by-step plan

### Task 1: Scaffold the plugin directory

**Objective:** Create the empty `plugin/` tree so later tasks have fixed paths.

**Files:**
- Create: `plugin/` and subdirs `plugin/skills/darkmoon-pentest/references/`, `plugin/scripts/`

**Step 1:** Run `mkdir -p plugin/skills/darkmoon-pentest/references plugin/scripts`

**Step 2:** Verify: `find plugin -type d` — expected the 4 dirs above.

**Step 3:** Commit.
```bash
git add plugin
git commit -m "chore(plugin): scaffold hermes plugin directory"
```

---

### Task 2: Write `plugin/plugin.json` manifest

**Objective:** Declare the portable v1 manifest so `hermes plugins` discovers it.

**Files:**
- Create: `plugin/plugin.json`

**Step 1:** Write exactly (only fields in the v1 allow-list `$schema,name,version,description,author,homepage,repository,license,keywords,extensions`):
```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "darkmoon",
  "version": "0.1.0",
  "description": "Autonomous AI penetration-testing toolbox: exposes darkmoon_* MCP tools (50+ offensive tools behind a security gatekeeper + privacy gateway) and a pentest skill. Requires the Dark-Moon Docker backend running locally.",
  "author": { "name": "Dark-Moon" },
  "license": "see repository LICENSE",
  "keywords": ["security", "pentest", "mcp", "offensive-security"]
}
```

**Step 2:** Validate JSON: `python -c "import json;json.load(open('plugin/plugin.json'))"` — expected: no output, exit 0.

**Step 3:** Verify `name` matches `^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$` — `darkmoon` passes.

**Step 4:** Commit.
```bash
git add plugin/plugin.json
git commit -m "feat(plugin): add v1 plugin manifest"
```

---

### Task 3: Write `plugin/mcp.json` (streamable-http)

**Objective:** Point Hermes at the running Dark-Moon MCP HTTP endpoint.

**Files:**
- Create: `plugin/mcp.json`

**Step 1:** Write (top-level keys MUST be exactly `$schema` + `mcpServers`; loopback http is allowed):
```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "darkmoon": {
      "type": "streamable-http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

**Step 2:** Confirm the real path/port. Run `grep -n "streamable\|/mcp\|path=\|port" mcp/src/http_server.py mcp/src/server.py` and adjust `url` if FastMCP mounts the endpoint at something other than `/mcp` (FastMCP `http` transport default path is `/mcp/` — verify and match exactly, trailing slash included if required).

**Step 3:** Validate JSON: `python -c "import json;json.load(open('plugin/mcp.json'))"`.

**Step 4:** Commit.
```bash
git add plugin/mcp.json
git commit -m "feat(plugin): add v1 mcp.json pointing at darkmoon http endpoint"
```

---

### Task 4: Write `plugin/skills/darkmoon-pentest/SKILL.md`

**Objective:** Teach Hermes the contract for using Dark-Moon (only `darkmoon_*` tools, privacy rules, bring-up step).

**Files:**
- Create: `plugin/skills/darkmoon-pentest/SKILL.md`

**Step 1:** Write the file with frontmatter `name: darkmoon-pentest` (must equal dir name; matches `^(?!.*--)[a-z0-9]+(?:-[a-z0-9]+)*$`):
```
---
name: darkmoon-pentest
description: Drive the Dark-Moon autonomous pentest toolbox from Hermes. Brings up the Docker backend, then only calls darkmoon_* MCP tools behind the privacy gateway. Use for authorized security testing of a stated target.
---
# Dark-Moon Pentest

Use when the user wants an AI-driven penetration test / security assessment of
an explicitly authorized target (URL, IP, or range they own or are contracted
for).

## Before any tool call
1. Confirm the backend is up. If `curl -sf http://localhost:8000/health` fails,
   run `bash <plugin-root>/scripts/darkmoon-up.sh` (see references/bringup.md).
2. The MCP is the ONLY execution boundary. Never shell out to nmap/nuclei etc.
   directly from Hermes — only call `darkmoon_*` tools.

## Privacy rules (mandatory)
- The MCP tokenizes real IPs/hosts/creds to `IP_PRIVATE_001`-style placeholders
  before they reach the model. Never hardcode real targets/creds in prompts,
  tool args you craft, or reports — pass targets as parameters, let the gateway
  mask output.
- Credential-gated actions (aws/azure/gcloud/sql/docker/AD/k8s/Vault) require a
  found artifact or explicit user authorization — never infer.

## Workflow
- Start with `darkmoon_*` recon/workflow tools (see references/tool-catalog.md).
- Summarize findings to the user; write reports with tokenized placeholders.

See references/bringup.md and references/tool-catalog.md for detail.
```

**Step 2:** Verify the frontmatter name matches the directory: `grep -A1 '^---$' plugin/skills/darkmoon-pentest/SKILL.md` should show `name: darkmoon-pentest`.

**Step 3:** Commit.
```bash
git add plugin/skills/darkmoon-pentest/SKILL.md
git commit -m "feat(plugin): add darkmoon-pentest skill"
```

---

### Task 5: Write the two reference files

**Objective:** Give the skill its backend-bringup and tool-catalog detail (kept out of SKILL.md to stay under the description/context budget).

**Files:**
- Create: `plugin/skills/darkmoon-pentest/references/bringup.md`
- Create: `plugin/skills/darkmoon-pentest/references/tool-catalog.md`

**Step 1 — bringup.md:** Document the exact backend start, sourced from repo reality:
- x86_64 uses `docker-compose.yml` (prebuilt image), ARM64 uses `docker-compose-dev.yml` (local build) — do not swap.
- First run: `./install.sh` (interactive provider config, writes `.opencode.env`).
- Subsequent: `docker compose -f docker-compose.yml up -d` (or `--keep` semantics per install.sh).
- MCP HTTP endpoint is served by the `darkmoon-mcp` container running `python -m src.http_server` on `DARKMOON_MCP_PORT` (default 8000); env `DARKMOON_MCP_HOST`/`DARKMOON_MCP_PORT`.
- Health probe: `curl -sf http://localhost:8000/health`.
- Note the docker-proxy boundary: the MCP reaches Docker via `tcp://docker-proxy:2375`; never mount `/var/run/docker.sock` into the MCP.

**Step 2 — tool-catalog.md:** List the tool families from `mcp/src/server.py` / `docs/mcp.md`:
- Health & diagnostics: `darkmoon_health_check`, `darkmoon_check_tool` (confirm exact registered names by running the server and listing tools, or `grep -n "@mcp.tool" mcp/src/server.py`).
- Generic executor (2 tools), workflow discovery + execution (2 tools).
- Available workflows from `mcp/src/tools/workflows/`: `port_scan`, `subdomain_discovery`, `vulnerability_scan`, `web_crawler`, `ad_enumeration`, `kubernetes_audit`, `list_workflows`.
- Restate privacy placeholder rules.

**Step 3:** Confirm real tool names before finalizing: `grep -n "@mcp.tool\|def " mcp/src/server.py | head -40` and reconcile the catalog to the actual `darkmoon_*` names.

**Step 4:** Commit.
```bash
git add plugin/skills/darkmoon-pentest/references/
git commit -m "docs(plugin): add bringup and tool-catalog references"
```

---

### Task 6: Write `plugin/scripts/darkmoon-up.sh` and `darkmoon-down.sh`

**Objective:** One idempotent command to start the backend + MCP and print the URL the plugin expects; one to stop it.

**Files:**
- Create: `plugin/scripts/darkmoon-up.sh`
- Create: `plugin/scripts/darkmoon-down.sh`

**Step 1 — darkmoon-up.sh:** Resolve repo root relative to the script (`REPO="$(cd "$(dirname "$0")/../.." && pwd)"`), pick the compose file by arch (`uname -m`: `aarch64`/`arm64` → `docker-compose-dev.yml`, else `docker-compose.yml`), then:
```bash
#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"
case "$(uname -m)" in aarch64|arm64) CF=docker-compose-dev.yml;; *) CF=docker-compose.yml;; esac
[ -f .opencode.env ] || { echo "Run ./install.sh first (creates .opencode.env)"; exit 1; }
docker compose -f "$CF" up -d
# wait for MCP health
for i in $(seq 1 30); do
  curl -sf "http://localhost:${DARKMOON_MCP_PORT:-8000}/health" >/dev/null && break
  sleep 2
done
echo "Dark-Moon MCP ready at http://localhost:${DARKMOON_MCP_PORT:-8000}/mcp"
```

**Step 2 — darkmoon-down.sh:** Same REPO/arch resolution, then `docker compose -f "$CF" down`.

**Step 3:** `chmod +x plugin/scripts/*.sh`.

**Step 4:** Lint: `shellcheck -x plugin/scripts/darkmoon-up.sh plugin/scripts/darkmoon-down.sh` — expected: no errors (CI already runs shellcheck on repo scripts; match that bar).

**Step 5:** Commit.
```bash
git add plugin/scripts/
git commit -m "feat(plugin): add backend bring-up/down helper scripts"
```

---

### Task 7: Write `plugin/README.md`

**Objective:** End-user install/enable/use instructions.

**Files:**
- Create: `plugin/README.md`

**Step 1:** Cover: what it is; prerequisites (Docker + Compose v2, run `./install.sh` once); install (`hermes plugins install <git-url-or-path>`), then `hermes plugins enable darkmoon` (portable packages install disabled); start backend (`bash plugin/scripts/darkmoon-up.sh`); usage (ask Hermes to pentest an authorized target; the `darkmoon-pentest` skill loads the `darkmoon_*` tools); the privacy-gateway guarantee; legal/authorization warning.

**Step 2:** Commit.
```bash
git add plugin/README.md
git commit -m "docs(plugin): add end-user README"
```

---

### Task 8: Validate with the real runtime

**Objective:** Prove Hermes accepts the package before shipping.

**Step 1:** Run `hermes plugins doctor plugin/` — expected: manifest parses, skill discovered, mcp server entry translated, `OK: ... registration passed`. Fix any `ERROR:` findings (usually: `$schema` mismatch, `name`≠dir, mcp.json extra top-level key).

**Step 2:** Dry install from the local path: `hermes plugins install ./plugin --no-enable` then `hermes plugins list` — expected: `darkmoon` present, disabled.

**Step 3:** Enable: `hermes plugins enable darkmoon`; then `hermes plugins capabilities darkmoon` — expected: declares mcp + skill capabilities.

**Step 4:** With backend up (`bash plugin/scripts/darkmoon-up.sh`), start a Hermes session and confirm `darkmoon_*` tools are listed (`hermes tools | grep darkmoon` or in-session tool list) and one read-only tool (`darkmoon_health_check`) returns.

**Step 5:** Commit any doctor-driven fixes.
```bash
git add plugin/
git commit -m "fix(plugin): satisfy hermes plugins doctor"
```

---

## Files likely to change

- **New:** everything under `plugin/` (manifest, mcp.json, skill + references, scripts, README).
- **No changes** to `conf/`, `mcp/src/`, `docker-compose*.yml`, `install.sh`, `darkmoon.sh`, or existing tests — verify with `git status` that only `plugin/` is touched.
- Optional follow-up (separate PR, not this plan): add a `plugin/` mention to root `README.md` / `AGENTS.md` and a CI job running `hermes plugins doctor`.

## Tests / validation

- `python -c "import json; json.load(open(f))"` for both JSON files.
- `shellcheck -x plugin/scripts/*.sh`.
- `hermes plugins doctor plugin/` (authoritative runtime gate).
- Manual: install → enable → backend up → `darkmoon_health_check` round-trip.
- Repo regression gate unaffected, but run `bash tools/check-no-regression.sh` to confirm no invariant broke.

## Risks, tradeoffs, and open questions

- **Backend dependency:** the plugin is NOT self-contained — it needs the Docker stack running. This is inherent (50+ tools live in the toolbox container). Mitigated by `darkmoon-up.sh` + health-gated skill step.
- **Transport (OPEN QUESTION):** plan assumes `streamable-http` to `localhost:8000`. Confirm with user; alternative `stdio` would need the MCP process launched by Hermes with docker-proxy reachable, which is more coupling and risks the docker-socket boundary. Recommend http.
- **Endpoint path:** must confirm FastMCP's actual mount path (`/mcp` vs `/mcp/`) and that a `/health` route exists (Task 3 Step 2 / Task 8). If no `/health`, use a cheap MCP list call as the readiness probe instead.
- **Auth:** the local http endpoint is unauthenticated on loopback. Acceptable for localhost; if exposed beyond loopback the v1 schema forces https + the plugin would need headers — out of scope here.
- **Tool names:** catalog must be reconciled to real registered `darkmoon_*` names (Task 5 Step 3) — don't ship guessed names.
- **Distribution:** decide whether the plugin ships in-repo under `plugin/` (installed via path/Git URL) or as a separate repo. Plan assumes in-repo; a split repo is a later option.


