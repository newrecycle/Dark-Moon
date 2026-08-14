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

The MCP server is **baked into the single `darkmoon` container** and runs tools
as **local subprocesses** (`DARKMOON_EXEC_MODE=local`) — there is no `docker-proxy`
sidecar. **Neither the plugin nor the container ever mounts `/var/run/docker.sock`.**
The scripts only ever run `docker compose … up -d` / `down` to bring the backend up.

---

## Prerequisites

- **Docker** and **Docker Compose v2** installed and on your `PATH`.
- Run `./install.sh` **once** from the repo root. It walks you through provider
  configuration and writes `.opencode.env` (with `chmod 600`). The `darkmoon-up.sh`
  script refuses to start the backend if `.opencode.env` is missing.

---

## Install the plugin

Portable plugin packages install **disabled** by default. Use the one-command
installer, which installs the *committed* plugin, enables it, and registers its
skills for slash-command discovery — all idempotent and with no Docker required:

```bash
bash plugin/scripts/install.sh
```

> **Note on reproducibility:** Hermes installs plugins by cloning Git HEAD, so any
> uncommitted or untracked change in the repository is *not* part of the installed
> plugin. Commit your changes before installing for a reproducible setup. The
> installer warns (but does not fail) when the worktree is dirty.

To install from a different checkout or a published package, point the installer
at the plugin directory, or run the equivalent steps by hand:

```bash
hermes plugins install /path/to/plugin   # or a git URL
hermes plugins enable darkmoon
bash plugin/scripts/setup-hermes-skills.sh
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

## Pentest sessions (isolated, explicit invocation)

The `darkmoon-pentest` skill creates a **separate, fully isolated** Hermes
session. It never mutates the invoking agent — it spins up a distinct
`darkmoon-pentest` profile and runs the pentest there.

**Trigger.** The secure trigger is the native `/darkmoon-pentest` slash command.
Hermes executes it directly (outside the model's context), which mints a
one-use, time-boxed **capability token** and starts the isolated session. An
ordinary prompt that merely asks for a pentest cannot create a session, because
the model cannot see or forge that token.

**Isolation guarantee.** The new profile never copies or loads the invoking
agent's identity (`AGENTS.md`, `SOUL.md`, `CLAUDE.md`, `.hermes.md`, memory or
user-profile Markdown, repository rules). It clears inherited personality,
hooks, plugins, memory, user-profile, prefill, and external skill configuration,
and `--ignore-rules` is mandatory on start and resume. The only environment
carried over is an **allowlist of provider/model credentials** copied into the
profile's `.env`; terminal state, session routing, plugin settings, hooks,
prefills, and identity-related variables are never copied. All Hermes
session-routing, cron, and delegated-child variables are stripped from the
nested process. The canonical DarkMoon `pentest` identity is loaded
server-side and its body is never returned or logged — only its fingerprint and
byte count are reported.

**Toolset.** The isolated session is limited to the DarkMoon MCP tools
(`mcp__darkmoon__*`) plus Hermes delegation, and inherits no unrelated parent
MCP servers. The pentest main can delegate specialist work (e.g. headless
browser) to leaf children, which receive the DarkMoon tools but not the
delegation toolset.

**Resume.** Pass a prior DarkMoon pentest session ID to `/darkmoon-pentest` to
resume; the same session ID is preserved.

**Portable skill namespaces vs. slash commands.** Hermes namespaces portable
plugin tools as `mcp__<server>__<tool>`; the session tools live on the
`darkmoon-session` server, so their stable names are
`mcp__darkmoon_session__start_pentest_session` and
`mcp__darkmoon_session__resume_pentest_session`. The parent-facing DarkMoon MCP
tools keep stable names such as `mcp__darkmoon__read_agent`. Slash *skills* are
for discovery; the actual authorization boundary is the native slash command's
capability token, not the skill instructions.

## Uninstall

Remove only the DarkMoon-owned skills registration (leaving unrelated external
skill directories untouched):

```bash
python plugin/hermes_registration.py --plugin-root plugin --unregister
# then, if desired:
hermes plugins disable darkmoon
hermes plugins uninstall darkmoon
```

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
