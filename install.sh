#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR"

OPENCODE_ENV_FILE=".opencode.env"
PERSISTENT_PATHS=(
  data
  darkmoon-settings
  workflows
  reports
  sessions
  workspace
)

CYAN="\033[1;36m"
BLUE="\033[1;34m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
MAGENTA="\033[1;35m"
BOLD="\033[1m"
RESET="\033[0m"

FORCE_PROVIDER=false
KEEP_DATA=false
for arg in "$@"; do
  case "$arg" in
    --init) FORCE_PROVIDER=true ;;
    --keep) KEEP_DATA=true ;;
    --reset) KEEP_DATA=false ;;
    --help|-h)
      cat <<'EOF'
Usage: ./install.sh [OPTIONS]

Options:
  --init   Force LLM provider reconfiguration.
  --keep   Preserve all bind-mounted data and named Docker volumes.
  --reset  Delete generated bind mounts and named volumes (default).
  --help   Show this help.

Normal installation removes: data, darkmoon-settings, workflows, reports,
sessions, and workspace. Use --keep to retain all six and named volumes.
EOF
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '%b%s%b\n' "$BLUE" "$*" "$RESET"; }
fail() { printf '%b%s%b\n' "$RED" "$*" "$RESET" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "Docker is not installed"
docker info >/dev/null 2>&1 || fail "Docker daemon is not running"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required"

# The bootstrap writes security-sensitive configuration with mode 0600. Run it
# as the invoking account so those files remain readable and editable on the
# host instead of becoming root-owned bind-mount artifacts.
export DARKMOON_UID="${DARKMOON_UID:-$(id -u)}"
export DARKMOON_GID="${DARKMOON_GID:-$(id -g)}"

printf '%b' "$CYAN"
cat <<'EOF'

  ____             _
 |  _ \  __ _ _ __| | ___ __ ___   ___   ___  _ __
 | | | |/ _` | '__| |/ / '_ ` _ \ / _ \ / _ \| '_ \
 | |_| | (_| | |  |   <| | | | | | (_) | (_) | | | |
 |____/ \__,_|_|  |_|\_\_| |_| |_|\___/ \___/|_| |_|

EOF
printf '%b' "$RESET"

load_provider_env() {
  local file=$1 key value
  [[ -f "$file" ]] || return 0
  while IFS='=' read -r key value || [[ -n "${key:-}" ]]; do
    key=${key%$'\r'}
    value=${value%$'\r'}
    case "$key" in
      OPENROUTER_PROVIDER|OPENROUTER_API_KEY|OPENCODE_MODEL|OPENCODE_LOCAL_MODE|OPENCODE_LOCAL_PROVIDER_ID|OPENCODE_LOCAL_PROVIDER_NAME|OPENCODE_LOCAL_BASE_URL|OPENCODE_LOCAL_MODEL|OPENCODE_LOCAL_API_KEY|ANTHROPIC_BASE_URL|ANTHROPIC_MODEL|ANTHROPIC_API_KEY)
        declare -gx "$key=$value"
        ;;
    esac
  done < "$file"
}

provider_is_complete() {
  if [[ -n "${OPENROUTER_PROVIDER:-}" && -n "${OPENROUTER_API_KEY:-}" && -n "${OPENCODE_MODEL:-}" ]]; then
    return 0
  fi
  if [[ "${OPENCODE_LOCAL_MODE:-}" == "true" && -n "${OPENCODE_LOCAL_PROVIDER_ID:-}" && -n "${OPENCODE_LOCAL_BASE_URL:-}" && -n "${OPENCODE_LOCAL_MODEL:-}" ]]; then
    return 0
  fi
  if [[ -n "${ANTHROPIC_BASE_URL:-}" && -n "${ANTHROPIC_MODEL:-}" && -n "${ANTHROPIC_API_KEY:-}" ]]; then
    return 0
  fi
  return 1
}

write_cloud_provider() {
  local provider model key
  read -r -p "Provider name (for example nvidia or openrouter): " provider
  [[ -n "$provider" ]] || fail "Provider name cannot be empty"
  read -r -p "Model name: " model
  [[ -n "$model" ]] || fail "Model name cannot be empty"
  read -r -s -p "API key: " key; echo
  [[ -n "$key" ]] || fail "API key cannot be empty"
  cat > "$OPENCODE_ENV_FILE" <<EOF
# Dark-Moon cloud provider configuration
OPENROUTER_PROVIDER=${provider}
OPENCODE_MODEL=${model}
OPENROUTER_API_KEY=${key}
EOF
}

write_anthropic_provider() {
  local url model key
  read -r -p "Anthropic-compatible base URL: " url
  [[ -n "$url" ]] || fail "Base URL cannot be empty"
  read -r -p "Model name: " model
  [[ -n "$model" ]] || fail "Model name cannot be empty"
  read -r -s -p "API key (leave empty only for a keyless endpoint): " key; echo
  cat > "$OPENCODE_ENV_FILE" <<EOF
# Dark-Moon Anthropic-compatible provider configuration
ANTHROPIC_BASE_URL=${url}
ANTHROPIC_MODEL=${model}
ANTHROPIC_API_KEY=${key:-darkmoon-local}
EOF
}

write_local_provider() {
  local choice provider name default_url url model key
  cat <<'EOF'
Local provider:
  1) Ollama
  2) llama.cpp / llama-server
  3) Custom OpenAI-compatible endpoint
