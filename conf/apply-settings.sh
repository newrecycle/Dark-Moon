#!/usr/bin/env bash
set -euo pipefail

OPENCODE_CONFIG_DIR="/root/.config/opencode"
OPENCODE_CONFIG_FILE="$OPENCODE_CONFIG_DIR/opencode.json"
OPENCODE_PLUGIN_DIR="$OPENCODE_CONFIG_DIR/plugins"
NVIDIA_COMPAT_PLUGIN="$OPENCODE_PLUGIN_DIR/nvidia-compat.ts"

OPENCODE_AUTH_DIR="/root/.local/share/opencode"
OPENCODE_AUTH_FILE="$OPENCODE_AUTH_DIR/auth.json"

fail() { echo "❌ $*" >&2; exit 1; }
log()  { echo "[INIT] $*" >&2; }

#######################################
# Environment (injected by runtime via .opencode.env)
#######################################

# Cloud provider vars
OPENROUTER_PROVIDER="${OPENROUTER_PROVIDER:-}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"
OPENCODE_MODEL="${OPENCODE_MODEL:-}"

# Local provider vars
OPENCODE_LOCAL_MODE="${OPENCODE_LOCAL_MODE:-false}"
OPENCODE_LOCAL_PROVIDER_ID="${OPENCODE_LOCAL_PROVIDER_ID:-}"
OPENCODE_LOCAL_PROVIDER_NAME="${OPENCODE_LOCAL_PROVIDER_NAME:-Local model}"
OPENCODE_LOCAL_BASE_URL="${OPENCODE_LOCAL_BASE_URL:-}"
OPENCODE_LOCAL_MODEL="${OPENCODE_LOCAL_MODEL:-}"
OPENCODE_LOCAL_API_KEY="${OPENCODE_LOCAL_API_KEY:-}"

# On-prem Anthropic-compatible vars (opencode reads ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY from env)
ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-}"
ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-}"

#######################################
# Decide model strategy
# Priority: local > anthropic > cloud > fallback
#######################################
USE_LOCAL=false
USE_ANTHROPIC=false
USE_OPENROUTER=false

if [ "${OPENCODE_LOCAL_MODE}" = "true" ] && \
   [ -n "${OPENCODE_LOCAL_PROVIDER_ID:-}" ] && \
   [ -n "${OPENCODE_LOCAL_BASE_URL:-}" ] && \
   [ -n "${OPENCODE_LOCAL_MODEL:-}" ]; then
  USE_LOCAL=true
elif [ -n "${ANTHROPIC_BASE_URL:-}" ] && [ -n "${ANTHROPIC_MODEL:-}" ]; then
  USE_ANTHROPIC=true
elif [ -n "${OPENROUTER_PROVIDER:-}" ] && \
     [ -n "${OPENROUTER_API_KEY:-}" ] && \
     [ -n "${OPENCODE_MODEL:-}" ]; then
  USE_OPENROUTER=true
fi

if [ "$USE_LOCAL" = true ]; then
  # Local provider: model string is just the model name (no provider/ prefix)
  FINAL_MODEL="${OPENCODE_LOCAL_PROVIDER_ID}/${OPENCODE_LOCAL_MODEL}"
  log "Using local provider: ${OPENCODE_LOCAL_PROVIDER_NAME} → model: ${FINAL_MODEL}"
  log "Base URL: ${OPENCODE_LOCAL_BASE_URL}"
elif [ "$USE_ANTHROPIC" = true ]; then
  # On-prem Anthropic-compatible: opencode routes via ANTHROPIC_BASE_URL + ANTHROPIC_API_KEY (env)
  FINAL_MODEL="anthropic/${ANTHROPIC_MODEL}"
  log "Using on-prem Anthropic-compatible endpoint → model: ${FINAL_MODEL}"
  log "Base URL: ${ANTHROPIC_BASE_URL}"
elif [ "$USE_OPENROUTER" = true ]; then
  FINAL_MODEL="$OPENROUTER_PROVIDER/$OPENCODE_MODEL"
  log "Using cloud provider: $FINAL_MODEL"
else
  FINAL_MODEL="opencode/big-pickle"
  log "No provider configured → fallback to $FINAL_MODEL"
fi

#######################################
# Create directories
#######################################
mkdir -p "$OPENCODE_CONFIG_DIR" "$OPENCODE_AUTH_DIR" "$OPENCODE_PLUGIN_DIR"

# Current OpenCode treats unknown legacy agent metadata as provider options.
# NVIDIA rejects those extra request fields, so remove only that metadata at
# the provider boundary. Keep this generated alongside opencode.json so clean
# installs and explicit reinitializations receive the compatibility fix too.
cat > "$NVIDIA_COMPAT_PLUGIN" <<'PLUGINEOF'
import type { Hooks, PluginInput } from "@opencode-ai/plugin"

const LEGACY_AGENT_FIELDS = ["id", "mcp", "primary", "secondary", "prompt_file"] as const

export async function NvidiaCompatibilityPlugin(_input: PluginInput): Promise<Hooks> {
  return {
    "chat.params": async (input, output) => {
      if (input.model.providerID !== "nvidia") return
      for (const field of LEGACY_AGENT_FIELDS) delete output.options[field]
    },
  }
}
PLUGINEOF

