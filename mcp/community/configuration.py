"""Provider profiles with encrypted API-key references and explicit application."""
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from .store import identifier, now


def profile(service, raw):
    mode = raw.get("mode")
    if mode not in {"cloud", "local", "anthropic"}:
        raise ValueError("Provider mode must be cloud, local or anthropic")
    name = str(raw.get("provider", ""))
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
        raise ValueError("Provider id must be a single identifier")
    model = str(raw.get("model", ""))
    if not model or len(model) > 240 or any(c.isspace() or c in '\"\'`$\\' for c in model):
        raise ValueError("Model must be a single model identifier")
    base = str(raw.get("base_url", ""))
    if mode != "cloud":
        parsed = urlsplit(base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Local/Anthropic mode requires a base URL without embedded credentials")
    credential = raw.get("credential_id") or ""
    if credential and not service.store.get("credentials", identifier(credential)):
        raise ValueError("Credential reference was not found")
    if mode == "cloud" and not credential:
        raise ValueError("Cloud mode requires a saved API-key credential")
    item = {"id": "provider_"+name, "mode": mode, "provider": name, "model": model, "base_url": base,
            "credential_id": credential, "created_at": now()}
    return service.store.save("providers", item)


def apply(service, profile_id):
    item = service.store.get("providers", identifier(profile_id))
    if not item:
        raise KeyError(profile_id)
    token = service.vault.resolve(item["credential_id"]) if item["credential_id"] else ""
    if any(c in token for c in "\r\n\x00\"'`$\\"):
        raise ValueError("This key cannot be safely represented by the upstream shell/env parser")
    values = {}
    if item["mode"] == "cloud":
        values = {"OPENROUTER_PROVIDER": item["provider"], "OPENCODE_MODEL": item["model"], "OPENROUTER_API_KEY": token}
    elif item["mode"] == "anthropic":
        values = {"ANTHROPIC_BASE_URL": item["base_url"], "ANTHROPIC_MODEL": item["model"], "ANTHROPIC_API_KEY": token or "darkmoon-local"}
    else:
        values = {"OPENCODE_LOCAL_MODE": "true", "OPENCODE_LOCAL_PROVIDER_ID": item["provider"],
                  "OPENCODE_LOCAL_PROVIDER_NAME": item["provider"], "OPENCODE_LOCAL_BASE_URL": item["base_url"],
                  "OPENCODE_LOCAL_MODEL": item["model"]}
        if token:
            values["OPENCODE_LOCAL_API_KEY"] = token
    for value in values.values():
        if any(c.isspace() or c in "\"'`$\\" for c in value):
            raise ValueError("Provider values must be safe single-line environment values")
    target = service.queue.repo / ".opencode.env"
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".opencode-provider-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write("# Applied from encrypted community provider profile\n")
            for key, value in values.items():
                stream.write(key+"="+value+"\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"applied": item["id"], "restart_required": True, "note": "Recreate the existing OpenCode service to apply its new environment"}
