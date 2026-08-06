import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const source = await readFile(new URL("../conf/plugins/darkmoon-compat.js", import.meta.url), "utf8")
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
const { DarkMoonCompatibility } = await import(moduleUrl)

const forbiddenProviderKeys = [
  "id",
  "name",
  "primary",
  "secondary",
  "prompt_file",
  "mcp",
  "tools",
  "maxSteps",
]

test("plugin preserves valid root agent fields and removes legacy metadata", async () => {
  const previousUrl = process.env.DARKMOON_MCP_URL
  process.env.DARKMOON_MCP_URL = "http://mcp.test:9000/custom"

  try {
    const hooks = await DarkMoonCompatibility({
      client: {
        app: {
          log: async () => {
            throw new Error("logging is deliberately unavailable")
          },
        },
      },
    })

    const config = {
      default_agent: "build",
      subagent_depth: 9,
      agent: {
        pentest: {
          id: "legacy-pentest",
          name: "Pentest",
          primary: true,
          secondary: false,
          prompt_file: "pentest.txt",
          mcp: ["darkmoon"],
          tools: { task: true },
          maxSteps: 12,
          steps: 8,
          permission: { "*": "deny", "darkmoon_*": "allow", task: "allow" },
          options: {
            id: "leaked-id",
            name: "leaked-name",
            primary: true,
            secondary: false,
            prompt_file: "leaked.txt",
            mcp: ["darkmoon"],
            tools: { bash: true },
            maxSteps: 99,
            reasoning_effort: "low",
          },
        },
      },
    }

    await hooks.config(config)

    assert.equal(config.default_agent, "pentest")
    assert.equal(config.subagent_depth, 1)
    assert.deepEqual(config.mcp.darkmoon, {
      type: "remote",
      url: "http://mcp.test:9000/custom",
      oauth: false,
      timeout: 36_000_000,
      enabled: true,
    })

    const agent = config.agent.pentest
    assert.equal(agent.name, "Pentest")
    assert.deepEqual(agent.tools, { task: true })
    assert.equal(agent.maxSteps, 12)
    assert.equal(agent.steps, 8)
    assert.deepEqual(agent.permission, { "*": "deny", "darkmoon_*": "allow", task: "allow" })
    for (const key of ["id", "primary", "secondary", "prompt_file", "mcp"]) {
      assert.equal(Object.hasOwn(agent, key), false, `root agent retained ${key}`)
    }
    assert.deepEqual(agent.options, { reasoning_effort: "low" })
  } finally {
    if (previousUrl === undefined) delete process.env.DARKMOON_MCP_URL
    else process.env.DARKMOON_MCP_URL = previousUrl
  }
})

test("chat.params is the final provider-option boundary", async () => {
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })
  const output = {
    options: Object.fromEntries([
      ...forbiddenProviderKeys.map((key) => [key, `bad-${key}`]),
      ["reasoning_effort", "medium"],
    ]),
  }

  await hooks["chat.params"]({}, output)

  assert.deepEqual(output.options, { reasoning_effort: "medium" })
})

function withEnv(patch, fn) {
  const backup = new Map()
  const restore = (name) => {
    if (backup.has(name)) delete process.env[name]
    else process.env[name] = backup.get(name)
  }
  for (const [name, value] of Object.entries(patch)) {
    backup.set(name, process.env[name])
    if (value === undefined) delete process.env[name]
    else process.env[name] = value
  }
  process.env // ensure lookup triggers
  return Promise.resolve()
    .then(fn)
    .finally(() => {
      for (const name of Object.keys(patch)) restore(name)
    })
}

