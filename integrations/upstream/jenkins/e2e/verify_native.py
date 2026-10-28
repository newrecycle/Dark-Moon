#!/usr/bin/env python3
"""Native Jenkins HPI acceptance. Docker isolation; synthetic OSS fixtures only."""
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from http.cookiejar import CookieJar

# The Jenkins CSRF crumb is session-bound. Keep its cookie for subsequent
# buildWithParameters requests instead of creating an unrelated HTTP session.
urllib.request.install_opener(urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(CookieJar())))

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ID = "dm-native-" + uuid.uuid4().hex[:10]
CONTROLLER, AGENT = ID + "-controller", ID + "-agent"
NETWORK = ID + "-network"
CTRL_IMAGE, AGENT_IMAGE = ID + "-controller-image", ID + "-agent-image"
SECRET = "SYNTHETIC_ONLY_CREDENTIAL_8e9ffab"
FORBIDDEN = ("SYNTHETIC_EVIDENCE_SECRET", "SYNTHETIC_RESPONSE_SECRET",
             "SYNTHETIC_UNRELATED_SECRET", SECRET, "raw_request", "raw_response")
TIMEOUT = 180


def cmd(*args, check=True):
    p = subprocess.run(args, text=True, capture_output=True, check=False)
    if check and p.returncode:
        raise AssertionError("Command failed: " + " ".join(args[:4]) + "\n" + p.stderr[-2500:])
    return p.stdout.strip()


def http(url, method="GET", data=None, headers=None, missing=False):
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if missing and exc.code == 404:
            return None
        detail = exc.read(900).decode("utf-8", errors="replace")
        raise AssertionError("Jenkins HTTP " + str(exc.code) + " on " +
                             urllib.parse.urlsplit(url).path + ": " +
                             re.sub(r"(?i)(token|secret|password)[^<> ]*", "[REDACTED]", detail)) from None


