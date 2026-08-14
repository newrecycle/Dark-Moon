"""Validation and data-minimization policy for headless-browser results."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_CAPABILITIES_PATH = Path(__file__).with_name("capabilities.json")
_CAPABILITIES = json.loads(_CAPABILITIES_PATH.read_text(encoding="utf-8"))

MODE_DESCRIPTIONS = dict(_CAPABILITIES["modes"])
ALLOWED_MODES = frozenset(MODE_DESCRIPTIONS)
ALLOWED_WAIT_UNTIL = frozenset(_CAPABILITIES["wait_until"])
BROWSER_DEFAULTS = dict(_CAPABILITIES["defaults"])
BROWSER_MINIMUMS = dict(_CAPABILITIES["minimums"])
BROWSER_LIMITS = dict(_CAPABILITIES["limits"])

MAX_URL_LENGTH = BROWSER_LIMITS["max_url_length"]
MAX_PAGES = BROWSER_LIMITS["max_pages"]
MAX_DEPTH = BROWSER_LIMITS["max_depth"]
MAX_REQUESTS = BROWSER_LIMITS["max_requests"]
MAX_TIMEOUT = BROWSER_LIMITS["max_timeout_seconds"]
MAX_SETTLE_MS = BROWSER_LIMITS["max_settle_ms"]
MAX_STRING_LENGTH = BROWSER_LIMITS["max_result_string_length"]
MAX_LIST_ITEMS = BROWSER_LIMITS["max_result_items"]

DEFAULT_MAX_PAGES = BROWSER_DEFAULTS["max_pages"]
DEFAULT_MAX_DEPTH = BROWSER_DEFAULTS["max_depth"]
DEFAULT_MAX_REQUESTS = BROWSER_DEFAULTS["max_requests"]
DEFAULT_TIMEOUT = BROWSER_DEFAULTS["timeout_seconds"]
DEFAULT_SETTLE_MS = BROWSER_DEFAULTS["settle_ms"]
DEFAULT_WAIT_UNTIL = BROWSER_DEFAULTS["wait_until"]


class BrowserPolicyError(ValueError):
    """Raised when a browser request violates a bounded policy constraint."""


def _bounded_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise BrowserPolicyError(f"{name} must be an integer")
    if isinstance(value, int):
        converted = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        converted = int(value)
    else:
        raise BrowserPolicyError(f"{name} must be an integer")
    if not minimum <= converted <= maximum:
        raise BrowserPolicyError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return converted


def _strict_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise BrowserPolicyError(f"{name} must be a boolean")


def validate_target_url(url: str) -> str:
    """Validate a browser target without resolving or contacting it."""

    if not isinstance(url, str):
        raise BrowserPolicyError("url must be a string")
    url = url.strip()
    if not url:
        raise BrowserPolicyError("url is required")
    if len(url) > MAX_URL_LENGTH:
        raise BrowserPolicyError(f"url exceeds {MAX_URL_LENGTH} characters")
    if any(char.isspace() or ord(char) == 127 for char in url):
        raise BrowserPolicyError("url contains whitespace or control characters")
    if "\\" in url:
        raise BrowserPolicyError("url contains a forbidden backslash")

    try:
        parsed = urlsplit(url)
        # Accessing .port performs its own validation.
        _ = parsed.port
    except ValueError as exc:
        raise BrowserPolicyError(f"url is invalid: {exc}") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise BrowserPolicyError("url scheme must be http or https")
    if not parsed.hostname:
        raise BrowserPolicyError("url must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise BrowserPolicyError("credentials in URL userinfo are forbidden")
    return url


def normalize_browser_request(
    *,
    url: str,
    mode: str = "snapshot",
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    timeout: int = DEFAULT_TIMEOUT,
    settle_ms: int = DEFAULT_SETTLE_MS,
    same_origin: bool = True,
    screenshot: bool = False,
    ignore_https_errors: bool = False,
    follow_links: bool = False,
    wait_until: str = DEFAULT_WAIT_UNTIL,
) -> Dict[str, Any]:
    """Return the canonical request sent to the fixed Node browser runner."""

    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in ALLOWED_MODES:
        raise BrowserPolicyError(
            f"mode must be one of: {', '.join(sorted(ALLOWED_MODES))}"
        )

    normalized_wait = str(wait_until).strip().lower()
    if normalized_wait not in ALLOWED_WAIT_UNTIL:
        raise BrowserPolicyError(
            f"wait_until must be one of: {', '.join(sorted(ALLOWED_WAIT_UNTIL))}"
        )

    normalized = {
        "url": validate_target_url(url),
        "mode": normalized_mode,
        "max_pages": _bounded_int(
            "max_pages", max_pages, BROWSER_MINIMUMS["max_pages"], MAX_PAGES
        ),
        "max_depth": _bounded_int(
            "max_depth", max_depth, BROWSER_MINIMUMS["max_depth"], MAX_DEPTH
        ),
        "max_requests": _bounded_int(
            "max_requests",
            max_requests,
            BROWSER_MINIMUMS["max_requests"],
            MAX_REQUESTS,
        ),
        "timeout": _bounded_int(
            "timeout", timeout, BROWSER_MINIMUMS["timeout_seconds"], MAX_TIMEOUT
        ),
        "settle_ms": _bounded_int(
            "settle_ms",
            settle_ms,
            BROWSER_MINIMUMS["settle_ms"],
            MAX_SETTLE_MS,
        ),
        "same_origin": _strict_bool("same_origin", same_origin),
        "screenshot": _strict_bool("screenshot", screenshot),
        "ignore_https_errors": _strict_bool(
            "ignore_https_errors", ignore_https_errors
        ),
        "follow_links": _strict_bool("follow_links", follow_links),
        "wait_until": normalized_wait,
    }

    if normalized_mode == "crawl":
        normalized["follow_links"] = True
    if normalized_mode == "screenshot":
        normalized["screenshot"] = True
    if not normalized["follow_links"]:
        normalized["max_pages"] = 1
        normalized["max_depth"] = 0
    return normalized


_URL_RE = re.compile(r"https?://[^\s\"'<>`|\\]+", re.IGNORECASE)
_JWT_RE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_PROVIDER_CREDENTIAL_RE = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{16,}|"
    r"(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{16,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AIza[0-9A-Za-z_-]{35}"
    r")\b"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|"
    r"api[_-]?key|secret|client[_-]?secret|authorization|session|session[_-]?id|sid)"
    r"\s*[:=]\s*"
    r"[^\s,;&]{3,}"
)

_BLOCKED_KEYS = {
    "authorization",
    "body",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "headers",
    "local_storage",
    "password",
    "post_data",
    "request_body",
    "request_headers",
    "response_body",
    "response_headers",
    "secret",
    "session_storage",
    "set_cookie",
    "storage",
}
_BLOCKED_COMPACT_KEYS = {key.replace("_", "") for key in _BLOCKED_KEYS}


def _redact_url_query(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return url
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = host
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        query = urlencode(
            [(key, "[REDACTED]") for key, _ in parse_qsl(parsed.query, keep_blank_values=True)],
            doseq=True,
        )
        return urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))
    except ValueError:
        return "[INVALID_URL]"


def _redact_text(value: str) -> str:
    value = _URL_RE.sub(lambda match: _redact_url_query(match.group(0)), value)
    value = _JWT_RE.sub("[REDACTED_TOKEN]", value)
    value = _BEARER_RE.sub("Bearer [REDACTED_TOKEN]", value)
    value = _AWS_KEY_RE.sub("[REDACTED_ACCESS_KEY]", value)
    value = _PROVIDER_CREDENTIAL_RE.sub("[REDACTED_CREDENTIAL]", value)
    value = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=[REDACTED_SECRET]", value
    )
    if len(value) > MAX_STRING_LENGTH:
        return value[:MAX_STRING_LENGTH] + "...[TRUNCATED]"
    return value


_DROP = object()


def _scrub(value: Any, key: str | None = None) -> Any:
    normalized_key = (key or "").strip().lower().replace("-", "_")
    if (
        normalized_key in _BLOCKED_KEYS
        or normalized_key.replace("_", "") in _BLOCKED_COMPACT_KEYS
    ):
        return _DROP
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [
            cleaned
            for item in value[:MAX_LIST_ITEMS]
            if (cleaned := _scrub(item)) is not _DROP
        ]
    if isinstance(value, tuple):
        return _scrub(list(value), key=key)
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for child_key, child_value in value.items():
            child_name = str(child_key)
            child = _scrub(child_value, key=child_name)
            if child is not _DROP:
                cleaned[child_name] = child
        return cleaned
    return _redact_text(str(value))


def scrub_browser_output(value: Any) -> Any:
    """Remove browser state/secrets and cap every LLM-bound value."""

    cleaned = _scrub(value)
    return None if cleaned is _DROP else cleaned
