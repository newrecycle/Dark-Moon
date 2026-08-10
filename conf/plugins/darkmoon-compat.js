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
  // AI SDK client-side retry options must never reach the provider API.
  // The nvidia endpoint returns "Bad Request: Validation: Unsupported
  // parameter(s)" if these are present in the request body.
  "maxRetries",
  "retryDelay",
  "respectRetryAfter",
  "maxRetryDelay",
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
 * Parse the configured provider id from a fully-qualified model string
 * (e.g. "nvidia/deepseek-v4-flash" -> "nvidia"). Returns undefined if the
 * model string is bare or malformed.
 */
function providerOf(model) {
  if (typeof model !== "string" || !model.includes("/")) return undefined
  const slash = model.indexOf("/")
  if (slash <= 0) return undefined
  return model.slice(0, slash)
}

function envFlag(name) {
  const value = process.env[name]
  return value === "1" || value === "true" || value === "yes"
}

/**
 * Resolve a model id to the fully-qualified "provider/model-part" form
 * OpenCode expects (e.g. "nvidia/deepseek-ai/deepseek-v4-flash").
 *
 * Catalogue ids may themselves contain slashes (nvidia: "deepseek-ai/…",
 * "poolside/laguna-xs-2.1"), so an id is only treated as already-qualified
 * when its first segment names a known provider (a configured provider, a
 * KNOWN_BASE_URLS provider, or the running provider). Everything else is
 * scoped under `defaultProvider`.
 */
function resolveModelId(raw, defaultProvider, knownProviders) {
  if (typeof raw !== "string" || !raw.trim()) return undefined
  const model = raw.trim()
  const slash = model.indexOf("/")
  if (slash > 0) {
    const prefix = model.slice(0, slash)
    if (knownProviders && knownProviders.has(prefix)) return model
    if (KNOWN_BASE_URLS[prefix]) return model
    if (KNOWN_MODEL_PREFIXES.has(prefix)) return model
  }
  if (!defaultProvider) return model
  return `${defaultProvider}/${model}`
}

/**
 * Known OpenAI-compatible base URLs for providers that OpenCode supports
 * natively via auth.json (no provider block in the generated config). Used
 * only for optional model discovery (DARKMOON_DISCOVER_MODELS).
 */
const KNOWN_BASE_URLS = {
  nvidia: "https://integrate.api.nvidia.com/v1",
  openrouter: "https://openrouter.ai/api/v1",
  openai: "https://api.openai.com/v1",
  groq: "https://api.groq.com/openai/v1",
  together: "https://api.together.xyz/v1",
  mistral: "https://api.mistral.ai/v1",
  xai: "https://api.x.ai/v1",
}

/**
 * Model id prefixes that OpenCode recognizes natively (not external
 * providers with a base URL). "opencode" is OpenCode's built-in model
 * namespace (e.g. "opencode/deepseek-v4-flash-free"). These are passed
 * through resolveModelId unchanged.
 */
const KNOWN_MODEL_PREFIXES = new Set([
  ...Object.keys(KNOWN_BASE_URLS),
  "opencode",
])

