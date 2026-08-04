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
