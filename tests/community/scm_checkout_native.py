"""Actual Git HTTPS checkout with synthetic SCM field credentials on loopback.

No provider, model, assessment, push or publication is invoked. Run with
PYTHONPATH=mcp:tests/community .venv/bin/python tests/community/scm_checkout_native.py
"""
import base64
import hmac
import ipaddress
import json
import os
import secrets
import ssl
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import test_community as fixtures
from community.source_checkout import checkout


def command(argv, **options):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, **options)
    if result.returncode:
        raise RuntimeError("Owned Git operation failed; output withheld")
    return result.stdout.decode().strip()


def main():
    fixture = fixtures.Fixture()
    fixture.setUp()
    server = None
    thread = None
    try:
        root = fixture.root
        seed = root / "seed"
        seed.mkdir()
        command(["git", "init", "-b", "main", str(seed)])
        (seed / "owned.txt").write_text("Owned HTTPS checkout acceptance\n")
        command(["git", "add", "owned.txt"], cwd=seed)
        command(["git", "-c", "user.name=Owned SCM fixture", "-c", "user.email=scm@example.invalid",
                 "commit", "-m", "Owned fixture"], cwd=seed)
        head = command(["git", "rev-parse", "HEAD"], cwd=seed)
        repos = root / "repositories"
        repos.mkdir()
        command(["git", "clone", "--bare", str(seed), str(repos / "owned.git")])
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Owned loopback SCM")])
        stamp = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(stamp - timedelta(minutes=1))
                .not_valid_after(stamp + timedelta(hours=1))
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(key, hashes.SHA256()))
        cert_path, key_path = root / "certificate.pem", root / "key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
        key_path.chmod(0o600)
        secret = secrets.token_urlsafe(32)
        state = {"username": "fixture", "secret": secret, "authorized": 0}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_git(self):
                expected = "Basic " + base64.b64encode((state["username"] + ":" + state["secret"]).encode()).decode()
                if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="Owned SCM fixture"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                state["authorized"] += 1
                parsed = urlsplit(self.path)
                if parsed.path not in ("/owned.git/info/refs", "/owned.git/git-upload-pack"):
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 1048576:
                    self.send_error(413)
                    return
                env = dict(os.environ, GIT_PROJECT_ROOT=str(repos), GIT_HTTP_EXPORT_ALL="1",
                           PATH_INFO=parsed.path, QUERY_STRING=parsed.query, REQUEST_METHOD=self.command,
                           CONTENT_TYPE=self.headers.get("Content-Type", ""), CONTENT_LENGTH=str(length),
                           REMOTE_USER="owned", REMOTE_ADDR="127.0.0.1")
                result = subprocess.run(["git", "http-backend"], input=self.rfile.read(length),
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, timeout=15)
                headers, separator, body = result.stdout.partition(b"\r\n\r\n")
                if result.returncode or not separator:
                    self.send_error(502)
                    return
                values = [line.decode().split(":", 1) for line in headers.split(b"\r\n") if b":" in line]
                status = next((int(value.strip().split()[0]) for key, value in values if key.lower() == "status"), 200)
                self.send_response(status)
                for header, value in values:
                    if header.lower() not in ("status", "content-length", "transfer-encoding", "connection"):
                        self.send_header(header, value.strip())
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = handle_git
            do_POST = handle_git

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "https://127.0.0.1:" + str(server.server_port)
        service = fixture.service
        service.accounts.create("native-scm", secrets.token_urlsafe(24), "admin")
        token = service.accounts.issue(service.store.get("users", "native-scm"))["token"]
        actor = service.identity("Bearer " + token)
        observations = []
        with patch.dict(os.environ, {"GIT_SSL_CAINFO": str(cert_path), "GIT_SSL_NO_VERIFY": "false", "GIT_CONFIG_GLOBAL": os.devnull,
                                     "GIT_CONFIG_SYSTEM": os.devnull}):
            for provider in ("github", "gitlab", "gitea", "gogs", "bitbucket", "azure_devops", "generic_git"):
                fields = {"token": secret, "endpoint_url": base + "/api"}
                state["username"] = "x-access-token" if provider in ("gitlab", "azure_devops") else "fixture"
                if provider not in ("gitlab", "azure_devops"):
                    fields["username"] = state["username"]
                row = service.vault.save({"provider": provider, "fields": fields}, actor=actor)
                destination = checkout(service, base + "/owned.git", "native_" + provider, row["id"], actor=actor)
                assert command(["git", "rev-parse", "HEAD"], cwd=destination) == head
                assert (destination / "owned.txt").read_text() == (seed / "owned.txt").read_text()
                service.vault.save({"revoked": True}, row["id"], actor=actor)
                before = state["authorized"]
                try:
                    checkout(service, base + "/owned.git", "native_" + provider, row["id"], actor=actor)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Revoked credential reused a cached checkout")
                assert state["authorized"] == before
                observations.append({"provider": provider, "exact_head": True, "exact_content": True,
                                     "revoked_cached_checkout_denied": True})
        report = {"tls_verification": True, "real_git_https": True, "loopback_only": True,
                  "authenticated_requests": state["authorized"], "providers": observations,
                  "scope": "Owned Git HTTP backend; does not establish vendor-host auth, PR or publication equivalence."}
        output = os.environ.get("DARKMOON_SCM_ACCEPTANCE_OUTPUT")
        if output:
            Path(output).write_text(json.dumps(report, indent=2) + "\n")
        print("PASS actual verified-TLS Git checkout for seven SCM field forms; exact HEAD/content and cached revocation denial")
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if thread:
            thread.join()
        fixture.tearDown()


if __name__ == "__main__":
    main()
