# SCM and workflow continuation — 1 November 2026

API06/07 now accept seven SCM token field forms through the existing encrypted
checkout adapter. The discovery catalog retains its five generic entries and
adds these seven input schemas. Its required-field/type/secrecy descriptions
were compared with live responses; full provider catalog equivalence remains open.

| Provider | Token plus supported metadata | Additional required fields |
|---|---|---|
| GitHub | endpoint_url, username | None |
| GitLab | endpoint_url | None |
| Gitea | endpoint_url, username | endpoint_url |
| Gogs | endpoint_url, username | endpoint_url |
| Bitbucket | endpoint_url, username | username |
| Azure DevOps | endpoint_url, project | endpoint_url |
| Generic Git over HTTPS | endpoint_url, username | None |

For example, an administrator can submit:

```json
{"name":"Owned source","provider":"gitea","fields":{"endpoint_url":"https://owned.example.invalid","username":"owned-user","token":"SYNTHETIC-EXAMPLE-ONLY"}}
```

The token remains encrypted and fully masked. New structured records default to
private ownership with only `source_checkout` eligibility. Rename, metadata-only
updates and token rotation preserve other fields and current policy. Legacy
records retain their scope until explicit migration. Revocation, administrator
CRUD controls and cross-owner use checks remain enforced.

Endpoint/project values are descriptive configuration. They do not implement
provider API access, choose the checkout destination or define an authorization
scope. Checkout uses its explicitly supplied repository URL and the saved
username/token through Git's temporary askpass helper. Endpoints must use HTTPS
without embedded credentials, query or fragment. No OAuth, SSH/cloud adapter,
PR capability or provider entitlement is inferred from these records.

`GET /api/v1/credentials?capability=scm` now aliases the existing checkout filter.
It does not add an internal `scm` or `pr` use capability; duplicate/unknown
filters remain rejected. The workspace credential form uses these structured
SCM inputs, honors required fields and clears secret input on provider changes.
Generic scalar-secret forms retain their existing contract.

Verification in this continuation:

- 354 fresh credential/catalog HTTP observations across both runtimes. Seven
  field schemas match names, types, required flags and secrecy. All seven live
  create/read/rename/rotate/delete flows preserve connection metadata. Fourteen
  populated `scm` filter observations returned the expected record.
- Actual authenticated Git HTTPS clones against an owned loopback Git backend
  verified exact HEAD/content and revoked cached-checkout denial for all seven
  forms. TLS verification stayed enabled. This is not vendor-host auth or
  publication acceptance. Reproduce with
  `PYTHONPATH=mcp:tests/community .venv/bin/python tests/community/scm_checkout_native.py`.
- 18 authenticated browser observations across both actual applications,
  including populated campaign/finding routes and mobile projects. Initial
  sign-in redirects were separated from authenticated navigation. The fork
  normalizes original paths to hashes; visual and complete interaction parity
  remain open.
- `tests/community/deep_link_browser.cjs` passed eight authenticated direct links,
  private SCM form creation, secret clearing, default evidence boundaries and
  viewer launch denial. The broader application browser regression passed.
- **549 backend tests and 375 subtests passed** after the API changes. The focused
  credential gate passed 53 tests and 62 subtests. The browser changes were then
  checked by both browser scripts.

[Actual webhook failure exhaustion and restart](webhook-durable-acceptance-2026-11-01.md)
also passed during this continuation. Those eight additional HTTP observations
and the earlier 1,935-observation run remain separately attributable.

Implementation commits are `fdb2c98`, `3dd1ccb`, `2ea6ce9` and `faf5f48`.
`d052380` records webhook acceptance and `d12d4c8` adds direct-link checks.
All commits are local. No push or hosted CI run was performed. The task map
keeps full acceptance open, including missing model/engine prerequisites,
other provider families, full consumer/state matrices and physical/licensed hosts.
