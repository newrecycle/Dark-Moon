# Dark-Moon → Single-Container Hermes Plugin (v2, supersedes v1 topology)

> **For Hermes:** Execute via subagent-driven-development, fresh subagent per task, two-stage review. This v2 REPLACES the multi-container assumption in the v1 plan (2026-08-13_130640). The `plugin/` package built under v1 (plugin.json, mcp.json, skills, scripts, README) stays — only the backend topology and the bring-up wiring change.

**Goal:** Collapse the Dark-Moon stack from 5 containers to **1**. Drop `opencode`, `opencode-bootstrap`, and `docker-proxy`. The single `darkmoon` toolbox container also runs the Dark-Moon MCP server, which now executes tools **locally (subprocess)** instead of `docker exec`-ing through the proxy. Hermes (on the host) is the LLM brain and talks to the MCP over `http://localhost:8000/mcp`.

**Why this works cleanly:** the `darkmoon` service is `network_mode: host`, so an MCP bound to `127.0.0.1:8000` inside it is reachable from the host with NO port publishing — which is exactly the connectivity gap that surfaced during v1 validation (the old `darkmoon-mcp` container only exposed 8000 on the internal `control` network).

**Security note (explicit decision by user):** removing `docker-proxy` retires the socket-isolation boundary between the MCP and Docker. That boundary existed because the MCP ran in a *separate* container and needed mediated Docker access. With the MCP running *inside* the toolbox and executing locally, it no longer needs Docker access at all. The privacy gateway (server-side tokenization of IPs/hosts/creds) is unchanged and still shields the model.

**Tech stack:** Docker Compose v2, Python 3.12, FastMCP (`fastmcp==3.4.5`), unittest + node --test. Portable Agent Plugins v1 for the Hermes side.

---

## Current context (verified by reading the files)

- `mcp/src/docker_client.py` — `DarkmoonDockerClient` executes every command via `docker.from_env()` + `client.api.exec_create/exec_start` against the `darkmoon` container, wrapped in coreutils `timeout`, with live UNIX-socket broadcast, GPU pinning (reads `/run/darkmoon-gpu.env` FROM the container), and `_reap_survivors`. `health_check` runs `which naabu/nuclei/httpx/subfinder` + `df -h` inside the container.
- `mcp/src/server.py` — builds `docker_client = DarkmoonDockerClient(container_name=$DOCKER_CONTAINER_NAME, timeout=$DOCKER_TIMEOUT)` and passes it to `GenericExecutor`, `HealthChecker`, `WorkflowRegistry`. Tools registered bare; `darkmoon_` prefix comes from the MCP server key.
- `mcp/src/http_server.py` — `mcp.run(transport="http", host=$DARKMOON_MCP_HOST=0.0.0.0, port=8000, path=/mcp)`.
- `mcp/src/healthcheck.py` — FastMCP `Client` hits `http://127.0.0.1:8000/mcp`, asserts tools `{get_session, health_check, execute_command, list_workflows}` exist.
- `conf/entrypoint-darkmoon.sh` — toolbox entrypoint: GPU detection, writes `/run/darkmoon-gpu.env`, then `exec "$@"` (CMD is `sleep infinity`). Comment at line 16-18 explicitly notes the env file exists because `export` doesn't reach the MCP's `docker exec` children — after the merge the MCP is a child of this entrypoint, so `export` DOES reach it (simplification, keep the file for back-comat).
- `Dockerfile` — toolbox image; Python at `/opt/darkmoon/python` symlinked to `/usr/local/bin/python|pip`; ENTRYPOINT `/entrypoint-darkmoon.sh`, CMD `sleep infinity`. `mcp/` is NOT currently in this image.
- `Dockerfile.mcp` — the standalone MCP image (installs `requirements.lock`, copies `mcp/`, runs `python -m src.http_server`). After merge this image is retired (or kept only for the protocol test fixture).
- Tests that assert the OLD topology and MUST change: `tests/test_compose_security.py` (docker-proxy, opencode, bootstrap, socket-consumer set), `tests/docker-compose.mcp.yml` + `tests/test_docker_mcp.sh` (protocol fixture uses proxy), `tests/test_production_stack.sh` (full 5-container bootstrap), `tests/test_opencode_config.py` / `tests/test_darkmoon_compat.mjs` (opencode plugin/config — verify scope). Root `AGENTS.md`, `conf/README.md`, `conf/agents/pentest.md`, `docs/mcp.md`, `docs/opencode-1.18-runtime.md` reference the old topology (docs — update after code).

