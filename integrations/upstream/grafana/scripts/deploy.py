#!/usr/bin/env python3
"""
Idempotently provision the Darkmoon Infinity datasource + dashboards into a
Grafana instance over its HTTP API. Used both for the live Grafana Cloud
deployment and by CI (.github/workflows/deploy.yml).

Env:
  GRAFANA_URL         base URL of the Grafana instance (no trailing slash)
  GRAFANA_SA_TOKEN    a Service-Account / API token (Bearer)
  DARKMOON_API_BASE   (optional) base URL the dashboards should query.
                      Default: the bundled Demo Shop fixtures on GitHub raw.
  DEPLOY_DEMO=1       deploy the self-contained Demo dashboard (default)
  DEPLOY_PROD=1       also deploy the production dashboard (default off)

Secrets are read from env and NEVER printed. Datasource creation is idempotent
(update by uid). Dashboards are imported with overwrite=true (idempotent by uid).
"""
import json
import os
import sys
import urllib.request
import urllib.error

URL = (os.environ.get("GRAFANA_URL") or "").strip().rstrip("/")
TOKEN = (os.environ.get("GRAFANA_SA_TOKEN") or "").strip()
DEMO_BASE = "https://raw.githubusercontent.com/ASCIT31/darkmoon-grafana/main/fixtures"
API_BASE = (os.environ.get("DARKMOON_API_BASE") or DEMO_BASE).strip().rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DS_UID = "darkmoon-demoshop-infinity"
DS_NAME = "Darkmoon (Demo Shop)"

if not URL or not TOKEN:
    print("ERROR: GRAFANA_URL and GRAFANA_SA_TOKEN must be set", file=sys.stderr)
    sys.exit(2)


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}
    except Exception as e:
        return 0, {"error": str(e)}


def ensure_infinity_ds():
    """Create or update the Darkmoon Infinity datasource (idempotent by uid)."""
    # Is the Infinity plugin installed?
    st, plugins = api("GET", "/api/plugins?embedded=0")
    ids = {p.get("id") for p in plugins} if isinstance(plugins, list) else set()
    if "yesoreyeram-infinity-datasource" not in ids:
        print("  ! Infinity plugin not installed on this instance.")
        # On Grafana Cloud it is available in the catalog; try to install it.
        api("POST", "/api/plugins/yesoreyeram-infinity-datasource/install", {})

    payload = {
        "name": DS_NAME,
        "uid": DS_UID,
        "type": "yesoreyeram-infinity-datasource",
        "access": "proxy",
        "isDefault": False,
        "jsonData": {
            "allowedHosts": [
                "https://raw.githubusercontent.com",
                API_BASE,
            ],
            "tlsSkipVerify": False,
        },
    }
    st, existing = api("GET", f"/api/datasources/uid/{DS_UID}")
    if st == 200 and existing.get("id"):
        payload["id"] = existing["id"]
        st, res = api("PUT", f"/api/datasources/uid/{DS_UID}", payload)
        print(f"  datasource updated ({DS_UID}) -> {st}")
    else:
        st, res = api("POST", "/api/datasources", payload)
        if st in (409,):  # exists by name
            print(f"  datasource already present ({DS_UID})")
        else:
            print(f"  datasource created ({DS_UID}) -> {st}")
    # Fall back to a pre-existing managed Infinity DS if creation was refused.
    st, check = api("GET", f"/api/datasources/uid/{DS_UID}")
    if st == 200 and check.get("uid"):
        return DS_UID
    st, allds = api("GET", "/api/datasources")
    for d in (allds if isinstance(allds, list) else []):
        if d.get("type") == "yesoreyeram-infinity-datasource":
            print(f"  falling back to existing Infinity DS: {d['uid']}")
            return d["uid"]
    return DS_UID


def import_dashboard(path, ds_uid):
    with open(path) as f:
        dash = json.load(f)
    # Wire the datasource + base URL into the dashboard's variables.
    for v in dash.get("templating", {}).get("list", []):
        if v["name"] == "darkmoon_ds":
            v["current"] = {"text": ds_uid, "value": ds_uid}
        if v["name"] == "darkmoon_url":
            v["current"] = {"text": API_BASE, "value": API_BASE}
            v["query"] = API_BASE
    dash["id"] = None
    body = {"dashboard": dash, "overwrite": True, "folderUid": "",
            "message": "Provisioned by darkmoon-grafana deploy"}
    st, res = api("POST", "/api/dashboards/db", body)
    if st == 200:
        print(f"  dashboard imported: {res.get('uid')} (v{res.get('version')}) "
              f"{URL}{res.get('url','')}")
        return res.get("url")
    print(f"  dashboard import FAILED {st}: {json.dumps(res)[:200]}")
    return None


def main():
    print(f"Deploying to {URL} (Darkmoon base: {API_BASE})")
    st, org = api("GET", "/api/org")
    print(f"  org: {org.get('name')} (auth {st})")
    ds_uid = ensure_infinity_ds()
    urls = []
    if os.environ.get("DEPLOY_DEMO", "1") == "1":
        u = import_dashboard(os.path.join(ROOT, "dashboards",
                                          "darkmoon-security-posture-demo.json"), ds_uid)
        if u:
            urls.append(u)
    if os.environ.get("DEPLOY_PROD", "0") == "1":
        u = import_dashboard(os.path.join(ROOT, "dashboards",
                                          "darkmoon-security-posture.json"), ds_uid)
        if u:
            urls.append(u)
    print("DONE. Dashboard URLs:")
    for u in urls:
        print("  " + URL + u)


if __name__ == "__main__":
    main()
