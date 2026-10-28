"""Fork-native versioned credential adapters and ownership policy.

Unversioned encrypted records remain legacy-v0 workspace-shared for backward
compatibility. No vendor-specific schema or default is inferred.
"""
from .store import identifier

VERSION = 1
SERVICE_ID = "workspace-owner"
ADAPTERS = {
    "username_password": {"fields": ("username", "secret"), "capabilities": ("assessment_login",)},
    "target_token": {"fields": ("secret",), "capabilities": ("assessment_token",)},
    "scm_token": {"fields": ("secret",), "capabilities": ("source_checkout",)},
    "provider_api_key": {"fields": ("secret",), "capabilities": ("provider_api_key",)},
}
SCOPES = {"private", "shared", "service"}
FIELDS = {"name", "provider", "username", "secret", "adapter", "model_version",
          "scope", "owner_id", "grants", "revoked"}


def metadata(item):
    if item.get("model_version") != VERSION:
        return {"model_version": 0, "adapter": "legacy_v0", "scope": "shared",
                "owner_id": SERVICE_ID, "grants": ["*"], "revoked": False}
    return {key: item[key] for key in
            ("model_version", "adapter", "scope", "owner_id", "grants", "revoked")}


def principal(identity, state):
    """Re-read current roles; never trust a stored/request-supplied role claim."""
    if identity is None:
        return SERVICE_ID  # Trusted internal service calls only; HTTP always passes identity.
    if not isinstance(identity, dict):
        return None
    uid = identity.get("id")
    if uid == SERVICE_ID:
        return SERVICE_ID if identity.get("authentication") == "workspace-token" else None
    user = state.get("users", {}).get(uid) if isinstance(uid, str) else None
    if not user or user.get("role") not in {"analyst", "admin"}:
        return None
    return uid


def may_use(item, identity, state):
    if not isinstance(item, dict) or item.get("internal") or item.get("revoked") is True:
        return False
    uid = principal(identity, state)
    if uid is None:
        return False
    model = metadata(item)
    if model["scope"] == "service":
        return uid == SERVICE_ID
    if model["scope"] == "private":
        return uid == model["owner_id"]
    if model["scope"] == "shared":
        return uid == model["owner_id"] or uid in model["grants"] or "*" in model["grants"]
    return False


def validate(raw, state, identity, previous=None):
    if not isinstance(raw, dict) or set(raw) - FIELDS:
        raise ValueError("Unknown structured credential field")
    version = raw.get("model_version", VERSION)
    if type(version) is not int or version != VERSION:
        raise ValueError("Unsupported credential model version")
    prior = metadata(previous) if previous and previous.get("model_version") == VERSION else {}
    adapter = raw.get("adapter", prior.get("adapter"))
    if adapter not in ADAPTERS:
        raise ValueError("Unsupported credential adapter")
    if previous and previous.get("model_version") == VERSION and adapter != previous.get("adapter"):
        raise ValueError("Credential adapter cannot change in place")
    uid = principal(identity, state)
    if uid is None:
        raise PermissionError("Credential administrator is unavailable")
    scope = raw.get("scope", prior.get("scope", "private"))
    if scope not in SCOPES:
        raise ValueError("Unsupported credential scope")
    owner = raw.get("owner_id", prior.get("owner_id", uid))
    if not isinstance(owner, str):
        raise ValueError("Invalid credential owner")
    identifier(owner)
    if scope == "service" and owner != SERVICE_ID:
        raise ValueError("Service credentials must be owned by the service identity")
    if scope != "service" and owner != SERVICE_ID:
        user = state.get("users", {}).get(owner)
        if not user or user.get("role") not in {"analyst", "admin"}:
            raise ValueError("Credential owner must be an active analyst or administrator")
    if scope == "private" and owner == SERVICE_ID and uid != SERVICE_ID:
        raise ValueError("A personal credential must have an account owner")
    grants = raw.get("grants", prior.get("grants", []))
    if not isinstance(grants, list) or len(grants) > 100 or len(grants) != len(set(map(str, grants))):
        raise ValueError("Invalid credential grants")
    for grantee in grants:
        user = state.get("users", {}).get(grantee) if isinstance(grantee, str) else None
        if not user or user.get("role") not in {"analyst", "admin"} or grantee == SERVICE_ID:
            raise ValueError("Credential grant must name an active analyst or administrator")
    if scope != "shared" and grants:
        raise ValueError("Only shared credentials accept grants")
    revoked = raw.get("revoked", prior.get("revoked", False))
    if previous and previous.get("revoked") is True and revoked is not True:
        raise ValueError("Revoked credentials cannot be reactivated; create a new ID")
    if type(revoked) is not bool:
        raise ValueError("Credential revoked flag must be boolean")
    username = raw.get("username", (previous or {}).get("username", ""))
    if not isinstance(username, str) or len(username) > 160:
        raise ValueError("Invalid credential username")
    if adapter == "username_password" and not username.strip():
        raise ValueError("Username/password adapter requires a username")
    return {"model_version": VERSION, "adapter": adapter, "scope": scope,
            "owner_id": owner, "grants": grants, "revoked": revoked}
