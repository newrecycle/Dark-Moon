"""Owned-loopback TLS and hostname verification for signed webhook transport.

Generated certificates, patched DNS, no external socket or vendor binary.
"""
import json
import os
import socket
import ssl
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from community.operations import deliver_https, signed_headers

HOST = "receiver.example.invalid"


def cert(name, issuer, public_key, signing_key, ca=False, san=None):
    timestamp = datetime.now(timezone.utc)
    value = (x509.CertificateBuilder()
             .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
             .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer)]))
             .public_key(public_key)
             .serial_number(x509.random_serial_number())
             .not_valid_before(timestamp - timedelta(minutes=5))
             .not_valid_after(timestamp + timedelta(days=1))
             .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if san:
        value = value.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
    return value.sign(signing_key, hashes.SHA256())


class LoopbackTLS(unittest.TestCase):
    def check_delivery(self, server_hostname, should_accept):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            root_key = ec.generate_private_key(ec.SECP256R1())
            root = cert("Offline test CA", "Offline test CA", root_key.public_key(), root_key, ca=True)
            leaf_key = ec.generate_private_key(ec.SECP256R1())
            leaf = cert(server_hostname, "Offline test CA", leaf_key.public_key(), root_key, san=server_hostname)
            ca_file, cert_file, key_file = (folder / file for file in ("ca.pem", "leaf.pem", "key.pem"))
            ca_file.write_bytes(root.public_bytes(serialization.Encoding.PEM))
            cert_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
            key_file.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            requests = []
            class Receiver(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass
                def do_POST(self):
                    size = int(self.headers.get("Content-Length", "0"))
                    requests.append((self.path, self.rfile.read(size), self.headers["X-Darkmoon-Event-Id"]))
                    self.send_response(302)
                    self.send_header("Location", "https://never-follow.example.invalid/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
            server = HTTPServer(("127.0.0.1", 0), Receiver)
            server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_ssl.load_cert_chain(str(cert_file), str(key_file))
            server.socket = server_ssl.wrap_socket(server.socket, server_side=True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                original_context = ssl.create_default_context
                dns = []
                def trusted():
                    return original_context(cafile=str(ca_file))
                def pinned(host, port, *args, **kwargs):
                    dns.append(host)
                    if host not in (HOST, "127.0.0.1"):
                        raise AssertionError("Unexpected external DNS lookup")
                    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                             ("127.0.0.1", port))]
                body = json.dumps({"id": "evt_test_fixture", "event": "webhook.test"}).encode()
                headers = signed_headers("offline-strong-signing-secret-123456", body, "evt_test_fixture")
                with patch("community.operations.socket.getaddrinfo", side_effect=pinned), \
                     patch("community.operations.ssl.create_default_context", side_effect=trusted), \
                     patch.dict(os.environ, {"DARKMOON_WEBHOOK_ALLOWED_HOSTS": HOST}):
                    if should_accept:
                        self.assertEqual(deliver_https(f"https://{HOST}:{server.server_port}/fixture?secret=opaque",
                                                       body, headers), 302)
                    else:
                        with self.assertRaises(ssl.SSLCertVerificationError):
                            deliver_https(f"https://{HOST}:{server.server_port}/fixture", body, headers)
                self.assertNotIn("never-follow.example.invalid", dns)
                if should_accept:
                    self.assertEqual(requests, [("/fixture?secret=opaque", body, "evt_test_fixture")])
                else:
                    self.assertEqual(requests, [], "TLS rejection must occur before transmitting HTTP")
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=5)

    def test_expected_hostname_and_sni_verified_with_real_tls_handshake(self):
        self.check_delivery(HOST, True)

    def test_trusted_ca_but_wrong_hostname_is_rejected_before_body(self):
        self.check_delivery("different.example.invalid", False)
