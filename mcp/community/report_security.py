"""AES-256 PDF encryption and an actual embedded CMS digital signature."""
import argparse
import datetime
import io
import os
import secrets
from pathlib import Path

from .store import Store


def init_signer(store, common_name, password):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID
    if not password or len(password) < 12:
        raise ValueError("Set DARKMOON_SIGNING_PASSWORD to a password of at least 12 characters")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(common_name)[:200])])
    current = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(current-datetime.timedelta(minutes=5))
            .not_valid_after(current+datetime.timedelta(days=730))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                        data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                                        encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    path = store.root / "report-signing.p12"
    content = pkcs12.serialize_key_and_certificates(b"DarkMoon report signer", key, cert, None,
                                                   serialization.BestAvailableEncryption(password.encode()))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
    public = store.root / "report-signing-cert.pem"
    public.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return {"pkcs12": str(path), "certificate": str(public), "self_signed": True,
            "note": "Operator signature; external trust requires your recipients to trust this certificate or supply a trusted signing chain"}


def secure_pdf(content, store, password=None, sign=True):
    if password is not None and (not isinstance(password, str) or not 12 <= len(password) <= 1024):
        raise ValueError("PDF password must be between 12 and 1024 characters")
    if password:
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        writer.clone_document_from_reader(PdfReader(io.BytesIO(content)))
        writer.encrypt(password, owner_password=secrets.token_urlsafe(48), algorithm="AES-256")
        target = io.BytesIO()
        writer.write(target)
        content = target.getvalue()
    if sign:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
        path = Path(os.environ.get("DARKMOON_SIGNING_P12", str(store.root / "report-signing.p12")))
        if not path.is_file():
            raise ValueError("Configure a PKCS#12 signer or initialize an operator signing certificate first")
        signer = signers.SimpleSigner.load_pkcs12(str(path), passphrase=os.environ.get("DARKMOON_SIGNING_PASSWORD", "").encode())
        if signer is None:
            raise ValueError("Signing certificate could not be loaded; verify its configured password")
        incremental = IncrementalPdfFileWriter(io.BytesIO(content))
        if password:
            incremental.encrypt(password)
        target = io.BytesIO()
        signers.sign_pdf(incremental, signers.PdfSignatureMetadata(field_name="DarkMoonReportSignature",
                         reason="Integrity of the recorded assessment evidence; human review required"), signer=signer, output=target)
        content = target.getvalue()
    return content


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init-signer",))
    parser.add_argument("--name", default="DarkMoon installation operator")
    parser.add_argument("--state-dir", type=Path)
    args = parser.parse_args(argv)
    import json
    print(json.dumps(init_signer(Store(args.state_dir), args.name, os.environ.get("DARKMOON_SIGNING_PASSWORD")), indent=2))


if __name__ == "__main__":
    main()