#######################################
# Write opencode.json (ALWAYS)
#######################################

# Build optional provider block.
# - local mode  : declares a full OpenAI-compatible provider.
# - anthropic   : registers the custom model id under the built-in "anthropic"
#                 provider, otherwise opencode validates the configured model
#                 against its hard-coded catalogue and rejects it with
#                 ProviderModelNotFoundError.
PROVIDER_BLOCK=""
if [ "$USE_LOCAL" = true ]; then
  # Optional API key for authenticated OpenAI-compatible endpoints (Bearer auth).
  # JSON-escaped via python3 so keys containing quotes/backslashes can't break the config.
  LOCAL_API_KEY_OPTION=""
  if [ -n "${OPENCODE_LOCAL_API_KEY:-}" ]; then
    LOCAL_API_KEY_OPTION=$(OPENCODE_LOCAL_API_KEY="$OPENCODE_LOCAL_API_KEY" python3 -c 'import json,os; print(",\n        \"apiKey\": " + json.dumps(os.environ["OPENCODE_LOCAL_API_KEY"]))')
  fi
  PROVIDER_BLOCK=$(cat <<PROVEOF
,

  "provider": {
    "${OPENCODE_LOCAL_PROVIDER_ID}": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "${OPENCODE_LOCAL_PROVIDER_NAME}",
      "options": {
        "baseURL": "${OPENCODE_LOCAL_BASE_URL}"${LOCAL_API_KEY_OPTION}
      },
      "models": {
        "${OPENCODE_LOCAL_MODEL}": {
          "name": "${OPENCODE_LOCAL_MODEL}"
        }
      }
    }
  }
PROVEOF
)
elif [ "$USE_ANTHROPIC" = true ]; then
  PROVIDER_BLOCK=$(cat <<PROVEOF
,

  "provider": {
    "anthropic": {
      "models": {
        "${ANTHROPIC_MODEL}": {
          "name": "${ANTHROPIC_MODEL}"
        }
      }
    }
  }
PROVEOF
)
fi

cat > "$OPENCODE_CONFIG_FILE" <<EOF
{
  "\$schema": "https://opencode.ai/config.json"${PROVIDER_BLOCK},

  "model": "$FINAL_MODEL",
  "small_model": "$FINAL_MODEL",

  "mcp": {
    "darkmoon": {
      "type": "local",
      "command": ["/usr/local/bin/darkmoon-mcp"],
      "timeout": 36000000,
      "enabled": true
    }
  },

  "permission": { "*": "allow" },

  "agent": {
    "pentest": {
      "model": "$FINAL_MODEL",
      "mode": "primary"
    },

    "aws": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "azure": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "entra-id": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "gcp": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "github": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "gitlab": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "jenkins": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "terraform": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "ansible": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "docker": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "container-registry": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "hashicorp-vault": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "sql-databases": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "messaging-cache": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },
    "firmware": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "sso-idp": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "gitops": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "observability": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "storage": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "edge-proxy": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "vpn-remote-access": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "firewall-network": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "email-infrastructure": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "backup": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "pki-adcs": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "nosql-databases": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "container-platform": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "hypervisor": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "business-platforms": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "mobile": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "mdm": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "active-directory": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "aspnet": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "python-flask": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "graphql": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "golang": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "headless-browser": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "kubernetes": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "nest": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "php": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "ruby-on-rails": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "springboot": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "nodejs": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "wordpress": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "prestashop": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "moodle": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "magento": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "joomla": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    },

    "drupal": {
      "model": "$FINAL_MODEL",
      "mode": "subagent"
    }
  }
}
EOF

echo "✅ OpenCode config written to $OPENCODE_CONFIG_FILE"

#######################################
# Write auth.json ONLY for cloud providers
#######################################
if [ "$USE_OPENROUTER" = true ]; then
  cat > "$OPENCODE_AUTH_FILE" <<EOF
{
  "$OPENROUTER_PROVIDER": {
    "type": "api",
    "key": "$OPENROUTER_API_KEY"
  }
}
EOF
  echo "✅ OpenCode auth written to $OPENCODE_AUTH_FILE"
elif [ "$USE_LOCAL" = true ]; then
  rm -f "$OPENCODE_AUTH_FILE"
  log "Local provider — no auth.json needed"
else
  rm -f "$OPENCODE_AUTH_FILE"
  log "No auth.json written (fallback model does not require API key)"
fi

#######################################
# Optional warmup (SAFE, NON BLOCKING)
#######################################

#######################################
# Optional opencode TUI bootstrap (TEST — NO KILL)
#######################################

log "Optional opencode TUI bootstrap (test mode, no kill)"

if command -v /usr/local/bin/opencode >/dev/null 2>&1; then
  (
    # Lancer opencode dans un vrai pseudo-TTY
    script -q -c "/usr/local/bin/opencode --model \"$FINAL_MODEL\"" /dev/null &
    OPENCODE_PID=$!

    log "opencode TUI started in background (pid=$OPENCODE_PID)"
    log "NOT killing it — test mode"
  ) &
fi

log "Warmup finished (script continues)"
