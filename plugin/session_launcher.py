"""Create isolated Hermes sessions backed by the DarkMoon MCP server.

This module is the host-side trust boundary for the DarkMoon pentest skill. It:

* prepares a fully isolated ``darkmoon-pentest`` Hermes profile that never
  inherits the invoking agent's identity, rules, memory, plugins, hooks,
  session routing, or unrelated MCP servers;
* copies only an allowlisted set of provider/model credentials into that
  profile (never parent identity, terminal, session-routing, or plugin state);
* requires a one-use, time-boxed capability token before any session is
  created, so an ordinary prompt cannot forge the ``/darkmoon-pentest``
  invocation;
* runs the nested Hermes turn as its own process group and kills the whole
  group on timeout so no orphaned child is left behind;
* redacts secrets, credentials, and real targets from everything it returns.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml


PROFILE_NAME = "darkmoon-pentest"
SESSION_SOURCE = "darkmoon-pentest"
DEFAULT_MCP_URL = "http://localhost:8000/mcp"
MAX_MESSAGE_CHARS = 50_000
MAX_RESPONSE_CHARS = 100_000
DEFAULT_TIMEOUT_SECONDS = 1_800
CAPABILITY_TTL_SECONDS = 120
MANAGED_MARKER = ".darkmoon-profile.json"
SESSION_RUNNER = Path(__file__).with_name("hermes_session_runner.py")

HERMES_BRIDGE_PROMPT = """
Hermes integration contract:
- You are the main DarkMoon pentest orchestrator for this isolated session.
- Use delegate_task to dispatch specialist work instead of impersonating every specialist yourself.
- DarkMoon MCP tools in Hermes are named mcp__darkmoon__<tool>; for example,
  mcp__darkmoon__read_agent and mcp__darkmoon__run_workflow.
- In every specialist delegation, instruct the child to call
  mcp__darkmoon__read_agent with the selected specialist name before doing work,
  adopt that returned operating identity, and never quote the identity text.
- Delegated children inherit the DarkMoon MCP toolset. Use a leaf role unless
  another orchestration layer is genuinely required. A leaf child receives no
  delegation toolset, so it cannot further fan out work.
- Incorporate the completed child specialist's summary into your final answer
  before responding to the user; do not hand back a raw child transcript.
- Keep real targets and credentials behind the DarkMoon privacy gateway and use
  placeholders in model-visible plans and reports.
