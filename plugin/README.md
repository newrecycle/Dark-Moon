# Dark-Moon Hermes Plugin

A **portable Hermes plugin** that exposes the Dark-Moon autonomous pentest
toolbox to the Hermes LLM brain. It is the client/glue layer: the real work
happens in a single local Docker container that runs the `darkmoon_*` MCP tools
behind a security gatekeeper and a privacy gateway.

- **`darkmoon_*` MCP tools** — 50+ offensive/defensive security tools, served
  over MCP Streamable HTTP and executed **locally** inside the container.
- **`darkmoon-pentest` skill** — loads when you authorize a security
  assessment and makes sure only `darkmoon_*` tools run.
- **`darkmoon-headless-browser` skill** — bounded, privacy-safe headless
  browser agent (no host browser, no host filesystem).
- **Isolated pentest sessions** — an explicit `/darkmoon-pentest` invocation
  spins up a separate, hardened Hermes profile and runs the assessment there,
  never in the invoking agent.

> Version **0.4.0**. License **GPL-3.0-or-later**.

---

## Architecture

```
            User
              │  "pentest the host I own at IP_PRIVATE_001"
              ▼
        ┌──────────────┐
        │   Hermes     │   LLM brain (host). Owns the conversation,
        │   (brain)    │   never executes tools directly.
        └──────┬───────┘
               │  /darkmoon-pentest  (native slash command = secure trigger)
               ▼
        ┌─────────────────────────────────────────────┐
        │  Dark-Moon plugin (host-side trust boundary)  │
        │   • darkmoon-pentest-command.sh  mints token  │
        │   • session_launcher.py   isolated profile,   │
        │        redaction, process-group kill          │
        │   • session_server.py     darkmoon-session MCP│
        │   • hermes_registration.py  install/enable     │
        └──────┬──────────────────────────┬─────────────┘
               │ streamable-http           │ stdio
               ▼                           ▼
        ┌──────────────────────┐   ┌──────────────────────────┐
        │ MCP: darkmoon        │   │ MCP: darkmoon-session     │
        │ (localhost:8000/mcp) │   │ (host-side session launch)│
        └──────────┬───────────┘   └──────────────────────────┘
                   ▼
        ┌─────────────────────────────────────────────┐
        │  Single `darkmoon` container (toolbox)        │
        │   • MCP server (gatekeeper + privacy gateway) │
        │   • runs tools as LOCAL subprocesses          │
        │   • network_mode: host, NO docker.sock mount  │
        └─────────────────────────────────────────────┘
```

Two MCP servers are declared in `mcp.json`:

| Server | Transport | Purpose |
|---------|-----------|---------|
| `darkmoon` | Streamable HTTP `@ http://localhost:8000/mcp` | The toolbox: all `darkmoon_*` tools (gatekeeper + privacy gateway). |
| `darkmoon-session` | stdio (via `scripts/darkmoon-session-mcp.sh`) | Host-side session launcher: explicit start/resume of an isolated pentest session. |

The plugin itself does **not** run tools. It only prepares an isolated Hermes
session and talks to the container's MCP. **Neither the plugin nor the
container ever mounts `/var/run/docker.sock`** — the helper scripts only ever
run `docker compose … up -d` / `down`.

See [`docs/HERMES_HANDOFF.md`](../docs/HERMES_HANDOFF.md) for the full integration
contract (trust boundary, capability token, isolation model, naming).

---

## Prerequisites

- **Docker** and **Docker Compose v2** installed and on your `PATH`.
- Run `./install.sh` **once** from the repo root. It walks you through provider
  configuration and writes `.opencode.env` (with `chmod 600`). The backend
  bring-up script refuses to start if `.opencode.env` is missing.

> `.opencode.env` is the LLM provider seed (API keys for the toolbox's provider
> access and the preflight base URL). The Hermes brain on the host is configured
> separately. It is excluded from version control.

---

## Install the plugin