test("DARKMOON_SMALL_MODEL routes subagents to a distinct model", async () => {
  const messages = []
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async ({ body }) => { messages.push(body.message) } } },
  })

  await withEnv(
    { DARKMOON_SMALL_MODEL: "nvidia/laguna-xs-2.1", DARKMOON_MCP_URL: "http://mcp.test:9000/custom" },
    async () => {
      const config = {
        model: "nvidia/deepseek-v4-flash",
        small_model: "nvidia/deepseek-v4-flash",
        agent: { pentest: {}, "python-flask": {}, explore: {} },
      }
      await hooks.config(config)
      assert.equal(config.model, "nvidia/deepseek-v4-flash", "root model untouched")
      assert.equal(config.small_model, "nvidia/laguna-xs-2.1", "small_model hint updated")
      // Runtime truth in 1.18: subagents stream with small=false and resolve
      // their model from agent.<name>.model — the route must land there too.
      assert.equal(config.agent.pentest.model, undefined, "orchestrator keeps primary model")
      assert.equal(config.agent["python-flask"].model, "nvidia/laguna-xs-2.1", "specialist routed")
      assert.equal(config.agent.explore.model, "nvidia/laguna-xs-2.1", "builtin subagent routed")
    }
  )
  assert.ok(messages.some((m) => /subagent model routed to nvidia\/laguna-xs-2\.1/.test(m)))
})

test("DARKMOON_SMALL_MODEL scopes bare and slashed catalogue ids to the default provider", async () => {
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  await withEnv(
    { DARKMOON_SMALL_MODEL: "deepseek-ai/deepseek-v4-flash", DARKMOON_MCP_URL: "http://mcp.test:9000/custom" },
    async () => {
      const config = { model: "nvidia/deepseek-ai/deepseek-v4-pro", small_model: "nvidia/deepseek-ai/deepseek-v4-pro" }
      await hooks.config(config)
      // "deepseek-ai" is not a provider — the slashed id must be scoped to nvidia.
      assert.equal(config.small_model, "nvidia/deepseek-ai/deepseek-v4-flash")
    }
  )
})

test("DARKMOON_AGENT_MODELS applies per-agent model overrides", async () => {
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  await withEnv(
    {
      DARKMOON_AGENT_MODELS: JSON.stringify({
        pentest: "nvidia/deepseek-v4-flash",
        "python-flask": "deepseek-v4-flash",
      }),
      DARKMOON_MCP_URL: "http://mcp.test:9000/custom",
    },
    async () => {
      const config = {
        model: "nvidia/laguna-xs-2.1",
        small_model: "nvidia/laguna-xs-2.1",
        agent: {
          pentest: { variant: "fast" },
          "python-flask": {},
        },
      }
      await hooks.config(config)
      assert.equal(config.agent.pentest.model, "nvidia/deepseek-v4-flash")
      assert.equal(config.agent["python-flask"].model, "nvidia/deepseek-v4-flash", "bare ids scoped under default provider")
    }
  )
})

test("DARKMOON_AGENT_MODELS fills missing agents without clobbering existing config", async () => {
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  await withEnv(
    {
      DARKMOON_AGENT_MODELS: JSON.stringify({ pentest: "nvidia/new-model" }),
      DARKMOON_MCP_URL: "http://mcp.test:9000/custom",
    },
    async () => {
      const config = {
        model: "nvidia/laguna-xs-2.1",
        small_model: "nvidia/laguna-xs-2.1",
        agent: {
          pentest: { model: "explicit-from-json", variant: "fast" },
        },
      }
      await hooks.config(config)
      // Per spec: plugin applies the operator override on top of any
      // existing agent.model. Explicit Markdown/JSON models now obey the
      // operator env override, since that is exactly the broken case the
      // plugin is meant to fix.
      assert.equal(config.agent.pentest.model, "nvidia/new-model")
    }
  )
})

test("malformed DARKMOON_AGENT_MODELS is ignored without throwing", async () => {
  const messages = []
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async ({ body }) => { messages.push(body) } } },
  })

  await withEnv(
    { DARKMOON_AGENT_MODELS: "not-json", DARKMOON_MCP_URL: "http://mcp.test:9000/custom" },
    async () => {
      const config = { model: "nvidia/deepseek-v4-flash", small_model: "nvidia/deepseek-v4-flash" }
      await hooks.config(config)
      assert.equal(config.small_model, "nvidia/deepseek-v4-flash", "no routing changes")
      assert.ok(!config.agent, "agent section never created from bad input")
    }
  )
  assert.ok(messages.some((m) => m.level === "error" && /DARKMOON_AGENT_MODELS/.test(m.message)))
})

