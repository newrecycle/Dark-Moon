"""Provider profiles with encrypted API-key references and explicit application."""

import os
import re
import uuid
from urllib.parse import urlsplit

from .store import identifier, now


def profile(service, raw, profile_id=None):
    mode = raw.get("mode")
    if mode not in {"cloud", "local", "anthropic"}:
        raise ValueError("Provider mode must be cloud, local or anthropic")
    name = str(raw.get("provider", ""))
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
        raise ValueError("Provider id must be a single identifier")
    model = str(raw.get("model", ""))
    if (
        not model
        or len(model) > 240
        or any(c.isspace() or c in "\"'`$\\" for c in model)
    ):
        raise ValueError("Model must be a single model identifier")
    base = str(raw.get("base_url", ""))
    if mode != "cloud":
        parsed = urlsplit(base)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Local/Anthropic mode requires a base URL without embedded credentials"
            )
    credential = raw.get("credential_id") or ""
    if credential and not service.store.get("credentials", identifier(credential)):
        raise ValueError("Credential reference was not found")
    if mode == "cloud" and not credential:
        from .opencode import catalog

        if not any(
            p["id"] == name and p["connected"] for p in catalog(service)["providers"]
        ):
            raise ValueError(
                "Connect this provider in OpenCode or choose a saved API-key credential"
            )
    title = str(raw.get("name") or "").strip()
    if len(title) > 160:
        raise ValueError("Profile name must be at most 160 characters")
    selected_id = (
        identifier(profile_id)
        if profile_id
        else "profile_" + uuid.uuid4().hex[:16]
        if title
        else "provider_" + name
    )
    existing = service.store.get("providers", selected_id)
    from .provider_checks import model_records

    models = []
    if raw.get("models"):
        models, _ = model_records(raw["models"])
    item = {
        "id": selected_id,
        "name": title or name + " / " + model,
        "models": models,
        "mode": mode,
        "provider": name,
        "model": model,
        "base_url": base,
        "credential_id": credential,
        "created_at": existing.get("created_at", now()) if existing else now(),
        "updated_at": now(),
    }
    return service.store.save("providers", item)


def apply(service, profile_id):
    from .opencode import paths, document, private_write, write_environment, native
    from api import json_storage as data
    import json

    item = service.store.get("providers", identifier(profile_id))
    if not item:
        raise KeyError(profile_id)
    token = (
        service.vault.resolve(item["credential_id"]) if item["credential_id"] else ""
    )
    pid = item["provider"]
    model = item["model"]
    if model.startswith(pid + "/"):
        model = model[len(pid) + 1 :]
    if item["mode"] == "cloud":
        values = {
            "OPENROUTER_PROVIDER": pid,
            "OPENCODE_MODEL": model,
            "OPENCODE_USE_SAVED_AUTH": "true",
        }
        if token:
            values["OPENROUTER_API_KEY"] = token
    elif item["mode"] == "anthropic":
        pid = "anthropic"
        values = {
            "ANTHROPIC_BASE_URL": item["base_url"],
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_API_KEY": token or "darkmoon-local",
        }
    else:
        values = {
            "OPENCODE_LOCAL_MODE": "true",
            "OPENCODE_LOCAL_PROVIDER_ID": pid,
            "OPENCODE_LOCAL_PROVIDER_NAME": pid,
            "OPENCODE_LOCAL_BASE_URL": item["base_url"],
            "OPENCODE_LOCAL_MODEL": model,
        }
        if token:
            values["OPENCODE_LOCAL_API_KEY"] = token
    config_path, auth_path, env_path = paths(service)
    with data._file_lock(config_path), data._file_lock(auth_path):
        config, auth = document(config_path), document(auth_path)
        config.update(model=pid + "/" + model, small_model=pid + "/" + model)
        patch = {"model": config["model"], "small_model": config["small_model"]}
        if item["mode"] != "cloud":
            provider = config.setdefault("provider", {}).setdefault(pid, {})
            for record in item.get("models", []):
                provider.setdefault("models", {}).setdefault(
                    record["id"], {"name": record["name"]}
                )
            provider.setdefault("models", {}).setdefault(model, {"name": model})
            provider.setdefault("options", {}).pop("apiKey", None)
            provider["options"]["baseURL"] = item["base_url"]
            if item["mode"] == "local":
                provider["npm"] = "@ai-sdk/openai-compatible"
            patch["provider"] = {pid: provider}
        if token:
            if any(c.isspace() or c in "\"'`$\\\x00#" for c in token):
                raise ValueError(
                    "This key cannot be represented safely by the installer environment parser"
                )
            auth[pid] = {"type": "api", "key": token}
        # Validate and update the installer env before either JSON document.
        write_environment(env_path, values)
        private_write(config_path, json.dumps(config, indent=2) + "\n")
        private_write(auth_path, json.dumps(auth, indent=2) + "\n")
    live = False
    warning = ""
    if os.environ.get("DARKMOON_OPENCODE_URL"):
        try:
            if token:
                native("PUT", "/auth/" + pid, {"type": "api", "key": token})
            native("PATCH", "/config", patch)
            observed = native("GET", "/config")
            if (
                not isinstance(observed, dict)
                or observed.get("model") != patch["model"]
                or observed.get("small_model") != patch["small_model"]
            ):
                raise ValueError(
                    "OpenCode accepted the update but did not confirm both model settings on readback; live activation was not verified"
                )
            live = True
        except ValueError as exc:
            warning = str(exc)
    return {
        "applied": item["id"],
        "restart_required": not live,
        "warning": warning,
        "note": "OpenCode updated live."
        if live
        else "Shared OpenCode files and installer environment updated. Restart the existing OpenCode service to load them.",
    }


def remove(service, profile_id):
    identifier(profile_id)

    def delete(state):
        if state.setdefault("providers", {}).pop(profile_id, None) is None:
            raise KeyError(profile_id)
        return {
            "deleted": profile_id,
            "note": "Saved profile removed; active OpenCode configuration and provider login retained.",
        }

    return service.store.update(delete)