def eventually(check, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            item = check()
            if item:
                return item
        except Exception as error:
            last = error
        time.sleep(2)
    raise AssertionError("Timed out waiting for Jenkins; last error: " + repr(last))


def safe_json(url):
    return json.loads(http(url))


def native():
    hpi = ROOT / "target" / "darkmoon-scan.hpi"
    assert hpi.is_file(), "Run Maven verify first; HPI not found"
    native_dir = HERE / ".native"
    native_dir.mkdir(exist_ok=True)
    (native_dir / "darkmoon-scan.hpi").write_bytes(hpi.read_bytes())
    print("native_hpi_bytes=" + str(hpi.stat().st_size), flush=True)

    cmd("docker", "build", "-q", "-t", CTRL_IMAGE, "-f", str(HERE / "Dockerfile"), str(HERE))
    cmd("docker", "build", "-q", "-t", AGENT_IMAGE, "-f", str(HERE / "agent.Dockerfile"), str(HERE))
    cmd("docker", "network", "create", NETWORK)
    cmd("docker", "run", "-d", "--name", CONTROLLER, "--network", NETWORK,
        "--network-alias", "controller", "-p", "127.0.0.1::8080", CTRL_IMAGE)
    binding = cmd("docker", "port", CONTROLLER, "8080/tcp")
    port = int(binding.rsplit(":", 1)[1])
    base = "http://127.0.0.1:" + str(port)
    eventually(lambda: http(base + "/login"))
    plugin = eventually(lambda: next((p for p in safe_json(base + "/pluginManager/api/json?tree=plugins[shortName,active,version]")["plugins"]
                                       if p["shortName"] == "darkmoon-scan" and p["active"]), None))
    print("native_plugin_active=true version=" + plugin["version"], flush=True)

    def jnlp_secret():
        xml = http(base + "/computer/dm-agent/jenkins-agent.jnlp")
        root = ET.fromstring(xml)
        args = [element.text for element in root.iter() if element.tag.endswith("argument")]
        return args[0] if args and args[0] else None

    agent_secret = eventually(jnlp_secret)
    cmd("docker", "run", "-d", "--name", AGENT, "--network", NETWORK,
        AGENT_IMAGE, "-url", "http://controller:8080/", "-secret", agent_secret,
        "-name", "dm-agent", "-webSocket", "-workDir", "/home/jenkins/agent workspace")
    eventually(lambda: safe_json(base + "/computer/dm-agent/api/json?tree=offline")["offline"] is False)
    node_version = cmd("docker", "exec", AGENT, "node", "--version")
    assert int(node_version.removeprefix("v").split(".")[0]) >= 18
    print("native_agent_online=true agent_node=" + node_version, flush=True)

    crumb = safe_json(base + "/crumbIssuer/api/json")
    auth = {crumb["crumbRequestField"]: crumb["crumb"]}
    cases = [
        ("high", "FAILURE", 1),
        ("empty", "SUCCESS", 0),
        ("nonempty_pass", "SUCCESS", 1),
        ("medium", "UNSTABLE", 1),
        ("missing_findings", "FAILURE", None),
        ("malformed_findings", "FAILURE", None),
        ("wrong_findings_type", "FAILURE", None),
        ("foreign_findings", "FAILURE", None),
        ("ambiguous_campaigns", "FAILURE", None),
        ("failed", "FAILURE", None),
        ("stopped", "FAILURE", None),
        ("timed_out", "FAILURE", None),
        ("missing_credential", "FAILURE", None),
        ("missing_node", "FAILURE", None),
    ]
    for scenario, expected, expected_issues in cases:
        before = safe_json(base + "/job/darkmoon-native/api/json?tree=nextBuildNumber")["nextBuildNumber"]
        body = urllib.parse.urlencode({"SCENARIO": scenario}).encode()
        http(base + "/job/darkmoon-native/buildWithParameters", method="POST", data=body, headers=auth)
        endpoint = base + "/job/darkmoon-native/" + str(before)
        result = eventually(lambda: (lambda info: info if info and not info["building"] else None)(
            safe_json(endpoint + "/api/json?tree=number,building,result")))
        log = http(endpoint + "/consoleText").decode("utf-8", errors="replace")
        if result["result"] != expected:
            safe_log = log
            for forbidden in FORBIDDEN:
                safe_log = safe_log.replace(forbidden, "[REDACTED]")
            print("NATIVE_BUILD_MISMATCH scenario=" + scenario +
                  " expected=" + expected + " actual=" + str(result["result"]) +
                  "\n" + safe_log[-7000:], flush=True)
            raise AssertionError(("unexpected Pipeline result", scenario, result))
        for forbidden in FORBIDDEN:
            assert forbidden not in log, ("secret leaked to build log", scenario, forbidden)
        assert "dm-agent" in log or "Running on" in log, ("not a remote Pipeline agent", scenario)

        artifacts = safe_json(endpoint + "/api/json?tree=artifacts[relativePath]")["artifacts"]
        names = {a["relativePath"] for a in artifacts}
        assert all(name.startswith("darkmoon-reports/") for name in names), (scenario, names)
        assert not any("unrelated-sensitive" in name or "darkmoon-report-full" in name for name in names)
        for name in names:
            payload = http(endpoint + "/artifact/" + name)
            for forbidden in FORBIDDEN:
                assert forbidden.encode() not in payload, ("secret leaked to artifact", scenario, name, forbidden)
        if expected_issues is not None:
            assert "darkmoon-reports/darkmoon.sarif" in names, (scenario, names, log[-1500:])
            sarif = json.loads(http(endpoint + "/artifact/darkmoon-reports/darkmoon.sarif"))
            findings = len(sarif["runs"][0]["results"])
            assert findings == expected_issues, (scenario, findings)
            issues = eventually(lambda: safe_json(endpoint + "/sarif/api/json?tree=totalSize"))
            assert issues["totalSize"] == expected_issues, (scenario, issues)
        else:
            assert "darkmoon-reports/darkmoon.sarif" not in names, (scenario, names)
        print("native_case=" + scenario + " build=" + str(before) + " result=" + result["result"] +
              " warnings=" + str(expected_issues) + " artifacts=" + str(len(names)), flush=True)

    extraction = cmd("docker", "exec", AGENT, "sh", "-c",
                     "find '/home/jenkins/agent workspace' -path '*/.darkmoon/client/darkmoon-ci.cjs' -type f | head -1")
    assert extraction and "agent workspace" in extraction and ".darkmoon/client" in extraction, extraction
    print("native_agent_bundle_extracted=true workspace_with_spaces=true", flush=True)


if __name__ == "__main__":
    try:
        native()
    except Exception:
        print("JENKINS_NATIVE_FAILURE controller=" + CONTROLLER + " agent=" + AGENT, flush=True)
        for name in (CONTROLLER, AGENT):
            log = cmd("docker", "logs", "--tail", "110", name, check=False)
            if log:
                # Container logs are test metadata only; filter secrets.
                for secret in FORBIDDEN:
                    log = log.replace(secret, "[REDACTED]")
                print(name + ": " + log[-6500:], flush=True)
        raise
    finally:
        if os.environ.get("KEEP_NATIVE_CONTAINERS") != "1":
            cmd("docker", "rm", "-f", CONTROLLER, AGENT, check=False)
            cmd("docker", "network", "rm", NETWORK, check=False)
            cmd("docker", "rmi", "-f", CTRL_IMAGE, AGENT_IMAGE, check=False)
