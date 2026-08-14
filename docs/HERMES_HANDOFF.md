# Dark-Moon ⇄ Hermes Handoff

This document is the integration contract between **Dark-Moon** (the autonomous
pentest toolbox) and **Hermes** (the LLM brain). It describes how the two fit
together, where the trust boundary sits, and what the plugin guarantees. It is
the canonical reference for anyone wiring Dark-Moon into a Hermes deployment.

> Audience: integrators and reviewers. For day-to-day usage, see
> [`plugin/README.md`](../plugin/README.md). For the broader Dark-Moon design,
> see [`docs/full.md`](./full.md) and [`docs/mcp.md`](./mcp.md).

---

## 1. Purpose

Dark-Moon never lets the model execute tools directly. Instead:

- **Hermes** is the brain: it reasons, plans, and decides. It runs on the host
  and is configured with its own provider credentials.
- **Dark-Moon** is the toolbox + gatekeeper: a single local Docker container
  that exposes `darkmoon_*` MCP tools over Streamable HTTP and executes them
  locally, behind a security gatekeeper and a privacy gateway.
- The **Dark-Moon plugin** is the glue that lives in the Hermes process: it
  prepares *isolated* pentest sessions, mints the authorization token, and
  scrubs everything that leaves the container before the model sees it.

The result is a single, auditable execution boundary (`darkmoon_*` MCP) with
the LLM brain fully outside it.

---

## 2. Architecture

```
        User
          │  authorized target, e.g. "pentest IP_PRIVATE_001"
          ▼
   ┌──────────────┐
   │   Hermes     │  brain on the host. No tool execution.
   │  (the brain) │  provider creds configured separately.
   └──────┬───────┘
          │  /darkmoon-pentest  (native slash command = secure trigger)
          ▼
   ┌──────────────────────────────────────────────────┐
   │  Dark-Moon plugin  (host-side trust boundary)      │
   │                                                    │
   │  darkmoon-pentest-command.sh                       │
   │     └─ mints a one-use capability token            │
   │  session_launcher.py                               │
   │     └─ isolated profile, redaction, group kill     │
   │  session_server.py  ── darkmoon-session MCP (stdio)│
   │  hermes_registration.py                            │
   │     └─ install / enable / skill registration       │
   └──────┬─────────────────────────┬───────────────────┘
          │ streamable-http         │ stdio
          ▼                         ▼
   ┌──────────────────┐     ┌──────────────────────────┐
   │ MCP: darkmoon    │     │ MCP: darkmoon-session     │
   │ :8000/mcp        │     │ host-side session launch  │
   └────────┬─────────┘     └──────────────────────────┘
            ▼
   ┌────────────────────────────────────────────────────┐
   │  Single `darkmoon` container (the toolbox)          │
   │   • MCP server: gatekeeper + privacy gateway        │
   │   • executes tools as LOCAL subprocesses             │
   │     (DARKMOON_EXEC_MODE=local)                      │
   │   • network_mode: host                              │
   │   • NO /var/run/docker.sock mount                  │
   └────────────────────────────────────────────────────┘
```

---

## 3. Components

| Component | Where | Role |
|-----------|-------|------|
| Hermes brain | host | Reasons and plans; owns provider credentials; never shells out to tools. |
| `darkmoon-pentest-command.sh` | plugin | Trusted slash-command dispatcher; mints the capability token **outside** the model's context. |
| `session_launcher.py` | plugin | Host-side trust boundary: validates the token, prepares the isolated profile, redacts output, kills the process group on timeout. |
| `session_server.py` | plugin | Host-side MCP facade (`darkmoon-session` server) for explicit start/resume of pentest sessions. |
| `hermes_session_runner.py` | plugin | Runs a resumable Hermes CLI turn with finite (stateless) delivery. |
| `hermes_registration.py` | plugin | Idempotent install/enable and skill registration; clean unregister. |
| `darkmoon` MCP server | container `:8000/mcp` | Gatekeeper + privacy gateway; runs the `darkmoon_*` toolbox tools locally. |
| `darkmoon` container | Docker | The only place tools execute. Single container, `network_mode: host`, no Docker socket. |

MCP servers are declared in `plugin/mcp.json`:

- **`darkmoon`** — Streamable HTTP at `http://localhost:8000/mcp`. The toolbox.
- **`darkmoon-session`** — stdio, launched via `scripts/darkmoon-session-mcp.sh`.
  The host-side session launcher.

---

## 4. Trust boundary & capability token

The authorization boundary is **not** the skill text — it is a cryptographic
capability token.

1. The user invokes the native `/darkmoon-pentest` slash command.
2. Hermes runs `darkmoon-pentest-command.sh` **directly**, outside the model's
   context.
3. The script calls `session_launcher issue-token`, which mints a **one-use,
   time-boxed** HMAC token (TTL ~120s) rooted in a per-install secret.
4. The token is passed to `session_launcher start --capability-token …`.
5. `session_launcher.consume_capability_token` verifies the HMAC and the
   single-use nonce, then — and only then — creates the isolated session.

Because the token is minted outside the model's reach and is consumed on first
use, an ordinary prompt that merely *asks* for a pentest cannot forge the
invocation. The skill instructions are guidance only; the token is the
enforcement.

---

## 5. Isolated pentest session model

Each `/darkmoon-pentest` invocation builds a **fresh, dedicated Hermes
profile** (`darkmoon-pentest`) and runs the assessment there — it never mutates
the invoking agent.

