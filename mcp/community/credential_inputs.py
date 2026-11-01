"""Narrow HTTP field aliases for the fork's existing encrypted adapters."""


def token_fields(raw, previous=None):
    """Translate the supported GitHub token form without changing old scopes.

    This is a single-token input adapter, not a provider integration or an
    arbitrary multi-field credential store. Existing typed policy is still
    validated by the vault in the same transaction.
    """
    if "fields" not in raw:
        return raw
    fields = raw["fields"]
    if not isinstance(fields, dict) or set(fields) - {"token"}:
        raise ValueError("Supported credential fields are a token object only")
    provider = raw.get("provider", (previous or {}).get("provider"))
    if provider != "github":
        raise ValueError("Token fields currently support the github provider only")
    adapter = raw.get("adapter", (previous or {}).get("adapter", "scm_token"))
    if adapter != "scm_token":
        raise ValueError("GitHub token fields require the scm_token adapter")
    converted = {key: value for key, value in raw.items() if key != "fields"}
    if "token" in fields:
        token = fields["token"]
        if not isinstance(token, str) or not 1 <= len(token) <= 65536:
            raise ValueError("A non-empty token is required (at most 64 KiB)")
        if "secret" in raw and raw["secret"] != token:
            raise ValueError("Token fields contradict the top-level secret")
        converted["secret"] = token
    if previous is None:
        # New field-shaped requests use the existing private typed model.
        # Legacy records require explicit migration and retain their policy.
        converted.setdefault("adapter", "scm_token")
    return converted
