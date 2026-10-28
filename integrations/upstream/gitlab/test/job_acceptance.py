#!/usr/bin/env python3
"""Offline acceptance of the GENERATED GitLab job body and pinned schemas.

Not a GitLab Runner or GitLab server acceptance test. The native runner test
is separate and executes the fork's patched CLI against disposable OSS data.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "test" / "render_flat.py"
VALIDATE = ROOT / "test" / "validate_schemas.py"
SECRET = "DO-NOT-PUBLISH-ENV-SECRET"
EVIDENCE = "DO-NOT-PUBLISH-EVIDENCE"
MOCK = r'''#!/usr/bin/env python3
import json, os, sys
case = os.environ["DM_TEST_CASE"]
cmd = sys.argv[1]
if cmd == "run":
    if case in ("authentication", "launch", "timeout", "failed", "stopped"):
        sys.exit(1)
    if case == "missing-id":
        print("{}")
        sys.exit(0)
    if case == "bad-run-json":
        print("{bad")
        sys.exit(0)
    fail_on = [] if os.environ["DM_FAIL_ON"] == "" else ["critical", "high"]
    empty = case == "empty"
    total = 0 if empty else 2
    offending = ({"critical": 1, "high": 1} if fail_on and not empty else {})
    payload = {
        "campaignId": "camp_exact", "verdict": "fail" if offending else "pass",
        "total": total, "offending": offending, "failOn": fail_on,
        "reason": "fixture",
    }
    if case == "wrong-count": payload["total"] = total + 1
    if case == "wrong-offending": payload["offending"] = {"high": 99}
    if case == "wrong-verdict": payload["verdict"] = "pass" if offending else "fail"
    if case == "wrong-exit": payload["verdict"] = "pass"; payload["offending"] = {}
    print(json.dumps(payload))
    if case == "wrong-exit": sys.exit(2)
    sys.exit(2 if offending else 0)
if cmd == "findings":
    if sys.argv[2] != "camp_exact": sys.exit(1)
    if case == "read-error": sys.exit(1)
    if case == "malformed": print("{bad"); sys.exit(0)
    if case == "bad-envelope": print("{}"); sys.exit(0)
    if case == "bad-item": print("[null]"); sys.exit(0)
    if case == "empty": print("[]"); sys.exit(0)
    rows = [
        {"id": "f_critical", "campaignId": "camp_exact", "severity": "critical",
         "title": "SQL injection at https://user:password@private.invalid/x?token=DO-NOT-PUBLISH-EVIDENCE",
         "endpoint": "POST https://private.invalid/credential?token=DO-NOT-PUBLISH-EVIDENCE",
         "category": "sql_injection", "description": "DO-NOT-PUBLISH-EVIDENCE",
         "remediation": "DO-NOT-PUBLISH-EVIDENCE",
         "evidence": {"raw": "DO-NOT-PUBLISH-EVIDENCE"}},
        {"id": "f_high", "campaignId": "camp_exact", "severity": "high",
         "title": "Controlled finding", "endpoint": "GET /rest/user/login",
         "category": "xss"},
    ]
    if case == "wrong-campaign": rows[1]["campaignId"] = "camp_foreign"
    if case == "duplicate-ids": rows[1]["id"] = rows[0]["id"]
    if case == "unknown-severity": rows[1]["severity"] = "unrated"
    print(json.dumps(rows))
    sys.exit(0)
if cmd == "report": sys.exit(0)
sys.exit(1)
'''


def run():
    with tempfile.TemporaryDirectory(prefix="dm-gitlab-job-") as folder:
        work = Path(folder)
        path = work / "flattened.yml"
        subprocess.run([sys.executable, str(RENDER), str(path),
                        "target=owned.invalid", "mode=oss",
                        "output-dir=output with ' quote"], check=True, capture_output=True)
        doc = yaml.safe_load(path.read_text())
        job = doc["darkmoon_scan"]
        assert job["artifacts"]["when"] == "always"
        assert job["artifacts"]["reports"]["sast"] == "gl-sast-report.json"
        assert job["artifacts"]["reports"]["codequality"] == "gl-code-quality-report.json"
        assert job["allow_failure"] == {"exit_codes": [250]}
        assert isinstance(job["script"], list) and len(job["script"]) == 1
        script = work / "job.sh"
        script.write_text(job["script"][0])
        cli = work / "darkmoon-ci"
        cli.write_text(MOCK)
        cli.chmod(0o755)

        cases = {
            "nonempty-pass": (0, 2, ""),
            "gate": (2, 2, "critical,high"),
            "empty": (0, 0, ""),
            "authentication": (1, 0, ""),
            "launch": (1, 0, ""),
            "timeout": (1, 0, ""),
            "failed": (1, 0, ""),
            "stopped": (1, 0, ""),
            "read-error": (1, 0, ""),
            "malformed": (1, 0, ""),
            "bad-envelope": (1, 0, ""),
            "bad-item": (1, 0, ""),
            "missing-id": (1, 0, ""),
            "bad-run-json": (1, 0, ""),
            "wrong-campaign": (1, 0, ""),
            "wrong-count": (1, 0, ""),
            "wrong-offending": (1, 0, ""),
            "wrong-verdict": (1, 0, "critical,high"),
            "wrong-exit": (1, 0, ""),
            "duplicate-ids": (1, 0, ""),
            "unknown-severity": (1, 0, ""),
        }
        for case, (expected_rc, count, gate) in cases.items():
            home = work / case
            home.mkdir()
            env = {**os.environ, **{k: str(v) for k, v in job["variables"].items()}}
            env.update(PATH=str(work) + os.pathsep + os.environ["PATH"],
                       DM_TEST_CASE=case, DM_FAIL_ON=gate,
                       DARKMOON_LICENSE_KEY=SECRET)
            result = subprocess.run(["sh", str(script)], cwd=home, env=env,
                                    capture_output=True, text=True, timeout=25)
            assert result.returncode == expected_rc, (case, result.returncode, result.stdout, result.stderr)
            cq = home / "gl-code-quality-report.json"
            sast = home / "gl-sast-report.json"
            assert cq.is_file() and sast.is_file(), (case, "missing shared artifacts")
            parsed = json.loads(sast.read_text())
            assert parsed["scan"]["status"] == ("failure" if expected_rc == 1 else "success"), case
            assert len(parsed["vulnerabilities"]) == count, (case, len(parsed["vulnerabilities"]))
            assert len(json.loads(cq.read_text())) == count, case
            output = cq.read_text() + sast.read_text() + result.stdout + result.stderr
            for forbidden in (SECRET, EVIDENCE, "user:password", "token="):
                assert forbidden not in output, (case, forbidden)
            assert not (home / env["DM_OUTPUT_DIR"] / "run.json").exists(), case
            assert not (home / env["DM_OUTPUT_DIR"] / "findings.json").exists(), case
            subprocess.run([sys.executable, str(VALIDATE), str(cq), str(sast)],
                           capture_output=True, check=True, timeout=25)

        # Explicitly disabled SAST must never manufacture a success scan.
        home = work / "no-sast"
        home.mkdir()
        env.update(DM_TEST_CASE="empty", DM_EMIT_SAST="false", DM_FAIL_ON="")
        result = subprocess.run(["sh", str(script)], cwd=home, env=env,
                                capture_output=True, timeout=25)
        assert result.returncode == 0
        assert not (home / "gl-sast-report.json").exists()
        # A missing executable still produces failure-state artifacts (if
        # Python is available), regardless of actual server upload behavior.
        home = work / "missing-cli"
        home.mkdir()
        env.update(PATH=os.environ["PATH"], DM_TEST_CASE="empty", DM_EMIT_SAST="true")
        result = subprocess.run(["sh", str(script)], cwd=home, env=env,
                                capture_output=True, timeout=25)
        assert result.returncode == 1
        assert json.loads((home / "gl-sast-report.json").read_text())["scan"]["status"] == "failure"
        print("PASS generated job: %d error/pass/gate scenarios, report schema and privacy checks" % len(cases))


if __name__ == "__main__":
    run()
