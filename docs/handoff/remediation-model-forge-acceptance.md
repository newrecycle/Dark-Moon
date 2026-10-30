# Actual model, Docker and forge acceptance

This optional native gate uses an owned synthetic SQLite SQL-injection
application, a pinned Apache-2.0 CPU model and a disposable Gitea host. No
provider credential, commercial license, external assessment or external
repository is needed. It executes production generation, edit scope checks,
separate review requests, real offline Docker probes and explicit publication.

Generation and review use separately pinned model families and stateless
requests. This provides model diversity, not a security guarantee. A
positive verdict never substitutes for before/after probes or human merge review.

## Fresh checkout

Prerequisites: Linux, Docker engine, Git, OpenSSL, Python 3.12, build/download
network access, at least 12 GiB RAM and 20 GiB free disk; four CPU cores
recommended. Do not use a constrained production host.

From the repository root at the recorded pro revision:

~~~sh
python3.12 -m venv /tmp/darkmoon-analysis-venv
/tmp/darkmoon-analysis-venv/bin/pip install -r mcp/requirements.txt -r mcp/community/requirements.txt
python3.12 -m venv /tmp/darkmoon-model-venv
/tmp/darkmoon-model-venv/bin/pip install torch==2.9.0+cpu --index-url https://download.pytorch.org/whl/cpu
/tmp/darkmoon-model-venv/bin/pip install transformers==4.57.1
docker build -f tools/lab/Dockerfile -t darkmoon-ui-lab .
PYTHONPATH=mcp DARKMOON_NATIVE_MODEL_PYTHON=/tmp/darkmoon-model-venv/bin/python \
 /tmp/darkmoon-analysis-venv/bin/python tests/community/remediation_model_native.py
~~~

community-runtime.yml runs real SQLi/Docker/operator-reviewed publication on
pushes. Positive model acceptance is a separate explicit workflow_dispatch
input, model_acceptance=true, and retains native-model-forge.json. Its known
CPU-model rejection remains a failed acceptance result, never successful
publication. Resource-intensive model-quality checks do not replace the normal
native gate. Python 3.12 is explicitly selected. A --model-only run explicitly omits Docker/forge acceptance.

## Pins and isolation

Generator: Qwen/Qwen2.5-Coder-1.5B-Instruct at immutable revision
d18ecad881a290f0c792f1c2b5dbee1820d4a424. Reviewer:
Qwen/Qwen3-4B-Instruct-2507 at immutable revision
abcc171021d4f320b2e7f47c6f0deca67ded870c. Remote model code is disabled;
safetensors are required. The optional server uses bfloat16 generation, then unloads that model and
loads the reviewer, converting one Linear at a time to PyTorch per-channel dynamic int8, keeping remaining operations float32.
This avoids a full-model float32 copy and CPU bfloat16 emulation. Reports name
the quantization profile; it is still actual model inference, with no canned
patches or verdicts. Production has no bundled model and keeps its explicitly
configured endpoint/model contract.

Gitea 1.24.6 rootless is pinned by manifest digest in native_forge.py. It binds
only a random loopback HTTPS port. Its disposable certificate is explicitly
trusted with hostname validation; verification is never disabled. Actions,
mail, registration and outbound integrations are disabled. Synthetic credentials
are used only while that owned repository exists and are not printed. No real
notification or merge is requested. The uniquely named container/volumes and
private fixture files are removed on exit.

## Acceptance requirements

1. Actual generated edits must remain in app.py, apply exactly, and pass the
   unchanged production scope and model-verdict schema/confidence gates.
2. The owned exploit must work before and fail after; legitimate admin/visitor
   behavior must remain. Real production Sandbox containers run with no network.
3. A separate actual model review must reject a comment-only diff that leaves
   the injectable query intact. A false verdict is never flipped from its prose.
4. Production publication, with both required opt-ins, must perform a real Git
   push and create a PR in disposable Gitea.
5. Read the PR back: exact head SHA/ref, target main, open/unmerged, unchanged
   base and original working tree. Repeated publication must return the same PR;
   the actual forge must contain exactly one PR.

Success requires accepted:true, actual_generation_and_review:true,
negative_control_rejected:true, docker_probes:true and all forge checks true.
The bounded generated synthetic patch and both actual review verdicts are
retained. Malformed output, low confidence, rejection or failed probes fail.
No operator patch, approving fake response or validation substitute is supplied.

## Observed checkpoints

Actual operator-edit Docker acceptance passed in run 40946712274 and repeated
later runtime runs: validated, failed and missing-image outcomes are distinct.
All commercial runtime evidence remains unavailable.

