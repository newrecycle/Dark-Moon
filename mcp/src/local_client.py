"""
Local-subprocess executor for the Darkmoon MCP server.

This is a drop-in replacement for DarkmoonDockerClient that runs tool commands
as LOCAL subprocesses instead of `docker exec`-ing into a toolbox container.
It is used when DARKMOON_EXEC_MODE=local is set, i.e. when the MCP runs INSIDE
the toolbox container itself and needs no Docker round-trip.

It mirrors DarkmoonDockerClient's public surface and semantics exactly:
  - same `timeout` envelope via coreutils `timeout` (enforced deadline)
  - same adapt_command / GPU-pinning pre-flight
  - same live UNIX-socket stream broadcast
  - same TIMEOUT/FAILED/SUCCESS result shapes and metadata
  - same reap-survivors post-timeout cleanup
  - same health-check / disk-usage / tool-availability helpers
"""

import os
import re
import time
import signal
import socket
import threading
import subprocess
from typing import Optional, List, Dict, Any

from src.models.common import ExecutionResult, ExecutionStatus
from src.execution_guard import adapt_command, classify, effective_timeout, remediation

STREAM_BASE = "/tmp/darkmoon_mcp_stream"

# Long-running scanners that routinely outlive the `timeout` wrapper: coreutils
# signals its direct child (bash), and a grandchild started through a pipe can be
# reparented and keep hammering the target long after the campaign moved on. Two
# of these were still running 72 minutes after their campaign had frozen.
_REAPABLE = (
    "hydra", "medusa", "ncrack", "patator", "sqlmap", "ffuf", "dirb",
    "gobuster", "feroxbuster", "wfuzz", "naabu", "masscan", "nuclei",
)


