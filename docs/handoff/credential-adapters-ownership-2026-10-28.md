# Fork credential adapters and ownership — 28 October 2026

This is an **independent fork policy**, not a recovered commercial DarkMoon
credential schema. The previous single-secret catalog only described eligible
consumer *uses*, not a vendor adapter or permission system.

## Version 1 structured model

A typed credential adds \`model_version: 1\`, \`adapter\`, \`scope\`, \`owner_id\`,
\`grants\`, and \`revoked\` to the existing encrypted, stable-ID vault record.
Required fields below are explicit; secret values are stored only as encrypted
\`sealed\` Fernet ciphertext and never returned to the API.

| Adapter | Required input | Allowed consumer |
| --- | --- | --- |
| \`username_password\` | \`username\`, \`secret\` | \`assessment_credential_id\` / local privacy tokenization |
| \`target_token\` | \`secret\` | \`assessment_token_id\` / local privacy tokenization |
| \`scm_token\` | \`secret\` | \`credential_id\` / read-only HTTPS source checkout and remediation |
| \`provider_api_key\` | \`secret\` | Provider profile, model metadata and OpenCode API-key connection |

All adapter names are fork-native. Unknown adapter IDs, model versions,
unrecognized structured fields, invalid owners, duplicate/unknown grants, and
missing required fields are rejected before writing storage. Provider labels
remain descriptive; they do **not** override the typed adapter. The launch
consumer's syntax restrictions (single-token username/target secret; valid
header value for API keys) are separately enforced when consumed. This model
does not provide AWS/OIDC/SCM OAuth exchanges, SSH private keys, arbitrary
multi-field cloud auth or any inferred vendor defaults.

## Explicit identity and scope policy

Administrator-only credential CRUD and catalog routes are retained. An admin
may inspect and manage masked metadata for any non-internal credential, but
this does **not** grant the administrator the right to *use* someone else's
private secret. For launches and selectable credential references, the
principal's current role and account existence are re-read from the store.

- **private:** only the active \`owner_id\` account may use the credential;
  owner must be an administrator or analyst.
- **shared:** the active owner or active explicitly named grants may use it;
  grants list only administrators and analysts. Empty grants mean owner only.
- **service:** only the local service/workspace-token identity may use it;
  owner is \`workspace-owner\`, with no user grants.
- **viewer:** no selections or credential use.
- **internal signing credentials:** excluded from list, detail, selection,
  updates and generic credential deletion, regardless of role.

The account used for \`/options\` gets only currently usable credentials.
Both REST assessment launch routes pass the authenticated principal into the
same capability and ownership check. Provider profile creation/application,
model discovery and OpenCode connection check the principal before touching
provider/network state. A scheduled execution uses the service identity and
may reference only compatible service or legacy workspace credentials.
Cached HTTPS checkout never bypasses credential authorization.

## Revocation and queued work

Deleting a credential, removing/demoting its owner or a grantee, or removing
a sharing grant immediately stops future eligibility. A queued assessment
rechecks its recorded request principal and all saved references before any
subprocess/privacy tokenizer invocation; stale references cause a generic
failure with no secret in the job error. New structured credentials may be
revoked through admin PATCH \`{"revoked": true}\`; this is irreversible for the
same credential ID. To restore access, create a replacement credential ID.
Changing owner/grants preserves ciphertext when the secret is omitted.
Already-running external subprocesses are not retroactively stopped by a
credential revocation; the boundary is rechecked before execution and use.

## Legacy compatibility and migration

Unversioned saved records are interpreted **without modifying ciphertext**
as \`legacy_v0\` workspace-shared credentials with historical capability
selection (username is required for target login). The compatibility path
preserves old IDs, custom provider labels, selectors and encrypted secrets.
Legacy records are never silently recast as a stronger typed adapter.

An administrator may explicitly convert an existing ID by PATCH/PUT with
\`adapter\` and \`model_version: 1\`. The migration does not require resupplying
the secret, preserves its existing encrypted blob, and starts from a private
scope with **no inherited wildcard grant**. \`owner_id\` and explicit grants
must be chosen. On disk, old records remain available to a restarted vault;
new records are versioned. Legacy broad eligibility is a compatibility risk
and should be migrated explicitly, rather than silently tightened or expanded.

## Verification and limits

The offline credential suite exercises cross-user visibility, all launch
paths, grant changes, stale queue references, revocation, restart, ciphertext
persistence, provider and scheduler boundaries, internal webhook exclusions,
adapter errors and redaction. All provider and launcher interactions are
mocked, never invoked externally. The dedicated GitHub workflow runs focused
credential/consumer tests and the full backend/community regression suite.
Record exact hosted results in the compatibility log after CI completes.

No claim of original commercial ownership parity, native consumer auth-wire
parity, secret reuse by third-party providers, or security of already-running
external processes is made.
