# Actual Pro 52-route API crosswalk — 2026-10-27

The actual original commercial image at `sha256:48248382877ec1fd7362d2268656956268129d5ea565befab3a24436ea2fc907` has **52 FastAPI decorated method/path declarations**, including trailing-slash aliases. Compared statically to `newrecycle/Dark-Moon:pro` at `84c9d360df5eefc059ed26eae4d6a1fc97c4603e` in `mcp/community/api.py` and `server.py`. See [image baseline](actual-pro-image-baseline-2026-10-27.md).

**2026-10-27 follow-up:** [Detailed static audit and machine-readable discrepancy list](../pro-audit/README.md) records **13** API compatibility issues: 12 method/path differences in this table plus `GET /credentials?capability=...` filtering. These are *not* 13 missing methods. No vendor HTTP runtime comparison has been executed.

`present` means a matching method/path is handled **only**. No equality of authorization, bodies, status, errors, response envelopes, pagination, ordering, stream format, or data schemas has been established. `different` and `missing` are *exact route* discrepancies, not necessarily missing user-facing capabilities. Statuses are static inspection results, not tests.

| # | Original method | Original exact path | Fork route inspection |
| ---: | --- | --- | --- |
| 1 | `GET` | `/api/v1/projects` | present |
| 2 | `GET` | `/api/v1/projects/{project_id}` | present |
| 3 | `GET` | `/api/v1/targets` | present |
| 4 | `GET` | `/api/v1/targets/{target_id}` | present |
| 5 | `GET` | `/api/v1/targets/{target_id}/evolution` | different:/targets/{id}/analytics |
| 6 | `GET` | `/api/v1/campaigns` | present |
| 7 | `GET` | `/api/v1/campaigns/{campaign_id}` | present |
| 8 | `GET` | `/api/v1/campaigns/{campaign_id}/infrastructure` | present |
| 9 | `GET` | `/api/v1/campaigns/{campaign_id}/report` | present |
| 10 | `GET` | `/api/v1/vulnerabilities` | present |
| 11 | `GET` | `/api/v1/vulnerabilities/history` | missing:fork treats history as vulnerability ID |
| 12 | `GET` | `/api/v1/vulnerabilities/{vuln_id}/evidence-meta` | present |
| 13 | `GET` | `/api/v1/vulnerabilities/{vuln_id}` | present |
| 14 | `GET` | `/api/v1/dashboard/overview` | present |
| 15 | `POST` | `/api/v1/run/campaign` | present |
| 16 | `GET` | `/api/v1/run/{run_id}/stream` | present |
| 17 | `DELETE` | `/api/v1/run/{run_id}/stop` | different:fork POST |
| 18 | `GET` | `/api/v1/run/active` | missing:fork treats active as run ID |
| 19 | `GET` | `/api/v1/run/logs` | missing:fork treats logs as run ID |
| 20 | `GET` | `/api/v1/run/logs/{run_id}` | present |
| 21 | `GET` | `/api/v1/scheduler/` | present:trailing slash normalized |
| 22 | `POST` | `/api/v1/scheduler/` | present:trailing slash normalized |
| 23 | `GET` | `/api/v1/scheduler/{schedule_id}` | present |
| 24 | `PUT` | `/api/v1/scheduler/{schedule_id}` | different:fork PATCH |
| 25 | `DELETE` | `/api/v1/scheduler/{schedule_id}` | present |
| 26 | `POST` | `/api/v1/auth/login` | present |
| 27 | `POST` | `/api/v1/auth/change-password` | different:fork /auth/password |
| 28 | `GET` | `/api/v1/auth/me` | present |
| 29 | `POST` | `/api/v1/auth/logout` | present |
| 30 | `GET` | `/api/v1/credentials/providers` | missing |
| 31 | `GET` | `/api/v1/credentials` | present |
| 32 | `POST` | `/api/v1/credentials` | present |
| 33 | `GET` | `/api/v1/credentials/{cred_id}` | missing |
| 34 | `PUT` | `/api/v1/credentials/{cred_id}` | present |
| 35 | `DELETE` | `/api/v1/credentials/{cred_id}` | present |
| 36 | `GET` | `/api/v1/pull-requests/finding/{vuln_id}` | missing |
| 37 | `GET` | `/api/v1/pull-requests/{pr_id}` | present |
| 38 | `GET` | `/api/v1/pull-requests` | present |
| 39 | `GET` | `/api/v1/system/update-status` | present |
| 40 | `GET` | `/api/v1/system/info` | present |
| 41 | `POST` | `/api/v1/webhooks` | present |
| 42 | `POST` | `/api/v1/webhooks/` | present:trailing slash normalized |
| 43 | `GET` | `/api/v1/webhooks` | present |
| 44 | `GET` | `/api/v1/webhooks/` | present:trailing slash normalized |
| 45 | `GET` | `/api/v1/webhooks/{webhook_id}` | missing |
| 46 | `DELETE` | `/api/v1/webhooks/{webhook_id}` | present |
| 47 | `POST` | `/api/v1/webhooks/{webhook_id}/test` | missing |
| 48 | `GET` | `/api/v1/events/stream` | present:implemented in HTTP server |
| 49 | `POST` | `/api/v1/retest` | present |
| 50 | `POST` | `/api/v1/retest/` | present:trailing slash normalized |
| 51 | `GET` | `/api/v1/retest/{retest_id}` | present |
| 52 | `GET` | `/api/v1/metrics/timeseries` | present |

**Summary:** 40 method/path declarations handled, 4 exact-path/method differences, and 8 exact handlers not found. Slash aliases are counted separately. The fork also intentionally exposes additional routes (OIDC, workspace setup, providers, source-files, report security, remediation, metrics views, schedule previews, posture, and update/integrity controls) that are *fork extensions*, not original Pro contract requirements.

## Contract closure standard

For each row, record a sanitized authentic vendor response or original packaged type/test fixture; verify request schema, success/error bodies, auth, method, status, ordering, sensitive-field policy and client compatibility; add fork tests before marking **wire-verified**. Prefer secure aliases and adapters. Never remove existing fork endpoints or lower security solely to match the vendor's historical behavior.

Related: [systematic parity backlog](actual-pro-parity-ledger-2026-10-27.md) · [fork feature matrix](../pro-feature-matrix.md).
