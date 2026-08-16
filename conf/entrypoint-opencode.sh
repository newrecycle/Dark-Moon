#!/usr/bin/env bash
set -u
# ⚠️ PAS de set -e global (contrôlé manuellement)

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fatal() {
  log "FATAL: $*"
  exit 1
}

#######################################
# Paths
#######################################
AGENTS_DIR="/root/.opencode/agents"
DEFAULT_AGENTS="/opt/darkmoon/default-agents"
DEFAULT_PLUGINS="/opt/darkmoon/default-plugins"
DEFAULT_WORKFLOWS="/opt/darkmoon/default-workflows"
WORKFLOWS_DIR="/opt/darkmoon/mcp/server/src/tools/workflows/"
OPENCODE_CONFIG_FILE="/root/.config/opencode/opencode.json"
OPENCODE_PLUGINS_DIR="/root/.config/opencode/plugins"
OPENCODE_AUTH_FILE="/root/.local/share/opencode/auth.json"
APPLY_SCRIPT="/root/conf/apply-settings.sh"
APPLY_MARKER="/root/.config/opencode/.darkmoon-apply-settings-once"
SHARED_DIR="${DARKMOON_SHARED_DIR:-/output}"
DARKMOON_USER="${DARKMOON_USER:-darkmoon}"
DARKMOON_UID="${DARKMOON_UID:-1000}"
DARKMOON_GID="${DARKMOON_GID:-1000}"

#######################################
# Host identity + bind-mount ownership
#######################################
prepare_runtime_identity() {
  # The image entrypoint starts as root only long enough to repair bind mounts
  # and grant access to the host Docker socket. The main process never stays
  # root, so newly-created host files use DARKMOON_UID:DARKMOON_GID.
  [ "$(id -u)" -eq 0 ] || return 0

  [[ "$DARKMOON_UID" =~ ^[1-9][0-9]*$ ]] || fatal "DARKMOON_UID must be a positive integer"
  [[ "$DARKMOON_GID" =~ ^[1-9][0-9]*$ ]] || fatal "DARKMOON_GID must be a positive integer"
  id "$DARKMOON_USER" >/dev/null 2>&1 || fatal "Runtime user missing: $DARKMOON_USER"
  command -v gosu >/dev/null 2>&1 || fatal "gosu is required to drop privileges"

  if [ "$(id -g "$DARKMOON_USER")" != "$DARKMOON_GID" ]; then
    groupmod --non-unique --gid "$DARKMOON_GID" "$DARKMOON_USER" \
      || fatal "Unable to map $DARKMOON_USER to GID $DARKMOON_GID"
  fi

  usermod --gid "$DARKMOON_GID" "$DARKMOON_USER" \
    || fatal "Unable to set the primary GID for $DARKMOON_USER"

  if [ "$(id -u "$DARKMOON_USER")" != "$DARKMOON_UID" ]; then
    usermod --non-unique --uid "$DARKMOON_UID" "$DARKMOON_USER" \
      || fatal "Unable to map $DARKMOON_USER to UID $DARKMOON_UID"
  fi

  # Match the mounted Docker socket's numeric group without weakening its mode.
  if [ -S /var/run/docker.sock ]; then
    socket_gid="$(stat -c '%g' /var/run/docker.sock)"
    if [ "$socket_gid" != "$DARKMOON_GID" ]; then
      socket_group="$(getent group "$socket_gid" | cut -d: -f1 | head -n1)"
      if [ -z "$socket_group" ]; then
        socket_group="darkmoon-docker"
        if getent group "$socket_group" >/dev/null 2>&1; then
          groupmod --non-unique --gid "$socket_gid" "$socket_group" \
            || fatal "Unable to update Docker socket group to GID $socket_gid"
        else
          groupadd --non-unique --gid "$socket_gid" "$socket_group" \
            || fatal "Unable to create Docker socket group for GID $socket_gid"
        fi
      fi
      usermod --append --groups "$socket_group" "$DARKMOON_USER" \
        || fatal "Unable to grant Docker socket access to $DARKMOON_USER"
    fi
  fi

  mutable_dirs=(
    "$SHARED_DIR"
    "/root/.opencode"
    "$(dirname "$OPENCODE_CONFIG_FILE")"
    "$(dirname "$OPENCODE_AUTH_FILE")"
    "/root/.cache/opencode"
    "/root/.npm"
    "/root/.local/state/opencode"
    "/root/.local/share/opencode/reports"
    "/root/.local/share/opencode/sessions"
    "$WORKFLOWS_DIR"
  )

  log "Mapping writable directories to ${DARKMOON_UID}:${DARKMOON_GID}"
  for dir in "${mutable_dirs[@]}"; do
    mkdir -p "$dir" || fatal "Unable to create writable directory: $dir"
    chown -R "$DARKMOON_UID:$DARKMOON_GID" "$dir" \
      || fatal "Unable to change ownership: $dir"
    chmod -R u+rwX "$dir" || fatal "Unable to make directory owner-writable: $dir"
  done

  chmod 2775 "$SHARED_DIR" || fatal "Unable to set shared-directory permissions"
  chmod 0755 /root
  chown -R "$DARKMOON_UID:$DARKMOON_GID" /root/conf /root/.bashrc

  log "Dropping privileges to ${DARKMOON_USER} (${DARKMOON_UID}:${DARKMOON_GID})"
  exec gosu "$DARKMOON_USER" env \
    HOME=/root \
    USER="$DARKMOON_USER" \
    LOGNAME="$DARKMOON_USER" \
    DARKMOON_PRIVILEGES_DROPPED=1 \
    "$0" "$@"
}