Earlier small-model attempts were rejected rather than published: 0.5B edited
outside the source context (41005816146); 1.5B produced a parameter-binding
patch but its reviewer misread deleted lines or verdict semantics
(41006616041, 41006913818, 41007286594). The review prompt now explains unified
diff semantics and boolean/confidence meanings; no threshold or denial changed.
An unquantized 4B CPU response exceeded the 140-second generation budget and
was rejected as incomplete JSON (41007607590). The int8 4B model returned an invalid empty edit list for generation
(41008272319). The final profile separates the proven 1.5B generator from the
larger 4B reviewer. Both are actual pinned model calls; no response is repaired.
The initial two-model run also rejected the patch (41009036100). Review now
receives exact complete before/after contents for changed approved files,
read from the pinned base commit and worktree, bounded to 200,000 characters.
Unrelated source is excluded and exact whitespace is preserved. This removes
partial-diff ambiguity without weakening a verdict or probe gate. The CPU
review profile uses per-channel weight quantization. Run 41009928342 still rejected the valid patch at confidence .2 with full
source context. Positive automatic model-review acceptance therefore remains
OPEN for this CPU profile. No verdict is overridden, and these failed runs
remain evidence rather than successful acceptance.

A synthetic pass would establish this fixture/profile/forge only. It cannot
prove another application/model/adapter, deployed remediation, vendor runtime
equivalence or independently verified exploitation on a real assessment.


## Explicit independent review configuration

Production defaults to the existing generation endpoint/model for review.
To select independent review, set DARKMOON_REMEDIATION_JUDGE_MODEL, optionally
DARKMOON_REMEDIATION_JUDGE_BASE_URL and DARKMOON_REMEDIATION_JUDGE_API_KEY.
A model-only override uses the generation endpoint and credential unless a
review key is provided. An explicit review endpoint requires an explicit review
model and uses only its review key, including no Authorization header if absent;
the generator key is never forwarded to that explicitly selected endpoint.
Redirects remain denied for both stages. Offline transport tests cover these
credential boundaries. The native harness sets both model identities explicitly.


## Close the remaining positive-model evidence gap

A capable explicitly configured review endpoint is required to establish a
positive result; no such provider credential is available in this environment.
A fresh worker can reuse the identical owned fixture and strict gates, without
changing code or the expected verdict:

~~~sh
# Explicit operator choice; only this public synthetic application is submitted.
export DARKMOON_REMEDIATION_BASE_URL=https://GENERATOR/v1
export DARKMOON_REMEDIATION_MODEL=GENERATOR_MODEL
export DARKMOON_REMEDIATION_JUDGE_BASE_URL=https://REVIEWER/v1
export DARKMOON_REMEDIATION_JUDGE_MODEL=REVIEW_MODEL
# Supply each endpoint's own credential through the environment if required.
PYTHONPATH=mcp /tmp/darkmoon-analysis-venv/bin/python \
 tests/community/remediation_model_native.py --configured-models
~~~

Record provider/model revision and configuration with the report. Local
operator-controlled endpoints also work; paid providers are not required.
Require actual positive review >= .75, rejection of the unfixed negative
control, exploit/normal probes, and all actual forge assertions. A
--configured-models --model-only result cannot close Docker/forge acceptance.
Never change false to true, lower the threshold, stub a response, or claim this
gap closed from the separate operator-reviewed publication gate.


## Final native publication result

The always-on operator-reviewed SQLi/Docker/HTTPS forge gate passed in runtime
run 41011660161 on 18057c8. Artifact owned-lab-analysis (12958041662) contains
native-remediation.json. Run without model dependencies:

~~~sh
python3.12 -m venv /tmp/darkmoon-analysis-venv
/tmp/darkmoon-analysis-venv/bin/pip install -r mcp/requirements.txt -r mcp/community/requirements.txt
docker build -f tools/lab/Dockerfile -t darkmoon-ui-lab .
PYTHONPATH=mcp /tmp/darkmoon-analysis-venv/bin/python tests/community/remediation_native.py
~~~

Require native_docker:true and forge_publication:true, model_inference:false,
validated/validation_failed/unreproduced cases, and all forge checks true.
It proves actual exploit/variant blocking, preserved normal behavior,
container restrictions, real push/PR creation, exact head/base and idempotency.
The fixture uses a rootless Gitea container, executable ephemeral repository
mount for its generated hooks, explicit PR support/readiness and a trusted
local callback certificate. It creates no external repository or merge.

The separate positive model gate is still OPEN: CPU reviewers rejected the
genuine parameter-binding patch. Passing operator publication does not close
that gap, and making the model test manual does not turn its failed runs into
passes. Reuse --configured-models with a capable explicitly selected endpoint
and retain the strict positive/negative controls above to close it.


## Local follow-up — 30 October 2026

A fresh managed worker reran the existing operator-reviewed Docker/HTTPS Gitea
harness successfully: validated fix, rejected bad fix, unreproduced missing image,
and every actual forge check true. Model inference was false. The
[retained summary and exact commands](../validation/remediation-followup-2026-10-30/README.md)
include the initial fixture-permission failure and successful rerun.

This worker has no configured generation/review endpoint, model or credential;
its environment readiness reports no secret/runtime-variable bindings. Provider
hosts are absent from its enforced restricted network policy. The real
`--configured-models` preflight exited 3 with `NATIVE UNAVAILABLE`; it made no
inference or review call. No positive or negative model verdict was obtained.
A capable operator-selected endpoint/model, each required credential, and allowed
network access remain prerequisites. The automatic acceptance gap stays OPEN.
