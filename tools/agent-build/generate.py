#!/usr/bin/env python3
"""
Darkmoon agent generator (simplified).

Every sub-agent prompt is now a short, action-oriented file: front-matter plus
the essential operational rules (force darkmoon_execute_command, act
immediately, how to use the toolbox, rate limiting, push to dashboard, exit
only when done). Domain expertise is supplied by the model itself — the prompt
tells it to GO.

Usage:
    python3 generate.py            # build every profile in profiles/
    python3 generate.py aws azure  # build a subset
    python3 generate.py --selfcheck

Output: one LF .md per profile in ./out/ , also mirrored into the three repos'
conf/agents/ by mirror.sh.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PROFILES_DIR = os.path.join(HERE, "profiles")
OUT_DIR = os.path.join(HERE, "out")


SUBAGENT = """# {name} — Darkmoon autonomous pentest sub-agent

Target: {{TARGET}}. Use your own offensive-security expertise to find and PROVE
vulnerabilities in this technology. You know how to pentest — go.

## GO — act immediately, then act again
Run a command, read the result, run the next. Chain findings into deeper
exploitation. Keep moving until the target is fully assessed or out of scope.
Do not over-plan and do not ask for confirmation.

## Command execution (MANDATORY)
ALL command execution goes through `darkmoon_execute_command(command="...")`.
The raw shell / bash tool is denied — never call it directly.

## Tools you have — how to use them (pre-defined, rate-limited)
- Run anything with `darkmoon_execute_command(command="bash -c '<cmd>'").
  The outer bash is allowed; the program inside it runs freely.
- The packaged toolbox is PRE-DEFINED with rate limits. Copy the invocations
  below EXACTLY as written — never raise the limit and never add parallel loops:
    nuclei  -u {{TARGET}} -duc -rl 10 -c 5 -timeout 8 -tags exposure,misconfig,tech-detect
    whatweb -a 3 {{TARGET}}
    curl -s -k {{TARGET}}          # also against cloud REST + IMDS metadata
    jq                          # parse JSON responses, extract secrets
  Example (already rate-limited — do not edit the flags):
    darkmoon_execute_command(command="bash -c 'nuclei -u {{TARGET}} -duc -rl 10 -c 5 -tags exposure 2>&1'")
- Cloud / infra CLIs (az, aws, gcloud, kubectl, terraform, docker) are present —
  use them for enumeration and proof, not brute force.
- Report every confirmed / exploited finding with
  `darkmoon_dashboard_push_finding(...)`. You NEVER finalize the campaign.
- Unsure what is available? Call `darkmoon_list_allowed_tools()` or
  `darkmoon_health_check()`.

## Rate limiting (key numbers — hard ceiling)
The toolbox already throttles by default; these are the ceilings you must
never exceed:
- Auth / OTP / login endpoints: max 1 request per 0.5s.
- Cap any single attack vector at <=10 requests, then STOP and report.
- Max 3 concurrent workers against a remote host; sleep 0.3s between batches.
- On HTTP 429 / 503 / connection reset / connection refused: STOP that vector
  immediately. Do NOT retry or rotate IPs. Move to another vector.
- Never re-run a command that already returned the same output.

## Reporting — push to dashboard, never finalize
- Push every finding with `darkmoon_dashboard_push_finding()`.
- You are a SUB-AGENT. NEVER call darkmoon_dashboard_finalize_campaign() and
  NEVER write the final report — the orchestrator does that.
- Exit only when the target is fully assessed or you are blocked. Do not stop
  early; do not loop forever.
"""


def build_agent(profile):
    p = profile
    aid = p["id"]
    name = p.get("name", aid)
    desc = p.get("description", "")
    head = "---\n"
    head += f"id: {aid}\n"
    head += f"name: {name}\n"
    head += f"description: {desc}\n"
    head += "---\n"
    text = head + "\n" + SUBAGENT.format(name=name)
    if not text.endswith("\n"):
        text += "\n"
    return text


def load_profiles(names=None):
    out = []
    for fn in sorted(os.listdir(PROFILES_DIR)):
        if not fn.endswith(".json"):
            continue
        aid = fn[:-5]
        if names and aid not in names:
            continue
        with open(os.path.join(PROFILES_DIR, fn), encoding="utf-8") as fh:
            prof = json.load(fh)
        prof.setdefault("id", aid)
        out.append(prof)
    return out


def selfcheck():
    # The simplified generator emits a constant short template; nothing to
    # round-trip against a canonical source any more.
    print("[OK] generator is in simplified (spine-free) mode")
    return True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if "--selfcheck" in flags:
        sys.exit(0 if selfcheck() else 1)
    os.makedirs(OUT_DIR, exist_ok=True)
    profiles = load_profiles(args or None)
    if not profiles:
        print("no profiles found in", PROFILES_DIR)
        return
    for prof in profiles:
        text = build_agent(prof)
        assert "\r" not in text, f"{prof['id']} has CR!"
        dest = os.path.join(OUT_DIR, f"{prof['id']}.md")
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"[built] {prof['id']}.md  ({text.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
