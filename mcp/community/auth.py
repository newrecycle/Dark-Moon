"""Local accounts, revocable short-lived JWTs, OIDC and encrypted credentials."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from api import json_storage as data
from .store import identifier, now


def private_key(path, length=32):
    path = Path(path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        os.chmod(path, 0o600)
        return path.read_bytes()
    value = secrets.token_bytes(length)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
    return value


class CredentialVault:
    def __init__(self, store):
        from cryptography.fernet import Fernet
        self.store = store
        key = os.environ.get("DARKMOON_SECRET_KEY")
        self.box = Fernet(key.encode() if key else base64.urlsafe_b64encode(private_key(store.root / "vault.key")))

    def save(self, raw, credential_id=None, *, internal=False):
        secret = raw.get("secret")
        if not isinstance(secret, str) or not 1 <= len(secret) <= 65536:
            raise ValueError("A non-empty secret is required (at most 64 KiB)")
        credential_id = identifier(credential_id) if credential_id else "cred_" + uuid.uuid4().hex[:16]
        item = {"id": credential_id, "name": str(raw.get("name", "Credential"))[:160],
                "provider": str(raw.get("provider", "generic"))[:80], "username": str(raw.get("username", ""))[:160],
                "sealed": self.box.encrypt(secret.encode()).decode(), "hint": "********", "created_at": now()}
        if internal:
            item["internal"] = True
        self.store.save("credentials", item)
        return self.public(item)

    @staticmethod
    def public(item):
        # Explicit allowlist: never forward extension fields or internal secrets.
        from .credential_catalog import capabilities
        def string(key):
            value = item.get(key)
            return value if isinstance(value, str) else ""
        return {"id": string("id"), "name": string("name"),
                "provider": string("provider"), "username": string("username"),
                "created_at": string("created_at"), "hint": "********",
                "set": bool(item.get("sealed")), "capabilities": capabilities(item)}

    def list(self, capability=None):
        from .credential_catalog import allows, check_capability
        check_capability(capability)
        records = sorted(self.store.items("credentials"), key=lambda row: str(row.get("id", "")))
        return [self.public(item) for item in records if allows(item, capability)]

    def get(self, credential_id, capability=None):
        from .credential_catalog import allows
        item = self.store.get("credentials", identifier(credential_id))
        if not item or not allows(item, capability):
            raise KeyError("Credential not found")
        return self.public(item)

    def require(self, credential_id, capability):
        # Even a guessed internal webhook signing key is not selectable.
        self.get(credential_id, capability)
        return identifier(credential_id)

    def resolve(self, credential_id):
        item = self.store.get("credentials", identifier(credential_id))
        if not item:
            raise KeyError(credential_id)
        return self.box.decrypt(item["sealed"].encode()).decode()

    def delete(self, credential_id):
        def change(state):
            if state.setdefault("credentials", {}).pop(identifier(credential_id), None) is None:
                raise KeyError(credential_id)
            return {"deleted": credential_id}
        return self.store.update(change)


class Accounts:
    def __init__(self, store):
        self.store = store
        self.key = private_key(store.root / "session.key")
        self.failures = {}
        self.guard = threading.Lock()
        self.oidc_flows = {}
        password = os.environ.get("DARKMOON_ADMIN_PASSWORD")
        if password and not self.store.items("users"):
            self.create(os.environ.get("DARKMOON_ADMIN_USERNAME", "admin"), password, "admin")

    def create(self, username, password, role="viewer", *, initial=False):
        identifier(username)
        if role not in {"admin", "analyst", "viewer"}:
            raise ValueError("Role must be admin, analyst or viewer")
        if not isinstance(password, str) or not 12 <= len(password) <= 1024:
            raise ValueError("Password must be between 12 and 1024 characters")
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
        user = {"id": username, "username": username, "role": role, "salt": salt, "password_hash": digest,
                "auth_version": 1, "created_at": now(), "must_change_password": False}
        def create(state):
            users = state.setdefault("users", {})
            if initial and users:
                raise ValueError("Initial account setup is already complete")
            if username in users:
                raise ValueError("Username already exists")
            users[username] = user
            return self.public(user)
        return self.store.update(create)

    @staticmethod
    def public(user):
        return {k: user[k] for k in ("id", "username", "role", "created_at", "must_change_password") if k in user} | {"authentication": "password" if user.get("password_hash") else "oidc" if user.get("provider") == "oidc" else "unknown"}

    def issue(self, user):
        import jwt
        timestamp = int(time.time())
        session = {"id": "session_" + uuid.uuid4().hex, "user_id": user["id"], "expires_at": timestamp + 3600}
        self.store.save("sessions", session)
        token = jwt.encode({"sub": user["id"], "jti": session["id"], "iat": timestamp, "exp": timestamp+3600,
                            "iss": "darkmoon-community", "aud": "darkmoon-api", "ver": user.get("auth_version", 1)}, self.key, algorithm="HS256")
        return {"token": token, "access_token": token, "token_type": "bearer", "expires_in": 3600,
                "must_change_password": False, "user": self.public(user)}

    def login(self, username, password, client):
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 1024:
            raise ValueError("Username and password are required")
        # Bound attacker-controlled rate-limit keys by client, not username.
        timestamp = time.time()
        with self.guard:
            self.failures = {k: v for k, v in self.failures.items() if v[0] > timestamp-900}
            attempts = self.failures.get(client, (timestamp, 0))
            if attempts[1] >= 10:
                raise PermissionError("Too many failed login attempts; retry in 15 minutes")
        user = self.store.get("users", username) if username and len(username) <= 200 else None
        salt = bytes.fromhex(user["salt"]) if user and user.get("salt") else b"darkmoon-dummy-salt"
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000).hex()
        if not user or not hmac.compare_digest(digest, user.get("password_hash", "")):
            with self.guard:
                self.failures[client] = (attempts[0], attempts[1]+1)
            raise PermissionError("Invalid username or password")
        with self.guard:
            self.failures.pop(client, None)
        return self.issue(user)

    def identity(self, token):
        import jwt
        try:
            claims = jwt.decode(token, self.key, algorithms=["HS256"], audience="darkmoon-api", issuer="darkmoon-community",
                                options={"require": ["exp", "iat", "sub", "jti", "ver"]})
            user = self.store.get("users", claims["sub"])
            session = self.store.get("sessions", claims["jti"])
            if not user or not session or claims["ver"] != user.get("auth_version", 1):
                return None
            return self.public(user) | {"session_id": claims["jti"]}
        except (jwt.PyJWTError, ValueError, KeyError):
            return None

    def logout(self, identity):
        self.store.update(lambda state: state.setdefault("sessions", {}).pop(identity.get("session_id"), None))

    def password(self, identity, old, new, *, renew=False):
        if not isinstance(old, str) or not isinstance(new, str):
            raise ValueError("Current and new passwords must be strings")
        if not 12 <= len(new) <= 1024:
            raise ValueError("Password must be between 12 and 1024 characters")
        def rotate(state):
            user = state.get("users", {}).get(identity["id"])
            if not user or not user.get("salt"):
                raise ValueError("This identity does not use a local password; create a local account or manage it at your SSO provider")
            digest = hashlib.pbkdf2_hmac("sha256", old.encode(), bytes.fromhex(user["salt"]), 600000).hex()
            if not hmac.compare_digest(digest, user["password_hash"]):
                raise PermissionError("Current password is incorrect")
            user["salt"] = secrets.token_hex(16)
            user["password_hash"] = hashlib.pbkdf2_hmac("sha256", new.encode(), bytes.fromhex(user["salt"]), 600000).hex()
            user["auth_version"] = user.get("auth_version", 1)+1
            # Verify and rotate inside the same transaction: concurrent changes
            # cannot both validate the old hash or reuse an auth version.
            return user
        updated = self.store.update(rotate)
        if renew:
            # Bind the replacement token to THIS rotation's version. A later
            # rotation revokes it even if session issuance happens afterwards.
            return self.issue(updated) | {"changed": True, "reauthenticate": False, "message": "Password updated"}
        return {"changed": True, "reauthenticate": True}

    def oidc_config(self):
        issuer = os.environ.get("DARKMOON_OIDC_ISSUER", "").rstrip("/")
        client = os.environ.get("DARKMOON_OIDC_CLIENT_ID", "")
        redirect = os.environ.get("DARKMOON_OIDC_REDIRECT_URI", "")
        return {"enabled": bool(issuer and client and redirect), "issuer": issuer, "client_id": client, "redirect_uri": redirect}

    @staticmethod
    def json_request(url, body=None):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                return None
        request = urllib.request.Request(url, data=urllib.parse.urlencode(body).encode() if body is not None else None,
                                         headers={"Accept": "application/json"})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            content = response.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError("OIDC response too large")
        return json.loads(content)

    def oidc_begin(self):
        config = self.oidc_config()
        if not config["enabled"] or not config["issuer"].startswith("https://"):
            raise ValueError("Configure an HTTPS OIDC issuer, client id and redirect URI")
        metadata = self.json_request(config["issuer"] + "/.well-known/openid-configuration")
        if metadata.get("issuer") != config["issuer"]:
            raise ValueError("OIDC issuer metadata mismatch")
        for endpoint in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not str(metadata.get(endpoint, "")).startswith("https://"):
                raise ValueError("OIDC endpoints must use HTTPS")
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        with self.guard:
            self.oidc_flows = {k: v for k, v in self.oidc_flows.items() if v["expires"] > time.time()}
            if len(self.oidc_flows) >= 512:
                raise ValueError("Too many pending sign-in flows; retry later")
            self.oidc_flows[state] = {"expires": time.time()+300, "nonce": nonce, "verifier": verifier, "metadata": metadata}
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        query = {"response_type": "code", "client_id": config["client_id"], "redirect_uri": config["redirect_uri"],
                 "scope": "openid profile email", "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
        return {"url": metadata["authorization_endpoint"] + "?" + urllib.parse.urlencode(query), "state": state}

    def oidc_finish(self, code, state):
        import jwt
        with self.guard:
            flow = self.oidc_flows.pop(str(state), None)
        if not flow or flow["expires"] < time.time():
            raise PermissionError("OIDC state is invalid, expired or already used")
        config = self.oidc_config()
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": config["redirect_uri"],
                "client_id": config["client_id"], "code_verifier": flow["verifier"]}
        if os.environ.get("DARKMOON_OIDC_CLIENT_SECRET"):
            form["client_secret"] = os.environ["DARKMOON_OIDC_CLIENT_SECRET"]
        result = self.json_request(flow["metadata"]["token_endpoint"], form)
        key = jwt.PyJWKClient(flow["metadata"]["jwks_uri"]).get_signing_key_from_jwt(result["id_token"]).key
        claims = jwt.decode(result["id_token"], key, algorithms=["RS256", "ES256"], audience=config["client_id"],
                            issuer=config["issuer"], options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]})
        if not hmac.compare_digest(claims["nonce"], flow["nonce"]):
            raise PermissionError("OIDC nonce mismatch")
        if (claims.get("azp") and claims["azp"] != config["client_id"]) or (isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and claims.get("azp") != config["client_id"]):
            raise PermissionError("OIDC authorized party does not match this client")
        subject = str(claims["sub"])
        user_id = "oidc_" + hashlib.sha256((config["issuer"]+"\0"+subject).encode()).hexdigest()[:32]
        admins = os.environ.get("DARKMOON_OIDC_ADMIN_SUBS", "").split(",")
        analysts = os.environ.get("DARKMOON_OIDC_ANALYST_SUBS", "").split(",")
        role = "admin" if subject in admins else "analyst" if subject in analysts else "viewer"
        user = {"id": user_id, "username": str(claims.get("preferred_username", subject))[:160], "role": role,
                "created_at": now(), "must_change_password": False, "auth_version": 1, "provider": "oidc"}
        self.store.save("users", user)
        return self.issue(user)
