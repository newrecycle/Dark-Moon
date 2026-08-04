#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

GENERATED_BIND_PATHS=(
  "./data"
  "./darkmoon-settings"
  "./workflows"
  "./reports"
  "./sessions"
  "./workspace"
)

OPENCODE_ENV_FILE=".opencode.env"

# Colors
CYAN="\033[1;36m"
BLUE="\033[1;34m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
MAGENTA="\033[1;35m"
BOLD="\033[1m"
RESET="\033[0m"

usage() {
  cat <<'USAGE'
Usage: ./install.sh [OPTIONS]

Options:
  --init    Force LLM provider reconfiguration (ignores existing .opencode.env)
  --keep    Preserve Docker volumes and all bind-mounted runtime data
  --help    Show this help

Examples:
  ./install.sh           # clean rebuild; reuse provider config when available
  ./install.sh --init    # clean rebuild and reconfigure LLM provider
  ./install.sh --keep    # rebuild without deleting sessions, projects or agent data
USAGE
}

# ─────────────────────────────────────────────────────────────────
# Parse args before any Docker or destructive operation
# ─────────────────────────────────────────────────────────────────
FORCE_RESET=false
KEEP_DATA=false
for ARG in "$@"; do
  case "${ARG}" in
    --help|-h)
      usage
      exit 0
      ;;
    --reset|--init)
      FORCE_RESET=true
      ;;
    --keep)
      KEEP_DATA=true
      ;;
    *)
      echo "Unknown option: ${ARG}" >&2
      echo "Run ./install.sh --help for usage." >&2
      exit 2
      ;;
  esac
done

echo -e "${CYAN}"
cat <<'EOF_BANNER'

  ____             _
 |  _ \  __ _ _ __| | ___ __ ___   ___   ___  _ __
 | | | |/ _` | '__| |/ / '_ ` _ \ / _ \ / _ \| '_ \
 | |_| | (_| | |  |   <| | | | | | (_) | (_) | | | |
 |____/ \__,_|_|  |_|\_\_| |_| |_|\___/ \___/|_| |_|

EOF_BANNER
echo -e "${RESET}"

echo -e "${BLUE}🔎 Checking prerequisites...${RESET}"

if ! command -v docker >/dev/null 2>&1; then
  echo -e "${RED}❌ Docker is not installed.${RESET}"
  echo -e "${YELLOW}Please install Docker before running this script.${RESET}"
  echo ""
  echo "Install guide: https://docs.docker.com/engine/install/"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo -e "${RED}❌ Docker daemon is not running.${RESET}"
  echo -e "${YELLOW}Please start Docker and retry.${RESET}"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo -e "${RED}❌ Docker Compose (v2) is not available.${RESET}"
  echo -e "${YELLOW}Install Docker Compose plugin:${RESET}"
  echo "https://docs.docker.com/compose/install/"
  exit 1
fi

echo -e "${GREEN}✔ Docker and Docker Compose detected${RESET}"

# ─────────────────────────────────────────────────────────────────
# Select one Compose configuration and use it for the entire run
# ─────────────────────────────────────────────────────────────────
ARCH="$(uname -m)"
COMPOSE_FILE="docker-compose.yml"
if [ "${ARCH}" = "aarch64" ] || [ "${ARCH}" = "arm64" ]; then
  COMPOSE_FILE="docker-compose-dev.yml"
  echo -e "${YELLOW}ARM64 architecture detected. Using ${COMPOSE_FILE}.${RESET}"
fi

COMPOSE_ARGS=(-f "${COMPOSE_FILE}")
if [ "${COMPOSE_FILE}" = "docker-compose.yml" ] &&
   docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q 'nvidia'; then
  COMPOSE_ARGS+=(-f docker-compose.gpu.yml)
  echo -e "${GREEN}GPU runtime detected. Enabling GPU passthrough for the toolbox.${RESET}"
else
  echo -e "${YELLOW}No applicable GPU runtime detected. The toolbox will run hashcat on CPU.${RESET}"
fi

compose() {
  docker compose "${COMPOSE_ARGS[@]}" "$@"
}

# Capture the selected stack image names before teardown. The same list is used
# for local-only root cleanup and for image removal after bind cleanup succeeds.
STACK_IMAGES=()
while IFS= read -r image; do
  [ -n "${image}" ] && STACK_IMAGES+=("${image}")
done < <(compose config --images 2>/dev/null | awk 'NF && !seen[$0]++')

# ─────────────────────────────────────────────────────────────────
# Save .opencode.env before a clean rebuild unless --init was requested
# ─────────────────────────────────────────────────────────────────
SAVED_OPENCODE_ENV=""
if [ "${FORCE_RESET}" = false ] && [ -f "${OPENCODE_ENV_FILE}" ]; then
  SAVED_OPENCODE_ENV="$(cat "${OPENCODE_ENV_FILE}")"
