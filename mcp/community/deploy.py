"""Prepare auditable community cloud deployments; no action without --execute.

Requires an operator-hosted source archive and SHA-256. Archive publishing is a
separate action: this command never uploads code or pushes a Git branch.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import tarfile
from pathlib import Path
from urllib.parse import urlsplit


def bundle(repo, destination):
    repo = Path(repo).resolve()
    names = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]).decode().split("\0")
    with tarfile.open(destination, "w:gz") as archive:
        for name in sorted(set(names)):
            if not name or name.startswith(("docs/pics/", "shared/", "data/", "sessions/", "reports/", ".github/")):
                continue
            path = repo / name
            if path.resolve() == Path(destination).resolve():
                continue
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(repo):
                continue
            if any(part.startswith(".env") or part == ".opencode.env" or part in {".venv", "__pycache__", ".pytest_cache", ".git"} for part in path.parts):
                continue
            if path.suffix.lower() in {".key", ".pem", ".pfx", ".p12", ".pyc"}:
                continue
            archive.add(path, arcname=name, recursive=False)
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()


def cloud_init(source_url, sha256):
    parsed = urlsplit(source_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Source archive requires an HTTPS URL without embedded credentials")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
        raise ValueError("Expected a 64-character SHA-256")
    bootstrap = '''#!/usr/bin/env python3
import hashlib, io, os, pathlib, pwd, subprocess, tarfile, urllib.request
source_url = SOURCE_URL
expected = SOURCE_SHA
root = pathlib.Path('/opt/darkmoon')
root.mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(source_url, timeout=120) as response:
    content = response.read(64 * 1024 * 1024 + 1)
if len(content) > 64 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != expected:
    raise SystemExit('Source archive size or checksum verification failed')
with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as archive:
    if sum(m.size for m in archive.getmembers()) > 256 * 1024 * 1024:
        raise SystemExit('Expanded archive exceeds 256 MiB')
    archive.extractall(root, filter='data')
if not (root/'mcp/community/server.py').exists():
    raise SystemExit('Archive must have community source at its top level')
subprocess.run(['python3','-m','venv',str(root/'.venv')],check=True)
subprocess.run([str(root/'.venv/bin/python'),'-m','pip','install','-r',str(root/'mcp/community/requirements.txt')],check=True)
try:
    account = pwd.getpwnam('darkmoon')
except KeyError:
    subprocess.run(['useradd','--system','--home-dir',str(root),'--shell','/usr/sbin/nologin','--groups','docker','darkmoon'],check=True)
    account = pwd.getpwnam('darkmoon')
for path in [root, *root.rglob('*')]:
    os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)
os.chmod(root/'community.sh',0o755)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','docker','darkmoon-community'],check=True)
'''.replace("SOURCE_URL", repr(source_url)).replace("SOURCE_SHA", repr(sha256.lower()))
    unit = """[Unit]
Description=DarkMoon Community dashboard
After=network-online.target docker.service
Wants=network-online.target
[Service]
User=darkmoon
Group=darkmoon
SupplementaryGroups=docker
WorkingDirectory=/opt/darkmoon
Environment=DARKMOON_PYTHON=/opt/darkmoon/.venv/bin/python
Environment=HOME=/opt/darkmoon
ExecStart=/opt/darkmoon/community.sh --host 127.0.0.1 --port 8780
Restart=on-failure
RestartSec=5
KillMode=control-group
TimeoutStopSec=15
[Install]
WantedBy=multi-user.target
"""
    document = {"package_update": True, "packages": ["python3-venv", "git", "docker.io", "docker-compose-v2"],
                "write_files": [{"path": "/usr/local/sbin/darkmoon-bootstrap", "permissions": "0700", "content": bootstrap},
                                {"path": "/etc/systemd/system/darkmoon-community.service", "permissions": "0644", "content": unit}],
                "runcmd": [["python3", "/usr/local/sbin/darkmoon-bootstrap"]]}
    # JSON is valid YAML and avoids interpolating user strings into YAML syntax.
    return "#cloud-config\n" + json.dumps(document, indent=2) + "\n"


def provider_command(provider, config, user_data):
    def need(key):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip() or value.startswith("-") or "\x00" in value:
            raise ValueError(f"Provider config requires a non-empty {key}")
        return value
    name = config.get("name", "darkmoon-community")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,61}[a-z0-9]", name):
        raise ValueError("Invalid instance name")
    path = str(Path(user_data).resolve())
    if provider == "aws":
        return ["aws", "ec2", "run-instances", "--image-id", need("image"), "--instance-type", need("size"),
                "--subnet-id", need("subnet"), "--security-group-ids", need("security_group"), "--key-name", need("ssh_key"),
                "--count", "1", "--user-data", "file://"+path, "--tag-specifications",
                f"ResourceType=instance,Tags=[{{Key=Name,Value={name}}}]", "--metadata-options", "HttpTokens=required"]
    if provider == "gcp":
        return ["gcloud", "compute", "instances", "create", name, "--project", need("project"), "--zone", need("zone"),
                "--machine-type", need("size"), "--image-family", "ubuntu-2404-lts-amd64", "--image-project", "ubuntu-os-cloud",
                "--network", need("network"), "--metadata-from-file", "user-data="+path]
    if provider == "azure":
        return ["az", "vm", "create", "--resource-group", need("resource_group"), "--name", name, "--image", "Ubuntu2404",
                "--size", need("size"), "--admin-username", "ubuntu", "--ssh-key-values", need("ssh_public_key"),
                "--nsg", need("security_group"), "--custom-data", path, "--public-ip-sku", "Standard"]
    if provider == "ovh":
        return ["openstack", "server", "create", "--image", need("image"), "--flavor", need("size"),
                "--network", need("network"), "--key-name", need("ssh_key"), "--security-group", need("security_group"),
                "--user-data", path, name]
    raise ValueError("Unsupported provider")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    archive = sub.add_parser("bundle", help="Package current source, excluding runtime data and credentials")
    archive.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    archive.add_argument("--output", type=Path, required=True)
    plan = sub.add_parser("plan", help="Write cloud-init and a provider CLI plan; execution is opt-in")
    plan.add_argument("--provider", choices=("aws", "gcp", "azure", "ovh"), required=True)
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--source-url", required=True)
    plan.add_argument("--sha256", required=True)
    plan.add_argument("--output-dir", type=Path, required=True)
    plan.add_argument("--execute", action="store_true", help="Actually create the cloud VM using your configured cloud CLI")
    args = parser.parse_args(argv)
    if args.action == "bundle":
        print(bundle(args.repo, args.output))
        return
    content = cloud_init(args.source_url, args.sha256)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "cloud-init.json"
    command = provider_command(args.provider, json.loads(args.config.read_text()), path)
    path.write_text(content)
    (args.output_dir / "plan.json").write_text(json.dumps({"provider": args.provider, "argv": command,
        "dashboard": "127.0.0.1:8780 (SSH tunnel)", "engine_setup": "Run install.sh as darkmoon to configure LLM and build the agent stack",
        "executed": bool(args.execute)}, indent=2)+"\n")
    print(shlex.join(command))
    if args.execute:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
