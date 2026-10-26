# Threat model (§4)

The plugin runs an offensive security tool from CI. Its outputs must never become a new
leak vector, and its gate must never be silently defeated.

## Assets

- **Secrets**: the Darkmoon Pro token / license (Jenkins credentials).
- **Findings**: vulnerability data. Two tiers — the redaction-safe surface (safe to show)
  and the un-redacted report (rehydrated real values, hosts, extracted data).

## Controls

| Threat | Control |
|--------|---------|
| Secret in `ps` / process table | Secrets passed via **environment only**, never argv. |
| Secret in the build console / shared log | The plugin prints only its own redaction-safe lines; the CLI's stdout/stderr go to an internal log file, and the CLI itself scrubs secrets. Verified: 0 secret occurrences in a real run. |
| Secret in an archived artifact | Artifacts are the redacted report, the SARIF (built from redaction-safe findings), and the CLI log (scrubbed). |
| Evidence / raw request-response leaking to the UI | SARIF is built only from normalized findings whose `evidence` is `null`; a unit test asserts no `raw_request` / `raw_response` / JWT fragments appear. |
| Un-redacted report exposure | Fetched only when `includeFullReport: true` (off by default), archived as an access-controlled Jenkins artifact with a console warning. |
| Gate silently defeated by an unknown severity | Unknown severities normalize to `info`, never dropped; the gate is computed from the summary counts, independent of the CLI exit code. |
| Gate skipped because the build already failed | The plugin's fail policy runs last; findings are published via `recordIssues(enabledForFailure: true, …)` so warnings-ng still records them on a failed build. |
| Credential exfiltration by a malicious job config | Credentials resolved through the standard Credentials API with per-job permission checks (`Item.EXTENDED_READ` / `USE_ITEM`) in the `doFillCredentialsIdItems` descriptor. |
| OSS campaign mis-attribution | OSS runs share a data dir; the CLI correlates by snapshot-diff + mtime and warns on collision. Operators run one container / compose-project per job. |
| Report artifact contains rehydrated host in the filename | The CLI slugifies the report filename; the plugin writes to a fixed workspace path. |

## Residual risks (documented, not mitigated in-plugin)

- Anyone with `Artifact/Read` on the job can read the archived (redacted) report and SARIF.
  With `includeFullReport`, they can read rehydrated values — restrict accordingly.
- The plugin trusts `darkmoon-ci`'s redaction. A compromised CLI on the agent could leak;
  pin and verify the CLI supply chain.