Portable plugin packages install **disabled** by default. Use the one-command
installer, which installs the *committed* plugin, enables it, registers its
skills for slash-command discovery, and is idempotent with no Docker required:

```bash
bash plugin/scripts/install.sh
```

> **Reproducibility:** Hermes installs plugins by cloning Git HEAD, so any
> uncommitted or untracked change is *not* part of the installed plugin. Commit
> your changes before installing. The installer warns (but does not fail) when
> the worktree is dirty.

Manual equivalent:

```bash
hermes plugins install /path/to/plugin   # or a git URL
hermes plugins enable darkmoon
bash plugin/scripts/setup-hermes-skills.sh
```

---

## Start / stop the backend

```bash
bash plugin/scripts/darkmoon-up.sh     # bring up; MCP at http://localhost:8000/mcp
bash plugin/scripts/darkmoon-down.sh   # tear down
```

`darkmoon-up.sh` picks the right compose file for your architecture:

- **x86_64** → `docker-compose.yml` (expects a prebuilt `ascit/darkmoon:local`).
- **ARM64** (`aarch64`/`arm64`) → `docker-compose-dev.yml` (local build).

Do not swap the two: the x86 file expects a prebuilt image that does not exist
on ARM, and the dev file on x86 defeats the prebuilt-image optimization.

### Readiness — there is **no** `/health` HTTP route

The backend does **not** expose an HTTP `/health` endpoint, so do not probe
`http://localhost:8000/health` (false negative). Confirm readiness via:

- the `darkmoon_health_check` MCP tool (the correct way once the server is up), or
- a TCP probe of the `/mcp` port — `curl -s -o /dev/null http://localhost:8000/mcp`
  returning *any* HTTP response (including 4xx/406) proves the server is listening.

`darkmoon-up.sh` already does this probe and prints
`Dark-Moon MCP ready at http://localhost:8000/mcp` on success.

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

## Privacy gateway & output redaction

The model **never sees real IPs, hostnames, or credentials**.

1. **Server-side tokenization (privacy gateway).** Real values are tokenized
   to `IP_PRIVATE_001`-style placeholders before they reach the model. Pass
   targets as tool parameters and let the gateway mask the output — do not
   hardcode real targets/creds in prompts, tool args, or reports.
2. **Host-side redaction (defense in depth).** Everything the plugin returns to
   the model is scrubbed by `session_launcher._redact`: IPv4 **and IPv6**
   addresses are replaced with `IP_REDACTED`, and `key=value`/`token=…` secret
   patterns are masked. IPv6 redaction is validated with the `ipaddress` module,
   so MAC addresses and hex dumps are **not** false-positive redacted.

Credential-gated planes (`aws`/`azure`/`gcloud`/`sql`/`docker`/`AD`/`k8s`/`Vault`)
require a discovered artifact or explicit user authorization — they are never
dispatched on inference alone.

---

## Pentest sessions (isolated, explicit invocation)

The `darkmoon-pentest` skill creates a **separate, fully isolated** Hermes
session. It never mutates the invoking agent.

**Trigger.** The secure trigger is the native `/darkmoon-pentest` slash command.
Hermes executes `scripts/darkmoon-pentest-command.sh` directly (outside the
model's context), which mints a one-use, time-boxed **capability token** and
starts the isolated session. An ordinary prompt that merely asks for a pentest
cannot create a session, because the model cannot see or forge that token.

**Isolation guarantee.** The new profile never copies or loads the invoking
agent's identity (`AGENTS.md`, `SOUL.md`, `CLAUDE.md`, `.hermes.md`, memory or
user-profile Markdown, repository rules). It clears inherited personality,
hooks, plugins, memory, user-profile, prefill, and external skill configuration,
and `--ignore-rules` is mandatory on start and resume. Only an **allowlist of
provider/model credentials** is copied into the profile's `.env`; terminal state,
session routing, plugin settings, hooks, prefills, and identity-related
variables are never copied. All Hermes session-routing, cron, and delegated-child
variables are stripped from the nested process.

