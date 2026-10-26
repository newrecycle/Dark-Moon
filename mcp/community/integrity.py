"""Operator-owned integrity baseline, encrypted state and local diagnostics.

No vendor activation, hardware-bound licence key or anti-debugging restriction.
The operator can inspect/reseal their own installation after reviewing changes.
"""
import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

from api import json_storage as data
from .auth import private_key
from .store import Store, now


def baseline(repo, store, files=None):
    repo = Path(repo).resolve()
    if files is None:
        files = [str(p.relative_to(repo)) for p in (repo / "mcp/community").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        files += [p for p in ("docker-compose.yml", "docker-compose.community-hardened.yml", "darkmoon.sh", "community.sh", "conf/entrypoint-opencode.sh") if (repo/p).is_file()]
    result = {}
    for name in files:
        path = (repo/name).resolve()
        if not path.is_relative_to(repo) or not path.is_file():
            raise ValueError("Integrity paths must be source files within the installation")
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"created_at": now(), "files": result}
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    key = private_key(store.root / "integrity.key")
    data._write_json(store.root / "integrity.json", {"manifest": manifest, "signature": hmac.new(key, payload, hashlib.sha256).hexdigest()})
    marker = store.root / "integrity-locked"
    if marker.exists():
        marker.unlink()
    return {"sealed": True, "files": len(result)}


def verify(repo, store):
    path, marker = store.root / "integrity.json", store.root / "integrity-locked"
    if not path.exists():
        return {"ok": False, "configured": False, "locked": marker.exists(), "mismatches": [], "reason": "No reviewed integrity baseline"}
    try:
        record = data._read_json(path)
        if not isinstance(record, dict) or not isinstance(record.get("manifest", {}).get("files"), dict):
            raise ValueError("Invalid integrity manifest")
    except (ValueError, TypeError, AttributeError):
        marker.write_text("Integrity manifest is invalid; review and explicitly reseal\n")
        return {"ok": False, "configured": True, "locked": True, "mismatches": ["manifest-format"]}
    payload = json.dumps(record.get("manifest", {}), sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(private_key(store.root / "integrity.key"), payload, hashlib.sha256).hexdigest()
    mismatches = []
    if not hmac.compare_digest(expected, str(record.get("signature", ""))):
        mismatches.append("manifest-signature")
    root = Path(repo).resolve()
    for name, digest in record.get("manifest", {}).get("files", {}).items():
        target = (root/name).resolve()
        if not target.is_relative_to(root) or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            mismatches.append(name)
    if mismatches:
        marker.write_text("Integrity mismatch; review files and explicitly reseal\n")
        os.chmod(marker, 0o600)
    return {"ok": not mismatches and not marker.exists(), "configured": True, "locked": marker.exists(), "mismatches": mismatches}


def seal_state(store, source, destination, decrypt=False):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    cipher = AESGCM(private_key(store.root / "sealed-state.key"))
    content = Path(source).read_bytes()
    if decrypt:
        if not content.startswith(b"DMSEALED1"):
            raise ValueError("Unknown sealed state format")
        result = cipher.decrypt(content[9:21], content[21:], b"DarkMoon community state v1")
    else:
        nonce = secrets.token_bytes(12)
        result = b"DMSEALED1"+nonce+cipher.encrypt(nonce, content, b"DarkMoon community state v1")
    destination = Path(destination)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(result)
    return {"written": str(destination), "encrypted": not decrypt}


def doctor(repo, store):
    modules = {n: bool(importlib.util.find_spec(n)) for n in ("reportlab", "cryptography", "jwt", "pyhanko", "pypdf")}
    return {"data_dir": str(data.DATA_DIR), "reports_dir": str(data.REPORTS_DIR), "state_private": store.root.stat().st_mode & 0o077 == 0,
            "launcher_exists": (Path(repo)/"darkmoon.sh").is_file(), "docker_cli": bool(shutil.which("docker")),
            "dependencies": modules, "integrity": verify(repo, store),
            "repairs": ["Install requirements with your workspace Python", "Configure the existing agent stack before launching assessments"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("doctor", "seal", "verify", "encrypt-state", "decrypt-state"))
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repair", action="store_true", help="Repair only owned state permissions/directories; never clear an integrity lock")
    args = parser.parse_args(argv)
    store = Store(args.state_dir)
    if args.action == "doctor":
        if args.repair:
            os.chmod(store.root, 0o700)
            for name in ("logs", "remediation", "privacy-vaults"):
                directory = store.root/name
                directory.mkdir(exist_ok=True, mode=0o700)
                os.chmod(directory, 0o700)
            for file in store.root.iterdir():
                if file.is_file() and (file.suffix == ".key" or file.name in {"access-token", "state.json", "report-signing.p12"}):
                    os.chmod(file, 0o600)
        result = doctor(args.repo, store)
    elif args.action == "seal":
        result = baseline(args.repo, store)
    elif args.action == "verify":
        result = verify(args.repo, store)
    else:
        if not args.input or not args.output:
            parser.error("State encryption/decryption requires --input and --output")
        result = seal_state(store, args.input, args.output, args.action == "decrypt-state")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
