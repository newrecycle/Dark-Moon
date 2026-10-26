"""Shared OpenCode state and an optional authenticated native-server bridge.

Secrets never enter catalog responses. Native OAuth remains owned by OpenCode.
"""

import base64
import json
import os
import re
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit, quote

from api import json_storage as data
from .store import identifier

MANAGED = {
    "OPENROUTER_PROVIDER",
    "OPENROUTER_API_KEY",
    "OPENCODE_MODEL",
    "OPENCODE_USE_SAVED_AUTH",
    "OPENCODE_LOCAL_MODE",
    "OPENCODE_LOCAL_PROVIDER_ID",
    "OPENCODE_LOCAL_PROVIDER_NAME",
    "OPENCODE_LOCAL_BASE_URL",
    "OPENCODE_LOCAL_MODEL",
    "OPENCODE_LOCAL_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_API_KEY",
}


def paths(service):
    root = Path(os.environ.get("DARKMOON_OPENCODE_DIR", str(data.DATA_DIR)))
    return (
        root / "opencode.json",
        root / "auth.json",
        service.queue.repo / ".opencode.env",
    )


def document(path):
    if not path.exists():
        return {}
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("OpenCode state exceeds 16 MiB")
    try:
        value = json.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise ValueError(
            "OpenCode state is not valid JSON; it was left unchanged"
        ) from None
    if not isinstance(value, dict):
        raise ValueError("OpenCode state must be a JSON object")
    return value


def environment(path):
    result = {}
    if path.exists():
        for line in path.read_text().splitlines():
            match = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$", line.strip())
            if match:
                result[match[1]] = match[2].strip().strip("\"'")
    return result


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".opencode-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_environment(path, values):
    # Never source a shell file. Preserve unrelated settings and comments.
    for key, value in values.items():
        if (
            not re.fullmatch(r"[A-Z][A-Z0-9_]*", key)
            or not re.fullmatch(r"[A-Za-z0-9_./:@%+=,?~-]*", value)
            or value.startswith("~")
        ):
            raise ValueError(
                "Provider values cannot be represented safely by the installer environment parser"
            )
    lines = path.read_text().splitlines() if path.exists() else []
    kept = [
        line
        for line in lines
        if not re.match(
            r"^\s*(?:export\s+)?(" + "|".join(sorted(MANAGED)) + r")\s*=", line
        )
    ]
    private_write(
        path, "\n".join(kept + [k + "=" + v for k, v in values.items()]) + "\n"
    )


