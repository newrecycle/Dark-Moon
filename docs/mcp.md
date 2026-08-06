# 🔌 Darkmoon — MCP (Model Context Protocol)

This document describes **the Darkmoon MCP server**, its role, how it works,
and why it is **central** to the architecture.

Target audience:
- architects
- backend developers
- AI engineers
- security experts

---

## 1. What is MCP in Darkmoon?

MCP (Model Context Protocol) is **the security and execution boundary**
between:

- the AI (OpenCode + agents),
- the real pentest tools.

👉 The AI **never directly** touches the tools.
👉 Everything goes through the MCP.

---

## 2. Role of the Darkmoon MCP

The MCP serves to:

- expose **controlled functions** to the AI,
- execute commands in the Docker toolbox,
- provide **ready-to-use business workflows**,
- prevent any unauthorized action.

---

## 3. Technical Implementation

The Darkmoon MCP is implemented with **FastMCP**.

Location:

```
mcp/src/server.py
```

It exposes:
- simple tools,
- advanced tools,
- dynamic workflows.

---

## 4. Exposed MCP Tools

### 4.1 Health & Diagnostics

- `health_check`
- `check_tool`
- `diagnose`

👉 Allows the AI to check the system state **before attacking**.

---

### 4.2 Generic Execution

- `execute_command`
- `list_allowed_tools`

Characteristics:
- strict whitelist,
- protection against dangerous commands,
- controlled timeouts.

---

### 4.3 Dynamic Workflows

- `list_workflows`
- `run_workflow`

Workflows are discovered **automatically** at runtime.

---

## 5. Interaction with Docker

The MCP uses:
- the local Docker API,
- a dedicated client (`DarkmoonDockerClient`),
- a fixed container name (`darkmoon`).

👉 The MCP:
- does not depend on the user shell,
- does not depend on the host,
- remains isolated.

---

## 6. Example of AI-side Usage

In the OpenCode chat:

> "run a vulnerability scan on example.com"

The AI:
1. identifies the need,
2. chooses the workflow,
3. calls `run_workflow`,
4. interprets the results,
5. chains if necessary.

---

## 7. Security by Design

The MCP enforces:
- no free execution,
- no direct Docker access,
- no uncontrolled mount,
- no implicit elevation.

👉 This is the **key to Darkmoon's overall security**.

---

## 8. Extending the MCP

To add a functionality:

1. create a new workflow,
2. or add an MCP tool,
3. restart the MCP server.

No agent-side modification required.

---

## 9. Why This Design is Robust

- AI / execution separation,
- total auditability,
- controlled extensibility,
- massive risk reduction.

---

## 10. Summary

The MCP is:
- the **execution heart** of Darkmoon,
- the **security barrier**,
- the main extension point.

---

➡️ To understand the real tools:
see `docs/toolbox.md`
