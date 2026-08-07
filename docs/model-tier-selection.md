# Per-Subagent Model Tier Selection (Solution 5: Env Var Injection)

## Overview
The orchestrator (pentest) now selects a **MODEL_TIER** per sub-agent dispatch:
- **fast** — speed-optimized, minimal reasoning
- **balanced** — default, standard depth
- **deep** — maximum reasoning, exhaustive

## How It Works

### 1. Orchestrator Decision (pentest.md)
- Added **MODEL TIER SELECTION** heuristics section
- Chooses tier based on: target criticality, data sensitivity, attack surface complexity, time budget, previous findings, FOCUS flags, plane type
- Documents choice in dispatch prompt: `TIER_CHOICE=<tier> REASON=<...>`

### 2. Dispatch Prompt Structure
```
TARGET=<value> SCOPE=<value> OUTPUT_DIR=<value> VARS=<value> MODEL_TIER=<fast|balanced|deep>
```

### 3. Sub-Agent Adaptation (all 50 agents)
Each subagent now includes:
- **Behavior adaptation table** per tier (tool selection, reasoning depth, execution time targets)
- **Implementation steps**: parse tier, branch logic, export `DARKMOON_MODEL_TIER`
- **Model proxy routing** for true model switching

### 4. True Model Switching (Optional)
Deploy a model proxy (LiteLLM, OpenRouter, etc.) that reads `DARKMOON_MODEL_TIER`:

| Tier | Models |
|------|--------|
| fast | claude-3-5-haiku, gemini-flash, gpt-4o-mini |
| balanced | claude-3-5-sonnet, gemini-pro, gpt-4o |
| deep | claude-3-opus, o1, o3-mini |

**Proxy config example (LiteLLM):**
```yaml
# config.yaml
model_list:
  - model_name: darkmoon-fast
    litellm_params:
      model: anthropic/claude-3-5-haiku-20241022
  - model_name: darkmoon-balanced
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
  - model_name: darkmoon-deep
    litellm_params:
      model: anthropic/claude-3-opus-20240229

router_settings:
  routing_strategy: "tier-based"
  # Custom router reads DARKMOON_MODEL_TIER env var
```

**OpenCode config:**
```json
{
  "provider": {
    "darkmoon-proxy": {
      "npm": "@ai-sdk/openai-compatible",
      "options": { "baseURL": "http://model-proxy:4000/v1" }
    }
  }
}
```

## Validation
```bash
python3 conf/opencode-config.py validate --agents-dir conf/agents
# Passes silently
```

## Files Modified
- `conf/agents/pentest.md` — tier selection heuristics, dispatch prompt
- `conf/agents/*.md` (50 subagents) — MODEL_TIER handling section