---

## Tasks

### Task R1: Local-subprocess executor (env-selected)

**Objective:** Add an executor that runs commands as local subprocesses inside the toolbox, with the SAME public surface as `DarkmoonDockerClient`, selected by an env flag. Zero behavior change when the flag is off.

**Files:**
- Create: `mcp/src/local_client.py`
- Modify: `mcp/src/server.py:27-38` (client selection)
- Test: `mcp/tests/test_local_client.py`

**Surface to mirror (used by callers `GenericExecutor`, `HealthChecker`, `WorkflowRegistry`):**
`execute_command(command, timeout=None, workdir=None, environment=None, session_id=None) -> ExecutionResult`, `check_tool_available(name) -> bool`, `get_disk_usage() -> dict|None`, `health_check() -> dict`, `cleanup()`. Preserve semantics: coreutils `timeout --kill-after=5 <n>` wrapper, exit 124/137 → `ExecutionStatus.TIMEOUT` with `remediation(...)`, the `adapt_command`/`_gpu_state` GPU pinning, `_reap_survivors` via `pkill`, and the `_broadcast` live stream. For local mode, `_gpu_state` reads `/run/darkmoon-gpu.env` from the LOCAL filesystem (it's in the same container now) and `os.environ`.

**Step 1 (RED):** In `mcp/tests/test_local_client.py`, write a test that a `LocalCommandClient().execute_command("echo hi", timeout=5)` returns `status==SUCCESS`, `exit_code==0`, `stdout` contains "hi". Add a timeout test: `execute_command("sleep 5", timeout=1)` returns `ExecutionStatus.TIMEOUT`. Run `cd mcp && python -m pytest tests/test_local_client.py -q` → expect FAIL (module missing).

**Step 2 (GREEN):** Implement `mcp/src/local_client.py`. Use `subprocess.Popen(["timeout","--kill-after=5",str(hard_timeout),"bash","-c",command], stdout=PIPE, stderr=STDOUT)`, stream chunks to `_broadcast`, decode+accumulate, map exit codes exactly like `docker_client.py`. Reuse `execution_guard.adapt_command/classify/effective_timeout/remediation` and `models.common.ExecutionResult/ExecutionStatus`. Import-guard the GPU env read.

**Step 3:** Wire selection in `server.py` (keep the variable name `docker_client` so downstream code is untouched):
```python
if os.getenv("DARKMOON_EXEC_MODE", "docker").lower() == "local":
    from src.local_client import LocalCommandClient
    docker_client = LocalCommandClient(timeout=int(os.getenv("DOCKER_TIMEOUT","300")))
else:
    docker_client = DarkmoonDockerClient(container_name=os.getenv("DOCKER_CONTAINER_NAME","darkmoon"), timeout=int(os.getenv("DOCKER_TIMEOUT","300")))
```

**Step 4 (GREEN):** `cd mcp && python -m pytest tests/test_local_client.py tests/test_privacy.py -q` → expect PASS. Then `python -m pytest -q` in mcp for no regressions.

**Step 5:** Commit `feat(mcp): add local-subprocess executor selectable via DARKMOON_EXEC_MODE=local`.

---

### Task R2: Bake MCP into the toolbox image + launch from entrypoint

**Objective:** The single `darkmoon` image carries the MCP server and starts it, while still working when `mcp/` is bind-mounted at runtime (the "do both" requirement).

**Files:**
- Modify: `Dockerfile` (add MCP install + copy near the end, before ENTRYPOINT at line 368)
- Modify: `conf/entrypoint-darkmoon.sh` (optionally launch the MCP)
- Modify: `Dockerfile` CMD (line 373)

**Step 1 (Dockerfile bake):** After the GPU/wordlist setup and before `COPY conf/entrypoint-darkmoon.sh`, add:
```dockerfile
# --- Dark-Moon MCP server (baked; runs in-container, executes tools locally) ---
COPY mcp/requirements.lock /opt/darkmoon/mcp/server/requirements.lock
RUN pip install --no-cache-dir --disable-pip-version-check --require-hashes \
      --requirement /opt/darkmoon/mcp/server/requirements.lock
COPY mcp/ /opt/darkmoon/mcp/server/
ENV DARKMOON_EXEC_MODE=local \
    DARKMOON_MCP_HOST=127.0.0.1 \
    DARKMOON_MCP_PORT=8000 \
    DARKMOON_MCP_PATH=/mcp \
    DARKMOON_MCP_AUTOSTART=1
EXPOSE 8000
```
(Use the existing `/usr/local/bin/pip` symlink → `/opt/darkmoon/python`. Verify the lock installs cleanly against Python 3.12 in this image.)

**Step 2 (entrypoint launch):** In `conf/entrypoint-darkmoon.sh`, before the final `exec "$@"`, add an autostart guard that launches the MCP from its server dir when enabled:
```bash
if [ "${DARKMOON_MCP_AUTOSTART:-0}" = "1" ]; then
  ( cd /opt/darkmoon/mcp/server && exec python -m src.http_server ) &
fi
```
Rationale: entrypoint already runs GPU detection and `export`s DM_GPU_* — as a parent of the MCP those exports now reach it directly. Keep `/run/darkmoon-gpu.env` too (back-compat + local_client reads it).

**Step 3:** Bind-mount path must match the baked path so runtime mounts override the baked copy: compose (Task R3) mounts the repo `./mcp` at `/opt/darkmoon/mcp/server`. Confirm `python -m src.http_server` resolves `src` from CWD `/opt/darkmoon/mcp/server`.

**Step 4 (verify, no full build):** `python -m py_compile conf/bootstrap.py mcp/src/http_server.py mcp/src/local_client.py`. `bash -n conf/entrypoint-darkmoon.sh` and `shellcheck -x conf/entrypoint-darkmoon.sh`. Full image build is validated in R6.

**Step 5:** Commit `feat(docker): bake Dark-Moon MCP into toolbox image and autostart from entrypoint`.

---

### Task R3: Collapse compose to a single service

**Objective:** `docker-compose.yml` and `docker-compose-dev.yml` define ONLY the `darkmoon` service (host network, MCP autostarts inside it). Remove `opencode`, `opencode-bootstrap`, `docker-proxy`.

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose-dev.yml`

**Step 1 (prod `docker-compose.yml`):** Keep only:
```yaml
name: darkmoon-stack
services:
  darkmoon:
    image: ascit/darkmoon:latest
    container_name: darkmoon
    user: "0:0"
    network_mode: host
    environment:
      DM_MODE: default
      DARKMOON_EXEC_MODE: local
      DARKMOON_MCP_AUTOSTART: "1"
      DARKMOON_MCP_HOST: 127.0.0.1
      DARKMOON_MCP_PORT: "8000"
      DARKMOON_MCP_PATH: /mcp
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ${HOME}/.kube:/root/.kube:ro
      - ${DARKMOON_REPORTS_DIR:-./reports}:/root/.local/share/opencode/reports:rw
      - ${DARKMOON_WORKFLOWS_DIR:-./workflows}:/opt/darkmoon/mcp/server/src/tools/workflows:rw
    cap_add: [NET_RAW, NET_ADMIN]
    healthcheck:
      test: ["CMD","python","-m","src.healthcheck"]
      interval: 10s
      timeout: 10s
      start_period: 20s
      retries: 12
    restart: unless-stopped
```
Note: healthcheck runs from image WORKDIR `/opt/darkmoon` — set `working_dir` or use `["CMD","bash","-lc","cd /opt/darkmoon/mcp/server && python -m src.healthcheck"]`. Decide and make it correct. Keep `/var/run/docker.sock` mount ONLY if the toolbox itself still needs Docker for any tool (it historically had it for host-net + docker tooling); if not needed, drop it too. Verify against `conf/agents/docker.md` usage before removing.

**Step 2 (dev `docker-compose-dev.yml`):** Same single service but with `build: {context: ., dockerfile: Dockerfile, network: host}`, `image: ascit/darkmoon:local`, and add the bind mount `- ./mcp:/opt/darkmoon/mcp/server:rw` so local code is live. Keep the arch rule intact (dev = local build).

**Step 3 (verify):** `docker compose -f docker-compose.yml config >/dev/null` and same for dev → expect exit 0.

**Step 4:** Commit `refactor(compose): collapse stack to single darkmoon container running the MCP`.

---

### Task R4: Update tests to the single-container topology

**Objective:** Make CI green for the new topology; retire assertions about the removed containers.

**Files:**
- Modify: `tests/test_compose_security.py`
- Modify: `tests/docker-compose.mcp.yml` + `tests/test_docker_mcp.sh`
- Modify: `tests/test_production_stack.sh`
- Check (scope): `tests/test_opencode_config.py`, `tests/test_darkmoon_compat.mjs`

**Step 1 — `test_compose_security.py`:** Replace `check_topology` with a single-service assertion: `darkmoon` exists; no `docker-proxy`/`opencode`/`opencode-bootstrap` services; the MCP env `DARKMOON_EXEC_MODE=local` + `DARKMOON_MCP_AUTOSTART` present; the healthcheck references `src.healthcheck`; the only docker.sock consumer is `darkmoon` (or none if we dropped the mount in R3). Keep `test_protocol_fixture_uses_the_same_proxy_controls` → rename to reflect the new fixture (no proxy). Keep `test_production_fixture_uses_one_model_contract` (model contract is unaffected; if it referenced opencode service, re-point to the new layout — it may belong to a separate R4 sub-step or be dropped if it was opencode-only).

**Step 2 — `docker-compose.mcp.yml` + `test_docker_mcp.sh`:** Rewrite the protocol fixture as a single `darkmoon` service (local exec + MCP). `test_docker_mcp.sh` asserts the MCP speaks the stock OpenCode protocol fixture over `http://localhost:8000/mcp` — keep the protocol assertion, change only how the stack comes up (no proxy).

**Step 3 — `test_production_stack.sh`:** Change from 5-container bootstrap to: bring up `darkmoon`, wait for healthcheck, `curl http://localhost:8000/mcp` responds, call `darkmoon_health_check`/`darkmoon_list_workflows`, assert real toolbox MCP works. Remove opencode-dependent assertions.

**Step 4 — scope check:** `test_opencode_config.py` and `test_darkmoon_compat.mjs` test the OpenCode plugin/config (`conf/plugins/darkmoon-compat.js`). With opencode gone, decide: (a) keep them but they now assert the Hermes mapping, or (b) move to a `SKIP`/rename. Default: KEEP `test_opencode_config.py` (still validates config rendering) but verify it doesn't depend on the live opencode service; `test_darkmoon_compat.mjs` tests the compat plugin — keep if it's hermetic, else mark skipped with a TODO to port to Hermes. Document the decision in the plan review.

**Step 5:** Run `python -m unittest -v tests.test_compose_security` → PASS. `bash tests/test_docker_mcp.sh` (needs Docker) — run if images available (R6). Commit `test(compose): update security + protocol + production tests to single-container topology`.

---

### Task R5: Point the plugin bring-up + docs at the single container

**Objective:** `plugin/scripts/darkmoon-up.sh` and the skill/README/bringup no longer start proxy/opencode; just `docker compose up -d` and the MCP autostarts.

**Files:**
- Modify: `plugin/scripts/darkmoon-up.sh`
- Modify: `plugin/skills/darkmoon-pentest/references/bringup.md`
- Modify: `plugin/skills/darkmoon-pentest/references/tool-catalog.md` (no docker-proxy mention)
- Modify: `plugin/README.md`

**Step 1 — `darkmoon-up.sh`:** Remove the docker-proxy boundary note. The readiness probe is unchanged (port 8000, path /mcp) — still valid because `darkmoon` is host-networked. Confirm `.opencode.env` is still required by `install.sh`; the script's guard stays. Add nothing new.

**Step 2 — `bringup.md`:** Update to: one container `darkmoon`; MCP autostarts via `DARKMOON_MCP_AUTOSTART`; no proxy; the `darkmoon` service runs network_mode host so `localhost:8000/mcp` is reachable. Remove credential-gated-via-proxy language; keep the docker.sock note only if R3 kept the mount.

**Step 3 — tool-catalog.md / README.md:** Drop docker-proxy references; state the MCP executes locally inside the toolbox (privacy gateway still masks outputs). README install/enable flow unchanged.

**Step 4:** `shellcheck -x plugin/scripts/darkmoon-up.sh` clean. Commit `docs(plugin): align bring-up docs with single-container topology`.

---

### Task R6: Validate end-to-end

**Objective:** Prove the merged stack works: unit tests, compose config, image build (dev), and a live `darkmoon_health_check` round-trip.

**Step 1 (unit, fast):** `cd mcp && python -m pytest -q` → PASS. `python -m unittest -v tests.test_compose_security` → PASS. `node --test tests/test_darkmoon_compat.mjs` → (see R4 scope decision). `bash tools/check-no-regression.sh` → PASS.

**Step 2 (compose config):** `docker compose -f docker-compose.yml config` and `-f docker-compose-dev.yml config` → exit 0.

**Step 3 (image build, dev — may be slow/large):** `docker compose -f docker-compose-dev.yml build` (local build of the merged image). If the build is infeasible in this environment (Go toolchain + 50+ tools, ~minutes–gigabytes), document the attempt and rely on config+unit validation; full prod build is the user's infra. MUST at least succeed at the MCP install layer: after bake, `pip` from `requirements.lock` resolves.

**Step 4 (live round-trip):** `bash plugin/scripts/darkmoon-up.sh` (brings up `darkmoon`, autostarts MCP). Then:
```bash
curl -s -o /dev/null -w "mcp HTTP %{http_code}\n" --max-time 5 http://localhost:8000/mcp
python3 - <<'PY'
import json,urllib.request,re
b=urllib.request.urlopen(urllib.request.Request("http://localhost:8000/mcp",
  data=json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"p","version":"0"}}}).encode(),
  headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"}),timeout=10).read().decode()
# then tools/list ...
PY
```
Confirm `darkmoon_health_check` is in the tool set and returns a health dict. This was the step that FAILED in v1 (port not published) — now it must pass.

**Step 5:** `hermes plugins doctor plugin/` still PASS. (Optional) re-copy `plugin/` into `~/.hermes/plugins/darkmoon` and `hermes plugins enable darkmoon`; start a Hermes session and confirm `darkmoon_*` tools appear and `darkmoon_health_check` returns.

**Step 6:** Commit any fixups `fix(plugin): final validation fixes for single-container layout`.

---

## Risks / trade-offs

- **Full prod image build is heavy** (Go toolchain + 50+ tools). I can validate MCP install + config + unit tests here; the complete `ascit/darkmoon:latest` rebuild is on the user's infra. The dev build (R6 Step 3) is the best available proxy.
- **docker.sock mount:** R3 must decide whether the toolbox still needs it. If a tool (e.g. `docker` recon, or host-networking tooling) needs Docker, keep the mount (it's the toolbox itself, not the MCP, so the proxy-retirement decision is unaffected). Verify against `conf/agents/docker.md` before dropping.
- **Healthcheck working_dir:** the compose `healthcheck` runs from image WORKDIR — must `cd` into the MCP server dir. Make it explicit so `src.healthcheck` imports resolve.
- **opencode-config tests:** `test_opencode_config.py`/`test_darkmoon_compat.mjs` may need scope decisions (R4 Step 4) — don't silently delete; document.
- **Back-compat:** `DARKMOON_EXEC_MODE` defaults to `docker`, so non-merged deployments (old 5-container) keep working until they adopt the new compose. The old `Dockerfile.mcp` can remain for the protocol fixture or be retired in R4.
- **Privacy unchanged:** `mcp/src/privacy/*` (gateway) is untouched; the model still only sees tokenized placeholders. Removing docker-proxy does NOT weaken this.



