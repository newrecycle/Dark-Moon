#!/usr/bin/env bash
#
# install.sh — one-command, reproducible Dark-Moon Hermes plugin setup.
#
# Installs the *committed* plugin, enables it in Hermes, and registers its
# skills for slash-command discovery. Idempotent on repeated runs and does not
# require Docker.
#
# NOTE: Hermes installs plugins by cloning Git HEAD. Any uncommitted or untracked
# change in this repository will NOT be part of the installed plugin. This script
# warns (but does not fail) when the worktree is dirty so the install stays
# reproducible from version control.
set -euo pipefail

# Resolve repository root from this script's location:
#   plugin/scripts/<this>  ->  .. = plugin  ->  ../.. = repo root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

HERMES_BIN="$(command -v hermes || true)"
if [ -z "${HERMES_BIN}" ]; then
    echo "Error: the 'hermes' CLI was not found in PATH." >&2
    exit 1
fi

# Warn about a dirty worktree (Git HEAD clone caveat).
if [ -d "${REPO_ROOT}/.git" ]; then
    if [ -n "$(git -C "${REPO_ROOT}" status --porcelain 2>/dev/null)" ]; then
        echo "Warning: the repository has uncommitted or untracked changes." >&2
        echo "Hermes installs plugins by cloning Git HEAD, so those changes will" >&2
        echo "NOT be installed. Commit (or stash) them before installing for a" >&2
        echo "reproducible install." >&2
    fi
fi

# 1. Install (or update) the committed plugin. Re-running is safe.
if "${HERMES_BIN}" plugins install "${PLUGIN_DIR}" >/dev/null 2>&1; then
    echo "Installed Dark-Moon plugin from ${PLUGIN_DIR}"
else
    # Already installed: try an in-place update instead.
    if "${HERMES_BIN}" plugins update darkmoon >/dev/null 2>&1; then
        echo "Updated existing Dark-Moon plugin installation"
    else
        echo "Error: could not install or update the Dark-Moon plugin." >&2
        exit 1
    fi
fi

# 2. Enable the plugin (idempotent).
"${HERMES_BIN}" plugins enable darkmoon >/dev/null 2>&1 || true
echo "Enabled plugin: darkmoon"

# 3. Register skills for slash-command discovery (idempotent, no Docker).
bash "${PLUGIN_DIR}/scripts/setup-hermes-skills.sh" --quiet
echo "Registered Dark-Moon skills with Hermes"

echo
echo "Done. Start (or reload) a Hermes session and invoke /darkmoon-pentest."
