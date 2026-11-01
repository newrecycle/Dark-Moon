# Focused acceptance capture

This runner produces **new** private observations for remaining gaps. It cannot
recover old capture bytes/hashes. Default selection excludes previously used
successful auth, trend, seven-provider SCM, durable-webhook and direct-link
captures, broad status sweeps and failed harness fixtures. `--plan` explains
selection; duplicate `--only` entries execute once.

```sh
.venv/bin/python tools/acceptance/capture.py --plan
.venv/bin/python tools/acceptance/capture.py \
  --config /private/endpoints.json --out /private/new-run
```

Use a NEW output path outside the repository. The directory is0700, files0600.
`captures.jsonl` contains actual request bodies and response bytes/headers/JSON;
it is PRIVATE, not a sanitized export. Bearer request headers are omitted.
`body_sha256`, per-line hashes and `manifest.json` preserve provenance. Summary
records source revision/dirty state, selected scenarios, boundaries and outcomes.
Response bodies may contain secrets; never upload them to public CI or Git.
Redirects are recorded but never followed, remote HTTP is rejected, normal
proxy/CA settings are honored, response reads are bounded. SSE windows retain
received frames and explicitly record incomplete observation windows.

## Existing authorized endpoints

Copy `config.example.json` outside Git and set tokens through its named
environment variables. URLs are origins, not `/api/v1` prefixes. The runner adds
the exact paths. HTTPS certificate verification is always enabled.

```json
{
  "reference": {
    "url": "http://127.0.0.1:8000",
    "token_env": "REFERENCE_CAPTURE_TOKEN",
    "target_id": "OWNED_TARGET_ID",
    "event_cursor": 0
  },
  "fork": {
    "url": "http://127.0.0.1:8780",
    "token_env": "FORK_CAPTURE_TOKEN",
    "target_id": "OWNED_TARGET_ID",
    "event_cursor": 0
  }
}
```

For a network-isolated existing reference container add
`"container":"darkmoon-capture-NAME"` to `reference`. URL remains container
loopback. Transport uses `docker exec -i`, user10001 and the normal app Python
`/opt/darkmoon/mcp/server/.venv/bin/python3`; override `user`/`python` only for a
different legitimate deployment. The stdlib wire client runs inside the
container; the host Docker socket is never mounted into it. Tokens travel over
stdin, not process arguments. Obtain tokens via normal authorized login; the
runner does not mint sessions or bypass authentication.

## Disposable local fork and synthetic history

In one terminal:

```sh
.venv/bin/python tools/acceptance/local_fork.py --state /private/new-fork
```

It prints the config path, starts the normal service/workers, and creates three
synthetic campaigns/findings with normal producers. No scan or model is run.
In another terminal, read `/private/new-fork/token` into `FORK_CAPTURE_TOKEN`
without printing it, then merge its `config.json` fork section into your private
endpoint config. Ctrl-C stops the service; private state remains for inspection.

For a disposable reference container, create an equivalent owned synthetic
cohort through its normal producers (no edits to vendor modules):

```sh
docker exec -i --user 10001 --workdir /opt/darkmoon/mcp/server \
  darkmoon-capture-NAME /opt/darkmoon/mcp/server/.venv/bin/python3 \
  < tools/acceptance/seed_cohort.py > /private/reference-cohort.json
```

Use returned `target_id`. This seed uses a unique namespace and retains IDs;
remove the disposable runtime after evidence review. It does not claim a real
assessment or a mutation journal. For event replay choose a retained cursor with
actual producer events. Empty/expired cohorts return unavailable, not a pass.

## Prepare and start a restricted reference

Use a legitimately prepared image with its normal guarded entrypoint. Private
image/installer inputs belong in the private handoff, never this repository.
The handoff includes a separate helper to reconstruct those supplied inputs
without executing its installer and to audit the resulting image. The public
launcher starts the prepared image only:

```sh
.venv/bin/python tools/acceptance/reference_container.py start \
  --image AUTHORIZED_IMAGE --policy /private/original-policy.yml \
  --state /private/new-reference --name darkmoon-capture-NAME
```

