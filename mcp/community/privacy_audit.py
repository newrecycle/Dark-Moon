"""Optional sealed privacy vault and metadata-only rehydration journal.

Used by community.guarded_mcp, without editing upstream privacy behavior.
No real value, command, payload, placeholder or credential is written to audit.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from api import json_storage as data
from src.privacy.vault import PrivacyVault, Category, _Entry
from .auth import private_key
from .store import Store, now


def append_audit(store, session_id, category, permitted):
    path = store.root / "privacy-audit.jsonl"
    key = private_key(store.root / "privacy-audit.key")
    with data._file_lock(path):
        previous, sequence = "0"*64, 0
        if path.exists() and path.stat().st_size:
            if path.stat().st_size > 64*1024*1024:
                raise ValueError("Privacy audit journal reached its limit; archive it before resuming")
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size-4096))
                last = json.loads(stream.read().splitlines()[-1])
            previous, sequence = last["mac"], last["seq"]
        event = {"seq": sequence+1, "at": now(), "operation": "rehydrate", "category": category,
                 "session_ref": hmac.new(key, str(session_id).encode(), hashlib.sha256).hexdigest()[:24],
                 "outcome": "allowed" if permitted else "denied", "previous": previous}
        payload = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
        event["mac"] = hmac.new(key, payload, hashlib.sha256).hexdigest()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as stream:
            stream.write(json.dumps(event, separators=(",", ":"))+"\n")
            stream.flush();os.fsync(stream.fileno())


def audit_summary(store):
    path = store.root / "privacy-audit.jsonl"
    if not path.exists():
        return {"enabled": False, "events": 0, "valid": None}
    key = private_key(store.root / "privacy-audit.key")
    previous, sequence, categories = "0"*64, 0, {}
    with data._file_lock(path), path.open() as stream:
        for line in stream:
            try:
                event = json.loads(line)
                signature = event.pop("mac")
                expected = hmac.new(key, json.dumps(event, separators=(",", ":"), sort_keys=True).encode(), hashlib.sha256).hexdigest()
                if event["previous"] != previous or event["seq"] != sequence+1 or not hmac.compare_digest(signature, expected):
                    return {"enabled": True, "events": sequence, "valid": False}
                previous, sequence = signature, event["seq"]
                categories[event["category"]] = categories.get(event["category"], 0)+1
            except (ValueError, KeyError, TypeError):
                return {"enabled": True, "events": sequence, "valid": False}
    return {"enabled": True, "events": sequence, "valid": True, "categories": categories,
            "scope": "Recorded local rehydrations only; this is not an assertion about all network egress"}


class SealedPrivacyVault(PrivacyVault):
    def __post_init__(self):
        super().__post_init__()
        self._seal_store = Store(os.environ.get("DARKMOON_VAULT_STATE_DIR"))
        self._seal_key = private_key(self._seal_store.root / "privacy-vault.key")
        name = hmac.new(self._seal_key, self.session_id.encode(), hashlib.sha256).hexdigest()
        self._seal_path = self._seal_store.root / "privacy-vaults" / (name+".sealed")
        self._seal_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with data._file_lock(self._seal_path):
            self._restore()

    def _restore(self):
        if not self._seal_path.exists():
            return
        content = self._seal_path.read_bytes()
        state = json.loads(AESGCM(self._seal_key).decrypt(content[:12], content[12:], self.session_id.encode()))
        import time
        if time.time()-state["created_at"] > self.ttl_seconds:
            return
        self._key = base64.b64decode(state["key"])
        self._hmac_key = base64.b64decode(state["hmac_key"])
        self._fernet_key = base64.urlsafe_b64encode(self._key)
        self._fernet = Fernet(self._fernet_key)
        self.created_at = state["created_at"]
        self._by_hash, self._by_ph = {}, {}
        for row in state["entries"]:
            entry = _Entry(row["placeholder"], base64.b64decode(row["ciphertext"]), Category(row["category"]))
            self._by_hash[row["fingerprint"]] = entry
            self._by_ph[entry.placeholder] = entry
        self._counters = {Category(k): v for k, v in state["counters"].items()}

    def _persist(self):
        state = {"key": base64.b64encode(self._key).decode(), "hmac_key": base64.b64encode(self._hmac_key).decode(),
                 "created_at": self.created_at, "counters": {k.value: v for k, v in self._counters.items()},
                 "entries": [{"fingerprint": fp, "placeholder": entry.placeholder, "ciphertext": base64.b64encode(entry.ciphertext).decode(),
                              "category": entry.category.value} for fp, entry in self._by_hash.items()]}
        nonce = secrets.token_bytes(12)
        content = nonce+AESGCM(self._seal_key).encrypt(nonce, json.dumps(state).encode(), self.session_id.encode())
        fd, temporary = tempfile.mkstemp(dir=self._seal_path.parent, prefix=".privacy-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary, self._seal_path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)

    def register(self, value, category):
        with data._file_lock(self._seal_path), self._lock:
            self._restore()
            result = super().register(value, category)
            self._persist()
            return result

    def rehydrate(self, placeholder, allow_secret=False):
        with data._file_lock(self._seal_path), self._lock:
            self._restore()
            result = super().rehydrate(placeholder, allow_secret)
            category = self.category_of(placeholder)
            append_audit(self._seal_store, self.session_id, category.value if category else "UNKNOWN", result is not None)
            return result

    def purge(self):
        with data._file_lock(self._seal_path), self._lock:
            super().purge()
            if self._seal_path.exists():self._seal_path.unlink()
