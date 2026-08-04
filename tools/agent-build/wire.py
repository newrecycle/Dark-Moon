#!/usr/bin/env python3
"""
Wire credential-gated sub-agent signals into a repo's pentest.md.

OpenCode automatically derives each agent identifier from its Markdown filename
and publishes all loaded subagents in the task tool definition. This script only
maintains Dark-Moon's routing signal matrix. It is newline-safe and idempotent.

These new planes are CREDENTIAL-GATED / POSITIVE-ARTIFACT ONLY (like kubernetes
and active-directory): never auto-dispatched on inference, only on a concrete
artifact (a leaked key, an exposed API/port, an operator-provided credential).
They are NOT web agents, so they are deliberately NOT added to the
headless-browser trigger list.

Usage: python3 wire.py <path-to-repo> [<path-to-repo> ...]
"""
import os
import sys

# (agent id, one-line positive-artifact trigger for the signal matrix)
NEW_AGENTS = [
    ("aws", "a leaked AKIA/ASIA key, an ~/.aws/credentials, an EC2/ECS IMDS (169.254.169.254) response, or operator-provided AWS credentials"),
    ("azure", "an az session, a service-principal id+secret, an Azure IMDS (169.254.169.254/metadata/identity) response, or an azureProfile.json"),
    ("entra-id", "a Microsoft Graph token, an app clientId+clientSecret, or a device-code session for the tenant"),
    ("gcp", "a service_account.json, a ya29./AIza token, a GCE metadata (metadata.google.internal) response, or a gcloud auth session"),
    ("github", "a ghp_/ghs_/github_pat_ token, an exposed .git/config with credentials, or a GitHub App installation token"),
    ("gitlab", "a glpat- token, a leaked CI/CD variable, or a runner registration token"),
    ("jenkins", "a reachable Jenkins URL (X-Jenkins header, /api/json, or a Jenkins login/Whitelabel banner) or provided Jenkins credentials"),
    ("terraform", "an exposed .tfstate / remote-state http backend, or an operator-provided Terraform/IaC repository"),
    ("ansible", "inventory/playbook/vault files, or an AWX/Automation-Controller URL plus a token"),
    ("docker", "an exposed Docker daemon socket (/var/run/docker.sock) or an unauthenticated Docker TCP API on 2375/2376"),
    ("container-registry", "a reachable OCI registry v2 API (/v2/ on Harbor/Quay/GHCR/GitLab/Artifactory/Nexus/ECR/ACR/GAR)"),
    ("hashicorp-vault", "a reachable $VAULT_ADDR/v1/sys/health, or a Vault token / AppRole / Kubernetes-auth material"),
    ("sql-databases", "a reachable database port (5432/3306/1433/1521) together with operator-provided or leaked credentials"),
    ("messaging-cache", "a reachable broker/cache port (Redis 6379, RabbitMQ 5672/15672, Kafka 9092, MQTT 1883, ActiveMQ 8161, ZooKeeper 2181)"),
]

SIGNAL_ANCHOR = "PHASE 3 — REACTIVE FEEDBACK LOOP (CORE MECHANISM)"


def detect_nl(raw_bytes):
    return "\r\n" if raw_bytes.count(b"\r\n") > 20 else "\n"


def read(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    nl = detect_nl(raw)
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return text, nl


def write(path, text, nl):
    data = text.replace("\n", nl).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)


def signal_section():
    lines = []
    add = lines.append
    add("=" * 80)
    add("PHASE 2b — CREDENTIAL-GATED PLANES (MANUAL / POSITIVE-ARTIFACT DISPATCH)")
    add("=" * 80)
    add("")
    add("The following planes are CLOUD / IDENTITY / CI-CD / IaC / SECRETS / DATA")
    add("planes. They are NEVER dispatched by inference and NEVER on the mere absence")
    add("of other-language markers. Each dispatches ONLY when a concrete POSITIVE")
    add("ARTIFACT names it — a leaked credential, an exposed API/port, or a scope")
    add("value the operator supplied. This mirrors the kubernetes / active-directory")
    add("manual-only doctrine and prevents false-positive dispatch (INC-010).")
    add("")
    add("Dispatch rule for every entry below:")
    add("  - If the operator supplied credentials/scope for the plane -> dispatch it.")
    add("  - Else if a parent agent surfaced the positive artifact listed -> dispatch it.")
    add("  - Else -> do NOT dispatch. Log 'Detected — Manual Authorization Required'")
    add("    in the report and continue. Never guess the plane from absence of signal.")
    add("These agents are NOT web agents: they do NOT trigger headless-browser.")
    add("")
    for aid, trigger in NEW_AGENTS:
        add("-" * 80)
        add(f"SIGNAL: {aid} plane present")
        add("-" * 80)
        add("POSITIVE ARTIFACT (any one; required — inference is NOT a signal):")
        add(f"    - {trigger}")
        add(f"DISPATCH: {aid}")
        add("DISPATCH MODE: CREDENTIAL-GATED / POSITIVE-ARTIFACT ONLY — flag but do not")
        add("    auto-dispatch unless the operator provided scope or the artifact fired.")
        add("CONTEXT PASS: target/endpoint, the credential or artifact source, discovered")
        add("    resource identifiers, and any downstream secrets to hand off.")
        add("")
    return "\n".join(lines)


def wire_pentest(path):
    text, nl = read(path)
    changed = False
    # Insert before the ==== fence that precedes PHASE 3.
    if "PHASE 2b — CREDENTIAL-GATED PLANES" not in text and SIGNAL_ANCHOR in text:
        idx = text.index(SIGNAL_ANCHOR)
        # back up to the start of the ==== fence line just above PHASE 3
        pre = text.rindex("\n" + "=" * 80, 0, idx)
        # pre points at the newline before the opening fence of PHASE 3's banner
        insert_at = pre + 1  # start of the fence line
        block = signal_section() + "\n\n"
        text = text[:insert_at] + block + text[insert_at:]
        changed = True
    if changed:
        write(path, text, nl)
    return changed


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    for repo in sys.argv[1:]:
        pm = os.path.join(repo, "conf", "agents", "pentest.md")
        c1 = wire_pentest(pm) if os.path.exists(pm) else None
        print(f"{os.path.basename(repo):24} pentest.md signals wired={c1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