class LocalCommandClient:
    """
    Local-subprocess executor mirroring DarkmoonDockerClient.

    Runs commands on the host (i.e. inside the toolbox) as local processes
    instead of through a Docker proxy, with the same timeout envelope, stream
    broadcast, and result semantics.
    """

    def __init__(
        self,
        timeout: int = 300,
    ):
        self.default_timeout = timeout

        # Ensure stream socket exists (server created by darkmoon-cli)
        # Client will just connect if available.
        self._stream_enabled = True
        self._gpu_cache = None

    def _broadcast(self, b: bytes, session_id: str | None = None):
        if not self._stream_enabled:
            return

        sock_path = f"{STREAM_BASE}_{session_id}.sock" if session_id else f"{STREAM_BASE}.sock"

        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.01)
            s.connect(sock_path)
            s.sendall(b)
            s.close()
        except Exception:
            pass

    def execute_command(
        self,
        command: str | List[str],
        timeout: Optional[int] = None,
        workdir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,   # NEW
    ) -> ExecutionResult:
        """
        Execute a command locally as a subprocess.
        Streams stdout/stderr live to monitoring console via UNIX socket.
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()

        try:
            # Every command is wrapped in coreutils `timeout` so the deadline is
            # enforced even if the client goes away (mirrors docker_client).
            hard_timeout = effective_timeout(timeout)

            # Route heavy offline cracking to the right component instead of
            # refusing it (GPU pinning for hashcat).
            if isinstance(command, str):
                adapted, note = adapt_command(command, self._gpu_state())
                if note:
                    command = adapted
                    self._broadcast(f"\n\033[1;33m[guard]\033[0m {note}\n".encode(), session_id)

            if isinstance(command, list):
                cmd = ["timeout", "--kill-after=5", str(hard_timeout)] + command
                cmd_str = " ".join(command)
            else:
                cmd = ["timeout", "--kill-after=5", str(hard_timeout), "bash", "-c", command]
                cmd_str = command

            # OPTIONAL: ignore health checks in the live stream (no spam)
            is_noise = cmd_str.startswith("which ") or cmd_str.startswith("df -h ")

            # Inject cyan prompt with timestamp before streaming
            if not is_noise:
                ts = time.strftime("%H:%M:%S")
                prefix = f"\n\033[1;32m[{ts}] darkmoon>\033[0m {cmd_str}\n\n"
                self._broadcast(prefix.encode(), session_id)

            # Build the merged environment (caller env overrides process env).
            merged_env = {**os.environ}
            if environment:
                merged_env.update(environment)

            # Run locally as a subprocess, merging stderr into stdout.
            # start_new_session gives the `timeout` wrapper its OWN process
            # group, so we can kill the whole group (direct child + any
            # backgrounded grandchild) when the wall-clock deadline is exceeded.
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=workdir,
                env=merged_env,
                start_new_session=True,
            )

            assert proc.stdout is not None

            # Stream the merged pipe from a dedicated reader thread. A blocking
            # read is the only correct way to drain a pipe, but a backgrounded
            # grandchild can keep the write end open (and the read blocked)
            # forever. The MAIN thread enforces the wall-clock deadline below and
            # kills the whole process group if it is exceeded, which closes the
            # pipe and unblocks this reader.
            stdout_chunks: list[bytes] = []

            def _reader() -> None:
                assert proc.stdout is not None
                while True:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        break  # EOF: every writer closed the pipe
                    stdout_chunks.append(chunk)
                    # broadcast raw bytes (keeps ANSI + CRLF exactly)
                    if not is_noise:
                        self._broadcast(chunk, session_id)

            reader = threading.Thread(target=_reader, daemon=True)
            reader.start()

            # Wall-clock deadline against the merged pipe. The `timeout` binary
            # only SIGKILLs its direct child (bash); a grandchild started in the
            # background can keep the pipe open and make a blocking read hang
            # forever. We wait on the reader for at most `hard_timeout`, then
            # kill the whole process group (which closes the pipe) and join.
            deadline_exceeded = False
            while reader.is_alive() and (time.time() - start_time) < hard_timeout:
                reader.join(0.25)

            if reader.is_alive():
                # Deadline exceeded: tear down the process group so the orphan
                # holding the pipe open cannot keep this call (and the MCP)
                # blocked. Closing the group's write end unblocks the reader.
                deadline_exceeded = True
                self._kill_process_group(proc.pid)
                reader.join(5.0)

            # The group is dead (or finished on its own), so the pipe is closed
            # and the reader has reached EOF. Reap with bounded waits so neither
            # call can block indefinitely.
            try:
                exit_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._kill_process_group(proc.pid)
                exit_code = proc.wait(timeout=5)
            reader.join(timeout=5)
            try:
                proc.stdout.close()
            except (OSError, ValueError):
                pass
            stdout_acc = b"".join(stdout_chunks).decode("utf-8", errors="ignore")

            duration = time.time() - start_time

            # If our wall-clock deadline fired (e.g. a backgrounded grandchild
            # kept the pipe open past `timeout`), report TIMEOUT even though the
            # direct child may have already exited cleanly.
            if deadline_exceeded:
                self._reap_survivors(cmd_str)
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    stdout=stdout_acc,
                    stderr=remediation(cmd_str, duration, hard_timeout),
                    exit_code=exit_code,
                    duration=duration,
                    metadata={
                        "command": cmd_str,
                        "workdir": workdir,
                        "timeout": hard_timeout,
                        "timed_out": True,
                        "guard": classify(cmd_str).label or "unclassified",
                    },
                )

            # coreutils `timeout` reports 124 on expiry (137 when it had to SIGKILL).
            if exit_code in (124, 137):
                self._reap_survivors(cmd_str)
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    stdout=stdout_acc,
                    stderr=remediation(cmd_str, duration, hard_timeout),
                    exit_code=exit_code,
                    duration=duration,
                    metadata={
                        "command": cmd_str,
                        "workdir": workdir,
                        "timeout": hard_timeout,
                        "timed_out": True,
                        "guard": classify(cmd_str).label or "unclassified",
                    },
                )

            status = (
                ExecutionStatus.SUCCESS
                if exit_code == 0
                else ExecutionStatus.FAILED
            )

            return ExecutionResult(
                status=status,
                stdout=stdout_acc,
                stderr="",
                exit_code=exit_code,
                duration=duration,
                metadata={
                    "command": cmd_str,
                    "workdir": workdir,
                    "timeout": hard_timeout,
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                stderr=f"Execution error: {str(e)}",
                exit_code=1,
                duration=duration,
                metadata={"command": str(command), "error": str(e)},
            )

    def _gpu_state(self) -> Dict[str, str]:
        """Read the GPU profile the toolbox entrypoint wrote at startup.

        Reads /run/darkmoon-gpu.env from the LOCAL filesystem (this process and
        the toolbox share the same host/container), with os.environ as a fallback
        and CPU assumptions as the final default. Cached for the process lifetime.
        Never raises.
        """
        if getattr(self, "_gpu_cache", None) is not None:
            return self._gpu_cache

        state = {"DM_GPU": "0", "DM_GPU_VENDOR": "unknown", "DM_HASHCAT_OPTS": ""}

        # File is authoritative when present; env fills the gaps (fallback).
        try:
            with open("/run/darkmoon-gpu.env") as fh:
                for line in fh:
                    if "=" in line:
                        k, _, v = line.strip().partition("=")
                        state[k.strip()] = v.strip()
        except OSError:
            pass

        # os.environ fallback for any of the known keys not supplied by the file.
        for key in ("DM_GPU", "DM_GPU_VENDOR", "DM_HASHCAT_OPTS"):
            if key in os.environ:
                state[key] = os.environ[key]

        self._gpu_cache = state
        return state

    def _kill_process_group(self, pid: int) -> None:
        """Kill the entire process group rooted at `pid`.

        `start_new_session=True` made the wrapper a process-group leader, so
        SIGTERM/SIGKILL delivered to the group tears down the direct child AND
        any backgrounded grandchild that inherited the stdout pipe. A short
        SIGTERM grace precedes the SIGKILL so tools can flush/exit cleanly.
        Never raises.
        """
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, OSError):
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        time.sleep(0.2)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass

    def _reap_survivors(self, cmd_str: str) -> None:
        """Kill scanner grandchildren that outlived the `timeout` wrapper.

        `timeout` signals the bash it started; a tool launched inside a pipeline
        can survive that and keep running against the target indefinitely. Only
        binaries from a fixed allow-list are reaped, and only when the command
        that just expired actually mentions them, so this can never kill an
        unrelated process.
        """
        targets = [t for t in _REAPABLE if re.search(rf"\b{t}\b", cmd_str or "")]
        if not targets:
            return
        try:
            for tool in targets:
                subprocess.run(
                    ["pkill", "-9", "-x", tool],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass  # best effort: never let cleanup mask the timeout itself

    def check_tool_available(self, tool_name: str) -> bool:
        result = self.execute_command(f"which {tool_name}", timeout=5)
        return result.success

    def get_disk_usage(self) -> Optional[Dict[str, Any]]:
        """Get disk usage information from the local filesystem."""
        result = self.execute_command("df -h /opt/darkmoon/out", timeout=5)
        if result.success:
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                return {
                    "filesystem": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "use_percent": parts[4],
                    "mounted_on": parts[5] if len(parts) > 5 else "-",
                }
        return None

    def health_check(self) -> Dict[str, Any]:
        """Perform a comprehensive health check (no container concept locally)."""
        tools_to_check = ["naabu", "nuclei", "httpx", "subfinder"]
        tools_status = {}
        for tool in tools_to_check:
            tools_status[tool] = self.check_tool_available(tool)

        disk_usage = self.get_disk_usage()
        all_tools_available = all(tools_status.values())

        return {
            "healthy": all_tools_available,
            "container_running": True,
            "tools_available": tools_status,
            "disk_usage": disk_usage,
            "message": "All systems operational"
            if all_tools_available
            else "Some tools are not available",
        }

    def cleanup(self):
        """Clean up local client resources (no-op; no Docker handle to close)."""
        pass