/**
 * Dark-Moon compatibility and model-routing plugin for stock OpenCode 1.18.12.
 *
 * Responsibilities:
 *  1. Legacy metadata is stripped from normalized agent configuration (root
 *     agent fields and provider options). Valid agent fields such as tools,
 *     permission, steps, maxSteps, model, and variant remain available.
 *  2. default_agent / subagent_depth / darkmoon MCP are forced so a stale
 *     generated config never subverts the Dark-Moon contract.
 *  3. OpenCode 1.18.12 applies an agent's configured variant only when that
 *     agent also has a matching configured model. Dark-Moon historically
 *     selected one model globally and placed only `variant` in agent
 *     frontmatter. Variant-bearing agents without an explicit model are
 *     bound to the selected root model so reasoning variants are not
 *     silently discarded. Explicit per-agent models are always preserved.
 *  4. Model routing without an external proxy:
 *       • DARKMOON_SMALL_MODEL  — distinct model for subagent dispatch.
 *         In 1.18.12, task-dispatched subagents stream with small=false and
 *         resolve their model from agent.<name>.model (NOT small_model).
 *         So the small model is written to config.agent[].model for every
 *         agent except the primary, plus the built-in subagents
 *         (explore/general/researcher/debugger/documenter) which OpenCode
 *         injects at runtime and are absent from the generated config.
 *         config.small_model is also set as a secondary hint for
 *         background/summary streams.
 *       • DARKMOON_AGENT_MODELS — JSON object mapping agent name to model
 *         id, applied as config.agent.<name>.model. Bare ids are scoped
 *         to the default provider.
 *       • DARKMOON_DISCOVER_MODELS=1 — at startup, query each configured
 *         OpenAI-compatible provider's /v1/models endpoint and merge the
 *         returned model ids into config.provider.<id>.models so the agent
 *         sees the full catalogue the API key grants. Known built-in
 *         providers (nvidia, openrouter, openai, …) are resolved even
 *         without an explicit provider block. Failures are logged and
 *         skipped; the hook never throws.
 *  5. Concurrency & rate limiting (chat.params + event hooks):
 *       • DARKMOON_MAX_CONCURRENCY — max simultaneous in-flight LLM requests
 *         across all sessions (default: 4). Enforced via a semaphore acquired
 *         in chat.params and released on step.ended / step.failed.
 *       • DARKMOON_RPM_LIMIT — max LLM requests per minute across all
 *         sessions (default: 60). Enforced via a token bucket.
 *       • DARKMOON_BACKOFF_BASE_MS / DARKMOON_BACKOFF_MAX_MS — exponential
 *         backoff applied globally when a 429 (rate-limit) response is
 *         detected from the provider. All new requests pause until the
 *         backoff window clears. Backoff halves on each successful step.
 *
 * Note: In OpenCode 1.18.12, the chat.params hook output carries only
 * sampling parameters (temperature, topP, topK, maxOutputTokens, options)
 * — no `model` or `messages` fields. Per-request model rewriting via
 * chat.params is therefore not possible. All model routing is done at
 * config time via config.agent.<name>.model, which the agent layer reads
 * for every subagent dispatch.
 */
