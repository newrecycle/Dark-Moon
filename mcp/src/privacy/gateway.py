"""
CommandGateway — context-aware rehydration + exfiltration control.

The gateway sits between the LLM and local execution. It:
  * receives an LLM-generated raw command or a structured tool call,
  * detects placeholders and validates they are allowed *in that position*,
  * rehydrates placeholders only in approved argument positions,
  * blocks unsafe usage (exfiltration, echo/print, sending values to arbitrary
    external endpoints),
  * hands back a real command for local execution,
  * re-sanitizes stdout/stderr before results go back to the LLM.

Rehydration is deliberately NOT a naive global string replace: a placeholder is
only turned back into its real value after the surrounding shell context has
been proven safe, and only for placeholder tokens known to the session vault.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

from .vault import Category, PrivacyVault, PLACEHOLDER_RE

# Commands that would print / echo a value straight back (exfil / extraction).
_PRINT_SINKS = {"echo", "printf", "print", "cat", "tee", "logger", "write"}
# Commands whose *destination* is an external host we could exfiltrate to.
_NET_SINKS = {"curl", "wget", "nc", "ncat", "netcat", "telnet", "ssh", "scp", "sftp", "ftp", "socat"}
_SHELL_WRAPPERS = {"bash", "sh", "zsh", "dash", "ash"}
# curl/wget flags that put data in the *outbound* request body.
_OUTBOUND_DATA_FLAGS = {
    "-d", "--data", "--data-raw", "--data-binary", "--data-ascii",
    "--data-urlencode", "-F", "--form", "--form-string", "-T", "--upload-file",
}
# Characters that must never appear in a rehydrated value (injection guard).
_SHELL_META_RE = re.compile(r"""[;|&`$><(){}\[\]\n\r'"\\!*?~]""")
_NET_REDIRECT_RE = re.compile(r"/dev/(?:tcp|udp)/|>\(|<\(")
_HOST_CATEGORIES = {
    Category.IP_PRIVATE,
    Category.IP_PUBLIC,
    Category.HOST_INTERNAL,
    Category.DOMAIN,
}
_HOST_LABEL_RE = re.compile(
    r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?"
)


def _safe_rehydrated_host(value: str) -> Optional[str]:
    """Return a normalized host value or ``None`` when it is not host-only."""

    host = value.strip()
    if not host or len(host) > 253 or any(char.isspace() for char in host):
        return None
    if any(char in host for char in "/?#@[]"):
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass

    trailing_dot = host.endswith(".")
    candidate = host[:-1] if trailing_dot else host
    try:
        ascii_host = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    labels = ascii_host.split(".")
    if not labels or any(not _HOST_LABEL_RE.fullmatch(label) for label in labels):
        return None
    return f"{ascii_host}." if trailing_dot else ascii_host


class GatewayDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"


@dataclass
class GatewayResult:
    decision: GatewayDecision
    # For ALLOW (raw command): the real, locally-executable command.
    command: Optional[str] = None
    # For ALLOW (structured tool call): the rehydrated argument dict.
    resolved: Optional[Dict[str, object]] = None
    # For BLOCK: human-readable reason (safe to show the LLM — no real values).
    reason: Optional[str] = None
    placeholders: List[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == GatewayDecision.ALLOW

    @property
    def blocked(self) -> bool:
        return self.decision == GatewayDecision.BLOCK


class CommandGateway:
    """Stateless policy engine; all secret state lives in the per-session vault."""

    def _block(self, reason: str, placeholders: Sequence[str]) -> GatewayResult:
        return GatewayResult(GatewayDecision.BLOCK, reason=reason, placeholders=list(placeholders))

    # ------------------------------------------------------------------ raw shell
    def process_command(self, command: str, vault: PrivacyVault, _depth: int = 0) -> GatewayResult:
        # Secret placeholders (credentials/tokens) must never end up in an
        # executed command, even glued to a flag (e.g. `-pCRED_001`), so scan
        # for them without a word boundary and refuse outright.
        secret_prefixes = [c.value for c in vault.SECRET_CATEGORIES]
        if secret_prefixes:
            secret_re = re.compile(r"(?:%s)_\d{3,}" % "|".join(secret_prefixes))
            if secret_re.search(command):
                return self._block("secret value must never be restored into an executed command", [])

        placeholders = PLACEHOLDER_RE.findall(command)
        if not placeholders:
            # No sensitive tokens involved — pass through unchanged.
            return GatewayResult(GatewayDecision.ALLOW, command=command)

        placeholders = list(dict.fromkeys(placeholders))  # dedupe, keep order

        # Every placeholder must be one the vault actually minted this session.
        # A model-invented placeholder is refused (it cannot be resolved and is a
        # sign of tampering / hallucination).
        unknown = [p for p in placeholders if vault.category_of(p) is None]
        if unknown:
            return self._block(f"unknown placeholder(s) not issued this session: {unknown}", placeholders)

        if vault.is_expired():
            return self._block("session privacy vault expired; refusing to rehydrate", placeholders)

        if _depth > 3:
            return self._block("command nesting too deep", placeholders)

        try:
            argv = shlex.split(command)
        except ValueError:
            return self._block("command could not be parsed safely", placeholders)
        if not argv:
            return self._block("empty command", placeholders)

        tool = os.path.basename(argv[0])

        # 1) Shell wrappers: analyse the inner command with the same rules.
        if tool in _SHELL_WRAPPERS and "-c" in argv:
            try:
                idx = argv.index("-c")
                inner = argv[idx + 1]
            except (ValueError, IndexError):
                return self._block("malformed shell -c invocation", placeholders)
            inner_res = self.process_command(inner, vault, _depth=_depth + 1)
            if inner_res.blocked:
                return inner_res
            rebuilt = " ".join(argv[:idx + 1]) + " " + shlex.quote(inner_res.command or "")
            return GatewayResult(GatewayDecision.ALLOW, command=rebuilt, placeholders=placeholders)

        # 2) Print / echo sinks — refuse to reveal a value.
        if tool in _PRINT_SINKS:
            return self._block(
                f"placeholder passed to '{tool}' (printing/echoing a protected value is not allowed)",
                placeholders,
            )

        # 3) Network redirection / process substitution carrying a placeholder.
        if _NET_REDIRECT_RE.search(command):
            return self._block("placeholder combined with a network redirect/process substitution", placeholders)

        # 4) Per-token URL analysis (the classic exfil vector).
        for tok in argv:
            tok_ph = PLACEHOLDER_RE.findall(tok)
            if not tok_ph:
                continue
            if re.match(r"https?://", tok, re.IGNORECASE):
                parts = urlsplit(tok)
                # urlsplit lowercases .hostname; restore case to match a placeholder.
                host = (parts.hostname or "").upper()
                host_is_ph = bool(PLACEHOLDER_RE.fullmatch(host))
                # A protected value in the query/fragment is exfiltration.
                if PLACEHOLDER_RE.search(parts.query) or PLACEHOLDER_RE.search(parts.fragment):
                    return self._block(
                        "placeholder embedded in a URL query/fragment (exfiltration vector)", placeholders
                    )
                # If the destination host is a literal (not the target itself),
                # any placeholder in the URL is being sent to a third party.
                if not host_is_ph:
                    return self._block(
                        "placeholder sent to a literal (non-target) URL host (exfiltration)", placeholders
                    )

        # 5) Outbound request bodies (curl/wget POST/upload) with a placeholder.
        for i, tok in enumerate(argv):
            if tok in _OUTBOUND_DATA_FLAGS:
                nxt = argv[i + 1] if i + 1 < len(argv) else ""
                if PLACEHOLDER_RE.search(nxt) or (tok.startswith("--") and "=" in tok and PLACEHOLDER_RE.search(tok)):
                    return self._block("placeholder placed in an outbound request body/upload (exfiltration)", placeholders)

        # 6) Bare network sinks (nc/telnet/ssh/...): the destination must be the
        #    target placeholder itself, never a literal with a placeholder tag along.
        if tool in _NET_SINKS and tool not in {"curl", "wget"}:
            arg_hosts = [a for a in argv[1:] if not a.startswith("-")]
            dest_is_ph = any(PLACEHOLDER_RE.fullmatch(a) for a in arg_hosts[:1])
            if not dest_is_ph:
                return self._block(
                    f"'{tool}' with a placeholder but a non-target destination (exfiltration)", placeholders
                )

        # Approved: rehydrate the validated placeholders in place.
        return self._rehydrate(command, placeholders, vault)

    def _rehydrate(self, command: str, placeholders: Sequence[str], vault: PrivacyVault) -> GatewayResult:
        real_map: Dict[str, str] = {}
        for ph in placeholders:
            cat = vault.category_of(ph)
            if cat in vault.SECRET_CATEGORIES:
                # Secrets (credentials/tokens) are never restored into a command.
                return self._block(
                    f"secret value {ph} is never restored into an executed command", placeholders
                )
            real = vault.rehydrate(ph)
            if real is None:
                return self._block(f"could not resolve placeholder {ph}", placeholders)
            # A rehydrated value must never carry shell metacharacters — that
            # would turn a scan argument into a command-injection primitive.
            if _SHELL_META_RE.search(real):
                return self._block(f"resolved value for {ph} contains unsafe characters", placeholders)
            real_map[ph] = real

        def repl(m: re.Match) -> str:
            return real_map[m.group("ph")]

        rehydrated = PLACEHOLDER_RE.sub(repl, command)
        return GatewayResult(GatewayDecision.ALLOW, command=rehydrated, placeholders=list(placeholders))

    # ------------------------------------------------------------- structured tool
    def process_tool_call(
        self,
        tool: str,
        args: Dict[str, object],
        rehydrate_fields: Sequence[str],
        vault: PrivacyVault,
    ) -> GatewayResult:
        """Rehydrate only the whitelisted fields of a structured tool call.

        Everything not in ``rehydrate_fields`` is left as-is; a placeholder found
        in a non-approved field is refused (it must not be silently resolved).
        """
        resolved: Dict[str, object] = {}
        seen: List[str] = []
        allow = set(rehydrate_fields)
        for key, value in args.items():
            if isinstance(value, str):
                phs = PLACEHOLDER_RE.findall(value)
                if phs and key not in allow:
                    return self._block(
                        f"placeholder in non-approved field '{key}' (only {sorted(allow)} may be rehydrated)",
                        phs,
                    )
                if phs:
                    seen.extend(phs)
                    res = self._rehydrate(value, phs, vault)
                    if res.blocked:
                        return res
                    resolved[key] = res.command
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        return GatewayResult(
            GatewayDecision.ALLOW,
            resolved=resolved,
            placeholders=list(dict.fromkeys(seen)),
        )

    def process_target_url(self, url: str, vault: PrivacyVault) -> GatewayResult:
        """Resolve a protected HTTP(S) target without permitting URL exfiltration.

        A full ``URL_*`` placeholder may represent the complete target. Otherwise
        placeholders are accepted only as the entire hostname. Protected values
        in userinfo, path, query, or fragment positions are refused.
        """

        value = (url or "").strip()
        full_placeholder = PLACEHOLDER_RE.fullmatch(value)
        if full_placeholder:
            placeholder = full_placeholder.group("ph")
            category = vault.category_of(placeholder)
            if category is None:
                return self._block(
                    f"unknown placeholder not issued this session: {placeholder}",
                    [placeholder],
                )
            if category is not Category.URL:
                return self._block(
                    "only a URL placeholder may replace the complete target URL",
                    [placeholder],
                )
            real_url = vault.rehydrate(placeholder)
            if real_url is None:
                return self._block(
                    f"could not resolve placeholder {placeholder}", [placeholder]
                )
            value = real_url

        placeholders = list(dict.fromkeys(PLACEHOLDER_RE.findall(value)))
        unknown = [item for item in placeholders if vault.category_of(item) is None]
        if unknown:
            return self._block(
                f"unknown placeholder(s) not issued this session: {unknown}",
                placeholders,
            )
        if vault.is_expired():
            return self._block(
                "session privacy vault expired; refusing to rehydrate", placeholders
            )

        try:
            parts = urlsplit(value)
            port = parts.port
        except ValueError:
            return self._block("target URL could not be parsed safely", placeholders)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return self._block("target URL must use http or https", placeholders)
        if parts.username is not None or parts.password is not None:
            return self._block(
                "credentials in target URL userinfo are forbidden", placeholders
            )

        protected_non_host = "".join((parts.path, parts.query, parts.fragment))
        if PLACEHOLDER_RE.search(protected_non_host):
            return self._block(
                "placeholder in URL path/query/fragment is an exfiltration vector",
                placeholders,
            )

        # A fully rehydrated URL_* value has no placeholders left and is now safe.
        if not placeholders:
            return GatewayResult(GatewayDecision.ALLOW, command=value)

        host_token = (parts.hostname or "").upper()
        host_match = PLACEHOLDER_RE.fullmatch(host_token)
        if host_match is None or set(placeholders) != {host_match.group("ph")}:
            return self._block(
                "protected target must occupy the complete URL hostname",
                placeholders,
            )

        placeholder = host_match.group("ph")
        category = vault.category_of(placeholder)
        if category not in _HOST_CATEGORIES:
            return self._block(
                f"placeholder {placeholder} does not contain a hostname",
                placeholders,
            )
        real_host = vault.rehydrate(placeholder)
        if real_host is None:
            return self._block(
                f"could not resolve placeholder {placeholder}", placeholders
            )
        normalized_host = _safe_rehydrated_host(real_host)
        if normalized_host is None or _SHELL_META_RE.search(normalized_host):
            return self._block(
                f"resolved value for {placeholder} is not a safe hostname",
                placeholders,
            )

        rendered_host = (
            f"[{normalized_host}]" if ":" in normalized_host else normalized_host
        )
        netloc = rendered_host if port is None else f"{rendered_host}:{port}"
        resolved_url = urlunsplit(
            (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
        )
        return GatewayResult(
            GatewayDecision.ALLOW,
            command=resolved_url,
            placeholders=placeholders,
        )

    # ------------------------------------------------------------------ output
    def sanitize_output(self, text: str, vault: PrivacyVault) -> str:
        """Re-tokenize any real value in tool output before the LLM sees it.

        Two passes: (1) pattern-based tokenization (catches new + known values,
        deterministically reusing existing placeholders); (2) a belt-and-braces
        replacement of any *known* real value that slipped past the patterns.
        """
        if not text:
            return text
        out = vault.tokenize(text)
        # Belt-and-braces pass for values the patterns cannot match: only the
        # register-only categories (credentials/usernames) or categories not
        # covered by the regex pass. Skipping the pattern-covered categories
        # avoids decrypting every known value on large outputs (O(N) -> O(few)).
        regex_cats = set(vault.enabled_categories)
        for ph in vault.known_placeholders():
            cat = vault.category_of(ph)
            if cat in regex_cats:
                continue  # already handled deterministically by tokenize()
            real = vault.rehydrate(ph, allow_secret=True)  # local masking may touch secrets to hide them
            if real and real in out:
                out = out.replace(real, ph)
        return out
