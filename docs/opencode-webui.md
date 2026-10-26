# OpenCode providers and WebUI choices

The WebUI reads the same `darkmoon-settings/opencode.json` and `auth.json`
that the existing Compose stack mounts into OpenCode. It reads `.opencode.env`
without executing it. Override the shared location with `DARKMOON_OPENCODE_DIR`
when OpenCode is hosted elsewhere. `DARKMOON_DATA_DIR` remains the default.

Settings shows the configured default model, native login types, catalog models
and saved profiles. Model IDs come from the actual shared config or native
provider API; preset provider names do not imply an installed model or account.
Choose Custom provider/model for an endpoint not listed in that catalog.

- **Sync from OpenCode** imports API keys into the encrypted workspace vault
  under stable references; repeated sync does not duplicate entries. Native
  OAuth refresh/access tokens stay in OpenCode and are never returned to the UI.
- **Connect provider** uses a saved credential or a new API key. When the native
  bridge is available, its advertised OAuth methods appear alongside API keys.
  Provider authorization and callback processing run through OpenCode itself.
- **Apply profile** preserves unrelated environment variables, comments, config
  sections, MCP wiring and other provider logins. It writes private atomic files
  and updates the native server when connected. Provider-prefixed model names
  are normalized to avoid duplicate prefixes. Existing literal local API keys
  are removed from the selected provider config in favor of shared auth state.
- **Disconnect** removes the selected native login and matching installer key,
  preserving other providers. It does not revoke the API key at its issuer or
  delete a separately saved vault credential. Without the bridge, restart is
  required before a running OpenCode process drops its cached login.

New API keys and OAuth completion also update matching installer settings so a
restart cannot silently restore a stale key. The startup script merges the
selected API login instead of replacing/deleting `auth.json`, and accepts a
configured saved API/OAuth login via `OPENCODE_USE_SAVED_AUTH=true`.

## Native bridge

File-based sync works without a server. Native OAuth and live model changes need
an authenticated OpenCode HTTP server reachable by the dashboard. The adapter
uses the documented `/provider`, `/provider/auth`, `/config`, `/auth/{id}` and
provider OAuth routes. It targets the shared-file OpenCode generation built by
this repository. A server version with a different API/storage contract requires
compatibility validation; this is not an opaque proxy to arbitrary endpoints.

For the existing Compose stack, the optional overlay builds this branch's
OpenCode image (including the login-preserving startup script), runs its native
server as the service process, and publishes port 4096 on **host loopback only**.
The existing persistent MCP and shared volumes are retained by Compose merging.
Choose a strong password and export the same value for the dashboard and server:

```bash
export OPENCODE_SERVER_PASSWORD='REPLACE_WITH_A_LONG_RANDOM_PASSWORD'
export OPENCODE_SERVER_USERNAME=opencode
export DARKMOON_OPENCODE_URL=http://127.0.0.1:4096

docker compose -f docker-compose.yml -f docker-compose.community-bridge.yml up -d --build opencode
DARKMOON_PYTHON="$PWD/.venv/bin/python" ./community.sh
```

Building/recreating the service is an explicit deployment step and can interrupt
active agent sessions. It was not performed during validation: Docker was not
available in the coding environment. For an existing native server, omit the
Compose overlay and configure its URL/password directly. Remote bridges require
HTTPS. Redirects and credentials embedded in the URL are rejected. The dashboard
keeps Basic authentication server-side; it is never sent to browser JavaScript.
A native request failure is shown as a warning and restart-required state; it is
not reported as successful live activation. Native authentication never replaces
the dashboard's own password/OIDC/recovery-token authentication.

## Populated forms

Saved targets fill target addresses and suggested assessment names. Focus,
exclusions, severity, additional/excluded saved targets, report formats, saved
target/SCM credentials, webhook events, retest campaigns/findings and provider/
model choices use selectors. Custom targets, scope rules and custom endpoint/
model IDs retain editable fields. No secret is auto-filled back into an input.
Empty focus/severity selections mean the runtime default; select several using
the platform's standard multiple-select gesture.

Remediation suggests previously used/configured local repositories and lists
tracked source paths on demand. Only filenames are returned. Custom relative
paths and structured edits remain available. To suggest local repositories before
any previous runs, set `DARKMOON_SOURCE_REPOSITORIES` to an OS-path-separator list
(`:` on Linux/WSL). Remote clone URLs remain available in the assessment source
field but are not auto-selected as an existing local remediation repository.

Viewers see read-only controls and their own account settings; administrator
provider/credential/webhook controls are hidden and still protected by the API.
Password changes are offered only for password accounts, not recovery-token or
OIDC identities.

## Verification

The community suite now has **99 passing tests**, including shared-state sync,
API/OAuth login preservation, key rotation, saved OAuth startup, safe environment
application, invalid JSON handling, metadata redaction, native route contracts,
permission checks and restart/failure reporting. **117 upstream MCP tests** and
the repository's **no-regression gate** pass.

Chromium acceptance covers every dashboard route, model selection/live apply,
OAuth start/finish, key connect/disconnect, saved target and credential choices,
source-file selection, account creation/login/password rotation, viewer controls,
project analytics, webhook/retest lifecycle, schedules, queue/logical completion,
local remediation/patches, report preview and Markdown/JSON/PDF/signed-encrypted
PDF downloads, plus desktop/mobile layout and malicious-looking literal evidence.
Screenshots were visually reviewed. Native calls use a real loopback HTTP fixture
with Basic auth; target assessments, model calls and webhook delivery are fake or
disabled. The protected PDF is actually encrypted and signed.

A real Docker boot, real provider/subscription OAuth, live inference, production
OIDC, external deliveries, and headset VR still require the operator's deployed
environment. Those are not asserted as tested or equivalent to private Pro code.