fi

env_value() {
  local key="$1"
  local file="$2"
  awk -v prefix="${key}=" 'index($0, prefix) == 1 { sub(/^[^=]*=/, ""); sub(/\r$/, ""); print; exit }' "${file}"
}

SKIP_PROVIDER_FORM=false
if [ -n "${SAVED_OPENCODE_ENV}" ]; then
  OPENROUTER_PROVIDER="$(env_value OPENROUTER_PROVIDER "${OPENCODE_ENV_FILE}")"
  OPENROUTER_API_KEY="$(env_value OPENROUTER_API_KEY "${OPENCODE_ENV_FILE}")"
  OPENCODE_MODEL="$(env_value OPENCODE_MODEL "${OPENCODE_ENV_FILE}")"
  OPENCODE_LOCAL_MODE="$(env_value OPENCODE_LOCAL_MODE "${OPENCODE_ENV_FILE}")"
  OPENCODE_LOCAL_PROVIDER_ID="$(env_value OPENCODE_LOCAL_PROVIDER_ID "${OPENCODE_ENV_FILE}")"
  OPENCODE_LOCAL_BASE_URL="$(env_value OPENCODE_LOCAL_BASE_URL "${OPENCODE_ENV_FILE}")"
  OPENCODE_LOCAL_MODEL="$(env_value OPENCODE_LOCAL_MODEL "${OPENCODE_ENV_FILE}")"
  ANTHROPIC_BASE_URL="$(env_value ANTHROPIC_BASE_URL "${OPENCODE_ENV_FILE}")"
  ANTHROPIC_MODEL="$(env_value ANTHROPIC_MODEL "${OPENCODE_ENV_FILE}")"

  if [ -n "${OPENROUTER_PROVIDER}" ] &&
     [ -n "${OPENROUTER_API_KEY}" ] &&
     [ -n "${OPENCODE_MODEL}" ]; then
    SKIP_PROVIDER_FORM=true
  elif [ "${OPENCODE_LOCAL_MODE}" = "true" ] &&
       [ -n "${OPENCODE_LOCAL_PROVIDER_ID}" ] &&
       [ -n "${OPENCODE_LOCAL_BASE_URL}" ] &&
       [ -n "${OPENCODE_LOCAL_MODEL}" ]; then
    SKIP_PROVIDER_FORM=true
  elif [ -n "${ANTHROPIC_BASE_URL}" ] && [ -n "${ANTHROPIC_MODEL}" ]; then
    SKIP_PROVIDER_FORM=true
  fi
fi

prompt_nonempty() {
  local prompt="$1"
  local value=""
  while [ -z "${value}" ]; do
    read -r -p "$(echo -e "${YELLOW}${prompt}: ${RESET}")" value
    [ -n "${value}" ] || echo -e "${RED}  Value cannot be empty.${RESET}" >&2
  done
  printf '%s' "${value}"
}

prompt_secret_required() {
  local prompt="$1"
  local value=""
  while [ -z "${value}" ]; do
    read -r -s -p "$(echo -e "${YELLOW}${prompt}: ${RESET}")" value
    echo "" >&2
    [ -n "${value}" ] || echo -e "${RED}  Value cannot be empty.${RESET}" >&2
  done
  printf '%s' "${value}"
}

# ─────────────────────────────────────────────────────────────────
# LLM provider configuration
# ─────────────────────────────────────────────────────────────────
if [ "${SKIP_PROVIDER_FORM}" = true ]; then
  echo -e "${GREEN}✔ LLM provider already configured — skipping${RESET}"
  printf '%s\n' "${SAVED_OPENCODE_ENV}" > "${OPENCODE_ENV_FILE}"
else
  echo ""
  echo -e "${BOLD}${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo -e "  🤖  LLM PROVIDER CONFIGURATION"
  echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo ""
  echo -e "  ${CYAN}[1]${RESET} ${BOLD}Cloud provider${RESET}  (Anthropic, OpenRouter, OpenAI, etc.)"
  echo -e "  ${CYAN}[2]${RESET} ${BOLD}Local model${RESET}     (Ollama, llama.cpp / llama-server)"
  echo -e "  ${CYAN}[3]${RESET} ${BOLD}On-prem Anthropic-compatible${RESET}"

  while true; do
    read -r -p "$(echo -e "${YELLOW}Your choice [1/2/3]: ${RESET}")" PROVIDER_TYPE
    case "${PROVIDER_TYPE}" in
      1|cloud|Cloud) PROVIDER_TYPE="cloud"; break ;;
      2|local|Local) PROVIDER_TYPE="local"; break ;;
      3|anthropic|Anthropic) PROVIDER_TYPE="anthropic"; break ;;
      *) echo -e "${RED}  Please enter 1, 2 or 3.${RESET}" ;;
    esac
  done

  if [ "${PROVIDER_TYPE}" = "cloud" ]; then
    CLOUD_PROVIDER="$(prompt_nonempty 'Provider name (e.g. anthropic)')"
    CLOUD_MODEL="$(prompt_nonempty 'Model name (e.g. claude-opus-4-6)')"
    CLOUD_API_KEY="$(prompt_secret_required 'API key')"
    cat > "${OPENCODE_ENV_FILE}" <<EOF_ENV
