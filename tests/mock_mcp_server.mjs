import { pathToFileURL } from "node:url"
import { appendFile } from "node:fs/promises"

const source = process.env.OPENCODE_SOURCE_DIR
if (!source) throw new Error("OPENCODE_SOURCE_DIR is required")

const sdk = `${source}/packages/opencode/node_modules/@modelcontextprotocol/sdk/dist/esm`
const { Server } = await import(pathToFileURL(`${sdk}/server/index.js`).href)
const { StdioServerTransport } = await import(pathToFileURL(`${sdk}/server/stdio.js`).href)
const { CallToolRequestSchema, ListToolsRequestSchema } = await import(pathToFileURL(`${sdk}/types.js`).href)

async function trace(event) {
  if (process.env.MOCK_MCP_CALLED_FILE) await appendFile(process.env.MOCK_MCP_CALLED_FILE, `${event}\n`)
}

const server = new Server(
  { name: "darkmoon-regression", version: "1.0.0" },
  { capabilities: { tools: {} } },
)

server.setRequestHandler(ListToolsRequestSchema, async () => {
  await trace("list_tools")
  return {
    tools: [
      {
        name: "get_session",
        description: "Return a deterministic Dark-Moon regression session",
        inputSchema: { type: "object", properties: {}, additionalProperties: false },
      },
    ],
  }
})

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  if (request.params.name !== "get_session") throw new Error(`unknown tool: ${request.params.name}`)
  await trace("darkmoon_get_session")
  return { content: [{ type: "text", text: '{"session_id":"issue-36-regression"}' }] }
})

await trace("started")
await server.connect(new StdioServerTransport())
