#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import selectors
import signal
import socket
import sys

STREAM_BASE = "/tmp/darkmoon_mcp_stream"
running = True


def socket_path(session_id: str | None) -> str:
    return f"{STREAM_BASE}_{session_id}.sock" if session_id else f"{STREAM_BASE}.sock"


def handle_signal(_signum, _frame):
    global running
    running = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream live Dark-Moon MCP command output")
    parser.add_argument("session_id", nargs="?", help="optional Dark-Moon MCP session id")
    parser.add_argument("--check", action="store_true", help="print the resolved socket path and exit")
    return parser.parse_args()


def main() -> int:
    global running
    args = parse_args()
    path = socket_path(args.session_id)
    if args.check:
        print(path)
        return 0

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if os.path.exists(path):
        os.remove(path)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(50)
    os.chmod(path, 0o600)

    sel = selectors.DefaultSelector()
    sel.register(srv, selectors.EVENT_READ)
    clients: set[socket.socket] = set()

    label = f" session={args.session_id}" if args.session_id else ""
    sys.stdout.write(f"\n\033[1;32mdarkmoon(live)>\033[0m streaming MCP output{label}...\n\n")
    sys.stdout.flush()

    try:
        while running:
            for key, _ in sel.select(timeout=0.5):
                if key.fileobj is srv:
                    client, _ = srv.accept()
                    client.setblocking(False)
                    clients.add(client)
                    sel.register(client, selectors.EVENT_READ)
                    continue

                client = key.fileobj
                try:
                    data = client.recv(4096)
                    if not data:
                        sel.unregister(client)
                        clients.discard(client)
                        client.close()
                        continue
                    os.write(sys.stdout.fileno(), data)
                except Exception:
                    try:
                        sel.unregister(client)
                    except Exception:
                        pass
                    clients.discard(client)
                    try:
                        client.close()
                    except Exception:
                        pass
    finally:
        sys.stdout.write("\n\033[1;31mdarkmoon(live)>\033[0m stopped.\n")
        sys.stdout.flush()
        for client in list(clients):
            try:
                sel.unregister(client)
                client.close()
            except Exception:
                pass
        try:
            sel.unregister(srv)
            srv.close()
        except Exception:
            pass
        if os.path.exists(path):
            os.remove(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
