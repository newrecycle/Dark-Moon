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

# Subagent model — specialized sub-agents use this instead of the primary
# model. Falls back to the same provider with a smaller/faster model so the
# orchestrator (pentest) keeps the primary model. Set OPENCODE_SUBAGENT_MODEL
# in .opencode.env to override.
OPENCODE_SUBAGENT_MODEL="${OPENCODE_SUBAGENT_MODEL:-tencent/hy3:free}"

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

# Subagent model — same provider routing as the primary model, but using
# OPENCODE_SUBAGENT_MODEL (a smaller/faster model) so the orchestrator keeps
# the heavyweight primary model while sub-agents run the lightweight one.
if [ "$USE_OPENROUTER" = true ]; then
  SUBAGENT_MODEL="${OPENROUTER_PROVIDER}/${OPENCODE_SUBAGENT_MODEL}"
elif [ "$USE_ANTHROPIC" = true ]; then
  SUBAGENT_MODEL="anthropic/${OPENCODE_SUBAGENT_MODEL}"
elif [ "$USE_LOCAL" = true ]; then
  SUBAGENT_MODEL="${OPENCODE_LOCAL_PROVIDER_ID}/${OPENCODE_SUBAGENT_MODEL}"
else
  SUBAGENT_MODEL="opencode/big-pickle"
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
elif [ "$USE_OPENROUTER" = true ]; then
  # Register the Nous-compatible provider with BOTH the primary (orchestrator)
  # and subagent models. reasoningEffort is set to high on both so every agent
  # runs with maximum thinking/interleaved reasoning.
  PROVIDER_BLOCK=$(cat <<PROVEOF
,

  "provider": {
    "${OPENROUTER_PROVIDER}": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "${OPENROUTER_PROVIDER}",
      "options": {
        "baseURL": "https://inference-api.${OPENROUTER_PROVIDER}research.com/v1",
        "includeUsage": true
      },
      "models": {
        "${OPENCODE_SUBAGENT_MODEL}": {
          "name": "${OPENCODE_SUBAGENT_MODEL}",
          "reasoning": true,
          "interleaved": {
            "field": "reasoning"
          },
          "options": {
            "reasoningEffort": "high"
          }
        },
        "${OPENCODE_MODEL}": {
          "name": "${OPENCODE_MODEL}",
          "reasoning": true,
          "interleaved": {
            "field": "reasoning"
          },
          "options": {
            "reasoningEffort": "high"
          }
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
      "mode": "primary",
      "tools": {
        "darkmoon_get_session": true,
        "darkmoon_dashboard_init_campaign": true,
        "darkmoon_dashboard_finalize_campaign": true,
        "darkmoon_dashboard_push_infra_node": true,
        "darkmoon_dashboard_push_finding": true,
        "darkmoon_list_allowed_tools": true,
        "darkmoon_health_check": true,
        "darkmoon_execute_command": false
      },
      "permission": {
        "bash": "deny",
        "read": "deny",
        "glob": "deny",
        "edit": "deny",
        "grep": "deny",
        "list": "deny",
        "task": "allow",
        "darkmoon_run_workflow": "deny",
        "darkmoon_execute_command": "deny"
      }
    },

    "aws": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "azure": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "entra-id": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "gcp": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "github": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "gitlab": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "jenkins": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "terraform": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "ansible": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "docker": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "container-registry": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "hashicorp-vault": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "sql-databases": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "messaging-cache": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },
    "firmware": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "sso-idp": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "gitops": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "observability": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "storage": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "edge-proxy": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "vpn-remote-access": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "firewall-network": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "email-infrastructure": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "backup": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "pki-adcs": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "nosql-databases": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "container-platform": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "hypervisor": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "business-platforms": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "mobile": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "mdm": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "active-directory": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "aspnet": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "flask": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "graphql": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "golang": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "headless-browser": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "kubernetes": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "nest": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "php": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "ruby": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "springboot": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "nodejs-express-angular": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "wordpress": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "prestashop": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "moodle": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "magento": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "joomla": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
    },

    "drupal": {
      "model": "$SUBAGENT_MODEL",
      "mode": "subagent",
      "tools": {
        "darkmoon_*": true
      }
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