The container uses network none, read-only root, required writable tmpfs areas,
four owned persistent volumes, no-new-privileges, NET_RAW dropped, no additional
capabilities, no host socket and no published ports. Entrypoint/command are not
overridden. The receipt says **started_not_health_verified**: inspect normal
health/login before capture. Missing licensing/startup is a blocker, not a reason
to patch the guard. Only a synthetic JWT secret is configured for this disposable
runtime; no session is fabricated. After review:

```sh
.venv/bin/python tools/acceptance/reference_container.py stop \
  --receipt /private/new-reference/receipt.json
```

Cleanup verifies ownership and the exact container ID, removes only its container
and four owned volumes, and retains image/private files. Do not run general prune.

## Scenario scope and explicit native commands

| Selection | What runs | What it does not establish |
|---|---|---|
| `scheduler` | Three disabled future schedules, default interval, set3, change type, readback, delete owned IDs | Actual dispatch, DST/month arithmetic |
| `history` | Three populated owned-target pages | Historic journal equivalence, unrecorded mutations |
| `events` | Bounded poll, next cursor, filter, unknown cursor and SSE window | Cold restart, eviction, completed scan |
| `logs` | Existing owned run log pages/detail, requires `run_id` | Successful engine run or raw-evidence access |
| `publication` | Actual populated collection/detail/finding lookup, provider/state | New publication, multi-finding pipeline equivalence |
| `native-publication` | Existing operator-edit Docker/Gitea workflow plus fork HTTP capture | Model generation or reference pipeline equivalence |
| `configured-model` | Existing configured production model/review/probes/Gitea harness | Other applications/models or vendor pipeline equivalence |

For `publication`, add per-side `publication` with `provenance:"actual_pipeline"`,
`campaign_id`, `finding_id`, `pr_id`. IDs must come from a real production result;
this declared provenance is a precondition, not independent pipeline proof.
Do not seed successful result flags. For fresh actual fork proof instead run:

```sh
python3 tools/acceptance/bootstrap.py native-image
.venv/bin/python tools/acceptance/capture.py \
  --only native-publication --out /private/new-native
```

The existing fixture retains its original positive/negative/missing-image tests;
its observer only reads real HTTP projection after actual publication. This
closes the previously uncaptured post-fix projection, not global acceptance.
Gitea is pinned in `tests/community/native_forge.py`, bound to loopback HTTPS,
with verified certificates and a disposable repository; no external PR is opened.

Model acceptance is never selected by default. Configure
`DARKMOON_REMEDIATION_BASE_URL`, `DARKMOON_REMEDIATION_MODEL`, optional
`DARKMOON_REMEDIATION_API_KEY`, and separate
`DARKMOON_REMEDIATION_JUDGE_BASE_URL`, `DARKMOON_REMEDIATION_JUDGE_MODEL`,
`DARKMOON_REMEDIATION_JUDGE_API_KEY` when appropriate. See
[the detailed model runbook](../../docs/handoff/remediation-model-forge-acceptance.md).

```sh
.venv/bin/python tools/acceptance/capture.py \
  --only configured-model --out /private/new-model-run
```

Usually3 model requests, at most5 with the default retry. Normal development and
default captures make zero. There is no automatic retry after review rejection.

Exit0: requested checks observed; exit1: at least one failed; exit3: missing
prerequisites. Every report sets full_reference_acceptance:false. Review actual
response values/intentional differences before closing a task; observed pages
alone are not semantic parity. Keep failed runs rather than rewriting them.

### Private DeepSeek configuration

The private handoff includes `private/secrets/deepseek.json`. Fill its `api_key`
locally; never commit it. Leave `model` blank to require a unique current Flash
alias from the provider's authenticated `/models` response. No alias is guessed
or silently replaced. Empty/ambiguous lists block the run. The same selected
model receives separate generation and review requests unless `review_model`
names another offered model. This is separate requests, not model diversity.

```sh
.venv/bin/python tools/acceptance/model_run.py \
  --config /private/secrets/deepseek.json --out /private/first-model-acceptance \
  --reason initial-ready
```

**Run once when tooling is ready. Rerun only for relevant remediation/model
changes or failure investigation. NEVER run on every commit.** Subsequent runs
require the explicit reason `relevant-change` or `failure-investigation` and a
new output directory. The wrapper makes one model-list request, followed by the
usual3 (up to5) inference requests. Key values stay in the private file/process
environment and are not logged by the wrapper or placed in process arguments.