EOF
  read -r -p "Choice [1/2/3]: " choice
  case "$choice" in
    1) provider=ollama; name="Ollama (local)"; default_url=http://host.docker.internal:11434/v1 ;;
    2) provider=llama.cpp; name="llama-server (local)"; default_url=http://host.docker.internal:8080/v1 ;;
    3) provider=local; name="Local model"; default_url= ;;
    *) fail "Choose 1, 2, or 3" ;;
  esac
  read -r -p "Base URL [${default_url}]: " url
  url=${url:-$default_url}
  [[ -n "$url" ]] || fail "Base URL cannot be empty"
  read -r -p "Model name: " model
  [[ -n "$model" ]] || fail "Model name cannot be empty"
  read -r -s -p "API key (optional): " key; echo
  cat > "$OPENCODE_ENV_FILE" <<EOF
# Dark-Moon local OpenAI-compatible provider configuration
OPENCODE_LOCAL_MODE=true
OPENCODE_LOCAL_PROVIDER_ID=${provider}
OPENCODE_LOCAL_PROVIDER_NAME=${name}
OPENCODE_LOCAL_BASE_URL=${url}
OPENCODE_LOCAL_MODEL=${model}
EOF
  [[ -z "$key" ]] || printf 'OPENCODE_LOCAL_API_KEY=%s\n' "$key" >> "$OPENCODE_ENV_FILE"
}

if [[ -f "$OPENCODE_ENV_FILE" && "$FORCE_PROVIDER" == false ]]; then
  load_provider_env "$OPENCODE_ENV_FILE"
fi

if provider_is_complete && [[ "$FORCE_PROVIDER" == false ]]; then
  printf '%bProvider configuration found; keeping %s.%b\n' "$GREEN" "$OPENCODE_ENV_FILE" "$RESET"
else
  printf '%b%s%b\n' "$BOLD$MAGENTA" "LLM PROVIDER CONFIGURATION" "$RESET"
  cat <<'EOF'
  1) Cloud provider
  2) Local OpenAI-compatible provider
  3) On-prem Anthropic-compatible provider
EOF
  read -r -p "Choice [1/2/3]: " provider_type
  case "$provider_type" in
    1) write_cloud_provider ;;
    2) write_local_provider ;;
    3) write_anthropic_provider ;;
    *) fail "Choose 1, 2, or 3" ;;
  esac
fi
chmod 600 "$OPENCODE_ENV_FILE"

case "$(uname -m)" in
  aarch64|arm64)
    COMPOSE_FILE="$SCRIPT_DIR/docker-compose-dev.yml"
    printf '%bARM64 detected: building the toolbox locally with the same MCP/plugin topology.%b\n' "$YELLOW" "$RESET"
    ;;
  *) COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml" ;;
esac

COMPOSE=(docker compose -f "$COMPOSE_FILE")
if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q 'nvidia' \
  || docker run --rm --gpus all ubuntu:22.04 true >/dev/null 2>&1; then
  COMPOSE+=(-f "$SCRIPT_DIR/docker-compose.gpu.yml")
  printf '%bGPU runtime detected; enabling toolbox GPU passthrough.%b\n' "$GREEN" "$RESET"
else
  printf '%bNo GPU runtime detected; toolbox will use CPU.%b\n' "$YELLOW" "$RESET"
fi

log "Stopping the existing stack"
if [[ "$KEEP_DATA" == true ]]; then
  "${COMPOSE[@]}" down --remove-orphans || true
else
  "${COMPOSE[@]}" down --remove-orphans --volumes --rmi all || true
fi

safe_remove() {
  local relative=$1 target
  target="$SCRIPT_DIR/$relative"
  case "$target" in
    "$SCRIPT_DIR"/*) ;;
    *) fail "Refusing to remove path outside repository: $target" ;;
  esac
  if [[ -L "$target" ]]; then
    fail "Refusing to recursively remove symlink: $target"
  fi
  if [[ -e "$target" ]]; then
    printf '%bRemoving %s%b\n' "$YELLOW" "$target" "$RESET"
    rm -rf --one-file-system -- "$target"
  fi
}

if [[ "$KEEP_DATA" == false ]]; then
  log "Removing generated bind mounts"
  for path in "${PERSISTENT_PATHS[@]}"; do
    safe_remove "$path"
  done
else
  printf '%bPreserving bind mounts and named volumes (--keep).%b\n' "$GREEN" "$RESET"
fi

for path in "${PERSISTENT_PATHS[@]}"; do
  mkdir -p -- "$SCRIPT_DIR/$path"
done

log "Validating Compose configuration"
"${COMPOSE[@]}" config >/dev/null

log "Pulling stock images"
"${COMPOSE[@]}" pull --ignore-buildable

log "Building Dark-Moon support images"
"${COMPOSE[@]}" build --pull --no-cache

log "Starting Dark-Moon"
"${COMPOSE[@]}" up -d --force-recreate

wait_for_stack() {
  local agents mcp
  for _ in $(seq 1 90); do
    if agents="$("${COMPOSE[@]}" exec -T opencode opencode agent list 2>/dev/null)" \
      && grep -q 'pentest (primary)' <<<"$agents" \
      && mcp="$("${COMPOSE[@]}" exec -T opencode opencode mcp list 2>/dev/null)" \
      && grep -Eqi 'darkmoon.*connected' <<<"$mcp"; then
      return 0
    fi
    sleep 2
  done
  "${COMPOSE[@]}" ps >&2 || true
  "${COMPOSE[@]}" logs --no-color opencode-bootstrap darkmoon-mcp opencode >&2 || true
  return 1
}

wait_for_stack || fail "Dark-Moon did not become ready"
[[ -r "$SCRIPT_DIR/darkmoon-settings/opencode.json" ]] || fail "OpenCode bootstrap did not create a user-readable opencode.json"
[[ -r "$SCRIPT_DIR/darkmoon-settings/.darkmoon-bootstrap.json" ]] || fail "OpenCode bootstrap state marker is missing or unreadable"

printf '%bDark-Moon installation is ready.%b\n' "$GREEN" "$RESET"
