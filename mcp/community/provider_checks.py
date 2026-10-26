"""Explicit administrator-requested provider probes; never performs inference."""

import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from . import opencode
from .store import identifier, now


def model_records(items):
    if not isinstance(items, list):
        raise ValueError("The endpoint did not return a model list")
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if (
            not isinstance(mid, str)
            or not mid
            or len(mid) > 240
            or any(c.isspace() or c in "\"'`$\\" for c in mid)
        ):
            continue
        if mid in seen:
            continue
        seen.add(mid)
        result.append({"id": mid, "name": str(item.get("name") or mid)[:160]})
    if not result:
        raise ValueError("The endpoint returned no usable model IDs")
    return result[:1000], len(result) > 1000


def endpoint_models(service, raw):
    mode = raw.get("mode")
    if mode not in {"local", "anthropic"}:
        raise ValueError(
            "Model discovery requires a custom OpenAI-compatible or Anthropic endpoint"
        )
    base = str(raw.get("base_url", "")).rstrip("/")
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
            "Use an HTTP(S) base URL without credentials, query or fragment"
        )
    credential = raw.get("credential_id") or ""
    secret = service.vault.resolve(identifier(credential)) if credential else ""
    if any(c in secret for c in "\r\n\x00"):
        raise ValueError("This credential cannot be used as an HTTP header")
    headers = {"Accept": "application/json"}
    if mode == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
        if secret:
            headers["x-api-key"] = secret
        suffix = "/models" if parsed.path.rstrip("/").endswith("/v1") else "/v1/models"
    else:
        if secret:
            headers["Authorization"] = "Bearer " + secret
        suffix = "/models"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None

    request = urllib.request.Request(base + suffix, headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.build_opener(NoRedirect).open(
            request, timeout=15
        ) as response:
            content = response.read(4 * 1024 * 1024 + 1)
        if len(content) > 4 * 1024 * 1024:
            raise ValueError("Model response exceeds 4 MiB")
        listing = json.loads(content)
        models, truncated = model_records(
            listing.get("data") if isinstance(listing, dict) else None
        )
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        # Do not return response bodies, URLs or request headers: they may echo keys.
        if code in {401, 403}:
            raise ValueError(
                "The model endpoint rejected authentication (HTTP " + str(code) + ")"
            ) from None
        raise ValueError(
            "Model discovery failed (HTTP "
            + str(code)
            + "); check the base URL and API compatibility"
        ) from None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError(
            "The model endpoint could not be reached or did not return JSON"
        ) from None
    return {
        "models": models,
        "truncated": truncated,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "checked_at": now(),
        "credential_sent": bool(secret),
        "inference_performed": False,
        "note": "A successful model list is a connectivity check, not proof of inference access or account entitlement.",
    }


def bridge_health():
    started = time.monotonic()
    if not __import__("os").environ.get("DARKMOON_OPENCODE_URL"):
        return {
            "healthy": False,
            "configured": False,
            "status": "not_configured",
            "note": "Configure the authenticated native bridge to check the running server.",
        }
    try:
        result = opencode.native("GET", "/global/health")
        if not isinstance(result, dict) or result.get("healthy") is not True:
            raise ValueError("The server did not report healthy status")
        return {
            "healthy": True,
            "configured": True,
            "status": "healthy",
            "version": str(result.get("version", "unknown"))[:100],
            "latency_ms": round((time.monotonic() - started) * 1000),
            "checked_at": now(),
        }
    except ValueError as exc:
        return {
            "healthy": False,
            "configured": True,
            "status": "unavailable",
            "note": str(exc),
            "checked_at": now(),
        }


def check_profile(service, profile_id):
    item = service.store.get("providers", identifier(profile_id))
    if not item:
        raise KeyError(profile_id)
    if item["mode"] in {"local", "anthropic"}:
        try:
            result = endpoint_models(service, item)
            model = item["model"].removeprefix(item["provider"] + "/")
            found = any(m["id"] == model for m in result["models"])
            result = {k: v for k, v in result.items() if k != "models"} | {
                "status": "model_listed" if found else "model_not_listed",
                "model_list_reachable": True,
                "model_list_includes_selected": found,
            }
        except ValueError as exc:
            result = {
                "status": "failed",
                "note": str(exc),
                "checked_at": now(),
                "inference_performed": False,
            }
    else:
        health = bridge_health()
        provider = next(
            (
                p
                for p in opencode.catalog(service)["providers"]
                if p["id"] == item["provider"]
            ),
            {},
        )
        found = any(
            m["id"] == item["model"].removeprefix(item["provider"] + "/")
            for m in provider.get("models", [])
        )
        result = {
            "status": "catalog_available"
            if health["healthy"] and provider.get("connected") and found
            else "needs_attention",
            "bridge": health,
            "login_present": bool(provider.get("connected")),
            "model_in_catalog": found,
            "checked_at": now(),
            "inference_performed": False,
            "note": "Native catalog/login presence checked. No provider API key, subscription or inference entitlement was verified.",
        }

    def save(state):
        profile = state.setdefault("providers", {}).get(profile_id)
        if not profile:
            raise KeyError(profile_id)
        profile["last_check"] = result
        return result

    return service.store.update(save)