# Darkmoon — LLM cloud provider config
# Generated by install.sh on $(date '+%Y-%m-%d %H:%M:%S')
OPENROUTER_PROVIDER=${CLOUD_PROVIDER}
OPENCODE_MODEL=${CLOUD_MODEL}
OPENROUTER_API_KEY=${CLOUD_API_KEY}
EOF_ENV
  elif [ "${PROVIDER_TYPE}" = "anthropic" ]; then
    CUSTOM_ANTHROPIC_BASE_URL="$(prompt_nonempty 'Base URL')"
    CUSTOM_ANTHROPIC_MODEL="$(prompt_nonempty 'Model name')"
    read -r -s -p "$(echo -e "${YELLOW}API key (optional): ${RESET}")" CUSTOM_ANTHROPIC_API_KEY
    echo ""
    cat > "${OPENCODE_ENV_FILE}" <<EOF_ENV
# Darkmoon — on-prem Anthropic-compatible LLM config
# Generated by install.sh on $(date '+%Y-%m-%d %H:%M:%S')
ANTHROPIC_BASE_URL=${CUSTOM_ANTHROPIC_BASE_URL}
ANTHROPIC_MODEL=${CUSTOM_ANTHROPIC_MODEL}
ANTHROPIC_API_KEY=${CUSTOM_ANTHROPIC_API_KEY:-darkmoon-local}
EOF_ENV
  else
    echo -e "${CYAN}Local provider options:${RESET}"
    echo -e "  ${YELLOW}[1]${RESET} Ollama"
    echo -e "  ${YELLOW}[2]${RESET} llama.cpp"
    echo -e "  ${YELLOW}[3]${RESET} Custom URL"
    while true; do
      read -r -p "$(echo -e "${YELLOW}Local engine [1/2/3]: ${RESET}")" LOCAL_ENGINE
      case "${LOCAL_ENGINE}" in
        1|ollama|Ollama)
          LOCAL_PROVIDER_ID="ollama"
          LOCAL_PROVIDER_NAME="Ollama (local)"
          DEFAULT_BASE_URL="http://localhost:11434/v1"
          break
          ;;
        2|llama*|llamacpp)
          LOCAL_PROVIDER_ID="llama.cpp"
          LOCAL_PROVIDER_NAME="llama-server (local)"
          DEFAULT_BASE_URL="http://localhost:8080/v1"
          break
          ;;
        3|custom|Custom)
          LOCAL_PROVIDER_ID="local"
          LOCAL_PROVIDER_NAME="Local model"
          DEFAULT_BASE_URL=""
          break
          ;;
        *) echo -e "${RED}  Please enter 1, 2 or 3.${RESET}" ;;
      esac
    done

    read -r -p "$(echo -e "${YELLOW}Base URL [${DEFAULT_BASE_URL}]: ${RESET}")" LOCAL_BASE_URL
    LOCAL_BASE_URL="${LOCAL_BASE_URL:-${DEFAULT_BASE_URL}}"
    while [ -z "${LOCAL_BASE_URL}" ]; do
      LOCAL_BASE_URL="$(prompt_nonempty 'Base URL')"
    done
    LOCAL_MODEL="$(prompt_nonempty 'Model name')"
    read -r -s -p "$(echo -e "${YELLOW}API key (optional): ${RESET}")" LOCAL_API_KEY
    echo ""

    cat > "${OPENCODE_ENV_FILE}" <<EOF_ENV
# Darkmoon — LLM local provider config
# Generated by install.sh on $(date '+%Y-%m-%d %H:%M:%S')
OPENCODE_LOCAL_MODE=true
OPENCODE_LOCAL_PROVIDER_ID=${LOCAL_PROVIDER_ID}
OPENCODE_LOCAL_PROVIDER_NAME=${LOCAL_PROVIDER_NAME}
OPENCODE_LOCAL_BASE_URL=${LOCAL_BASE_URL}
OPENCODE_LOCAL_MODEL=${LOCAL_MODEL}
EOF_ENV
    if [ -n "${LOCAL_API_KEY}" ]; then
      printf 'OPENCODE_LOCAL_API_KEY=%s\n' "${LOCAL_API_KEY}" >> "${OPENCODE_ENV_FILE}"
    fi
  fi
