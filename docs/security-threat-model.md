# 🔐 Darkmoon — Threat Model & Security Design

This document describes **Darkmoon's own threat model**.

Objective:
- understand the attack surfaces,
- justify the architecture choices,
- demonstrate that Darkmoon is **designed defensively**, despite its offensive purpose.

Target audience:
- CISOs
- auditors
- security architects
- demanding clients

---

## 1. Foundational Principle

Darkmoon is built on a non-negotiable principle:

> **The AI must never be able to freely execute code.**

Everything is built around this constraint.

---

## 2. Assets to Protect

| Asset | Description |
|-----|------------|
| User host | Operator's system |
| LLM API Keys | Model access |
| Toolbox | Pentest tools |
| DarkMoon Agent Configuration | Agents, prompts |
| Scan Results | Sensitive data |

---

## 3. Global Threat Model

Threats considered:

- prompt injection
- arbitrary command execution
- secret leakage
- privilege escalation
- Docker breakout
- LLM abuse

---

## 4. Security Boundaries (Defense in Depth)

### 4.1 AI ↔ Execution

| Element | Measure |
|------|-------|
| Agents | Auditable Markdown |
| AI | No direct commands |
| MCP | Sole execution point |

👉 **Most important barrier**.

---

### 4.2 MCP ↔ Toolbox

| Element | Measure |
|------|-------|
| Execution | Isolated Docker |
| Tools | Whitelist |
| Timeouts | Controlled |
| Parsing | Structured |

---

### 4.3 Toolbox ↔ Host

| Element | Measure |
|------|-------|
| Isolation | Docker |
| Volumes | Controlled |
| Network | Limited |
| Permissions | Root controlled |

### 4.4 Data ↔ LLM (Privacy Gateway — v1.2.0)

**Data minimization** boundary between the model and execution (`mcp/src/privacy/`). The LLM **never** receives real sensitive values (IP, hostnames, domains, URLs, emails, credentials, internal paths): it only manipulates **deterministic placeholders** (`IP_PRIVATE_001`, `HOST_INTERNAL_001`…). Real values are re-injected **locally, just before tool execution**, then re-masked in any output before returning to the model → no sensitive data leaves the perimeter toward the model provider.

| Element | Measure |
|------|-------|
| Tokenization | Per-session deterministic (`PrivacyVault`) |
| Mapping | Encrypted (Fernet) + HMAC dedup; **no raw value** retained/logged; TTL |
| Rehydration | *Context-aware* (`CommandGateway`), never a global replacement |
| Exfiltration | Blocked: placeholder in query URL / literal external host / echo-print / outgoing body / `/dev/tcp` / nc-telnet outside target |
| Secrets | `CRED` never restored in an executed command |
| Config | `DARKMOON_PRIVACY` (on by default) · `DARKMOON_PRIVACY_CATEGORIES` |

Open-source core; enterprise hardening (vault sealed by runtime guard, audit trail, compliance mention in signed report) in Pro edition.

---

## 5. Secret Management

- API keys **never** hardcoded
- `.env` outside image
- `auth.json` generated dynamically
- Volumes persisted on user side

---

## 6. Prompt Injection & LLM Safety

Measures:

- strict agents (no exposed reasoning),
- mandatory MCP,
- no self-modification of rules,
- no uncontrolled dynamic user input.

👉 An injection does **not** allow code execution.

---

## 7. Accepted Risks

| Risk | Justification |
|-----|---------------|
| Offensive tools | Core product |
| Root in toolbox | Necessary |
| Docker socket | Controlled |

👉 These risks are **known, controlled, and documented**.

---

## 8. What Darkmoon Does NOT Do

- no self-propagation,
- no out-of-scope persistence,
- no destructive exploitation,
- no out-of-scope execution.

---

## 9. Security Conclusion

Darkmoon is:
- offensive by purpose,
- defensive by design,
- controlled by architecture.

👉 **Security is a foundational constraint, not an add-on.**
