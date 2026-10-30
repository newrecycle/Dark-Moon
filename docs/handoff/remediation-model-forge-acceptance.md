# Actual model and forge acceptance

This uses an owned synthetic SQLite SQL-injection application, a pinned public
CPU model and a disposable Gitea Docker host. No provider credential, commercial
license, external assessment or external repository is needed. It exercises
production generation, scope validation, independent review request, real
offline Docker probes and explicitly authorized publication. Both model calls
use the same weights in separate stateless requests; this is not independent
model diversity or a security guarantee.

Prerequisites: Linux, Docker engine, Git, OpenSSL, Python 3.11/3.12, internet for
pinned dependencies/model/image downloads, at least 7 GiB RAM and 8 GiB free
disk. Do not run on a constrained production host. All application/forge test
traffic is loopback; the forge's outbound integrations, actions and registration
are disabled. The script creates only its own ephemeral fixture and deletes it,
including its uniquely named Docker container/volumes. No real notifications or
merges are requested.

From a fresh checkout of pro at the recorded commit:

~~~sh
python3 -m venv /tmp/darkmoon-analysis-venv
/tmp/darkmoon-analysis-venv/bin/pip install -r mcp/requirements.txt -r mcp/community/requirements.txt
python3 -m venv /tmp/darkmoon-model-venv
/tmp/darkmoon-model-venv/bin/pip install torch==2.9.0+cpu --index-url https://download.pytorch.org/whl/cpu
/tmp/darkmoon-model-venv/bin/pip install transformers==4.57.1
docker build -f tools/lab/Dockerfile -t darkmoon-ui-lab .
PYTHONPATH=mcp DARKMOON_NATIVE_MODEL_PYTHON=/tmp/darkmoon-model-venv/bin/python \
 /tmp/darkmoon-analysis-venv/bin/python tests/community/remediation_model_native.py
~~~

The public model is Qwen/Qwen2.5-Coder-0.5B-Instruct at immutable revision
ea3f2471cf1b1f0db85067f1ef93848e38e88c25; remote model code is disabled.
Gitea 1.24.6 rootless is pinned by manifest digest in native_forge.py.
Its disposable certificate is explicitly trusted with hostname validation;
verification is never disabled. Publication requires both production opt-ins,
set only while the owned disposable repository exists. Synthetic credentials
are neither recorded in output nor used for any external account.

Success requires actual generated edits, a valid approving model verdict
(confidence >= .75), vulnerable-before/fixed-after exploit probes and preserved
normal behavior, followed by a real Git push and PR. The harness reads the PR
back and checks exact head SHA, target main, open/unmerged state, unchanged base
and original working tree, and one PR after a repeated publication call.
Malformed model output or rejected/failed validation fails; no fixture patches
or approving verdicts are substituted. The report must say accepted:true with
docker_probes:true and all forge checks true. A model-only run explicitly omits
container and forge acceptance and cannot close those requirements.

community-runtime.yml runs this in its existing owned-lab job and retains
native-model-forge.json, including failure disposition. Check the exact run SHA
before citing a pass. A successful synthetic acceptance is not proof for another
application, model, forge adapter, vendor runtime or real-world remediation.
The local model experiment lost its execution environment before completion;
no local generation/forge success is claimed. Hosted acceptance is pending.
