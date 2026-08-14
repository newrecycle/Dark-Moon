"""Register DarkMoon's portable skills with Hermes slash-command discovery.

Registration is idempotent, atomic, and concurrent-safe (flock). It adds only
the DarkMoon-owned skills directory to ``skills.external_dirs`` and removes
stale DarkMoon skill paths left by earlier installations. It never touches
unrelated external skill directories and never alters the rest of config.yaml.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml


class HermesRegistrationError(RuntimeError):
    """A safe registration failure suitable for setup-script output."""


def _is_darkmoon_skill_path(path: Path) -> bool:
    """True for a path DarkMoon owns (a skills dir under a darkmoon plugin).

    Matched case-insensitively so both ``darkmoon`` and ``darkmoon-<hash>``
    install layouts are recognized, regardless of the host filesystem case.
    """

    return path.name == "skills" and any(
        part.lower() == "darkmoon" or part.lower().startswith("darkmoon-")
        for part in path.parts
    )


def default_hermes_root() -> Path:
    configured = os.environ.get("DARKMOON_HERMES_HOME", "").strip()
    if not configured:
        configured = os.environ.get("HERMES_HOME", "").strip()
    home = Path(configured).expanduser() if configured else Path.home() / ".hermes"
    home = home.resolve()
    if home.parent.name == "profiles":
        return home.parent.parent
    return home


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise HermesRegistrationError(f"Could not read the Hermes configuration: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise HermesRegistrationError("The Hermes configuration must contain a mapping.")
    return loaded


def _atomic_write(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, previous_mode)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


@contextmanager
def _registration_lock(home: Path) -> Iterator[None]:
    lock_dir = home / "plugin-data" / "darkmoon"
    lock_dir.mkdir(parents=True, exist_ok=True)
    handle = (lock_dir / "skill-registration.lock").open("a+")
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


def _ensure_capability_secret(home: Path) -> None:
    """Create the DarkMoon capability secret (mode 600) if it is absent."""

    import secrets

    data_dir = home / "plugin-data" / "darkmoon"
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_path = data_dir / "capability-secret"
    if secret_path.is_file():
        return
    secret = secrets.token_bytes(32)
    fd, temporary = tempfile.mkstemp(prefix=".cap.", dir=str(data_dir))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(secret)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, secret_path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def register_skill_directory(
    plugin_root: str | Path,
    *,
    hermes_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(plugin_root).expanduser().resolve()
    skills_dir = (root / "skills").resolve()
    if not skills_dir.is_dir():
        raise HermesRegistrationError(f"DarkMoon skills directory is missing: {skills_dir}")

    home = (
        Path(hermes_root).expanduser().resolve()
        if hermes_root is not None
        else default_hermes_root()
    )
    with _registration_lock(home):
        config_path = home / "config.yaml"
        config = _read_config(config_path)

        skills = config.get("skills")
        if not isinstance(skills, dict):
            skills = {}
        existing = skills.get("external_dirs")
        if not isinstance(existing, list):
            existing = []

        kept: list[str] = []
        resolved: set[Path] = set()
        for item in existing:
            if not isinstance(item, str) or not item.strip():
                continue
            try:
                resolved_path = Path(item).expanduser().resolve()
            except OSError:
                kept.append(item.strip())
                continue
            # Drop stale DarkMoon skill paths; unrelated dirs are preserved.
            if _is_darkmoon_skill_path(resolved_path) and resolved_path != skills_dir:
                continue
            kept.append(str(resolved_path))
            resolved.add(resolved_path)

        changed = skills_dir not in resolved
        if changed:
            kept.append(str(skills_dir))

        # De-duplicate while preserving order.
        seen: set[str] = set()
        normalized: list[str] = []
        for value in kept:
            if value not in seen:
                seen.add(value)
                normalized.append(value)

        skills["external_dirs"] = normalized
        config["skills"] = skills
        if changed or not config_path.exists():
            _atomic_write(config_path, config)
        _ensure_capability_secret(home)

    return {
        "ok": True,
        "changed": changed,
        "hermes_root": str(home),
        "skills_dir": str(skills_dir),
    }


def unregister_skill_directory(
    *,
    hermes_root: str | Path | None = None,
) -> dict[str, Any]:
    """Remove only the DarkMoon-owned skills.external_dirs entries."""

    home = (
        Path(hermes_root).expanduser().resolve()
        if hermes_root is not None
        else default_hermes_root()
    )
    with _registration_lock(home):
        config_path = home / "config.yaml"
        config = _read_config(config_path)
        skills = config.get("skills")
        if not isinstance(skills, dict) or not isinstance(
            skills.get("external_dirs"), list
        ):
            return {
                "ok": True,
                "changed": False,
                "hermes_root": str(home),
                "removed": [],
            }

        existing = skills["external_dirs"]
        removed: list[str] = []
        kept: list[str] = []
        for item in existing:
            if not isinstance(item, str) or not item.strip():
                kept.append(item)
                continue
            try:
                resolved_path = Path(item).expanduser().resolve()
            except OSError:
                kept.append(item)
                continue
            if _is_darkmoon_skill_path(resolved_path):
                removed.append(str(resolved_path))
                continue
            kept.append(str(resolved_path))

        seen: set[str] = set()
        normalized: list[str] = []
        for value in kept:
            if value not in seen:
                seen.add(value)
                normalized.append(value)

        skills["external_dirs"] = normalized
        config["skills"] = skills
        if removed:
            _atomic_write(config_path, config)

    return {
        "ok": True,
        "changed": bool(removed),
        "hermes_root": str(home),
        "removed": removed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-root", required=True)
    parser.add_argument("--hermes-root")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--unregister", action="store_true")
    args = parser.parse_args()
    try:
        if args.unregister:
            result = unregister_skill_directory(hermes_root=args.hermes_root)
        else:
            result = register_skill_directory(
                args.plugin_root,
                hermes_root=args.hermes_root,
            )
    except HermesRegistrationError as exc:
        parser.exit(1, f"DarkMoon Hermes registration failed: {exc}\n")
    if not args.quiet:
        if args.unregister:
            if result["removed"]:
                print(f"DarkMoon Hermes skills removed: {', '.join(result['removed'])}")
            else:
                print("No DarkMoon Hermes skills were registered.")
        else:
            state = "registered" if result["changed"] else "already registered"
            print(f"DarkMoon Hermes skills {state}: {result['skills_dir']}")
            print("Start a new Hermes session, or run /reload-skills in an existing one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
