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

community-runtime.yml executes this in its existing owned-lab job, with Python
3.12 explicitly selected, and retains native-model-forge.json. Failures remain
failures. A --model-only run explicitly omits Docker/forge acceptance.

## Pins and isolation

Generator: Qwen/Qwen2.5-Coder-1.5B-Instruct at immutable revision
d18ecad881a290f0c792f1c2b5dbee1820d4a424. Reviewer:
Qwen/Qwen3-4B-Instruct-2507 at immutable revision
abcc171021d4f320b2e7f47c6f0deca67ded870c. Remote model code is disabled;
safetensors are required. The optional server uses bfloat16 generation, then unloads that model and
loads the reviewer, converting one Linear at a time to PyTorch dynamic int8, keeping remaining operations float32.
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
The two-model profile and negative control are pending hosted execution. These failed attempts remain evidence,
not successful acceptance.

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
