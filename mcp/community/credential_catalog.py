"""Fork credential discovery: use-site capabilities, not vendor integration parity.

The workspace vault stores a single opaque secret and optional username.
Provider is a descriptive label, not a vendor capability or owner scope.
"""

CAPABILITIES = {
    "assessment_login": {"name": "Target login", "consumer": "assessment_credential_id", "requires_username": True},
    "assessment_token": {"name": "Target token", "consumer": "assessment_token_id", "requires_username": False},
    "source_checkout": {"name": "HTTPS Git checkout", "consumer": "credential_id (launch/remediation)", "requires_username": False},
    "provider_api_key": {"name": "OpenCode/provider API key", "consumer": "credential_id (provider profile/connection)", "requires_username": False},
}

# Suggested labels for fork consumers. Not a list of implemented vendor adapters.
PROVIDERS = (
    ("generic", "Generic single-secret credential", tuple(CAPABILITIES)),
    ("target-login", "Target login credential", ("assessment_login",)),
    ("target-token", "Target token", ("assessment_token",)),
    ("scm", "HTTPS Git checkout credential", ("source_checkout",)),
    ("api-key", "OpenCode/provider API key", ("provider_api_key",)),
)


def catalog():
    from .credential_policy import ADAPTERS, VERSION
    return {
        "model_version": VERSION,
        "adapters": [{"id": key, "required_fields": list(spec["fields"]), "capabilities": list(spec["capabilities"])}
                     for key, spec in ADAPTERS.items()],
        "data": [{"id": key, "name": name, "capabilities": list(caps),
                  "fields": ["name", "provider", "username", "secret"]}
                 for key, name, caps in PROVIDERS],
        "total": len(PROVIDERS),
        "capabilities": [{"id": key, **metadata} for key, metadata in CAPABILITIES.items()],
        "scope": "administrator-managed workspace vault",
        "note": "Provider labels are descriptive, not a verified vendor entitlement or owner-scoped schema.",
    }


def check_capability(capability):
    if capability is not None and capability not in CAPABILITIES:
        raise ValueError("Unsupported credential capability")


def capabilities(item):
    if item.get("internal") or item.get("revoked") is True or not isinstance(item.get("sealed"), str) or not item["sealed"]:
        return []
    from .credential_policy import ADAPTERS, VERSION
    if item.get("model_version") == VERSION:
        entry = ADAPTERS.get(item.get("adapter"))
        if not entry:
            return []
        if item.get("adapter") == "username_password" and not str(item.get("username") or "").strip():
            return []
        return list(entry["capabilities"])
    values = [key for key, spec in CAPABILITIES.items() if not spec["requires_username"]]
    if isinstance(item.get("username"), str) and item["username"].strip():
        values.insert(0, "assessment_login")
    return values


def allows(item, capability=None):
    check_capability(capability)
    return not item.get("internal") and item.get("revoked") is not True and (capability is None or capability in capabilities(item))