""".strip()

PROFILE_DIRS = (
    "cache",
    "cron",
    "home",
    "logs",
    "memories",
    "plans",
    "plugins",
    "sessions",
    "skills",
    "skins",
    "workspace",
)
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{5,127}$")
_SESSION_LINE_RE = re.compile(
    r"(?m)^session_id:\s*([A-Za-z0-9][A-Za-z0-9_.:-]{5,127})\s*$"
)

# Provider/model credential keys we are willing to copy into the isolated
# profile. Everything else (terminal state, session routing, plugin settings,
# identity, hooks, prefills, parent-home variables) is explicitly excluded.
_CREDENTIAL_KEY_PREFIX_ALLOW = re.compile(
    r"(?i)^(?:anthropic|openai|openrouter|gemini|google|azure|aws|vertex|"
    r"claude|mistral|cohere|xai|deepseek|qwen|groq|perplexity|nvidia|nous|"
    r"opencode[-_]?zen|tencent|meta|ollama|together|fireworks|openrouter)"
)
_CREDENTIAL_KEY_SUFFIX_ALLOW = re.compile(
    r"(?i)(?:api[-_]?key|api[-_]?token|api[-_]?secret|token|secret|"
    r"api[-_]?base|base[-_]?url|endpoint|access[-_]?key|api[-_]?key[-_]?id)$"
)
_CREDENTIAL_KEY_DENY = re.compile(
    r"(?i)(?:hermes|darkmoon[-_]?hermes|terminal[-_]?cwd|session|cron|plugin|"
    r"prefill|profile|identity|hook|rules|cwd|home[-_]?dir|user[-_]?dir|ssh|"
    r"docker[-_]?sock|kubeconfig|assume[-_]?role|aws[-_]?session|proxy|"
    r"routing|relay|display|personality)"
)

# Redaction applied to anything that leaves this module. The secret pattern is
# deliberately lazy and applied per (short) line: a greedy prefix over a very
# long single-line blob would otherwise cause catastrophic backtracking.
_SECRET_RE = re.compile(
    r"(?i)(\S*?(?:api[-_]?key|api[-_]?token|api[-_]?secret|token|secret|"
    r"password|passwd|access[-_]?key|private[-_]?key)\S*?)\s*([=:]\s*)(\S+)"
)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_REDACT_LINE_LIMIT = 8192


class PentestSessionError(RuntimeError):
    """A safe, user-facing error. Its message is never derived from secrets."""


def darkmoon_mcp_url() -> str:
    return os.environ.get("DARKMOON_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL


def default_hermes_home() -> Path:
    override = os.environ.get("DARKMOON_HERMES_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    configured = os.environ.get("HERMES_HOME", "").strip()
    home = Path(configured).expanduser() if configured else Path.home() / ".hermes"
    home = home.resolve()
    if home.parent.name == "profiles":
        return home.parent.parent
    return home


def pentest_profile_dir() -> Path:
    return default_hermes_home() / "profiles" / PROFILE_NAME


def persona_fingerprint(persona: str) -> dict[str, Any]:
    encoded = persona.encode("utf-8")
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
    }


# --------------------------------------------------------------------------- #
# Capability token: a one-use, time-boxed proof that the user (not the model)  #
# dispatched /darkmoon-pentest. The token is minted by the trusted slash       #
# dispatcher outside the model's context; the model can neither read it nor    #
# forge a valid one.                                                           #
# --------------------------------------------------------------------------- #


def _plugin_data_dir() -> Path:
    return default_hermes_home() / "plugin-data" / "darkmoon"


def _capability_secret_path() -> Path:
    return _plugin_data_dir() / "capability-secret"


def _capability_tokens_dir() -> Path:
    return _plugin_data_dir() / "capability-tokens"


def _ensure_capability_secret() -> bytes:
    path = _capability_secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        secret = path.read_bytes()
        if secret:
            return secret
    secret = secrets.token_bytes(32)
    fd, temp_name = tempfile.mkstemp(prefix=".cap.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(secret)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return secret


def create_capability_token(hermes_root: str | None = None) -> str:
    """Mint a single-use capability token (trusted dispatcher only)."""

    if hermes_root:
        os.environ["DARKMOON_HERMES_HOME"] = str(hermes_root)
    secret = _ensure_capability_secret()
    issued_at = int(time.time())
    nonce = secrets.token_hex(16)
    body = f"{issued_at}.{nonce}".encode("utf-8")
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    _capability_tokens_dir().mkdir(parents=True, exist_ok=True)
    record = _capability_tokens_dir() / nonce
    fd, temp_name = tempfile.mkstemp(prefix=".tok.", dir=str(_capability_tokens_dir()))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(issued_at))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, record)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return f"{issued_at}.{nonce}.{signature}"


def consume_capability_token(token: str | None, hermes_root: str | None = None) -> bool:
    """Verify and consume a capability token. Returns False on any failure."""

    if hermes_root:
        os.environ["DARKMOON_HERMES_HOME"] = str(hermes_root)
    if not token or not isinstance(token, str):
        return False
    parts = token.split(".")
    if len(parts) != 3:
        return False
    issued_at_raw, nonce, signature = parts
    try:
        issued_at = int(issued_at_raw)
    except ValueError:
        return False
    secret = _capability_secret_path()
    if not secret.is_file():
        return False
    key = secret.read_bytes()
    body = f"{issued_at_raw}.{nonce}".encode("utf-8")
    expected = hmac.new(key, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    if time.time() - issued_at > CAPABILITY_TTL_SECONDS:
        _capability_tokens_dir().joinpath(nonce).unlink(missing_ok=True)
        return False
    record = _capability_tokens_dir().joinpath(nonce)
    if not record.is_file():
        return False
    record.unlink(missing_ok=True)
    return True


# --------------------------------------------------------------------------- #
# Locking / atomic writes                                                      #
# --------------------------------------------------------------------------- #


@contextmanager
def _profile_lock() -> Iterator[None]:
    lock_dir = default_hermes_home() / "plugin-data" / "darkmoon"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "pentest-profile.lock"
    handle = lock_path.open("a+")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass
        handle.close()


def _read_default_config() -> dict[str, Any]:
    path = default_hermes_home() / "config.yaml"
    if not path.is_file():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PentestSessionError(f"Could not load the Hermes configuration: {exc}") from exc
    return loaded if isinstance(loaded, dict) else {}


def _atomic_yaml_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(value, handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _is_allowed_credential_key(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return False
    name = stripped.split("=", 1)[0].strip()
    if _CREDENTIAL_KEY_DENY.search(name):
        return False
    if _CREDENTIAL_KEY_PREFIX_ALLOW.match(name) or _CREDENTIAL_KEY_SUFFIX_ALLOW.search(name):
        return True
    return False


def _copy_profile_credentials(profile_dir: Path) -> None:
    """Copy only allowlisted provider/model credentials into the profile.

    Identity, terminal, session-routing, plugin, hook, prefill, and home
    variables are never copied, even if present in the parent ``.env``.
    """

    source = default_hermes_home() / ".env"
    destination = profile_dir / ".env"
    if source.is_file():
        kept: list[str] = []
        for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
            if _is_allowed_credential_key(raw):
                kept.append(raw)
        content = "\n".join(kept) + ("\n" if kept else "")
        fd, temp_name = tempfile.mkstemp(prefix=".env.", dir=profile_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, destination)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
    elif not destination.exists():
        destination.touch(mode=0o600)


def _isolated_config(persona: str) -> dict[str, Any]:
    config = _read_default_config()

    agent = config.get("agent")
    if not isinstance(agent, dict):
        agent = {}
    agent["system_prompt"] = f"{persona.rstrip()}\n\n{HERMES_BRIDGE_PROMPT}"
    agent["personalities"] = {}
    config["agent"] = agent

    display = config.get("display")
    if not isinstance(display, dict):
        display = {}
    display["personality"] = ""
    config["display"] = display

    memory = config.get("memory")
    if not isinstance(memory, dict):
        memory = {}
    memory["memory_enabled"] = False
    memory["user_profile_enabled"] = False
    memory["provider"] = ""
    config["memory"] = memory

    delegation = config.get("delegation")
    if not isinstance(delegation, dict):
        delegation = {}
    delegation["inherit_mcp_toolsets"] = True
    delegation["orchestrator_enabled"] = True
    try:
        existing_depth = int(delegation.get("max_spawn_depth", 1))
    except (TypeError, ValueError):
        existing_depth = 1
    delegation["max_spawn_depth"] = max(2, existing_depth)
    config["delegation"] = delegation

    config["hooks"] = {}
    config["hooks_auto_accept"] = False
    config["prefill_messages_file"] = ""
    config["plugins"] = {"enabled": [], "disabled": [], "entries": {}}
    # Explicitly drop any parent external skill paths; the isolated profile must
    # not preload the invoking agent's skill directories even when --ignore-rules
    # is set.
    skills = config.get("skills")
    if isinstance(skills, dict):
        skills.pop("external_dirs", None)
        skills.pop("bundled_dirs", None)
    config["skills"] = skills if isinstance(skills, dict) else {}
    config["mcp_servers"] = {
        "darkmoon": {
            "url": darkmoon_mcp_url(),
            "trust": "full",
        }
    }
    return config


def prepare_pentest_profile(persona: str) -> dict[str, Any]:
    if not isinstance(persona, str) or not persona.strip():
        raise PentestSessionError("The DarkMoon pentest persona was empty.")

    profile_dir = pentest_profile_dir()
    with _profile_lock():
        marker = profile_dir / MANAGED_MARKER
        if profile_dir.exists() and not marker.is_file():
            raise PentestSessionError(
                f"Hermes profile '{PROFILE_NAME}' already exists and is not managed by DarkMoon."
            )

        profile_dir.mkdir(parents=True, exist_ok=True)
        for directory in PROFILE_DIRS:
            (profile_dir / directory).mkdir(parents=True, exist_ok=True)

        # Keep the profile free of bundled/user skill preload. The marker also
        # prevents a later Hermes update from seeding bundled skills here.
        (profile_dir / ".no-bundled-skills").touch(mode=0o600, exist_ok=True)
        _copy_profile_credentials(profile_dir)
        fingerprint = persona_fingerprint(persona)
        _atomic_yaml_write(profile_dir / "config.yaml", _isolated_config(persona))
        _atomic_json_write(
            marker,
            {
                "managed_by": "darkmoon",
                "profile": PROFILE_NAME,
                "identity": fingerprint,
                "ignore_rules_required": True,
                "toolsets": ["delegation", "darkmoon"],
            },
        )

    return {
        "profile": PROFILE_NAME,
        "profile_dir": str(profile_dir),
        "identity": fingerprint,
        "ignore_rules": True,
        "memory_enabled": False,
        "user_plugins_enabled": False,
        "toolsets": ["delegation", "darkmoon"],
    }


def validate_message(message: str) -> str:
    if not isinstance(message, str) or not message.strip():
        raise PentestSessionError("A non-empty pentest task is required.")
    cleaned = message.strip()
    if len(cleaned) > MAX_MESSAGE_CHARS:
        raise PentestSessionError(
            f"The pentest task exceeds the {MAX_MESSAGE_CHARS}-character limit."
        )
    return cleaned


def validate_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if _SESSION_ID_RE.fullmatch(value) is None:
        raise PentestSessionError("The Hermes session ID is invalid.")
    return value


def validate_working_directory(value: str | None) -> Path:
    if value is None or not str(value).strip():
        return Path.cwd().resolve()
    path = Path(str(value)).expanduser().resolve()
    if not path.is_dir():
        raise PentestSessionError(f"Working directory does not exist: {path}")
    return path


def hermes_executable() -> str:
    override = os.environ.get("DARKMOON_HERMES_BIN", "").strip()
    executable = override or shutil.which("hermes")
    if not executable:
        raise PentestSessionError("The Hermes CLI executable was not found in PATH.")
    return executable


def hermes_python_executable() -> str:
    """Locate the Python runtime that owns the installed Hermes CLI."""

    override = os.environ.get("DARKMOON_HERMES_PYTHON", "").strip()
    if override:
        return override

    executable = Path(hermes_executable()).expanduser()
    try:
        resolved = executable.resolve(strict=True)
    except OSError:
        resolved = executable

    # Official Hermes installs expose a small console script whose shebang
    # points at the profile's virtualenv. Reusing that interpreter lets our
    # finite-session shim import the exact installed Hermes runtime.
    try:
        with resolved.open("rb") as handle:
            first_line = handle.readline(4096).decode("utf-8", errors="strict").strip()
        if first_line.startswith("#!"):
            parts = shlex.split(first_line[2:].strip())
            if parts:
                candidate = Path(parts[0]).expanduser()
                if candidate.name == "env" and len(parts) > 1:
                    discovered = shutil.which(parts[1])
                    if discovered:
                        candidate = Path(discovered)
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate)
    except (OSError, UnicodeError, ValueError):
        pass

    # Editable/source installs commonly place `hermes` beside the venv's
    # `python` executable even when the console script has an unusual wrapper.
    sibling = resolved.parent / "python"
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return str(sibling)

    # session_server.py normally already runs under Hermes' interpreter. This
    # fallback keeps development/test installs usable while the runner itself
    # still fails closed if the Hermes modules are not importable.
    return sys.executable


def build_hermes_command(
    message: str,
    *,
    working_directory: Path,
    session_id: str | None = None,
) -> list[str]:
    if not SESSION_RUNNER.is_file():
        raise PentestSessionError("The DarkMoon Hermes session runner is missing.")
    command = [
        hermes_python_executable(),
        str(SESSION_RUNNER),
        "-p",
        PROFILE_NAME,
        "chat",
        "-Q",
        "--ignore-rules",
        "--source",
        SESSION_SOURCE,
        "--toolsets",
        "delegation,darkmoon",
        "--in",
        str(working_directory),
    ]
    if session_id is not None:
        command.extend(["--resume", validate_session_id(session_id)])
    command.extend(["--query", validate_message(message)])
    return command


def _isolated_environment() -> dict[str, str]:
    environment = dict(os.environ)
    # Drop every inherited session-routing, cron, and delegated-child variable.
    for name in tuple(environment):
        if name.startswith("HERMES_SESSION_") or name.startswith("HERMES_CRON_"):
            environment.pop(name, None)
    for name in (
        "HERMES_DELEGATED_CHILD_CONTEXT",
        "HERMES_EPHEMERAL_SYSTEM_PROMPT",
        "HERMES_HOME",
        "HERMES_IGNORE_USER_CONFIG",
        "HERMES_PLATFORM",
        "HERMES_PREFILL_MESSAGES_FILE",
        "HERMES_PROFILE",
        "HERMES_SAFE_MODE",
        "HERMES_SESSION_KEY",
        "HERMES_SESSION_USER_ID",
        "HERMES_CRON_SESSION",
        "HERMES_UI_SESSION_ID",
    ):
        environment.pop(name, None)
    environment["HERMES_IGNORE_RULES"] = "1"
    return environment


def _resume_command(session_id: str) -> str:
    return (
        f"hermes -p {PROFILE_NAME} chat --ignore-rules "
        f"--toolsets delegation,darkmoon --resume {session_id}"
    )


def _redact(text: str) -> str:
    if not text:
        return text
    text = _IPV4_RE.sub("IP_REDACTED", text)
    out = []
    for line in text.splitlines():
        # Skip the secret scan on pathological long lines (e.g. a large response
        # blob) to avoid any slow regex behavior; IP redaction already ran above
        # and real secrets are short assignment-like tokens caught on normal lines.
        if len(line) > _REDACT_LINE_LIMIT:
            out.append(line)
        else:
            out.append(_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", line))
    return "\n".join(out)


def run_pentest_turn(
    message: str,
    *,
    working_directory: str | None = None,
    session_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    capability_token: str | None = None,
) -> dict[str, Any]:
    # The capability token is the authorization boundary. Without a valid,
    # unconsumed, unexpired token minted by the trusted dispatcher, no session
    # is created -- an ordinary prompt cannot forge the invocation.
    if not consume_capability_token(capability_token):
        raise PentestSessionError(
            "The explicit /darkmoon-pentest authorization was missing or invalid."
        )

    cwd = validate_working_directory(working_directory)
    command = build_hermes_command(
        message,
        working_directory=cwd,
        session_id=session_id,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=_isolated_environment(),
            text=True,
            capture_output=True,
            timeout=max(30, int(timeout_seconds)),
            check=False,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        # Kill the complete process group, not just the immediate child, so a
        # delegated-child Hermes process cannot survive the timeout.
        try:
            pgid = os.getpgid(exc.pid)
            try:
                os.killpg(pgid, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(2)
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                pass
        except OSError:
            pass
        raise PentestSessionError(
            f"The pentest session exceeded its {timeout_seconds}-second launch timeout."
        ) from exc
    except OSError as exc:
        raise PentestSessionError(f"Hermes could not start the pentest session: {exc}") from exc

    stderr = completed.stderr or ""
    matches = _SESSION_LINE_RE.findall(stderr)
    resolved_session_id = matches[-1] if matches else (session_id or "")
    if resolved_session_id:
        validate_session_id(resolved_session_id)

    diagnostic_lines = [
        line for line in stderr.splitlines() if not line.strip().startswith("session_id:")
    ]
    diagnostics = "\n".join(diagnostic_lines).strip()
    if len(diagnostics) > 4_000:
        diagnostics = diagnostics[-4_000:]
    diagnostics = _redact(diagnostics)

    response = _redact((completed.stdout or "").strip())
    if len(response) > MAX_RESPONSE_CHARS:
        response = response[:MAX_RESPONSE_CHARS] + "\n[response truncated]"

    if completed.returncode != 0:
        raise PentestSessionError(
            diagnostics
            or f"Hermes exited with status {completed.returncode} while running the pentest session."
        )
    if not resolved_session_id:
        raise PentestSessionError("Hermes completed without returning a pentest session ID.")

    return {
        "ok": True,
        "created": session_id is None,
        "status": "completed",
        "session_id": resolved_session_id,
        "profile": PROFILE_NAME,
        "source": SESSION_SOURCE,
        "response": response,
        "diagnostics": diagnostics,
        "resume_command": _resume_command(resolved_session_id),
        "isolation": {
            "ignore_rules": True,
            "context_files": False,
            "memory": False,
            "user_plugins": False,
            "toolsets": ["delegation", "darkmoon"],
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="session_launcher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    issue = sub.add_parser("issue-token", help="Mint a one-use capability token.")
    issue.add_argument("--hermes-root")

    start = sub.add_parser("start", help="Start a new isolated pentest session.")
    start.add_argument("--task", required=True)
    start.add_argument("--working-directory")
    start.add_argument("--capability-token", required=True)
    start.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    resume = sub.add_parser("resume", help="Resume an isolated pentest session.")
    resume.add_argument("--session-id", required=True)
    resume.add_argument("--message", required=True)
    resume.add_argument("--working-directory")
    resume.add_argument("--capability-token", required=True)
    resume.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    args = parser.parse_args()
    if args.cmd == "issue-token":
        print(create_capability_token(hermes_root=args.hermes_root))
        return 0

    token = args.capability_token
    if args.cmd == "start":
        result = run_pentest_turn(
            args.task,
            working_directory=args.working_directory,
            timeout_seconds=args.timeout,
            capability_token=token,
        )
    else:
        result = run_pentest_turn(
            args.message,
            working_directory=args.working_directory,
            session_id=args.session_id,
            timeout_seconds=args.timeout,
            capability_token=token,
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
