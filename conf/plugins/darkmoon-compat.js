const LEGACY_AGENT_KEYS = new Set([
  "id",
  "primary",
  "secondary",
  "prompt_file",
  "mcp",
])

const FORBIDDEN_PROVIDER_KEYS = new Set([
  ...LEGACY_AGENT_KEYS,
  "name",
  "tools",
  "maxSteps",
])

function stripKeys(value, keys) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return
  for (const key of Object.keys(value)) {
    if (keys.has(key)) delete value[key]
  }
}

function selectedModel(config) {
  return typeof config?.model === "string" && config.model.includes("/")
    ? config.model
    : undefined
}

/**
 * Dark-Moon compatibility layer for stock OpenCode 1.18.12.
 *
 * Dark-Moon policy stays outside the OpenCode source tree. Legacy agent
 * metadata is removed from normalized agent configuration, while valid agent
 * fields such as tools, permission, steps, maxSteps, model, and variant remain
 * available to OpenCode. The chat.params hook is the final provider-request
 * boundary.
 *
 * OpenCode 1.18.12 applies an agent's configured variant only when that agent
 * also has a matching configured model. Dark-Moon historically selected one
 * model globally and placed only `variant` in agent frontmatter. Bind those
 * variant-bearing agents to the selected root model so reasoning variants are
 * not silently discarded. Explicit per-agent models are always preserved.
 */
export const DarkMoonCompatibility = async ({ client }) => {
  try {
    await client.app.log({
      body: {
        service: "darkmoon-compat",
        level: "info",
        message: "Dark-Moon compatibility plugin loaded",
      },
    })
  } catch {
    // Logging must never prevent OpenCode from loading the compatibility layer.
  }

  return {
    config: async (config) => {
      config.default_agent = "pentest"
      config.subagent_depth = 1

      config.mcp ??= {}
      config.mcp.darkmoon = {
        type: "remote",
        url: process.env.DARKMOON_MCP_URL ?? "http://darkmoon-mcp:8000/mcp",
        oauth: false,
        timeout: 36_000_000,
        enabled: true,
      }

      const model = selectedModel(config)
      if (config.agent && typeof config.agent === "object") {
        for (const agent of Object.values(config.agent)) {
          if (!agent || typeof agent !== "object") continue
          stripKeys(agent, LEGACY_AGENT_KEYS)
          stripKeys(agent.options, FORBIDDEN_PROVIDER_KEYS)

          if (
            model &&
            !agent.model &&
            typeof agent.variant === "string" &&
            agent.variant.trim()
          ) {
            agent.model = model
          }
        }
      }
    },

    "chat.params": async (_input, output) => {
      stripKeys(output.options, FORBIDDEN_PROVIDER_KEYS)
    },
  }
}
