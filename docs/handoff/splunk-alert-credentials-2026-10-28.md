# Splunk alert credential and connection continuation

28 October 2026. Baseline: forwarder source reconciliation `7ac6cda` plus any
intervening `pro` commits. This separate scope changes the alert action, setup
page and their configuration. It leaves the forwarder/dashboard verification
worker and the Grafana/run/history/Jenkins workstreams untouched.

## Credential selection and rotation

The former action selected the first app credential if no named key matched.
It now selects only the configured opaque realm and canonical username
`darkmoon`. Legacy empty-realm settings permit canonical `darkmoon` first or,
only when absent, exactly one of `token`/`api_token`. Duplicate/missing/invalid
matching credentials fail; other realms/names are never fallback secrets.

Setup formerly saved a new URL before deleting/replacing its credential. The
new flow creates a cryptographically random `darkmoon-<32 hex>` realm for each
replacement, stores its encrypted token first, then saves base URL, TLS flag and
`credential_realm` together in the settings request. It never overwrites/deletes
the old generation. A reader using old settings therefore still selects the
old secret. A failed settings confirmation does not repoint an old generation.
Settings are read before allowing a save, saves are serialized in the page,
and changing the normalized base URL requires an explicitly supplied token.

This is a coherent reference-selection contract, not a transaction across all
Splunk REST resources. Stanza update atomicity, API acknowledgement loss and
concurrent native SDK behavior require later host verification. Old/orphaned
encrypted generations remain stored; retirement requires an explicit policy
that accounts for in-flight readers. No existing secret is deleted or migrated.
Direct administrator edits and older clients remain administrative actions,
not covered by the new setup page's save protocol.

## Authenticated transport and request contracts

- Splunk management destinations require HTTPS, no userinfo/query/fragment,
  valid ports and root service paths. Only the two fixed app settings/password
  reads are allowed. Session/token headers reject controls and oversized values.
- Remote and named management hosts always retain certificate verification.
  The existing self-signed exception applies only to literal loopback HTTPS
  addresses, not arbitrary `server_uri` names or plaintext HTTP.
- Management responses are capped at 8 MiB; alert input at 1 MiB. Errors do not
  echo raw exception details, response bodies, session keys or passwords.
- The action supports only `retest`/`campaign`, `non-destructive`/`authorized`
  and explicit boolean values. Invalid choices are rejected, never silently
  converted to another launch. Profile requests still require the allowlist's
  existing opt-in and do not establish what a real assessment will execute.
- Host normalization handles exact canonical IPv4/IPv6/DNS hosts and rejects
  credential-bearing/invalid locators. Invalid/duplicate allowlist rows invalidate
  the whole allowlist rather than returning partially read permissions.
- Quota files/locks must be regular single-link files. State reads are bounded,
  timestamp/count/config types are checked, and failures deny admission. Existing
  dry-run quota consumption is preserved. POSIX/Windows locking and atomic writes
  remain; this increment does not prove native multi-process behavior.
- Retests still resolve one authenticated saved target. Launch responses need
  valid identities, consistent retest/target aliases and no failed terminal state.
  An accepted reference never establishes completed assessment or a deployed fix.

## Verification boundary

Source/diff review, Python AST, JavaScript syntax, XML/stanza and JSON parsing
only. No tests, native host, provider, launch, notification or deployment ran.

The post-commit worker should cover exact realm/name selection, legacy ambiguity,
failed/concurrent setup saves and in-flight old readers, local-vs-remote TLS
contexts, invalid management URIs/paths/headers, bounded inputs/responses, generic
errors, strict action/scope booleans, IPv6/duplicate allowlists, quota file types
and future/oversized state, exact target resolution and launch identity failures.
Adapt old loopback mocks to the saved-target contract instead of weakening it.
Native SDK storage/passwords realm behavior and settings update semantics remain
explicit host acceptance requirements. Use synthetic secrets, mocked transport
and owned loopback fixtures; do not launch a real assessment or send external
messages. Commit focused verification/corrections with actual evidence.