export const DarkMoonCompatibility = async ({ client }) => {
  const log = async (level, message) => {
    try {
      await client?.app?.log?.({
        body: { service: "darkmoon-compat", level, message },
      })
    } catch {
      // Logging must never prevent OpenCode from loading the plugin.
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Concurrency & Rate Limiting
  // ─────────────────────────────────────────────────────────────
  // DARKMOON_MAX_CONCURRENCY — max simultaneous in-flight LLM requests
  //   across all sessions (semaphore). Prevents overwhelming the provider
  //   with too many parallel calls when subagents fan out.
  // DARKMOON_RPM_LIMIT — max LLM requests per minute across all sessions
  //   (token bucket). Prevents exceeding provider RPM quotas.
  // DARKMOON_BACKOFF_BASE_MS / DARKMOON_BACKOFF_MAX_MS — exponential
  //   backoff applied globally when a 429 is detected. All new requests
  //   pause until the backoff window clears, then resume with halved
  //   multiplier on each successful step.
  const MAX_CONCURRENCY = parseInt(process.env.DARKMOON_MAX_CONCURRENCY || "4", 10)
  const RPM_LIMIT = parseInt(process.env.DARKMOON_RPM_LIMIT || "60", 10)
  const BACKOFF_BASE_MS = parseInt(process.env.DARKMOON_BACKOFF_BASE_MS || "1000", 10)
  const BACKOFF_MAX_MS = parseInt(process.env.DARKMOON_BACKOFF_MAX_MS || "60000", 10)

  // Semaphore: activeRequests counts in-flight LLM steps across all sessions.
  let activeRequests = 0

  // Token bucket: tokens are replenished at RPM_LIMIT/60 per second.
  const TOKEN_INTERVAL_MS = 60000 / RPM_LIMIT
  let lastTokenTime = Date.now()
  let tokens = RPM_LIMIT

  // Global backoff state (shared across all sessions/models).
  let backoffMultiplier = 1
  let backoffUntil = 0

  // Track the pending release per session so we can defensively release
  // before re-acquiring (prevents deadlocks when chat.params fires again
  // before the previous step.ended event arrives).
  const pendingBySession = new Map()

  function is429Error(error) {
    if (!error) return false
    // ApiError carries data.statusCode from the provider response.
    if (error.data?.statusCode === 429) return true
    // Fallback: scan the message for 429 / rate-limit patterns.
    const msg = error.message || error.data?.message || ""
    return /429|rate.?limit/i.test(msg)
  }

  async function acquireSlot(sessionID) {
    // Defensive: release any previous pending slot for this session so we
    // never hold two slots for the same session simultaneously.
    const prev = pendingBySession.get(sessionID)
    if (prev) {
      prev.release()
      pendingBySession.delete(sessionID)
    }

    while (true) {
      const now = Date.now()

      // 1. Global backoff pause (triggered by a recent 429).
      if (now < backoffUntil) {
        const waitMs = backoffUntil - now
        await new Promise((resolve) => setTimeout(resolve, Math.min(waitMs, 1000)))
        continue
      }

      // 2. Concurrency semaphore.
      if (activeRequests >= MAX_CONCURRENCY) {
        await new Promise((resolve) => setTimeout(resolve, 100))
        continue
      }

      // 3. Token bucket (rate limiting).
      const elapsed = now - lastTokenTime
      const newTokens = Math.floor(elapsed / TOKEN_INTERVAL_MS)
      if (newTokens > 0) {
        tokens = Math.min(RPM_LIMIT, tokens + newTokens)
        lastTokenTime = now
      }
      if (tokens <= 0) {
        await new Promise((resolve) => setTimeout(resolve, Math.max(1, TOKEN_INTERVAL_MS)))
        continue
      }

      // All gates passed — acquire the slot.
      tokens--
      activeRequests++

      // Auto-release after a safety timeout. In headless mode (opencode run),
      // the step.ended event may not fire reliably. If the slot isn't released
      // within SLOT_TIMEOUT_MS, release it automatically to prevent deadlock.
      const SLOT_TIMEOUT_MS = parseInt(
        process.env.DARKMOON_SLOT_TIMEOUT_MS || "120000",
        10
      )
      const timer = setTimeout(() => {
        const pending = pendingBySession.get(sessionID)
        if (pending && pending.timer === timer) {
          pendingBySession.delete(sessionID)
          activeRequests--
          if (activeRequests < 0) activeRequests = 0
          log("warn", `chat.params: auto-released expired slot for session ${sessionID} (activeRequests: ${activeRequests})`)
        }
      }, SLOT_TIMEOUT_MS)

      const release = () => {
        clearTimeout(timer)
        activeRequests--
        if (activeRequests < 0) activeRequests = 0
      }
      pendingBySession.set(sessionID, { release, timer })
      return release
    }
  }

  function releaseForSession(sessionID, reason) {
    const pending = pendingBySession.get(sessionID)
    if (!pending) return
    pendingBySession.delete(sessionID)
    pending.release()
  }

  function handle429() {
    backoffMultiplier = Math.min(backoffMultiplier * 2, BACKOFF_MAX_MS / BACKOFF_BASE_MS)
    backoffUntil = Date.now() + BACKOFF_BASE_MS * backoffMultiplier
  }

  function handleSuccess() {
    backoffMultiplier = Math.max(1, backoffMultiplier * 0.5)
  }

  await log("info", "Dark-Moon compatibility plugin loaded")

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
      const defaultProvider = providerOf(model)

      // Provider ids the user may explicitly scope to in a model/route id:
      // any configured provider block plus the known built-in catalogue.
      const knownProviders = new Set()
      if (defaultProvider) knownProviders.add(defaultProvider)
      if (config.provider && typeof config.provider === "object") {
        for (const id of Object.keys(config.provider)) knownProviders.add(id)
      }

      // ── Variant binding (existing behavior) ──────────────────────
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

      // ── Subagent model routing ────────────────────────────────────
      // In OpenCode 1.18, task-dispatched subagents resolve their model via
      // agent.<name>.model (NOT small_model — subagent streams are
      // small=false). So a "default subagent model" must land on
      // config.agent[].model for every agent except the primary.
      // config.small_model is still set as a secondary hint where the
      // runtime uses it (background/summary streams).
      const smallModelRaw = process.env.DARKMOON_SMALL_MODEL
      const primaryAgent = typeof config.default_agent === "string"
        ? config.default_agent
        : "pentest"
      if (smallModelRaw && smallModelRaw.trim()) {
        const resolved = resolveModelId(smallModelRaw, defaultProvider, knownProviders)
        if (resolved) {
          config.small_model = resolved
          await log("info", `subagent model routed to ${resolved}`)
          if (config.agent && typeof config.agent === "object") {
            for (const [name, agent] of Object.entries(config.agent)) {
              if (!agent || typeof agent !== "object") continue
              if (name === primaryAgent) continue // never touch the orchestrator
              if (agent.model) continue // explicit per-agent model wins
              agent.model = resolved
            }
          }
          // Built-in opencode subagents are NOT surfaced in config.agent, so
          // explicitly publish the same route for them (best-effort override
          // for explore/general/researcher/debugger/documenter).
          if (config.agent) {
            for (const builtin of ["explore", "general", "researcher", "debugger", "documenter"]) {
              config.agent[builtin] ??= {}
              config.agent[builtin].model = resolved
            }
          }
        }
      }

      // ── Per-agent model routing ───────────────────────────────────
      // DARKMOON_AGENT_MODELS is a JSON object: { "<agent>": "<model>" }.
      // Bare model ids are scoped under the default provider. Explicit
      // agent.model values written by render_config take precedence only
      // when DARKMOON_AGENT_MODELS does not name that agent.
      const agentModelsRaw = process.env.DARKMOON_AGENT_MODELS
      if (agentModelsRaw && agentModelsRaw.trim()) {
        let parsed
        try {
          parsed = JSON.parse(agentModelsRaw)
        } catch (error) {
          await log("error", `DARKMOON_AGENT_MODELS is not valid JSON: ${error?.message ?? error}`)
          parsed = undefined
        }
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          config.agent ??= {}
          for (const [name, rawModel] of Object.entries(parsed)) {
            if (typeof name !== "string" || typeof rawModel !== "string") continue
            const resolved = resolveModelId(rawModel, defaultProvider, knownProviders)
            if (!resolved) continue
            config.agent[name] ??= {}
            if (typeof config.agent[name] !== "object") continue
            // Never clobber an explicit Markdown/JSON agent.model — the
            // plugin only fills gaps and applies operator overrides.
            config.agent[name].model = resolved
          }
          await log("info", `per-agent model overrides applied for ${Object.keys(parsed).length} agent(s)`)
        }
      }

       // ── Provider retry configuration ──────────────────────────────
      // NOTE: In OpenCode 1.18.12 the top-level config.provider map does NOT
      // exist at config-hook time — providers are synthesised at runtime from
      // auth.json + known base-URLs. Provider retry options must therefore be
      // injected in the chat.params hook (see below) where output.options is
      // the actual options object passed to the AI SDK language-model call.
      // We keep this section for documentation / forward-compatibility.

      // ── Optional provider model discovery ─────────────────────────
      // DARKMOON_DISCOVER_MODELS=1 → for every OpenAI-compatible provider
      // (including known built-ins resolved from the root model's provider
      // prefix), fetch <baseURL>/models and merge the ids into the
      // provider's model map. This is the "auto-populate" path. It is
      // opt-in because it adds startup latency and network calls.
      if (envFlag("DARKMOON_DISCOVER_MODELS")) {
        await discoverProviderModels(config, log)
      }
    },

    "chat.params": async (input, output) => {
      // Acquire a concurrency/rate-limit slot before the LLM request is sent.
      // The slot is held until the step ends (released in the event hook)
      // so that tool execution counts against the concurrency budget — this
      // is intentionally conservative to avoid bursting past provider limits.
      await log("debug", `chat.params: acquiring slot for session ${input.sessionID} (activeRequests before: ${activeRequests})`)
      const release = await acquireSlot(input.sessionID)
      await log("debug", `chat.params: slot acquired for session ${input.sessionID} (activeRequests after: ${activeRequests})`)

      // In 1.18.12, chat.params output carries only sampling parameters
      // (temperature, topP, topK, maxOutputTokens, options) — no `model` or
      // `messages`. This hook is the final provider-option boundary.
      //
      // ── Provider retry configuration ─────────────────────────
      // IMPORTANT: OpenCode 1.18.12 maps chat.params output.options into
      // the provider request body via `be.providerOptions()`. The nvidia
      // endpoint rejects unknown keys with "Bad Request: Validation:
      // Unsupported parameter(s)". retryDelay, maxRetryDelay,
      // respectRetryAfter, maxRetries are AI SDK CLIENT-SIDE config —
      // NOT valid provider API fields — and OpenCode disables the AI SDK
      // inner retry anyway (`y.retries ?? 0` → maxRetries:0 in streamText).
      //
      // OpenCode's outer SessionRetry policy (wl.policy) uses hardcoded
      // constants vs=2000, Ds=2, producing 2,4,8,16,32,64,128s backoff.
      // These are compiled into the binary and cannot be overridden from
      // the plugin. The plugin's own backoff (handle429) in acquireSlot
      // is the only lever — it adds additional wait time. To engage it,
      // the event hook detects 429s via session.status retry events.

      // Strip forbidden keys from the outbound options object.
      stripKeys(output.options, FORBIDDEN_PROVIDER_KEYS)
    },

    event: async ({ event }) => {
      const props = event?.properties
      if (!props) {
        return
      }

       switch (event.type) {
         case "session.status":
           // OpenCode's SessionRetry policy emits session.status events with
           // status.type === "retry" BEFORE each retry, including the attempt
           // number. In headless mode (opencode run) this is the ONLY signal
           // that a 429/stream errors — step.failed/step.ended don't fire.
           // We use it to (a) release the prior slot and (b) engage the
           // plugin's own exponential backoff so the intended interval
           // pattern (BACKOFF_BASE_MS * 2^n, capped) is respected.
           if (props.sessionID && props.status?.type === "retry") {
             const isRateLimited =
               props.status.action?.reason === "rate_limit" ||
               /429|rate.?limit|too many|retry/i.test(props.status.message || "")
             if (isRateLimited) {
               await log("warn", `retry detected for session ${props.sessionID} (attempt ${props.status.attempt ?? "?"}): ${props.status.message || props.status.action?.title || "rate-limited"}; engaging plugin backoff`)
               handle429()
             } else {
               await log("debug", `session.status: non-rate-limit retry for session ${props.sessionID} (attempt ${props.status.attempt ?? "?"}): ${props.status.message || "other"}`)
             }
           }
           return

         case "session.next.step.ended":
           releaseForSession(props.sessionID, "step.ended")
           handleSuccess()
           await log("debug", `step.ended: released slot for session ${props.sessionID} (activeRequests: ${activeRequests})`)
           return
         case "session.next.step.failed":
           releaseForSession(props.sessionID, "step.failed")
           if (is429Error(props.error)) {
             await log("warn", `429 detected for session ${props.sessionID}; backing off`)
             handle429()
           }
           return
         case "session.error":
           releaseForSession(props.sessionID, "session.error")
           if (is429Error(props.error)) {
             await log("warn", `429 detected for session ${props.sessionID}; backing off`)
             handle429()
           }
           return
         case "session.deleted":
           releaseForSession(props.sessionID, "session.deleted")
           return
         default:
           await log("debug", `event: unhandled event type: ${event.type}`)
       }
    },
  }
}

