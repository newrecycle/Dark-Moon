/** Bind campaign initialization to the tool caller's root, never the newest run.
 * Uses the public plugin hook/SDK in the pinned ASCIT31/opencode runtime.
 * Privacy session_id is deliberately untouched. No model calls or global state.
 */
type SessionClient = {
  session: {
    get: (options: { path: { id: string }; signal: AbortSignal }) => Promise<{
      data?: { id: string; parentID?: string }; error?: unknown
    }>
  }
}

export const DarkmoonCampaignPlugin = async ({ client }: { client: SessionClient }) => ({
  "tool.execute.before": async (
    input: { tool: string; sessionID: string },
    output: { args: Record<string, unknown> },
  ) => {
    // MCP tools are named <server>_<tool>; don't touch unrelated tools/args.
    if (input.tool !== "darkmoon_dashboard_init_campaign") return
    let id = input.sessionID
    const seen = new Set<string>()
    const signal = AbortSignal.timeout(10000)
    while (!seen.has(id) && seen.size < 64) {
      if (!/^ses_[A-Za-z0-9_-]+$/.test(id)) throw new Error("Invalid OpenCode session identity")
      seen.add(id)
      const result = await client.session.get({ path: { id }, signal })
      if (result.error || result.data?.id !== id) {
        throw new Error("Cannot bind campaign to its OpenCode root; retry initialization")
      }
      if (!result.data.parentID) {
        // Overwrite model-supplied identity with the verified local caller root.
        output.args.opencode_session_id = id
        return
      }
      id = result.data.parentID
    }
    throw new Error("Cyclic or excessive OpenCode session ancestry")
  },
})

export default DarkmoonCampaignPlugin
