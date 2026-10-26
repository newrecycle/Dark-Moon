#!/usr/bin/env python3
"""Live native-server/Docker validation. No inference, account login or target scan.

Uses a disposable OpenCode home or a disposable Docker container. Results mark
missing engines/accounts explicitly; test-provider keys never leave the server.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opencode-binary")
    parser.add_argument("--docker-image")
    parser.add_argument("--docker-binary", default=shutil.which("docker") or "docker")
    parser.add_argument("--compose-binary")
    parser.add_argument("--public-catalog", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    repo = Path(__file__).resolve().parents[1]

    def record(name, status, **details):
        results.append({"check": name, "status": status, **details})
        print(name + ": " + status, flush=True)

    def command(argv, **kw):
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=kw.pop("timeout", 60), **kw
        )

    compose = (
        [args.compose_binary]
        if args.compose_binary
        else [args.docker_binary, "compose"]
    )
    for name, files in [
        ("base", ["docker-compose.yml"]),
        ("bridge", ["docker-compose.yml", "docker-compose.community-bridge.yml"]),
        (
            "hardened-bridge",
            [
                "docker-compose.yml",
                "docker-compose.community-bridge.yml",
                "docker-compose.community-hardened.yml",
            ],
        ),
    ]:
        try:
            argv = compose[:]
            for file in files:
                argv += ["-f", str(repo / file)]
            # Resolve required env files in a disposable project directory.
            # This works with Compose versions predating --no-env-resolution
            # and never reads or creates an operator's .opencode.env.
            with tempfile.TemporaryDirectory(prefix="darkmoon-compose-") as project:
                (Path(project) / ".opencode.env").write_text("")
                r = command(
                    argv
                    + ["--project-directory", project, "config", "--format", "json"],
                    env=dict(
                        os.environ, OPENCODE_SERVER_PASSWORD="compose-validation-only"
                    ),
                )
            if r.returncode:
                raise ValueError("Compose rejected the configuration")
            config = json.loads(r.stdout)
            if name != "base":
                service = config["services"]["opencode"]
                assert service["ports"][0]["host_ip"] == "127.0.0.1"
                assert service["command"][1] == "serve"
                if name == "hardened-bridge":
                    assert service["read_only"] is True
            record("compose_" + name, "passed")
        except (OSError, ValueError, AssertionError, subprocess.TimeoutExpired) as exc:
            record(
                "compose_" + name,
                "blocked" if isinstance(exc, OSError) else "failed",
                reason=str(exc),
            )
    if args.public_catalog:
        try:
            with urllib.request.urlopen(
                "https://openrouter.ai/api/v1/models", timeout=30
            ) as response:
                listing = json.load(response)
            assert isinstance(listing.get("data"), list) and listing["data"]
            record(
                "openrouter_public_models",
                "passed",
                models=len(listing["data"]),
                credential_verified=False,
                inference_performed=False,
            )
        except (OSError, ValueError, AssertionError) as exc:
            record("openrouter_public_models", "failed", reason=type(exc).__name__)
    docker_available = False
    try:
        r = command([args.docker_binary, "info", "--format", "{{json .ServerVersion}}"])
        docker_available = r.returncode == 0
        record(
            "docker_engine",
            "passed" if docker_available else "blocked",
            reason=""
            if docker_available
            else "No usable Docker daemon in this environment",
        )
    except (OSError, subprocess.TimeoutExpired):
        record(
            "docker_engine",
            "blocked",
            reason="No usable Docker client/daemon in this environment",
        )
    password = "validation-" + uuid.uuid4().hex
    authorization = (
        "Basic " + base64.b64encode(("opencode:" + password).encode()).decode()
    )

    def request(base, path, method="GET", body=None, auth=True):
        req = urllib.request.Request(
            base + path,
            method=method,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": authorization} if auth else {}),
            },
            data=json.dumps(body).encode() if body is not None else None,
        )
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.load(response)

    def probe(base, label):
        health = None
        for _ in range(150):
            try:
                health = request(base, "/global/health")
                break
            except (OSError, ValueError):
                time.sleep(0.2)
        if not isinstance(health, dict) or health.get("healthy") is not True:
            raise ValueError("Native server failed to become healthy")
        try:
            request(base, "/provider", auth=False)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError(
                "Native server accepted an unauthenticated provider request"
            )
        listing = request(base, "/provider")
        methods = request(base, "/provider/auth")
        config = request(base, "/config")
        assert isinstance(listing.get("all"), list) and listing["all"]
        assert isinstance(methods, dict)
        connected = set(listing.get("connected", []))
        provider = next(
            (p for p in listing["all"] if p["id"] in connected and p.get("models")),
            None,
        )
        if not provider:
            raise ValueError(
                "No connected catalog provider was available for config validation"
            )
        candidates = [provider["id"] + "/" + mid for mid in provider["models"]]
        model = next(
            (mid for mid in candidates if mid != config.get("model")), candidates[0]
        )
        changed = request(
            base, "/global/config", "PATCH", {"model": model, "small_model": model}
        )
        assert changed.get("model") == model, (
            "Config PATCH did not return the requested model"
        )
        observed = request(base, "/config")
        model_verified = observed.get("model") == model
        small_verified = observed.get("small_model") == model
        assert (
            request(
                base,
                "/auth/darkmoon-validation",
                "PUT",
                {
                    "type": "api",
                    "key": "disposable-validation-key-not-a-provider-account",
                },
            )
            is True
        ), "Auth PUT did not return true"
        assert request(base, "/auth/darkmoon-validation", "DELETE") is True, (
            "Auth DELETE did not return true"
        )
        record(
            label,
            "passed" if model_verified and small_verified else "failed",
            model_readback_verified=model_verified,
            small_model_readback_verified=small_verified,
            reason=""
            if model_verified and small_verified
            else "Config PATCH accepted, but readback did not confirm the requested model settings",
            version=str(health.get("version", "unknown")),
            providers=len(listing["all"]),
            auth_method_providers=len(methods),
            checks=[
                "Basic-auth rejection",
                "health",
                "provider catalog",
                "login-method discovery",
                "config patch/readback",
                "API-key write/delete",
            ],
            inference_performed=False,
            real_account_oauth="not_run_no_account_configured",
        )

    if args.opencode_binary:
        with tempfile.TemporaryDirectory(prefix="darkmoon-live-native-") as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            env = dict(
                os.environ,
                HOME=str(home),
                XDG_CONFIG_HOME=str(root / "config"),
                XDG_DATA_HOME=str(root / "data"),
                XDG_CACHE_HOME=str(root / "cache"),
                OPENCODE_SERVER_PASSWORD=password,
                OPENCODE_SERVER_USERNAME="opencode",
                OPENCODE_DISABLE_DEFAULT_PLUGINS="true",
            )
            for key in list(env):
                if key in {
                    "OPENAI_API_KEY",
                    "OPENROUTER_API_KEY",
                    "ANTHROPIC_API_KEY",
                    "OPENCODE_CONFIG",
                    "OPENCODE_CONFIG_CONTENT",
                    "OPENCODE_LOCAL_API_KEY",
                }:
                    env.pop(key)
            subprocess.run(
                ["git", "init", "--quiet", str(root)], check=True, capture_output=True
            )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            with (root / "server.log").open("w") as log:
                process = subprocess.Popen(
                    [
                        args.opencode_binary,
                        "serve",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=root,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                try:
                    probe("http://127.0.0.1:" + str(port), "native_opencode_binary")
                except Exception as exc:
                    record(
                        "native_opencode_binary",
                        "failed",
                        reason=type(exc).__name__ + ": " + str(exc)[:250],
                    )
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    if args.docker_image:
        if not docker_available:
            record(
                "docker_opencode_image",
                "blocked",
                reason="Docker daemon unavailable; no image boot was performed",
            )
        else:
            name = "darkmoon-validation-" + uuid.uuid4().hex[:12]
            r = command(
                [
                    args.docker_binary,
                    "run",
                    "-d",
                    "--name",
                    name,
                    "-p",
                    "127.0.0.1::4096",
                    "-e",
                    "OPENCODE_SERVER_PASSWORD=" + password,
                    "-e",
                    "OPENCODE_SERVER_USERNAME=opencode",
                    "-e",
                    "DARKMOON_SKIP_TUI_BOOTSTRAP=1",
                    args.docker_image,
                    "opencode",
                    "serve",
                    "--hostname",
                    "0.0.0.0",
                    "--port",
                    "4096",
                ]
            )
            try:
                if r.returncode:
                    raise ValueError("Docker failed to start the validation container")
                port = (
                    command([args.docker_binary, "port", name, "4096/tcp"])
                    .stdout.strip()
                    .rsplit(":", 1)[-1]
                )
                if not port.isdigit():
                    raise ValueError(
                        "Validation container did not expose its server port"
                    )
                probe("http://127.0.0.1:" + port, "docker_opencode_image")
            except Exception as exc:
                record(
                    "docker_opencode_image",
                    "failed",
                    reason=type(exc).__name__ + ": " + str(exc)[:250],
                )
            finally:
                collected = command([args.docker_binary, "logs", name])
                logs = collected.stdout + collected.stderr
                # This container has no operator credentials or mounted host data.
                if args.output:
                    args.output.with_suffix(".container.log").write_text(logs)
                command([args.docker_binary, "rm", "-f", name])
    report = {
        "checks": results,
        "inference_performed": False,
        "real_provider_account_validation": "not_run_no_account_configured",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return (
        1
        if any(r["status"] == "failed" for r in results)
        else 2
        if any(r["status"] == "blocked" for r in results)
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
