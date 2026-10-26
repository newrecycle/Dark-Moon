"""Metadata-only SIEM polling. Writes JSONL locally; never sends to a third party."""
import argparse
import json
import os
import urllib.request
from pathlib import Path
from .store import Store


def export(url, token, output):
    request = urllib.request.Request(url.rstrip("/") + "/api/v1/integrations/findings",
                                     headers={"Authorization": "Bearer " + token})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        content = response.read(16 * 1024 * 1024 + 1)
    if len(content) > 16 * 1024 * 1024:
        raise ValueError("Metadata response exceeds 16 MiB")
    findings = json.loads(content)
    allowed = {"id", "campaign_id", "severity", "status", "category", "mitre_attack_id", "iso27001_control"}
    with Path(output).open("w", encoding="utf-8") as stream:
        os.chmod(output, 0o600)
        for finding in findings:
            stream.write(json.dumps({key: value for key, value in finding.items() if key in allowed}) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8780")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    token = os.environ.get("DARKMOON_DASHBOARD_TOKEN") or (Store().root / "access-token").read_text().strip()
    export(args.url, token, args.output)


if __name__ == "__main__":
    main()
