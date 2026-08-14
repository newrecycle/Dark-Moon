#!/usr/bin/env bash
#
# plugin.sh — one-command Dark-Moon onboarding for a Hermes session.
#
# What it does, in order:
#   1. One-time setup  -> ./install.sh  (writes .opencode.env, prepares bind dirs)
#   2. Bring up        -> ./darkmoon.sh up   (single darkmoon container, waits for MCP)
#   3. Verify status   -> ./darkmoon.sh status (exits non-zero if MCP not reachable)
#
# Data safety: setup PRESERVES runtime data by default (install.sh --keep).
# Pass --clean for a destructive rebuild that purges volumes + bind data.
# The setup step is skipped automatically once .opencode.env exists, so this
# script is safe to re-run as a plain "bring it up" command.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR"

# ── Colors ────────────────────────────────────────────────────
CYAN='\033[1;36m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
BOLD='\033[1m'
RESET='\033[0m'

ENV_FILE=".opencode.env"

usage() {
  cat <<'EOF'
Usage: ./plugin.sh [OPTIONS]

One-command Dark-Moon onboarding for a Hermes session:
  1. Run one-time setup (./install.sh) — prepares .opencode.env + bind dirs.
  2. Bring the single darkmoon container up (waits for the MCP on :8000).
  3. Verify status before finishing (fails if the MCP is not reachable).

Options:
  --keep    Preserve Docker volumes and bind-mounted runtime data (default).
  --clean   Destructive rebuild: purge volumes + bind data before setup.
  --help    Show this help.
EOF
}

# ── Args ──────────────────────────────────────────────────────
KEEP=true
for ARG in "$@"; do
  case "$ARG" in
    --keep)  KEEP=true ;;
    --clean) KEEP=false ;;
    --help|-h) usage; exit 0 ;;
    *) echo -e "${RED}Unknown option: ${ARG}${RESET}" >&2; usage >&2; exit 2 ;;
  esac
done

echo -e "${CYAN}🌙 Dark-Moon plugin bring-up${RESET}"

# ── Step 1: one-time setup ───────────────────────────────────
needs_setup=true
if [[ -f "$ENV_FILE" ]]; then
  needs_setup=false
fi

if [[ "$needs_setup" == true ]]; then
  # install.sh prompts for the LLM provider on first run — require a TTY.
  if [[ ! -t 0 || ! -t 1 ]]; then
    echo -e "${RED}❌ First-time setup needs an interactive terminal to configure the LLM provider.${RESET}" >&2
    echo -e "${YELLOW}Run ./plugin.sh from an interactive shell, or pre-create ${ENV_FILE}.${RESET}" >&2
    exit 1
  fi
  echo -e "${BOLD}▶ Step 1/3: one-time setup${RESET}"
  if [[ "$KEEP" == true ]]; then
    echo -e "${YELLOW}  (preserving volumes + bind data via install.sh --keep)${RESET}"
    ./install.sh --keep
  else
    echo -e "${YELLOW}  (clean rebuild — volumes + bind data will be purged)${RESET}"
    ./install.sh
  fi
else
  echo -e "${GREEN}✔ Setup already complete (${ENV_FILE} present) — skipping install.sh${RESET}"
fi

# ── Step 2: bring the container up ───────────────────────────
echo -e "${BOLD}▶ Step 2/3: bring up the darkmoon container${RESET}"
./darkmoon.sh up

# ── Step 3: verify status ────────────────────────────────────
echo -e "${BOLD}▶ Step 3/3: verify status${RESET}"
if ./darkmoon.sh status; then
  echo -e "${GREEN}✅ Dark-Moon is ready — the darkmoon_* MCP tools are reachable from Hermes.${RESET}"
  exit 0
else
  echo -e "${RED}❌ Dark-Moon came up but the MCP is NOT reachable.${RESET}" >&2
  echo -e "${YELLOW}  Inspect with: ./darkmoon.sh mcp healthcheck${RESET}" >&2
  exit 1
fi
