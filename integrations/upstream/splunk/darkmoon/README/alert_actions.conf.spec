[darkmoon_campaign]
param.target = <string>
* Target host or URL to (re)test with Darkmoon.
* MUST match an allowlisted row in lookups/darkmoon_targets.csv.
* If empty, the script uses the "target" or "dest" field from the triggering result.

param.action_kind = <string>
* Either "retest" (POST /api/v1/retest) or "campaign" (POST /api/v1/run/campaign).
* Defaults to "retest" when omitted. Unsupported/malformed values are rejected.

param.scope_profile = <string>
* Safe-harbor profile. "non-destructive" (default) is enforced unless the target
* row in the allowlist explicitly authorizes the "authorized" profile. Other values are rejected.

param.dry_run = <boolean>
* When 1 (default), the action validates and logs its decision but does NOT call
* Darkmoon. Set to 0 to actually launch.

param.max_per_hour = <integer>
* Maximum launches per rolling hour (token bucket). Hard-capped by the script.

# Guard semantics
# Dry-run and live attempts both consume the rolling admission quota.
# Quota errors/corrupt state fail closed. Launch acceptance does not prove completion.