fi

chmod 600 "${OPENCODE_ENV_FILE}"
echo -e "${GREEN}✔ ${OPENCODE_ENV_FILE} written${RESET}"

# ─────────────────────────────────────────────────────────────────
# Root-owned bind cleanup, using selected stack images only
# ─────────────────────────────────────────────────────────────────
find_local_cleanup_image() {
  local image
  for image in "${STACK_IMAGES[@]}"; do
    if docker image inspect "${image}" >/dev/null 2>&1 &&
       docker run --rm --pull=never --user 0:0 \
         --entrypoint /bin/sh "${image}" \
         -c 'command -v rm >/dev/null 2>&1' >/dev/null 2>&1; then
      printf '%s\n' "${image}"
      return 0
    fi
  done
  return 1
}

remove_bind_path() {
  local path="$1"
  local relative_path="${path#./}"
  local cleanup_image=""

  case "${relative_path}" in
    data|darkmoon-settings|workflows|reports|sessions|workspace) ;;
    *)
      echo -e "${RED}❌ Refusing unsafe cleanup path: ${path}${RESET}" >&2
      exit 1
      ;;
  esac

  if [ ! -e "${path}" ] && [ ! -L "${path}" ]; then
    echo -e "${YELLOW}  - ${path} (absent)${RESET}"
    return 0
  fi

  echo -e "${YELLOW}  - removing ${path}${RESET}"
  if rm -rf -- "${path}" 2>/dev/null; then
    return 0
  fi

  echo -e "${YELLOW}    host permissions blocked removal; retrying as container root${RESET}"
  if ! cleanup_image="$(find_local_cleanup_image)"; then
    echo -e "${RED}❌ No local stack image can run /bin/sh and rm as root.${RESET}" >&2
    printf 'Run this command and retry: sudo rm -rf -- %q\n' "${SCRIPT_DIR}/${relative_path}" >&2
    exit 1
  fi

  if ! docker run --rm --pull=never --user 0:0 \
      -v "${SCRIPT_DIR}:/darkmoon-root" \
      --entrypoint /bin/sh \
      "${cleanup_image}" \
      -c 'rm -rf -- "/darkmoon-root/$1"' sh "${relative_path}"; then
    echo -e "${RED}❌ Could not remove ${path} with local image ${cleanup_image}.${RESET}" >&2
    printf 'Run this command and retry: sudo rm -rf -- %q\n' "${SCRIPT_DIR}/${relative_path}" >&2
    exit 1
  fi

  if [ -e "${path}" ] || [ -L "${path}" ]; then
    echo -e "${RED}❌ Cleanup completed without deleting ${path}.${RESET}" >&2
    printf 'Run this command and retry: sudo rm -rf -- %q\n' "${SCRIPT_DIR}/${relative_path}" >&2
    exit 1
  fi
}

# ─────────────────────────────────────────────────────────────────
# Stop stack, optionally purge persistent state, then remove images
# ─────────────────────────────────────────────────────────────────
if [ "${KEEP_DATA}" = true ]; then
  echo -e "${BLUE}🛑 Stopping stack while preserving volumes and bind-mounted data...${RESET}"
  compose down --remove-orphans
  echo -e "${GREEN}✔ Persistent sessions, projects, reports, workflows and agent data retained${RESET}"
else
  echo -e "${BLUE}🛑 Stopping stack and removing named volumes...${RESET}"
  compose down --remove-orphans --volumes

  echo -e "${BLUE}🧹 Purging generated bind mounts...${RESET}"
  for path in "${GENERATED_BIND_PATHS[@]}"; do
    remove_bind_path "${path}"
  done
fi

echo -e "${BLUE}🗑️  Removing previous stack images...${RESET}"
for image in "${STACK_IMAGES[@]}"; do
  if docker image inspect "${image}" >/dev/null 2>&1; then
    docker image rm "${image}" >/dev/null ||
      echo -e "${YELLOW}  - could not remove shared image ${image}; continuing${RESET}"
  fi
done

echo -e "${BLUE}🧽 Purging docker build cache...${RESET}"
docker builder prune -f

echo -e "${BLUE}🔨 Rebuilding images (no cache)...${RESET}"
compose build --no-cache

echo -e "${BLUE}🚀 Recreating containers...${RESET}"
compose up -d --force-recreate

if [ "${KEEP_DATA}" = true ]; then
  echo -e "${GREEN}✅ Darkmoon stack rebuilt with persistent data retained${RESET}"
else
  echo -e "${GREEN}✅ Darkmoon stack rebuilt CLEAN${RESET}"
fi