- **No inherited identity:** the profile does not load the parent's
  `AGENTS.md`/`SOUL.md`/`CLAUDE.md`/`.hermes.md`, memory, user-profile, rules,
  hooks, plugins, or prefills. `--ignore-rules` is mandatory on start and resume.
- **Credential allowlist only:** an explicit allowlist of provider/model
  credential keys is copied into the profile's `.env`. Terminal state, session
  routing, plugin settings, hooks, prefills, and identity-related variables are
  **never** copied. A denylist additionally blocks `TERMINAL_CWD`,
  `HERMES_SESSION_*`, `DOCKER_SOCK`, `KUBECONFIG`, `ASSUME_ROLE`, and similar.
- **Toolset:** the isolated session gets the DarkMoon MCP tools
  (`mcp__darkmoon__*`) plus Hermes delegation, and **no** unrelated parent MCP
  servers. Leaf children may receive the DarkMoon tools but not the delegation
  toolset, so they cannot fan out further.
- **Process-group isolation:** the nested Hermes turn runs as its own process
  group; on timeout the whole group is killed (SIGTERM then SIGKILL) so no
  orphaned child survives.
- **Redaction:** both `stdout` (the model-facing `response`) and `stderr`
  (diagnostics) are passed through `session_launcher._redact` before return —
  IPv4 **and** IPv6 addresses become `IP_REDACTED`, and `key=value`/`token=…`
  secrets are masked (validated with `ipaddress` so MAC addresses and hex dumps
  survive).

---

## 6. Tool & skill naming contract

- The Dark-Moon MCP server key is **`darkmoon`**, so its tools appear with the
  bare names `get_session`, `execute_command`, `list_workflows`, … and the
  stable client names `mcp__darkmoon__get_session`, etc. The `darkmoon_*` prefix
  is applied by the server key, not hardcoded per tool. Tests assert every
  registered tool matches the `darkmoon_*` wildcard.
- The session launcher lives on the **`darkmoon-session`** server:
  `mcp__darkmoon_session__start_pentest_session` and
  `mcp__darkmoon_session__resume_pentest_session`.
- **Slash skills** (`darkmoon-pentest`, `darkmoon-headless-browser`) exist for
  *discovery and guidance*. The actual authorization is the native slash
  command's capability token, not the skill body.

---

## 7. Privacy gateway

Two layers keep real values away from the model:

1. **Server-side tokenization (privacy gateway).** Real IPs/hosts/credentials
   are replaced with `IP_PRIVATE_001`-style placeholders before output leaves
   the container. Pass targets as tool parameters; do not hardcode them in
   prompts, tool args, or reports.
2. **Host-side redaction (defense in depth).** `session_launcher._redact`
   scrubs IPv4/IPv6 and secrets from everything returned to the model, as a
   second guard in case any value reaches the host side.

Credential-gated planes (`aws`/`azure`/`gcloud`/`sql`/`docker`/`AD`/`k8s`/`Vault`)
are dispatched only on a discovered artifact or explicit user authorization —
never on inference alone.

---

## 8. Install & run (recipe)

```bash
# 1. Host prerequisites
docker --version && docker compose version

# 2. One-time provider seed (writes .opencode.env, chmod 600)
./install.sh

# 3. Install + enable the plugin (idempotent; no Docker needed)
bash plugin/scripts/install.sh

# 4. Bring up the backend (MCP at http://localhost:8000/mcp)
bash plugin/scripts/darkmoon-up.sh

# 5. In a Hermes session, authorize a pentest:
#    "/darkmoon-pentest assess the host I own at IP_PRIVATE_001"
```

Reproducibility note: Hermes installs plugins from Git HEAD, so **commit your
changes before installing** — uncommitted/untracked files are not part of the
installed plugin.

---

## 9. Testing & reproducibility

| Layer | Command | Needs Docker? |
|-------|---------|---------------|
| Plugin unit (token, profile, redaction, group kill) | `python -m unittest tests.test_pentest_session_launcher` | No |
| Plugin manifest/registration/skills | `python -m unittest tests.test_hermes_plugin` | No |
| MCP unit (privacy gateway, local executor) | `cd mcp && uv run --with pytest --with pydantic --with fastmcp --with docker python -m pytest -q` | No |
| Single-container MCP round-trip | `bash tests/test_docker_mcp.sh` | Yes (builds `Dockerfile.mcp`) |
| Production stack (real toolbox + MCP) | `bash tests/test_production_stack.sh` | Yes (builds `tests/Dockerfile.toolbox-mcp`) |

The Docker integration fixtures **build the MCP image locally**
(`Dockerfile.mcp` for the protocol fixture; `tests/Dockerfile.toolbox-mcp`
layered onto the toolbox image for the production stack) so they do not depend
on a prebaked `newrecycle/darkmoon` image having the MCP server inside it. Both
fixtures remain a **single `darkmoon` container** — no `opencode`,
`darkmoon-mcp`, or `docker-proxy` sidecar is ever added.

---

## 10. References

- [`plugin/README.md`](../plugin/README.md) — usage, install, skills, file tree.
- [`plugin/plugin.json`](../plugin/plugin.json) — manifest (`name: darkmoon`,
  `version: 0.4.0`).
- [`plugin/mcp.json`](../plugin/mcp.json) — MCP endpoint definitions.
- [`docs/mcp.md`](./mcp.md) — the MCP security/execution boundary.
- [`docs/full.md`](./full.md) — full Dark-Moon design.
- [`docs/security-threat-model.md`](./security-threat-model.md) — threat model.
