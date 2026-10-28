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

    def save(self, raw, credential_id=None, *, internal=False, actor=None):
        from .credential_policy import VERSION, validate
        if not isinstance(raw, dict):
            raise ValueError("Credential body must be an object")
        credential_id = identifier(credential_id) if credential_id else "cred_" + uuid.uuid4().hex[:16]
        def change(state):
            credentials = state.setdefault("credentials", {})
            old = credentials.get(credential_id)
            if old and old.get("internal") and not internal:
                raise KeyError("Credential not found")
            structured = ("adapter" in raw or "model_version" in raw or
                          "scope" in raw or "owner_id" in raw or "grants" in raw or
                          "revoked" in raw or (old and old.get("model_version") == VERSION))
            policy = validate(raw, state, actor, old) if structured else {}
            secret = raw.get("secret")
            if secret is None and old and structured:
                sealed = old.get("sealed")
            elif isinstance(secret, str) and 1 <= len(secret) <= 65536:
                sealed = self.box.encrypt(secret.encode()).decode()
            else:
                raise ValueError("A non-empty secret is required (at most 64 KiB)")
            if not isinstance(sealed, str) or not sealed:
                raise ValueError("Credential secret is missing")
            name = raw.get("name", (old or {}).get("name", "Credential"))
            provider = raw.get("provider", (old or {}).get("provider", "generic"))
            username = raw.get("username", (old or {}).get("username", ""))
            if not all(isinstance(v, str) for v in (name, provider, username)) or len(name) > 160 or len(provider) > 80 or len(username) > 160:
                raise ValueError("Invalid credential metadata")
            item = {"id": credential_id, "name": name, "provider": provider,
                    "username": username, "sealed": sealed,
                    "hint": "********", "created_at": (old or {}).get("created_at", now())}
            if internal or (old and old.get("internal")):
                item["internal"] = True
            item.update(policy)
            credentials[credential_id] = item
            return self.public(item)
        return self.store.update(change)

    @staticmethod
    def public(item):
        from .credential_catalog import capabilities
        from .credential_policy import VERSION, metadata
        def string(key):
            v = item.get(key)
            return v if isinstance(v, str) else ""
        result = {"id": string("id"), "name": string("name"),
                  "provider": string("provider"), "username": string("username"),
                  "created_at": string("created_at"), "hint": "********",
                  "set": bool(item.get("sealed")), "capabilities": capabilities(item)}
        if item.get("model_version") == VERSION:
            result.update(metadata(item))
        return result

    def list(self, capability=None, *, actor=None, for_use=False):
        from .credential_catalog import allows, check_capability
        from .credential_policy import may_use
        check_capability(capability)
        state = self.store.read()
        rows = sorted(state.get("credentials", {}).values(), key=lambda r: str(r.get("id", "")))
        return [self.public(item) for item in rows
                if not item.get("internal")
                and (capability is None or allows(item, capability))
                and (not for_use or may_use(item, actor, state))]

    def get(self, credential_id, capability=None):
        from .credential_catalog import allows
        item = self.store.get("credentials", identifier(credential_id))
        if not item or item.get("internal") or (capability is not None and not allows(item, capability)):
            raise KeyError("Credential not found")
        return self.public(item)

    def require(self, credential_id, capability, *, actor=None):
        from .credential_catalog import allows
        from .credential_policy import may_use
        identifier(credential_id)
        state = self.store.read()
        item = state.get("credentials", {}).get(credential_id)
        if not item or not allows(item, capability) or not may_use(item, actor, state):
            raise KeyError("Credential unavailable")
        return credential_id

    def resolve(self, credential_id):
        item = self.store.get("credentials", identifier(credential_id))
        if not item:
            raise KeyError(credential_id)
        return self.box.decrypt(item["sealed"].encode()).decode()

    def delete(self, credential_id):
        def change(state):
            records = state.setdefault("credentials", {})
            item = records.get(identifier(credential_id))
            if not item or item.get("internal"):
                raise KeyError("Credential not found")
            del records[credential_id]
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
        if username == "workspace-owner":
            raise ValueError("Reserved service identity")
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
            # A recreated username is a new principal, not a resurrection of
            # past private ownership, grants, sessions or queued launches.
            for credential in state.get("credentials", {}).values():
                if credential.get("model_version") == 1:
                    if credential.get("owner_id") == username:
                        credential["revoked"] = True
                    if username in credential.get("grants", []):
                        credential["grants"] = [g for g in credential["grants"] if g != username]
            for session_id, session in list(state.get("sessions", {}).items()):
                if session.get("user_id") == username:
                    del state["sessions"][session_id]
            for job in state.get("jobs", {}).values():
                if (job.get("status") == "queued" and
                    isinstance(job.get("request_actor"), dict) and
                    job["request_actor"].get("id") == username):
                    job.update(status="cancelled", finished_at=now(),
                               error="Queued principal no longer exists")
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
        def bind_oidc(state):
            users = state.setdefault("users", {})
            if user_id not in users:
                # Re-provisioning a revoked SSO subject must not resurrect an
                # orphaned private credential, grant or queued launch.
                for credential in state.get("credentials", {}).values():
                    if credential.get("model_version") == 1:
                        if credential.get("owner_id") == user_id:
                            credential["revoked"] = True
                        if user_id in credential.get("grants", []):
                            credential["grants"] = [g for g in credential["grants"] if g != user_id]
                for sid, session in list(state.get("sessions", {}).items()):
                    if session.get("user_id") == user_id:
                        del state["sessions"][sid]
                for job in state.get("jobs", {}).values():
                    if (job.get("status") == "queued" and
                        isinstance(job.get("request_actor"), dict) and
                        job["request_actor"].get("id") == user_id):
                        job.update(status="cancelled", finished_at=now(),
                                   error="Queued principal no longer exists")
            else:
                user["auth_version"] = users[user_id].get("auth_version", 1)
            users[user_id] = user
        self.store.update(bind_oidc)
        return self.issue(user)