def native(method, path, body=None):
    base = os.environ.get("DARKMOON_OPENCODE_URL", "").rstrip("/")
    if not base:
        raise ValueError(
            "Configure DARKMOON_OPENCODE_URL for native OpenCode OAuth and live updates"
        )
    parsed = urlsplit(base)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
        or (
            parsed.scheme != "https"
            and not (
                parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            )
        )
    ):
        raise ValueError(
            "OpenCode bridge requires HTTPS or loopback HTTP without credentials in its URL"
        )
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    if password:
        login = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode") + ":" + password
        headers["Authorization"] = "Basic " + base64.b64encode(login.encode()).decode()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None

    req = urllib.request.Request(
        base + path,
        method=method,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("OpenCode response too large")
        return json.loads(raw) if raw else True
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ValueError(
            "OpenCode server rejected the request (HTTP "
            + str(code)
            + "); check its authentication and API version"
        ) from None
    except (OSError, ValueError):
        raise ValueError(
            "OpenCode server request failed; check its URL, authentication and version"
        ) from None


def catalog(service):
    config_path, auth_path, env_path = paths(service)
    config, auth, env = (
        document(config_path),
        document(auth_path),
        environment(env_path),
    )
    providers = {}

    def add(pid, name=None):
        identifier(pid)
        return providers.setdefault(
            pid,
            {
                "id": pid,
                "name": name or pid,
                "models": [],
                "connected": False,
                "auth_type": "none",
                "methods": [],
            },
        )

    # Useful choices without fabricated model availability; models come from
    # the actual configuration/catalog. Custom entry always remains possible.
    for pid, name in [
        ("openrouter", "OpenRouter"),
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("opencode", "OpenCode"),
        ("ollama", "Ollama"),
        ("local", "OpenAI-compatible endpoint"),
    ]:
        add(pid, name)
    for pid, settings in config.get("provider", {}).items():
        p = add(pid, settings.get("name"))
        p["base_url"] = settings.get("options", {}).get("baseURL", "")
        p["models"] = [
            {"id": mid, "name": info.get("name", mid)}
            for mid, info in settings.get("models", {}).items()
        ]
    active = config.get("model", "")
    if env.get("OPENCODE_LOCAL_MODE") == "true":
        pid = env.get("OPENCODE_LOCAL_PROVIDER_ID", "local")
        mid = env.get("OPENCODE_LOCAL_MODEL", "")
        p = add(pid)
        p["base_url"] = env.get("OPENCODE_LOCAL_BASE_URL", "")
        active = pid + "/" + mid if mid else active
        if mid and not any(m["id"] == mid for m in p["models"]):
            p["models"].append({"id": mid, "name": mid})
        if env.get("OPENCODE_LOCAL_API_KEY"):
            p.update(connected=True, auth_type="environment")
    elif env.get("ANTHROPIC_BASE_URL") and env.get("ANTHROPIC_MODEL"):
        p = add("anthropic")
        p["base_url"] = env["ANTHROPIC_BASE_URL"]
        active = "anthropic/" + env["ANTHROPIC_MODEL"]
        if env.get("ANTHROPIC_API_KEY"):
            p.update(connected=True, auth_type="environment")
    elif env.get("OPENROUTER_PROVIDER") and env.get("OPENCODE_MODEL"):
        pid = env["OPENROUTER_PROVIDER"]
        p = add(pid)
        active = pid + "/" + env["OPENCODE_MODEL"]
        if env.get("OPENROUTER_API_KEY"):
            p.update(connected=True, auth_type="environment")
    for pid, record in auth.items():
        if not isinstance(record, dict):
            continue
        add(pid).update(
            connected=bool(
                record.get("key") or record.get("refresh") or record.get("access")
            ),
            auth_type=record.get("type", "unknown"),
        )
    if isinstance(active, str) and "/" in active:
        pid, mid = active.split("/", 1)
        p = add(pid)
        if not any(m["id"] == mid for m in p["models"]):
            p["models"].append({"id": mid, "name": mid})
    live = False
    warning = ""
    if os.environ.get("DARKMOON_OPENCODE_URL"):
        try:
            listing = native("GET", "/provider")
            methods = native("GET", "/provider/auth")
            current = native("GET", "/config")
            if isinstance(current, dict) and isinstance(current.get("model"), str):
                active = current["model"]
            for item in listing.get("all", []):
                p = add(item["id"], item.get("name"))
                p["name"] = item.get("name", p["name"])
                p["models"] = [
                    {"id": mid, "name": info.get("name", mid)}
                    for mid, info in item.get("models", {}).items()
                ]
                p["connected"] = p["id"] in listing.get("connected", [])
                p["methods"] = [
                    {
                        "index": i,
                        "type": v.get("type"),
                        "label": v.get("label", "Connect"),
                    }
                    for i, v in enumerate(methods.get(p["id"], []))
                ]
            live = True
        except ValueError as exc:
            warning = str(exc)
    return {
        "providers": sorted(providers.values(), key=lambda p: p["name"].lower()),
        "active_model": active,
        "live": live,
        "warning": warning,
        "source": "shared-files-and-native-server" if live else "shared-files",
        "oauth_available": live,
        "restart_required": not live,
    }


def sync(service):
    """Import API keys by reference; OAuth refresh tokens never leave OpenCode."""
    config_path, auth_path, env_path = paths(service)
    auth = document(auth_path)
    env = environment(env_path)
    imported = []
    candidates = {
        pid: record.get("key")
        for pid, record in auth.items()
        if isinstance(record, dict) and record.get("type") == "api"
    }
    if env.get("OPENROUTER_PROVIDER"):
        candidates[env["OPENROUTER_PROVIDER"]] = env.get(
            "OPENROUTER_API_KEY"
        ) or candidates.get(env["OPENROUTER_PROVIDER"])
    if env.get("OPENCODE_LOCAL_PROVIDER_ID"):
        candidates[env["OPENCODE_LOCAL_PROVIDER_ID"]] = env.get(
            "OPENCODE_LOCAL_API_KEY"
        ) or candidates.get(env["OPENCODE_LOCAL_PROVIDER_ID"])
    if env.get("ANTHROPIC_BASE_URL"):
        candidates["anthropic"] = env.get("ANTHROPIC_API_KEY") or candidates.get(
            "anthropic"
        )
    for pid, secret in candidates.items():
        if not secret:
            continue
        cid = "opencode_" + identifier(pid)
        service.vault.save(
            {"name": "OpenCode: " + pid, "provider": pid, "secret": secret}, cid
        )
        imported.append(cid)
    return {"imported": imported, "catalog": catalog(service)}


def connect(service, raw):
    pid = identifier(raw.get("provider"))
    cid = identifier(raw.get("credential_id"))
    secret = service.vault.resolve(cid)
    config_path, auth_path, _ = paths(service)
    _, _, env_path = paths(service)
    with data._file_lock(auth_path), data._file_lock(env_path):
        auth = document(auth_path)
        env = environment(env_path)
        values = {k: v for k, v in env.items() if k in MANAGED}
        updated = False
        for selector, provider, key in [
            ("OPENROUTER_PROVIDER", pid, "OPENROUTER_API_KEY"),
            ("OPENCODE_LOCAL_PROVIDER_ID", pid, "OPENCODE_LOCAL_API_KEY"),
        ]:
            if env.get(selector) == provider:
                values[key] = secret
                updated = True
        if pid == "anthropic" and env.get("ANTHROPIC_BASE_URL"):
            values["ANTHROPIC_API_KEY"] = secret
            updated = True
        if updated:
            write_environment(env_path, values)
        auth[pid] = {"type": "api", "key": secret}
        private_write(auth_path, json.dumps(auth, indent=2) + "\n")
    live = False
    warning = ""
    if os.environ.get("DARKMOON_OPENCODE_URL"):
        try:
            native(
                "PUT", "/auth/" + quote(pid, safe=""), {"type": "api", "key": secret}
            )
            live = True
        except ValueError as exc:
            warning = str(exc)
    return {
        "connected": pid,
        "restart_required": not live,
        "warning": warning,
        "catalog": catalog(service),
    }


def oauth(service, raw, finish=False):
    pid = identifier(raw.get("provider"))
    method = raw.get("method")
    if not isinstance(method, int) or isinstance(method, bool) or method < 0:
        raise ValueError("Choose an OpenCode login method")
    available = next((p for p in catalog(service)["providers"] if p["id"] == pid), {})
    if not any(
        m["index"] == method and m["type"] == "oauth"
        for m in available.get("methods", [])
    ):
        raise ValueError("That OAuth method is not available from OpenCode")
    body = {"method": method}
    if finish and raw.get("code"):
        body["code"] = str(raw["code"])[:8192]
    result = native(
        "POST",
        "/provider/"
        + quote(pid, safe="")
        + "/oauth/"
        + ("callback" if finish else "authorize"),
        body,
    )
    if finish:
        if result:
            _, _, env_path = paths(service)
            with data._file_lock(env_path):
                env = environment(env_path)
                if env.get("OPENROUTER_PROVIDER") == pid:
                    values = {
                        k: v
                        for k, v in env.items()
                        if k in MANAGED and k != "OPENROUTER_API_KEY"
                    }
                    values["OPENCODE_USE_SAVED_AUTH"] = "true"
                    write_environment(env_path, values)
        return {"connected": bool(result), "catalog": catalog(service)}
    url = str(result.get("url", ""))
    if not url.startswith("https://"):
        raise ValueError("OpenCode did not return an HTTPS authorization URL")
    return {
        "url": url,
        "method": result.get("method"),
        "instructions": str(result.get("instructions", ""))[:4000],
    }


def disconnect(service, raw):
    pid = identifier(raw.get("provider"))
    _, auth_path, env_path = paths(service)
    with data._file_lock(auth_path):
        auth = document(auth_path)
        auth.pop(pid, None)
        env = environment(env_path)
        values = {k: v for k, v in env.items() if k in MANAGED}
        if env.get("OPENROUTER_PROVIDER") == pid:
            values.pop("OPENROUTER_API_KEY", None)
        if env.get("OPENCODE_LOCAL_PROVIDER_ID") == pid:
            values.pop("OPENCODE_LOCAL_API_KEY", None)
        if pid == "anthropic":
            values.pop("ANTHROPIC_API_KEY", None)
        write_environment(env_path, values)
        private_write(auth_path, json.dumps(auth, indent=2) + "\n")
    live = False
    warning = ""
    if os.environ.get("DARKMOON_OPENCODE_URL"):
        try:
            native("DELETE", "/auth/" + quote(pid, safe=""))
            live = True
        except ValueError as exc:
            warning = str(exc)
    return {"disconnected": pid, "restart_required": not live, "warning": warning}
