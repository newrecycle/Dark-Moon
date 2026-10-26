# Darkmoon for VS Code

> **📦 Marketplace status:** Live on the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Darkmoon.darkmoon-vscode).


## ⭐ Darkmoon ecosystem

Darkmoon is open-source — **a star really helps us grow.** [![Star the Darkmoon core](https://img.shields.io/github/stars/ASCIT31/Dark-Moon?style=social&label=Star%20Darkmoon)](https://github.com/ASCIT31/Dark-Moon)

🌐 **Website:** [dark-moon.org](https://dark-moon.org) · 📚 **Docs:** [docs.dark-moon.org](https://docs.dark-moon.org) · ⭐ **Star the core:** [github.com/ASCIT31/Dark-Moon](https://github.com/ASCIT31/Dark-Moon)

**Install the integrations, right where you work:**

| Platform | Get it |
|---|---|
| VS Code | [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Darkmoon.darkmoon-vscode) |
| JetBrains | [JetBrains Marketplace](https://plugins.jetbrains.com/plugin/34497-darkmoon) |
| GitHub Actions | [GitHub Marketplace](https://github.com/marketplace/actions/darkmoon-pentest) |
| GitLab CI/CD | [CI/CD Catalog](https://gitlab.com/explore/catalog/Dark-Moon-X/darkmoon-scan) |
| Jenkins | [Download the .hpi](https://github.com/ASCIT31/darkmoon-jenkins/releases) |
| Client & CLI | [npm: @darkmoon_ai/client](https://www.npmjs.com/package/@darkmoon_ai/client) |


## Screenshots

Rendered from the bundled synthetic **Demo Shop** fixtures (`demo-shop.local`) with the extension's own webview HTML/CSS/JS and its real redaction logic — no mock data.

**Vulnerabilities** — filter by severity/status, free-text search and column sort:

![Vulnerabilities table](https://raw.githubusercontent.com/ASCIT31/darkmoon-vscode/master/docs/screenshots/vscode-vulnerabilities.png)

**Finding detail (redacted by default)** — description, evidence and remediation with sensitive values masked until you explicitly reveal them on a local workbench:

![Finding detail, redacted](https://raw.githubusercontent.com/ASCIT31/darkmoon-vscode/master/docs/screenshots/vscode-finding-redacted.png)

**Finding detail (revealed)** — after the local, confirmed *Reveal real values* action:

![Finding detail, revealed](https://raw.githubusercontent.com/ASCIT31/darkmoon-vscode/master/docs/screenshots/vscode-finding-revealed.png)

## Install

- **Marketplace:** search for **Darkmoon** in the Extensions view and click Install.
- **From VSIX:** `code --install-extension darkmoon-vscode-0.1.0.vsix` (or Extensions view → `...` → *Install from VSIX…*).

## Connect

Open Settings and pick your edition with `darkmoon.mode`:

- **OSS** — set `darkmoon.dataDir` to your Darkmoon settings directory (the tree that holds `campaigns/` and `vulnerabilities/`). Reports are read from `<dataDir>/reports` by default; set `darkmoon.cliPath` to `darkmoon.sh` if you want to launch campaigns from the editor.
- **Pro** — set `darkmoon.baseUrl` to your Pro API (`https://…`, with or without `/api/v1`) and store your JWT via **Darkmoon: Set Pro API Token**.

Then run **Darkmoon: Refresh**. Want a no-backend preview first? Toggle `darkmoon.dev.useFixtures` to load the bundled synthetic *Demo Shop* sample data.

## Use

1. **View findings** — open the **Campaigns** tree (status, overall risk, severity breakdown, agents) and the **Vulnerabilities** table (filter by severity/status, search, sort).
2. **Open a finding** — click a row to see description, redacted evidence and remediation.
3. **Open a report** — **Darkmoon: Open Report** shows the redacted Markdown; **Darkmoon: Open Full Report** reveals real values (local, non-remote workbench only, with a confirmation).

> **CI pass/fail is not decided here.** This extension is browse-only; the findings-based fail policy (`--fail-on`) lives in the `darkmoon-ci` CLI and the CI/CD integrations (GitHub Actions, GitLab, Jenkins).

## Features

- **Campaigns** — a tree of your campaigns with status, overall risk, severity breakdown, dispatched agents and their findings.
- **Vulnerabilities** — a rich table with **filter** (severity, status), **search** and **column sort** (severity, title/type, target/component, status, campaign).
- **Finding detail** — description, evidence (commands, request/response, logs) and remediation.
- **Reports** — Markdown preview of assessment reports.
- **Launch campaign** — start an assessment against a target you are authorised to test.

## Privacy & safety

- Reports and findings are shown **redacted by default**. Real infrastructure values (IPs, hosts, credentials, tokens) are revealed only on an **explicit, local** action, and never over a remote/untrusted workbench.
- Tokens and license keys are stored in the OS secret store (VS Code **SecretStorage**), never in `settings.json` and never logged.
- Webviews run under a strict Content-Security-Policy with no remote content.

## Capability boundary (OSS vs Pro)

Some capabilities are Pro-only and are hidden/disabled automatically on OSS (e.g. live status of running campaigns, the hosted web dashboard). This extension does **not** include an infrastructure graph or any automated pull-request feature.

## Configuration

| Setting | Description |
| --- | --- |
| `darkmoon.mode` | `auto` \| `oss` \| `pro` |
| `darkmoon.baseUrl` | Pro REST base URL (use `https`) |
| `darkmoon.dataDir` | OSS artifacts directory (reports are read from `<dataDir>/reports`) |
| `darkmoon.cliPath` | OSS CLI entrypoint (for launching campaigns) |
| `darkmoon.reports.redactByDefault` | Redact sensitive values until revealed |
| `darkmoon.dev.useFixtures` | Demo mode with bundled sample data |

Set secrets via the commands **Darkmoon: Set Pro API Token** and **Darkmoon: Set License Key**.

## Development

```bash
npm install
npm run compile        # bundle to dist/ (esbuild)
npm test               # headless integration + unit tests (@vscode/test-cli)
npx @vscode/vsce package   # produce the .vsix
```

## License

MIT © 2026 ASC-IT (SARL) / Darkmoon. See [LICENSE](LICENSE).

## 🎥 Video tutorial

[![Watch the Darkmoon + VS Code tutorial on YouTube](https://img.youtube.com/vi/GY7YOnYpteQ/maxresdefault.jpg)](https://youtu.be/GY7YOnYpteQ)

▶ **[Watch the full Darkmoon + VS Code tutorial on YouTube](https://youtu.be/GY7YOnYpteQ)** — real setup, end to end.

## Darkmoon ecosystem

Darkmoon is an open-source, AI-powered penetration testing platform. It runs a full autonomous assessment and this integration brings the results into your VS Code workflow.

- ⭐ **Flagship (star it):** https://github.com/ASCIT31/Dark-Moon
- 📚 **Docs:** https://docs.dark-moon.org
- 🌐 **Website:** https://dark-moon.org
- 🔗 **Related integrations:** [JetBrains](https://github.com/ASCIT31/darkmoon-jetbrains) · [SDK / CLI](https://github.com/ASCIT31/darkmoon-client) 
