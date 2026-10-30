# Original page surface mapping and acceptance

Read current-pro-status.md and commercial-api-parity.md first. These are fork
routes with independently implemented views, not recovered Angular source.
All direct GET paths serve only the public shell. API access still requires a
session. IDs are validated; query strings may not carry reveal grants or tokens.

| Original page | Fork direct path / hash | Behavior |
|---|---|---|
| Root/dashboard | / / #overview | Current posture; authenticated data |
| Login | /login / #login | Login modal when locked; never an implicit logout |
| Change password | /change-password / #change-password | Account-appropriate password form or SSO/recovery guidance |
| New campaign | /new-campaign / #new-campaign | Analyst/admin form; viewers denied; no assessment launches on navigation |
| Scheduler | /scheduler / #scheduler | Existing schedules, preview, edit and history |
| History | /history / #history | Assessment history and run/log navigation |
| Projects | /projects / #projects | Registered projects and analytics |
| Project | /project/ID / #project/ID | Exact project's retained assessments and findings |
| Campaign | /campaign/ID / #campaign/ID | Exact assessment detail |
| Report | /report/ID / #report/ID | Metadata first; explicit preview authorization, no automatic reveal |
| Vulnerability | /vulnerability/ID / #vulnerability/ID?campaign_id=ID | Exact scoped finding; unqualified reused IDs require assessment selection |
| Infrastructure | /infra/ID / #infra/ID | Exact assessment's safe graph and reviewed paths |
| Pull request | /pull-request/ID / #pull-request/ID | Distinguishes local proposal vs published PR; scoped patch download |

Unknown records produce an unavailable state, never substitute another record.
Navigation cancels stale requests; reload requires sign-in again and retains
resource identity. Back/Forward use the same hash state. Evidence grants never
enter links. WebXR capability denial leaves ordinary graph navigation available.
The normal desktop/mobile acceptance still covers all existing pages and forms.

Reproduce the pure routing checks with `node tests/community/resource_routes.cjs`.
HTTP shell/auth regression: `PYTHONPATH=mcp .venv/bin/python -m pytest
 tests/community/test_evidence_access.py -q` (13 passed / 12 subtests locally).
Hosted community-browser.yml additionally checks project/proposal/report/infra,
scheduler/history navigation, direct report path, reload/auth, Back, missing
records, and absence of restored evidence. Results belong to the matching commit.
Exact reference typography/brief animation states and actual headset input
remain evidence requirements, not claims inferred from these functional routes.
