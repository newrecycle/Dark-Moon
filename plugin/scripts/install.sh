#!/usr/bin/env bash
#
# install.sh — one-command, reproducible Dark-Moon Hermes plugin setup.
#
# Installs the *committed* plugin, enables it in Hermes, and registers its
# skills for slash-command discovery. Idempotent on repeated runs and does not
# require Docker.
#
# Reproducibility: Hermes installs plugins by cloning Git HEAD, so any
# uncommitted/untracked change is NOT part of the installed plugin. This script
# warns (but does not fail) on a dirty worktree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PLUGIN_NAME="darkmoon"
HERMES_BIN="$(command -v hermes || true)"

usage() {
  cat <<'USAGE'
Usage: plugin/scripts/install.sh [OPTIONS]

One-command Dark-Moon Hermes plugin setup (install + enable + register skills).
Idempotent; does not require Docker.

Options:
  --help, -h     Show this help

Notes:
  Hermes installs plugins from Git HEAD, so commit your changes first for a
  reproducible install. Uncommitted/untracked files are NOT included.
USAGE
}

for ARG in "$@"; do
  case "${ARG}" in
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: ${ARG}" >&2; usage; exit 2 ;;
  esac
done

if [ -z "${HERMES_BIN}" ]; then
  echo "Error: the 'hermes' CLI was not found in PATH." >&2
  exit 1
fi

# Warn (non-fatal) about a dirty worktree.
if [ -d "${REPO_ROOT}/.git" ]; then
  if [ -n "$(git -C "${REPO_ROOT}" status --porcelain 2>/dev/null)" ]; then
    echo "Warning: repository has uncommitted or untracked changes." >&2
    echo "Hermes installs plugins by cloning Git HEAD, so those changes will" >&2
    echo "NOT be installed. Commit (or stash) them for a reproducible install." >&2
  fi
fi

echo "==> Installing Dark-Moon plugin (${PLUGIN_DIR})"
if "${HERMES_BIN}" plugins install "${PLUGIN_DIR}" >/dev/null 2>&1; then
  echo "    installed"
elif "${HERMES_BIN}" plugins update "${PLUGIN_NAME}" >/dev/null 2>&1; then
  echo "    updated existing installation"
else
  echo "Error: could not install or update the Dark-Moon plugin." >&2
  exit 1
fi

echo "==> Enabling plugin: ${PLUGIN_NAME}"
"${HERMES_BIN}" plugins enable "${PLUGIN_NAME}" >/dev/null 2>&1 || true

echo "==> Registering Dark-Moon skills with Hermes"
bash "${PLUGIN_DIR}/scripts/setup-hermes-skills.sh" --quiet

echo
echo "Done. Start (or reload) a Hermes session and invoke /darkmoon-pentest."