prepare_runtime_identity "$@"

#######################################
# Sanity checks
#######################################
[ -d "$DEFAULT_AGENTS" ] || fatal "Default agents dir missing: $DEFAULT_AGENTS"

#######################################
# Prepare directories (bind-mount safe)
#######################################
log "Preparing directories"
mkdir -p \
  "$AGENTS_DIR" \
  "$OPENCODE_PLUGINS_DIR" \
  "$(dirname "$OPENCODE_CONFIG_FILE")" \
  "$(dirname "$OPENCODE_AUTH_FILE")"

#######################################
# Seed provider plugins (preserve local overrides)
#######################################
if [ -d "$DEFAULT_PLUGINS" ]; then
  for plugin in "$DEFAULT_PLUGINS"/*; do
    [ -f "$plugin" ] || continue
    target="$OPENCODE_PLUGINS_DIR/$(basename "$plugin")"
    if [ ! -e "$target" ]; then
      cp "$plugin" "$target" || fatal "Unable to seed provider plugin: $target"
    fi
  done
fi

#######################################
# Apply OpenCode config only when needed
#######################################
if [ -s "$OPENCODE_CONFIG_FILE" ] && [ ! -f "$APPLY_MARKER" ]; then
  log "Existing OpenCode configuration found → preserving it"
else
  log "Generating OpenCode configuration"

  log "Runtime environment variables available:"
  # Redact secret values (anything whose name contains KEY/TOKEN/SECRET/PASSWORD)
  env | grep -E 'OPENROUTER_|OPENCODE_' | sed -E 's/^([^=]*(KEY|TOKEN|SECRET|PASSWORD)[^=]*)=.*/\1=REDACTED/I' || true

  [ -x "$APPLY_SCRIPT" ] || fatal "Apply script not executable: $APPLY_SCRIPT"

  if ! "$APPLY_SCRIPT"; then
    fatal "apply-settings failed"
  fi

  rm -f "$APPLY_MARKER" || fatal "Unable to clear one-time settings marker"
fi

# Keep provider credentials private even when the surrounding bind mount is
# group-writable for collaboration.
if [ -f "$OPENCODE_AUTH_FILE" ]; then
  chmod 0600 "$OPENCODE_AUTH_FILE" || fatal "Unable to secure OpenCode auth file"
fi

#######################################
# Seed agents (VOLUME-SAFE)
#######################################
log "Checking agents directory"

mkdir -p "$AGENTS_DIR"

if [ -z "$(ls -A "$AGENTS_DIR" 2>/dev/null)" ]; then
  log "Agents dir empty → seeding from image"

  if ! cp -R "$DEFAULT_AGENTS/." "$AGENTS_DIR/"; then
    fatal "Failed to seed agents"
  fi

  log "Agents seeded successfully"
else
  log "Agents dir already populated → skip"
fi

#######################################
# Seed workflows (VOLUME-SAFE)
#######################################
log "Checking workflows directory"

mkdir -p "$WORKFLOWS_DIR"

if [ -z "$(ls -A "$WORKFLOWS_DIR" 2>/dev/null)" ]; then
  log "Workflows dir empty → seeding from image"

  if ! cp -R "$DEFAULT_WORKFLOWS/." "$WORKFLOWS_DIR/"; then
    fatal "Failed to seed workflows"
  fi

  log "Workflows seeded successfully"
else
  log "Workflows dir already populated → skip"
fi

#######################################
# Final state summary (debug friendly)
#######################################
log "Final agent directory content:"
ls -la "$AGENTS_DIR"


#######################################
# OpenCode Markdown export watcher
#######################################
#######################################
# Real-time Markdown watcher (inotify)
#######################################

SESSIONS_DIR="/root/.local/share/opencode/sessions"

log "Preparing OpenCode sessions directory"
mkdir -p "$SESSIONS_DIR"

log "Starting real-time Markdown watcher (inotify on /)"

inotifywait -m / \
  -e create -e moved_to -e close_write \
  --format '%w%f' |
while read -r path; do
  file="$(basename "$path")"

  case "$file" in
    *.md) ;;
    *) continue ;;
  esac

  case "$path" in
    /*.md) ;;
    *) continue ;;
  esac

  src="$path"
  dst="$SESSIONS_DIR/$file"

  [ -f "$src" ] || continue

  if [ -f "$dst" ]; then
    ts=$(date '+%Y%m%d-%H%M%S')
    dst="$SESSIONS_DIR/${file%.md}-$ts.md"
  fi

  log "Markdown detected → moving $src → $dst"
  mv -f "$src" "$dst"
done &

#######################################
# MCP container-restart watchdog
#######################################
# A background loop that probes the MCP server health and restarts the whole
# opencode container on persistent failure. The container has the Docker CLI
# + socket mounted, so it can restart itself. The watchdog dies with the
# container and is re-launched by the entrypoint on boot; the watchdog's own
# WARMUP period on the new instance prevents a restart loop.
#
# This replaces the abandoned socket-daemon approach: the MCP server is now run
# directly over stdio by opencode (darkmoon-mcp -> src.server), and liveness is
# enforced at the container level.
start_mcp_watchdog() {
  log "Starting MCP container-restart watchdog"
  setsid /usr/local/bin/mcp-watchdog.sh --restart-container \
    > /tmp/darkmoon-mcp-watchdog.log 2>&1 < /dev/null &
  disown 2>/dev/null || true
}

start_mcp_watchdog

#######################################
# Start main process
#######################################
log "Starting main process: $*"
exec "$@"
