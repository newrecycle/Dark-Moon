const MODELS_URL = "https://inference-api.nousresearch.com/v1/models"
const MODALITIES = new Set(["text", "audio", "image", "video", "pdf"])
const EFFORT_ORDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]

function finite(value) {
  if (value === null || value === undefined || value === "") return undefined
  const number = Number(value)
  return Number.isFinite(number) ? number : undefined
}

function modalities(values) {
  return Array.isArray(values) ? values.filter((value) => MODALITIES.has(value)) : []
}

function variants(reasoning) {
  if (!reasoning || !Array.isArray(reasoning.supported_efforts)) return undefined
  const result = Object.fromEntries(
    reasoning.supported_efforts.map((effort) => [effort, { reasoningEffort: effort }]),
  )
  if (result.none) result.direct = { reasoningEffort: "none" }
  return Object.keys(result).length ? result : undefined
}

function model(entry) {
  const providerContext = finite(entry.top_provider?.context_length)
  const context = providerContext ?? finite(entry.context_length) ?? 65536
  const output = Math.min(
    context,
    finite(entry.top_provider?.max_completion_tokens) ?? 65536,
  )
  const input = Math.max(1, context - output)
  const supported = new Set(entry.supported_parameters ?? [])
  const reasoning = entry.reasoning
  const defaultEffort = reasoning?.default_effort
  const inputModalities = modalities(entry.architecture?.input_modalities)
  const outputModalities = modalities(entry.architecture?.output_modalities)
  const promptCost = finite(entry.pricing?.prompt)
  const completionCost = finite(entry.pricing?.completion)
  const cacheReadCost = finite(entry.pricing?.input_cache_read)

  return {
    name: entry.name || entry.id,
    family: String(entry.id).split("/")[0],
    release_date: entry.created ? new Date(entry.created * 1000).toISOString().slice(0, 10) : undefined,
    attachment: inputModalities.some((item) => item !== "text"),
    reasoning: Boolean(reasoning),
    temperature: supported.has("temperature"),
    tool_call: supported.has("tools"),
    interleaved: reasoning ? { field: "reasoning" } : undefined,
    cost:
      promptCost !== undefined && completionCost !== undefined
        ? {
            input: promptCost * 1_000_000,
            output: completionCost * 1_000_000,
            ...(cacheReadCost !== undefined ? { cache_read: cacheReadCost * 1_000_000 } : {}),
          }
        : undefined,
    limit: { context, input, output },
    modalities: { input: inputModalities, output: outputModalities },
    status: "active",
    options: defaultEffort ? { reasoningEffort: defaultEffort } : undefined,
    variants: variants(reasoning),
  }
}

export default async function NousModelsPlugin() {
  return {
    async config(config) {
      const provider = config.provider?.nous
      if (!provider) return

      try {
        const response = await fetch(MODELS_URL, {
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(10000),
        })
        if (!response.ok) return
        const payload = await response.json()
        if (!Array.isArray(payload?.data)) return

        const existing = provider.models ?? {}
        provider.models = Object.fromEntries(
          payload.data
            .filter((entry) => entry && typeof entry.id === "string")
            .map((entry) => {
              const discovered = model(entry)
              const configured = existing[entry.id] ?? {}
              return [
                entry.id,
                {
                  ...discovered,
                  ...configured,
                  options: { ...(discovered.options ?? {}), ...(configured.options ?? {}) },
                  variants: { ...(discovered.variants ?? {}), ...(configured.variants ?? {}) },
                },
              ]
            }),
        )

        // The small model handles frequent internal work, so keep it at the
        // strongest effort Nous currently advertises rather than freezing its
        // default at the value that happened to exist when this config was made.
        const prefix = "nous/"
        const smallID = config.small_model?.startsWith(prefix) ? config.small_model.slice(prefix.length) : undefined
        const small = smallID ? provider.models[smallID] : undefined
        if (small) {
          const efforts = Object.values(small.variants ?? {})
            .map((variant) => variant?.reasoningEffort)
            .filter((effort) => EFFORT_ORDER.includes(effort))
          const highest = efforts.sort(
            (left, right) => EFFORT_ORDER.indexOf(right) - EFFORT_ORDER.indexOf(left),
          )[0]
          if (highest) small.options = { ...(small.options ?? {}), reasoningEffort: highest }
        }
      } catch {
        // Keep the statically configured fallback models when Nous is offline.
      }
    },
  }
}