**Toolset.** The isolated session is limited to the DarkMoon MCP tools
(`mcp__darkmoon__*`) plus Hermes delegation, and inherits no unrelated parent
MCP servers. The pentest main can delegate specialist work (e.g. headless
browser) to leaf children, which receive the DarkMoon tools but not the
delegation toolset.

**Resume.** Pass a prior DarkMoon pentest session ID to `/darkmoon-pentest` to
resume; the same session ID is preserved. The whole nested process group is
killed on timeout so no orphaned child is left behind.

**Portable skill namespaces vs. slash commands.** Hermes namespaces portable
plugin tools as `mcp__<server>__<tool>`; the session tools live on the
`darkmoon-session` server, so their stable names are
`mcp__darkmoon_session__start_pentest_session` and
`mcp__darkmoon_session__resume_pentest_session`. The parent-facing DarkMoon MCP
tools keep stable names such as `mcp__darkmoon__read_agent`. Slash *skills* are
for discovery; the actual authorization boundary is the native slash command's
capability token, not the skill instructions.

---

## Legal / authorization warning

> **Only test systems you own or are explicitly authorized to test.**
> Unauthorized scanning, probing, or exploitation is illegal. Obtain written
> authorization before running any assessment. The authors accept no liability
> for misuse of this tool.

---

## Uninstall

Remove only the DarkMoon-owned skills registration (leaving unrelated external
skill directories untouched):

```bash
python plugin/hermes_registration.py --plugin-root plugin --unregister
# then, if desired:
hermes plugins disable darkmoon
hermes plugins uninstall darkmoon
```

---

## Files

```
plugin/
├── plugin.json            # plugin manifest (name, version, description)
├── mcp.json              # MCP endpoint definitions (darkmoon + darkmoon-session)
├── README.md             # this file
├── session_launcher.py   # host-side trust boundary: capability token,
│                         #   isolated profile, output redaction, group kill
├── session_server.py     # host-side MCP facade (darkmoon-session server)
├── hermes_session_runner.py  # runs a resumable Hermes CLI turn (finite delivery)
├── hermes_registration.py # install/enable/unregister + skill registration
├── scripts/
│   ├── install.sh            # one-command install (idempotent)
│   ├── setup-hermes-skills.sh# register slash skills for discovery
│   ├── darkmoon-up.sh        # arch-aware Docker bring-up + port probe
│   ├── darkmoon-down.sh      # arch-aware Docker tear-down
│   ├── darkmoon-pentest-command.sh  # trusted /darkmoon-pentest dispatcher (token mint)
│   └── darkmoon-session-mcp.sh      # stdio wrapper for the darkmoon-session MCP
└── skills/
    ├── darkmoon-pentest/        # skill: bring up backend + use only darkmoon_* tools
    │   ├── SKILL.md
    │   └── references/
    │       ├── bringup.md       # backend bring-up contract
    │       └── tool-catalog.md  # available darkmoon_* tools
    └── darkmoon-headless-browser/  # bounded, host-safe headless browser skill
        └── SKILL.md
```

---

## Development & testing

- **Unit tests (no Docker):** `python -m unittest tests.test_pentest_session_launcher`
  (capability token, isolated profile, redaction incl. IPv6, process-group
  timeout) and `python -m unittest tests.test_hermes_plugin` (manifest,
  registration, skills).
- **MCP unit tests (no Docker):** `cd mcp && uv run --with pytest --with pydantic
  --with fastmcp --with docker python -m pytest -q` (privacy gateway, local
  executor).
- **Integration (Docker):** `bash tests/test_docker_mcp.sh` and
  `bash tests/test_production_stack.sh` build the MCP image **locally**
  (`Dockerfile.mcp` / `tests/Dockerfile.toolbox-mcp`) so they do not depend on a
  prebaked image.

See [`docs/HERMES_HANDOFF.md`](../docs/HERMES_HANDOFF.md) for the integration contract
and [`docs/mcp.md`](../docs/mcp.md) / [`docs/full.md`](../docs/full.md) for the broader
Dark-Moon design.