/**
 * Discover model ids for every OpenAI-compatible provider we can reach.
 * Providers already defined in config.provider with a baseURL are polled
 * directly. Known built-in providers (nvidia, openrouter, openai, …) that
 * only live in auth.json are resolved from KNOWN_BASE_URLS and the root
 * model's provider prefix, then a provider block is synthesized so the
 * fetched catalogue is visible to OpenCode. Never throws — failures are
 * logged at warn level and skipped.
 */
async function discoverProviderModels(config, log) {
  const rootProvider = providerOf(config?.model)
  config.provider ??= {}

  // Synthesize providers for known built-ins referenced by the root model.
  if (rootProvider && !config.provider[rootProvider] && KNOWN_BASE_URLS[rootProvider]) {
    config.provider[rootProvider] = {
      npm: "@ai-sdk/openai-compatible",
      name: rootProvider,
      options: {
        baseURL: KNOWN_BASE_URLS[rootProvider],
        // OpenCode resolves the actual key from auth.json; the discovery
        // request needs it in-band, so read the operational env fallback.
        apiKey: process.env.OPENROUTER_API_KEY ?? "",
      },
      models: {},
    }
    await log("info", `synthesized known provider ${rootProvider} for model discovery`)
  }

  for (const [id, provider] of Object.entries(config.provider)) {
    if (!provider || typeof provider !== "object") continue
    // Only OpenAI-compatible providers expose a baseURL we can poll.
    const baseURL = provider?.options?.baseURL
    if (typeof baseURL !== "string" || !baseURL.trim()) continue
    const apiKey = provider?.options?.apiKey ?? ""

    // Accept both ".../v1" and ".../" base URLs; normalize to "/models".
    let url
    try {
      url = new URL(baseURL.endsWith("/") ? `${baseURL}models` : `${baseURL}/models`)
    } catch {
      continue
    }
    if (url.pathname.endsWith("/models") === false) {
      // baseURL already had a deeper path — append /models at the end.
      url = new URL(`${url.pathname.replace(/\/$/, "")}/models`, url.origin)
    }

    const headers = { Accept: "application/json", "Content-Type": "application/json" }
    if (apiKey) headers.Authorization = `Bearer ${apiKey}`

    let resp
    try {
      resp = await fetch(url, { headers, signal: AbortSignal.timeout(10_000) })
    } catch (error) {
      await log("warn", `model discovery for ${id} failed: ${error?.message ?? error}`)
      continue
    }
    if (!resp.ok) {
      await log("warn", `model discovery for ${id} returned ${resp.status}`)
      continue
    }
    let body
    try {
      body = await resp.json()
    } catch {
      continue
    }
    const remoteIds = extractModelIds(body)
    if (!remoteIds.length) continue

    provider.models ??= {}
    let added = 0
    for (const remoteId of remoteIds) {
      if (typeof remoteId !== "string" || !remoteId.trim()) continue
      if (!provider.models[remoteId]) {
        provider.models[remoteId] = { name: remoteId }
        added += 1
      }
    }
    if (added > 0) {
      await log("info", `discovered ${added} new model(s) for provider ${id}`)
    }
  }
}

function extractModelIds(body) {
  // OpenAI-style: { data: [{ id: "model-name" }, ...] }
  if (body && Array.isArray(body.data)) {
    return body.data.map((entry) => entry?.id).filter((id) => typeof id === "string")
  }
  // Anthropic-style listed model objects sometimes use `name`/`model`.
  if (Array.isArray(body)) {
    return body.map((entry) => entry?.id ?? entry?.name).filter((id) => typeof id === "string")
  }
  return []
}
