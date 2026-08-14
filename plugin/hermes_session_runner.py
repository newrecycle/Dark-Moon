"""Run a resumable Hermes CLI turn with finite completion delivery."""

from __future__ import annotations


def main() -> int:
    # Importing the CLI first applies its early `-p/--profile` override before
    # Hermes modules cache HERMES_HOME. The session launcher passes the same
    # normal Hermes argv that the console script accepts.
    from hermes_cli.main import main as hermes_main

    # A quiet `chat --query` turn is finite: once its response is emitted the
    # process exits. Tell Hermes that it cannot accept a detached completion so
    # top-level delegate_task calls use their built-in synchronous fallback.
    # The session is still persisted and can be resumed on the next invocation.
    from gateway.session_context import declare_stateless_channel

    declare_stateless_channel()
    result = hermes_main()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
