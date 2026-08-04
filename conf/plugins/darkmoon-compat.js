const FORBIDDEN_PROVIDER_KEYS = new Set([
  "id",
  "name",
  "primary",
  "secondary",
  "prompt_file",
  "mcp",
  "tools",
  "maxSteps",
])

function stripForbidden(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return
  for (const key of Object.keys(value)) {
    if (FORBIDDEN_PROVIDER_KEYS.has(key)) delete value[key]
  }
}

/**
 * Dark-Moon compatibility layer for stock OpenCode 1.18.12.
 *
 * The plugin keeps Dark-Moon policy out of the OpenCode source tree and makes
 * provider request sanitization the final boundary before NVIDIA NIM.
 */
export const DarkMoonCompatibility = async ({ client }) => {
  await client.app.log({
    body: {
      service: "darkmoon-compat",
      level: "info",
      message: "Dark-Moon compatibility plugin loaded",
    },
  })

  return {
    config: async (config) => {
      config.default_agent = "pentest"
      config.subagent_depth = 1

      config.mcp ??= {}
      config.mcp.darkmoon = {
        type: "local",
        command: ["/usr/local/bin/darkmoon-mcp"],
        timeout: 36_000_000,
        enabled: true,
      }

      if (config.agent && typeof config.agent === "object") {
        for (const agent of Object.values(config.agent)) {
          if (!agent || typeof agent !== "object") continue
          stripForbidden(agent)
          stripForbidden(agent.options)
        }
      }
    },

    "chat.params": async (_input, output) => {
      stripForbidden(output.options)
    },
  }
}