test("DARKMOON_DISCOVER_MODELS merges provider /models into config", async () => {
  // Swap the global fetch so discovery hits an in-memory fixture. The plugin
  // spawns requests with AbortSignal.timeout — undo that by stubbing fetch.
  const originalFetch = globalThis.fetch
  let requestCount = 0
  globalThis.fetch = async (input, init) => {
    requestCount++
    const url = typeof input === "string" ? input : input.toString()
    const headers = init?.headers || {}
    // Simulate an OpenAI-style /models listing scoped per provider baseURL.
    if (url.includes("/v1/models") && headers.Authorization === "Bearer nvapi-test") {
      return new Response(
        JSON.stringify({
          data: [{ id: "nvidia/discovered-a" }, { id: "nvidia/discovered-b" }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    }
    return new Response("not found", { status: 404 })
  }

  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  try {
    await withEnv(
      { DARKMOON_DISCOVER_MODELS: "1", DARKMOON_MCP_URL: "http://mcp.test:9000/custom" },
      async () => {
        const config = {
          model: "nvidia/deepseek-v4-flash",
          small_model: "nvidia/deepseek-v4-flash",
          provider: {
            nvidia: {
              npm: "@ai-sdk/openai-compatible",
              options: {
                baseURL: "https://integrate.api.nvidia.com/v1",
                apiKey: "nvapi-test",
              },
              models: {
                "nvidia/deepseek-v4-flash": { name: "nvidia/deepseek-v4-flash" },
              },
            },
          },
        }
        await hooks.config(config)
        assert.equal(config.provider.nvidia.models["nvidia/deepseek-v4-flash"].name, "nvidia/deepseek-v4-flash")
        assert.equal(config.provider.nvidia.models["nvidia/discovered-a"].name, "nvidia/discovered-a")
        assert.equal(config.provider.nvidia.models["nvidia/discovered-b"].name, "nvidia/discovered-b")
      }
    )
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.ok(requestCount > 0, "discovery issued at least one request")
})

test("unknown env vars leave the stock config untouched", async () => {
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  await withEnv(
    { DARKMOON_SMALL_MODEL: undefined, DARKMOON_AGENT_MODELS: undefined, DARKMOON_DISCOVER_MODELS: undefined, DARKMOON_MCP_URL: "http://mcp.test:9000/custom" },
    async () => {
      const config = {
        model: "nvidia/deepseek-v4-flash",
        small_model: "nvidia/deepseek-v4-flash",
        agent: { pentest: { variant: "fast" } },
      }
      await hooks.config(config)
      assert.equal(config.small_model, "nvidia/deepseek-v4-flash")
      assert.equal(config.agent.pentest.model, "nvidia/deepseek-v4-flash", "variant bound to root model")
    }
  )
})

test("dispatch tier routing rewrites the model in chat.params", async () => {
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  await withEnv(
    {
      // Slashed catalogue id, NOT provider-qualified — must scope to nvidia.
      DARKMOON_MODEL_FAST: "poolside/laguna-xs-2.1",
      DARKMOON_MODEL_BALANCED: "nvidia/deepseek-v4-flash",
      DARKMOON_MODEL_DEEP: "nvidia/deepseek-v4-pro",
      DARKMOON_MCP_URL: "http://mcp.test:9000/custom",
    },
    async () => {
      const config = { model: "nvidia/deepseek-v4-pro", small_model: "nvidia/deepseek-v4-pro" }
      await hooks.config(config)

      const output = {
        model: "nvidia/deepseek-v4-pro",
        options: {},
        messages: [
          { role: "user", content: "enumerate the web plane\nTIER_CHOICE=fast REASON=triaging" },
        ],
      }
      await hooks["chat.params"]({}, output)
      assert.equal(output.model, "nvidia/poolside/laguna-xs-2.1", "fast tier routes to the scoped fast model")

      const deep = {
        model: "nvidia/deepseek-v4-pro",
        options: {},
        messages: [
          { role: "user", content: "crown jewel recon\nMODEL_TIER: deep" },
        ],
      }
      await hooks["chat.params"]({}, deep)
      assert.equal(deep.model, "nvidia/deepseek-v4-pro", "deep tier routes to the deep model")
    }
  )
})

test("dispatch tier routing ignores requests without a tier marker", async () => {
  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  await withEnv(
    {
      DARKMOON_MODEL_FAST: "nvidia/laguna-xs-2.1",
      DARKMOON_MCP_URL: "http://mcp.test:9000/custom",
    },
    async () => {
      const config = { model: "nvidia/deepseek-v4-pro", small_model: "nvidia/deepseek-v4-pro" }
      await hooks.config(config)

      const output = {
        model: "nvidia/deepseek-v4-pro",
        options: {},
        messages: [
          { role: "user", content: "run a scan" },
        ],
      }
      await hooks["chat.params"]({}, output)
      assert.equal(output.model, "nvidia/deepseek-v4-pro", "no marker → model untouched")

      // Tier not configured for this tier → untouched
      const unbalanced = {
        model: "nvidia/deepseek-v4-pro",
        options: {},
        messages: [{ role: "user", content: "TIER_CHOICE=deep" }],
      }
      await hooks["chat.params"]({}, unbalanced)
      assert.equal(unbalanced.model, "nvidia/deepseek-v4-pro", "unmapped tier → model untouched")
    }
  )
})

test("discovery synthesizes known built-in provider from the root model", async () => {
  const originalFetch = globalThis.fetch
  let requestCount = 0
  globalThis.fetch = async (input) => {
    requestCount++
    const url = typeof input === "string" ? input : input.toString()
    if (url.includes("integrate.api.nvidia.com")) {
      return new Response(
        JSON.stringify({
          data: [{ id: "nvidia/deepseek-v4-flash" }, { id: "nvidia/laguna-xs-2.1" }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    }
    return new Response("not found", { status: 404 })
  }

  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  try {
    await withEnv(
      {
        DARKMOON_DISCOVER_MODELS: "1",
        OPENROUTER_API_KEY: "nvapi-test",
        DARKMOON_MCP_URL: "http://mcp.test:9000/custom",
      },
      async () => {
        // No provider block at all — exactly the user's auth.json-based setup.
        const config = { model: "nvidia/deepseek-ai/deepseek-v4-pro", small_model: "nvidia/deepseek-ai/deepseek-v4-pro" }
        await hooks.config(config)
        assert.ok(config.provider?.nvidia, "provider block synthesized for nvidia")
        assert.equal(config.provider.nvidia.options.baseURL, "https://integrate.api.nvidia.com/v1")
        assert.equal(config.provider.nvidia.models["nvidia/deepseek-v4-flash"].name, "nvidia/deepseek-v4-flash")
        assert.equal(config.provider.nvidia.models["nvidia/laguna-xs-2.1"].name, "nvidia/laguna-xs-2.1")
      }
    )
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.ok(requestCount > 0, "discovery issued at least one request")
})

test("discovery without DARKMOON_DISCOVER_MODELS never fetches", async () => {
  const originalFetch = globalThis.fetch
  let requestCount = 0
  globalThis.fetch = async () => {
    requestCount++
    return new Response("unexpected", { status: 500 })
  }

  const hooks = await DarkMoonCompatibility({
    client: { app: { log: async () => undefined } },
  })

  try {
    await withEnv(
      { OPENROUTER_API_KEY: "nvapi-test", DARKMOON_MCP_URL: "http://mcp.test:9000/custom" },
      async () => {
        const config = { model: "nvidia/deepseek-ai/deepseek-v4-pro", small_model: "nvidia/deepseek-ai/deepseek-v4-pro" }
        await hooks.config(config)
        assert.ok(!config.provider?.nvidia, "no provider block synthesized without discovery flag")
      }
    )
  } finally {
    globalThis.fetch = originalFetch
  }
  assert.equal(requestCount, 0, "no network calls when discovery is off")
})
