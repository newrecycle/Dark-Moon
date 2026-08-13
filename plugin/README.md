# Dark-Moon Hermes Plugin

A **portable Hermes Agent plugin** that exposes the Dark-Moon autonomous
pentest toolbox to Hermes:

- A set of **`darkmoon_*` MCP tools** (50+ offensive/defensive security tools
  behind a security gatekeeper + privacy gateway), served over MCP
  Streamable HTTP.
- A **`darkmoon-pentest` skill** that loads automatically when you ask for an
  authorized security assessment, and makes sure only `darkmoon_*` tools run.

The plugin itself is just the client/glue. It needs the **Dark-Moon Docker
backend** running locally to actually do anything. The helper scripts in
`scripts/` bring that backend up and down for you.

---

## What it is

| Piece | Where | Purpose |
|-------|-------|---------|
| MCP server | `http://localhost:8000/mcp` (Streamable HTTP) | The only execution boundary — runs the `darkmoon_*` tools. |
| Skill | `skills/darkmoon-pentest/` | Guides Hermes to bring up the backend and call only `darkmoon_*` tools. |
| Helper scripts | `scripts/darkmoon-up.sh`, `scripts/darkmoon-down.sh` | Arch-aware Docker bring-up / tear-down. |

The MCP reaches Docker through a `docker-proxy` sidecar (`tcp://docker-proxy:2375`).
**The plugin never mounts `/var/run/docker.sock`.** The scripts only ever run
`docker compose … up -d` / `down`.

---

## Prerequisites

- **Docker** and **Docker Compose v2** installed and on your `PATH`.
- Run `./install.sh` **once** from the repo root. It walks you through provider
  configuration and writes `.opencode.env` (with `chmod 600`). The `darkmoon-up.sh`
  script refuses to start the backend if `.opencode.env` is missing.

---

## Install the plugin

Portable plugin packages install **disabled** by default. Install, then enable:

```bash
# Install from a git URL or a local path:
hermes plugins install /home/justin/Dark-Moon/plugin
# or, for a published package:
hermes plugins install <git-url-or-local-path>

# Enable it (this is required — installs land disabled):
hermes plugins enable darkmoon
```

---

## Start / stop the backend

```bash
# Bring up the Docker stack (MCP at http://localhost:8000/mcp):
bash plugin/scripts/darkmoon-up.sh

# Stop it:
bash plugin/scripts/darkmoon-down.sh
```

`darkmoon-up.sh` picks the right compose file for your architecture automatically:

- **x86_64** → `docker-compose.yml` (pulls the prebuilt image).
- **ARM64** (`aarch64`/`arm64`) → `docker-compose-dev.yml` (local build).

Do not swap the two: the x86 file expects a prebuilt image that does not exist
on ARM, and the dev file on x86 defeats the prebuilt-image optimization.

### Readiness — there is **no** `/health` HTTP route

The backend does **not** expose an HTTP `/health` endpoint, so do not probe
`http://localhost:8000/health` (it gives a false negative). Readiness is
confirmed by:

- the `darkmoon_health_check` MCP tool (the correct way once the server is up), or
- a TCP probe of the `/mcp` port — `curl -s -o /dev/null http://localhost:8000/mcp`
  returning *any* HTTP response (including 4xx/406) proves the server is listening.

`darkmoon-up.sh` already does this port probe and prints
`Dark-Moon MCP ready at http://localhost:8000/mcp` when it succeeds.

---

## Usage

In a Hermes session, ask to pentest an **authorized** target, e.g.:
> "Run an authorized security assessment of the host I own at `IP_PRIVATE_001`."

The `darkmoon-pentest` skill loads and will:

1. Bring up the backend if needed (`darkmoon-up.sh`), then call `darkmoon_health_check`.
2. Discover workflows with `darkmoon_list_workflows`.
3. Run a chosen workflow with `darkmoon_run_workflow` (e.g. `port_scan`,
   `subdomain_discovery`, `vulnerability_scan`, `web_crawler`).
4. Use `darkmoon_execute_command` only for ad-hoc tool runs, still inside the gateway.

**The MCP is the ONLY execution boundary.** Hermes never shells out to
`nmap`/`nuclei`/etc. directly — it only calls `darkmoon_*` tools.

---

## Privacy gateway guarantee

The model **never sees real IPs, hostnames, or credentials**. Real values are
tokenized server-side to `IP_PRIVATE_001`-style placeholders before they reach
the model. Pass targets as tool parameters and let the gateway mask the output —
do not hardcode real targets/creds in prompts, tool args, or reports.

Credential-gated planes (`aws`/`azure`/`gcloud`/`sql`/`docker`/`AD`/`k8s`/`Vault`)
require a discovered artifact or explicit user authorization — they are never
dispatched on inference alone.

---

## Legal / authorization warning

> **Only test systems you own or are explicitly authorized to test.**
> Unauthorized scanning, probing, or exploitation is illegal. Obtain written
> authorization before running any assessment. The authors accept no liability
> for misuse of this tool.

---

## Files

```
plugin/
├── plugin.json            # plugin manifest (name, version, description)
├── mcp.json              # MCP Streamable-HTTP endpoint definition
├── README.md             # this file
├── scripts/
│   ├── darkmoon-up.sh    # arch-aware Docker bring-up + port probe
│   └── darkmoon-down.sh  # arch-aware Docker tear-down
└── skills/
    └── darkmoon-pentest/ # skill: bring up backend + use only darkmoon_* tools
```
