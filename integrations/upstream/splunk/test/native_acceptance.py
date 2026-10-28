#!/usr/bin/env python3
"""Native Splunk Enterprise acceptance, for an operator-owned disposable host.

Not an emulator. A pass means the *installed app* ran native REST/SPL and HEC
on a loopback, operator-authorized Splunk Enterprise instance. There is no
license bootstrap, Docker image pull, user creation, server restart, target
scan, external HEC, or external notification.

Prerequisites (mandatory):
 SPLUNK_NATIVE_ATTESTED=1
 SPLUNK_NATIVE_MGMT=https://127.0.0.1:8089
 SPLUNK_NATIVE_USER / SPLUNK_NATIVE_PASSWORD
 SPLUNK_NATIVE_HEC=https://127.0.0.1:8088/services/collector/event
 SPLUNK_NATIVE_HEC_TOKEN
 SPLUNK_NATIVE_PACKAGE_FILE=/absolute/path/to/staged/darkmoon-1.0.0.tar.gz
Optional:
 SPLUNK_NATIVE_INDEX=main
 SPLUNK_NATIVE_CA_FILE=/absolute/path/to/local/CA.pem
 SPLUNK_NATIVE_INSECURE_LOOPBACK=1  (only for literal loopback, disposable host)
Run: python test/native_acceptance.py --native
Missing prerequisites exit 3 (UNAVAILABLE), never success. Any failed
assertion/transport/search returns exit 1 (FAIL); success requires all probes.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from urllib.parse import urlsplit
import ipaddress

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ASSETS = (
    "darkmoon/default/app.conf", "darkmoon/default/props.conf",
    "darkmoon/default/macros.conf", "darkmoon/default/transforms.conf",
    "darkmoon/default/savedsearches.conf",
    "darkmoon/default/alert_actions.conf",
    "darkmoon/default/data/ui/alerts/darkmoon_campaign.html",
    "darkmoon/default/data/ui/views/darkmoon_findings.xml",
    "darkmoon/default/data/ui/views/darkmoon_remediation.xml",
    "darkmoon/default/data/ui/views/darkmoon_soc_overview.xml",
    "darkmoon/default/data/ui/views/darkmoon_campaigns.xml",
    "darkmoon/default/data/ui/views/darkmoon_setup.xml",
    "darkmoon/appserver/static/setup.js",
    "darkmoon/bin/darkmoon_campaign.py",
    "darkmoon/static/appIcon.png",
)
MAX_RESPONSE = 8 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def open_local(request, context, timeout):
    return urllib.request.build_opener(
        NoRedirect(), urllib.request.HTTPSHandler(context=context)
    ).open(request, timeout=timeout)


class Unavailable(Exception):
    pass


def local_url(name, default, required_scheme="https"):
    raw = os.environ.get(name, default)
    if not raw or any(c.isspace() for c in raw) or any(c in raw for c in "\\?#"):
        raise Unavailable(name + " must be a literal loopback URL")
    try:
        parts = urlsplit(raw)
        if (parts.scheme != required_scheme or
                not ipaddress.ip_address(parts.hostname).is_loopback or
                parts.username or parts.password or parts.port == 0 or
                parts.path not in ("", "/", "/services/collector/event")):
            raise ValueError()
    except (ValueError, TypeError):
        raise Unavailable(name + " must be a literal loopback URL with the specified scheme") from None
    if name == "SPLUNK_NATIVE_HEC" and parts.path != "/services/collector/event":
        raise Unavailable("HEC must be the local Splunk collector/event endpoint")
    return raw.rstrip("/")


def preflight():
    if os.environ.get("SPLUNK_NATIVE_ATTESTED") != "1":
        raise Unavailable("operator must attest a legally usable disposable Splunk host")
    credentials = ("SPLUNK_NATIVE_USER", "SPLUNK_NATIVE_PASSWORD", "SPLUNK_NATIVE_HEC_TOKEN",
                   "SPLUNK_NATIVE_PACKAGE_FILE")
    absent = [key for key in credentials if not os.environ.get(key)]
    if absent:
        raise Unavailable("missing required host configuration: " + ", ".join(absent))
    mgmt = local_url("SPLUNK_NATIVE_MGMT", "https://127.0.0.1:8089")
    hec = local_url("SPLUNK_NATIVE_HEC", "https://127.0.0.1:8088/services/collector/event")
    package = Path(os.environ["SPLUNK_NATIVE_PACKAGE_FILE"])
    if not package.is_absolute() or not package.is_file() or package.is_symlink():
        raise Unavailable("pre-staged package must be a regular absolute local file")
    index = os.environ.get("SPLUNK_NATIVE_INDEX", "main")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,60}", index):
        raise Unavailable("invalid disposable index")
    context = ssl.create_default_context(cafile=os.environ.get("SPLUNK_NATIVE_CA_FILE") or None)
    if os.environ.get("SPLUNK_NATIVE_INSECURE_LOOPBACK") == "1":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif os.environ.get("SPLUNK_NATIVE_INSECURE_LOOPBACK") not in (None, "", "0"):
        raise Unavailable("invalid loopback TLS override")
    # No installation before the package has passed structural/security checks.
    with tarfile.open(package, "r:*") as archive:
        names = set(archive.getnames())
        missing = set(REQUIRED_ASSETS) - names
        if missing:
            raise Unavailable("staged package missing required assets: " + ", ".join(sorted(missing)))
        for entry in archive:
            parts = Path(entry.name).parts
            if (not entry.name.startswith("darkmoon/") or entry.issym() or entry.islnk()
                    or any(part in ("local", "__pycache__") for part in parts)
                    or not (entry.isfile() or entry.isdir())):
                raise Unavailable("package includes unexpected or unsafe file")
    return mgmt, hec, index, package, context


class Client:
    def __init__(self, base, context, auth=None):
        self.base, self.context, self.auth = base, context, auth

    def call(self, endpoint, fields=None, json_body=None, headers=None, expected=(200, 201)):
        assert endpoint.startswith("/") and ".." not in endpoint
        data = None
        h = {"Accept": "application/json", **(headers or {})}
        if self.auth:
            h["Authorization"] = self.auth
        if fields is not None:
            data = urllib.parse.urlencode(fields).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_body is not None:
            data = json.dumps(json_body, separators=(",", ":")).encode()
            h["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + endpoint, data=data, headers=h,
                                         method="POST" if data is not None else "GET")
        try:
            with open_local(request, self.context, 20) as response:
                status, raw = response.status, response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as err:
            # Never echo response bodies; they can contain authorization data.
            raise AssertionError("native endpoint returned HTTP " + str(err.code)) from None
        except Exception as err:
            raise AssertionError("native endpoint is unavailable or transport failed (" +
                                 type(err).__name__ + ")") from None
        if status not in expected or len(raw) > MAX_RESPONSE:
            raise AssertionError("native endpoint returned an invalid status or oversized response")
        try:
            return json.loads(raw.decode())
        except (UnicodeError, ValueError):
            raise AssertionError("native endpoint returned invalid JSON") from None


def entry(payload):
    rows = payload.get("entry") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise AssertionError("native app resource missing or invalid")
    return rows[0].get("content", {})


def spl(client, search, earliest="-2h", latest="now"):
    endpoint = "/servicesNS/nobody/darkmoon/search/jobs/export?output_mode=json"
    fields = {"search": "search " + search, "earliest_time": earliest, "latest_time": latest,
              "output_mode": "json", "search_mode": "normal"}
    data = urllib.parse.urlencode(fields).encode()
    h = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
         "Authorization": client.auth}
    request = urllib.request.Request(client.base + endpoint, data=data, headers=h, method="POST")
    try:
        with open_local(request, client.context, 45) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as e:
        raise AssertionError("native SPL export HTTP " + str(e.code)) from None
    if len(raw) > MAX_RESPONSE:
        raise AssertionError("native SPL results exceeded response bound")
    results = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise AssertionError("malformed native SPL output") from None
        if not isinstance(row, dict):
            raise AssertionError("malformed native SPL frame")
        if "messages" in row and any(isinstance(m, dict) and m.get("type") == "ERROR"
                                     for m in row["messages"]):
            raise AssertionError("native SPL reported an error")
        if "result" in row:
            if not isinstance(row["result"], dict):
                raise AssertionError("invalid native SPL result shape")
            results.append(row["result"])
    return results


def number(value):
    if isinstance(value, bool):
        raise AssertionError("native count is boolean")
    try:
        return int(value)
    except (ValueError, TypeError):
        raise AssertionError("native count is invalid") from None


def check(condition, reason):
    if not condition:
        raise AssertionError(reason)


def native(mgmt, hec, index, package, context):
    digest = hashlib.sha256(package.read_bytes()).hexdigest()[:16]
    basic = base64.b64encode((os.environ["SPLUNK_NATIVE_USER"] + ":" +
                              os.environ["SPLUNK_NATIVE_PASSWORD"]).encode()).decode()
    management = Client(mgmt, context, "Basic " + basic)
    collector = Client(hec.rsplit("/services/collector/event", 1)[0], context)
    print("NATIVE: staged package fingerprint sha256:" + digest + " (no secrets)")
    # The operator has already staged the archive ON THIS SAME disposable host.
    # Use the documented server-local file install API. No license or terms flow.
    management.call("/services/apps/local?output_mode=json",
                    fields={"name": str(package), "filename": "true", "update": "true"})
    installed = entry(management.call("/services/apps/local/darkmoon?output_mode=json"))
    check(bool(installed), "native Splunk did not register the installed app")
    for name in ("darkmoon_findings", "darkmoon_remediation", "darkmoon_setup",
                 "darkmoon_campaigns", "darkmoon_soc_overview"):
        content = entry(management.call("/servicesNS/nobody/darkmoon/data/ui/views/" +
                                        name + "?output_mode=json"))
        check(isinstance(content, dict), "native dashboard not registered: " + name)
    action = entry(management.call("/servicesNS/nobody/darkmoon/alerts/alert_actions/" +
                                   "darkmoon_campaign?output_mode=json"))
    check(isinstance(action, dict) and bool(action), "native alert action missing")
    form = entry(management.call("/servicesNS/nobody/darkmoon/data/ui/alerts/" +
                                 "darkmoon_campaign?output_mode=json"))
    markup = str(form.get("eai:data", form.get("data", "")))
    for param in ("action_kind", "retest_scope", "campaign_id", "finding_id",
                  "scope_profile", "dry_run", "max_per_hour"):
        check("action.darkmoon_campaign.param." + param in markup,
              "native registered alert configuration form is incomplete")
    # Native effective conf: macro and EVAL guards, not local-source parse.
    macros = entry(management.call("/servicesNS/nobody/darkmoon/configs/conf-macros/" +
                                   "darkmoon_index?output_mode=json"))
    check("sourcetype=darkmoon:*" in str(macros.get("definition", "")),
          "installed macro does not restrict source types")
    saved = management.call("/servicesNS/nobody/darkmoon/saved/searches?output_mode=json&count=0")
    names = {e.get("name") for e in saved.get("entry", []) if isinstance(e, dict)}
    check(any("Exploited finding" in str(name) for name in names),
          "native disabled example alert missing")
    print("PASS native install, required app views, macro and alert registration")

    run = "splunknative_" + uuid.uuid4().hex[:16]
    f = "finding_native_" + uuid.uuid4().hex[:12]
    c1, c2 = run + "_c1", run + "_c2"
    now = int(time.time())
    # All events are synthetic metadata and bound to one ephemeral run marker.
    def ev(st, when, **fields):
        return {"time": when, "index": index, "sourcetype": "darkmoon:" + st,
                "event": {"native_test_run": run, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(when)),
                          **fields}}
    items = [
        ev("campaign", now-200, campaign_id=c1, target_id=run+"_target",
           target="demo-shop.local", status="running", project_id=run+"_project"),
        ev("campaign", now-100, campaign_id=c1, target_id=run+"_target",
           target="demo-shop.local", status="completed", project_id=run+"_project"),
        ev("finding", now-180, campaign_id=c1, finding_id=f, finding_key="UNTRUSTED_OVERRIDE",
           status="confirmed", severity="critical", title="Synthetic finding",
           target="demo-shop.local", project_id=run+"_project"),
        ev("finding", now-90, campaign_id=c1, finding_id=f, finding_key="UNTRUSTED_OVERRIDE",
           status="remediated", severity="critical", title="Synthetic finding",
           target="demo-shop.local", project_id=run+"_project"),
        ev("finding", now-80, campaign_id=c2, finding_id=f, finding_key="UNTRUSTED_OVERRIDE",
           status="exploited", severity="info", title="Synthetic finding",
           target="demo-shop.local", project_id=run+"_project"),
        ev("retest", now-110, retest_id=run+"_running", record_type="lifecycle",
           base_campaign_id=c1, target_id=run+"_target", status="running"),
        ev("retest", now-70, retest_id=run+"_completed", record_type="lifecycle",
           base_campaign_id=c1, new_campaign_id=c2, target_id=run+"_target", status="completed"),
        ev("retest", now-60, retest_id=run+"_completed", record_type="comparison",
           base_campaign_id=c1, new_campaign_id=c2, finding_campaign_id=c1,
           finding_id=f, target_id=run+"_target", verdict="not_observed", status="completed"),
        ev("remediation", now-55, proposal_id=run+"_local", campaign_id=c1,
           finding_ids=[f], status="validated", published=False),
        ev("pr", now-50, pr_id=run+"_published", campaign_id=c1, finding_ids=[f],
           provider="github", state="open", number=99, published=True),
    ]
    collector.call("/services/collector/event", json_body=items[0],
                   headers={"Authorization": "Splunk " + os.environ["SPLUNK_NATIVE_HEC_TOKEN"]})
    for item in items[1:]:
        reply = collector.call("/services/collector/event", json_body=item,
                               headers={"Authorization": "Splunk " + os.environ["SPLUNK_NATIVE_HEC_TOKEN"]})
        check(reply.get("code") == 0, "native HEC rejected synthetic metadata")
    base = "index=" + index + " sourcetype=darkmoon:* native_test_run=" + run
    deadline = time.monotonic() + 55
    while True:
        counts = spl(management, base + " | stats count as total")
        if counts and number(counts[0].get("total")) == len(items):
            break
        if time.monotonic() >= deadline:
            raise AssertionError("native HEC data not searchable within 55 seconds")
        time.sleep(3)
    print("PASS native HEC indexing and actual SPL extraction")
    rows = spl(management, base + " sourcetype=darkmoon:finding"
               + " | stats values(finding_key) as keys values(severity) as levels dc(dest) as dests"
               + " dc(signature) as signatures")
    check(len(rows) == 1, "native finding field result missing")
    row = rows[0]
    keys = row.get("keys", [])
    if isinstance(keys, str):
        keys = [keys]
    check(set(keys) == {c1+"::"+f, c2+"::"+f},
          "native EVAL-finding_key did not override hostile indexed value")
    severity = row.get("levels", [])
    check("informational" in (severity if isinstance(severity, list) else [severity]),
          "native severity calculated-field normalization not applied")
    check(number(row.get("dests", 0)) == 1 and number(row.get("signatures", 0)) == 1,
          "native CIM field aliases unavailable")
    live = spl(management, base + " sourcetype=darkmoon:finding | dedup finding_key sortby -_indextime -_time"
               + " | search NOT status IN (\"false_positive\",\"remediated\",\"resolved\",\"closed\",\"fixed\")"
               + " | stats count as n")
    check(number(live[0]["n"]) == 1, "native latest-observation filter resurrected old finding")
    scoped = spl(management, base + " sourcetype=darkmoon:finding"
                 + " | dedup finding_key sortby -_indextime -_time | stats dc(finding_key) as n")
    check(number(scoped[0]["n"]) == 2, "native campaign-qualified identity collapsed separate findings")
    empty = spl(management, base + " sourcetype=darkmoon:finding finding_id=no_such_native_finding"
                + " | stats count as n")
    check(number(empty[0]["n"]) == 0, "valid empty native search is not empty")
    retests = spl(management, base + " sourcetype=darkmoon:retest | stats count(eval(record_type=\"lifecycle\"))"
                  + " as lifecycles count(eval(verdict=\"not_observed\")) as unknown"
                  + " count(eval(verdict=\"fixed\")) as fixed")
    check(number(retests[0]["lifecycles"]) == 2 and number(retests[0]["unknown"]) == 1
          and number(retests[0]["fixed"]) == 0,
          "native SPL incorrectly treats not_observed or pending lifecycle as fixed")
    proposal = spl(management, base + " sourcetype=darkmoon:remediation | stats dc(proposal_id) as n")
    published = spl(management, base + " sourcetype=darkmoon:pr | stats dc(pr_id) as n")
    check(number(proposal[0]["n"]) == 1 and number(published[0]["n"]) == 1,
          "native local proposal/PR classification collapsed records")
    print("PASS native extraction, precedence, latest state, lifecycle and remediation SPL")
    print("NATIVE SPL/HEC PASS; browser SplunkJS and executable alert flow are separate gates")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="verify host prerequisites, never pass native")
    group.add_argument("--native", action="store_true", help="install and verify on operator-hosted Splunk")
    args = parser.parse_args()
    try:
        prereqs = preflight()
    except Unavailable as err:
        print("NATIVE UNAVAILABLE: " + str(err), file=sys.stderr)
        return 3
    except (OSError, tarfile.TarError):
        print("NATIVE UNAVAILABLE: staged package cannot be inspected", file=sys.stderr)
        return 3
    if args.check:
        print("NATIVE PREREQUISITES PRESENT; not a native acceptance pass")
        return 0
    try:
        native(*prereqs)
    except (AssertionError, OSError, ValueError) as err:
        # All error messages are generic; never log credentials, payloads, URLs.
        print("NATIVE FAIL: " + str(err), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
