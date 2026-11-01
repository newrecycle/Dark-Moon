"""HTTP SCM field aliases for the fork's existing encrypted checkout adapter."""
from .scm_credentials import SCM_PROVIDERS, endpoint


def token_fields(raw, previous=None):
    """Return canonical vault input and non-secret SCM connection metadata."""
    previous = previous or {}
    connection = dict(previous.get("scm_fields") or {})
    provider = raw.get("provider", previous.get("provider"))
    if connection and provider != previous.get("provider"):
        raise ValueError("SCM field provider cannot change in place")
    if "fields" not in raw and not connection:
        return raw, connection
    fields = raw.get("fields", {})
    spec = SCM_PROVIDERS.get(provider) if isinstance(provider, str) else None
    if spec is None:
        raise ValueError("Unsupported SCM field provider")
    if not isinstance(fields, dict) or set(fields) - set(spec["fields"]):
        raise ValueError("Unsupported SCM credential fields")
    adapter = raw.get("adapter", previous.get("adapter", "scm_token"))
    if adapter != "scm_token":
        raise ValueError("SCM token fields require the scm_token adapter")
    converted = {key: value for key, value in raw.items() if key != "fields"}
    if "token" in fields:
        token = fields["token"]
        if not isinstance(token, str) or not 1 <= len(token) <= 65536:
            raise ValueError("A non-empty token is required (at most 64 KiB)")
        if "secret" in raw and raw["secret"] != token:
            raise ValueError("Token fields contradict the top-level secret")
        converted["secret"] = token
    username = fields.get("username", raw.get("username", previous.get("username", "")))
    if (not isinstance(username, str) or len(username) > 160
            or any(ord(c) < 32 or ord(c) == 127 for c in username)):
        raise ValueError("Invalid SCM username")
    if "username" in fields:
        if "username" in raw and raw["username"] != username:
            raise ValueError("SCM username fields contradict the top-level username")
        converted["username"] = username
    if "username" in spec["required"] and not username.strip():
        raise ValueError("SCM provider requires a username")
    connection["endpoint_url"] = endpoint(fields.get("endpoint_url", connection.get("endpoint_url", spec.get("endpoint", ""))))
    if "endpoint_url" in spec["required"] and not connection["endpoint_url"]:
        raise ValueError("SCM provider requires an endpoint URL")
    if "project" in spec["fields"]:
        project = fields.get("project", connection.get("project", ""))
        if not isinstance(project, str) or len(project) > 160 or any(ord(c) < 32 or ord(c) == 127 for c in project):
            raise ValueError("Invalid SCM project")
        connection["project"] = project
    if not previous:
        # New field-shaped requests use the existing private typed model.
        # Legacy records require explicit migration and retain their policy.
        converted.setdefault("adapter", "scm_token")
    return converted, connection
