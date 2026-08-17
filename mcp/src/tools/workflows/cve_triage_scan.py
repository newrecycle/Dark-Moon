"""
CVE Triage Scan Workflow

Combines two layers:

  1. LOCAL nuclei CVE DETECTION  -- ALWAYS runs, offline, privacy-gateway-safe.
     Uses the pinned/fresh nuclei-templates `http/cves` category. Nuclei
     templates self-select via their own matchers, so this is inherently
     targeted to the fingerprint (no blind full-corpus sweep), satisfying the
     platform rule that CVE checks must be fingerprint-justified.

  2. LIVE cvemap TRIAGE           -- runs ONLY when the toolbox container has
     outbound internet egress. cvemap (projectdiscovery/cvemap, shipped as the
     `vulnx` binary) enriches confirmed CVEs with EPSS score + CISA KEV
     ("actively exploited") status, and surfaces CVEs that match the
     fingerprinted stack but have NO nuclei detection template yet
     (intel-only, clearly marked unconfirmed).

No Shodan integration. No external call ever carries the target host/IP --
cvemap is queried by product name or CVE ID only.
"""

import re
from typing import Dict, Any, List

from src.tools.workflows.base import BaseWorkflow

_CVE_RE = re.compile(r"CVE-\d{4}-\d{1,7}", re.I)

# Curated product tokens fed to `cvemap -product` (fingerprint -> CVEs).
# whatweb output is scanned case-insensitively for these substrings.
_PRODUCT_TOKENS = [
    "apache", "nginx", "microsoft-iis", "tomcat", "jetty", "httpd",
    "wordpress", "drupal", "joomla", "magento", "prestashop", "moodle",
    "spring", "django", "flask", "express", "rails", "ruby",
    "php", "node.js", "openssl", "openssh", "proftpd", "vsftpd",
    "jenkins", "gitlab", "grafana", "kibana", "elasticsearch", "redis",
    "mysql", "postgresql", "mongodb", "rabbitmq", "apache-activemq",
]


class CveTriageScanWorkflow(BaseWorkflow):
    """
    Local nuclei CVE detection (always) + conditional live cvemap triage.
    """

    def triage_cves(
        self,
        targets: List[str],
        severity: str = "critical,high",
        template_type: str = "cves",
        enable_egress_triage: bool = True,
        max_enrich_cves: int = 40,
        timeout: int = 900,
    ) -> Dict[str, Any]:
        """
        Detect CVEs with nuclei (always) and triage them with cvemap when egress exists.

        Args:
            targets: List of URLs/hosts to scan.
            severity: Comma-separated nuclei severities (critical,high,medium,low,info).
            template_type: nuclei template category (cves, exposures, misconfigs, all).
            enable_egress_triage: Run live cvemap triage when egress is detected.
            max_enrich_cves: Cap on per-CVE cvemap enrichment calls (bounds runtime).
            timeout: Total timeout in seconds.

        Returns:
            Structured result: confirmed (enriched) findings + intel-only CVEs.
        """
        first = targets[0] if targets else "unknown"
        safe = first.replace("https://", "").replace("http://", "").replace("/", "_").replace(":", "_")
        ws = f"/opt/darkmoon/out/cve_triage_{safe}"
        self.execute_step("Create workspace", f"mkdir -p {ws}", timeout=10, parse_json=False)

        tf = f"{ws}/targets.txt"
        escaped = [t.replace("'", "'\\''") for t in targets]
        self.docker_client.execute_command(
            f"echo '{chr(10).join(escaped)}' > {tf}", timeout=10
        )

        scan_timeout = int(timeout * 0.6)
        triage_timeout = int(timeout * 0.35)

        # ---------------------------------------------------------------
        # STEP 1 -- ALWAYS: nuclei CVE detection (local, gateway-safe)
        # ---------------------------------------------------------------
        template_paths = {
            "cves": "~/nuclei-templates/http/cves",
            "exposures": "~/nuclei-templates/http/exposures",
            "misconfigs": "~/nuclei-templates/http/misconfiguration",
            "all": "~/nuclei-templates/http",
        }
        template_path = template_paths.get(template_type, "~/nuclei-templates/http/cves")
        nuclei_out = f"{ws}/nuclei_cves.json"
        ok, findings, _ = self.execute_step(
            step_name=f"Nuclei CVE detection ({len(targets)} targets, sev {severity})",
            command=(
                f"nuclei -list {tf} -severity {severity} -t {template_path} "
                f"-jsonl -silent -o {nuclei_out}; "
                f"test -f {nuclei_out} && cat {nuclei_out} || echo ''"
            ),
            timeout=scan_timeout,
        )

        confirmed_cve_ids = set()
        for f in findings:
            blob = " ".join(str(f.get(k, "")) for k in ("templateID", "template", "type"))
            blob += " " + str(f.get("info", {}).get("name", ""))
            for m in _CVE_RE.findall(blob):
                confirmed_cve_ids.add(m.upper())

        # ---------------------------------------------------------------
        # STEP 2 -- Fingerprint (product tokens for cvemap -product)
        # ---------------------------------------------------------------
        fingerprint_products = self._fingerprint(targets, scan_timeout)

        # ---------------------------------------------------------------
        # STEP 3 -- CONDITIONAL: cvemap triage when egress exists
        # ---------------------------------------------------------------
        egress = False
        enrichment: Dict[str, Dict[str, Any]] = {}
        intel_only: List[Dict[str, Any]] = []
        if enable_egress_triage:
            egress = self._probe_egress()
            if egress:
                enrichment = self._enrich_cves(
                    sorted(confirmed_cve_ids), max_enrich_cves, triage_timeout
                )
                intel_only = self._product_triage(
                    fingerprint_products, confirmed_cve_ids, triage_timeout
                )

        # Attach triage metadata to confirmed findings
        for f in findings:
            blob = " ".join(str(f.get(k, "")) for k in ("templateID", "template", "type"))
            blob += " " + str(f.get("info", {}).get("name", ""))
            cids = {c.upper() for c in _CVE_RE.findall(blob)}
            meta = {c: enrichment[c] for c in cids if c in enrichment}
            if meta:
                f.setdefault("cvemap_triage", meta)

        sev = self.count_by_severity(findings)
        top = [f.get("info", {}).get("name", "") for f in findings[:10] if f.get("info", {}).get("name")]

        steps = {
            "nuclei_cve_detection": {
                "success": ok,
                "cves_confirmed": len(findings),
                "confirmed_cve_ids": sorted(confirmed_cve_ids),
                "severity_breakdown": sev,
            },
            "cvemap_triage": {
                "egress_available": egress,
                "enriched_cve_count": len(enrichment),
                "intel_only_cve_count": len(intel_only),
                "intel_only_cves": intel_only[:50],
            },
        }

        summary = {
            "total_confirmed": len(findings),
            "critical_findings": sev.get("critical", 0),
            "affected_hosts": len({f.get("host", "") for f in findings if f.get("host")}),
            "egress_used": egress,
            "intel_only_cves": len(intel_only),
            "top_vulns": top,
            "note": (
                "confirmed = nuclei detection template matched on target. "
                "intel_only = cvemap-flagged for this stack but NO nuclei template "
                "confirmed on target (unverified). cvemap triage requires container egress."
            ),
        }

        return self.create_result_dict("triage_cves", targets, steps, summary)

    # ------------------------------------------------------------------
    def _fingerprint(self, targets: List[str], timeout: int) -> List[str]:
        """Run whatweb to extract product tokens for product-based cvemap triage."""
        joined = " ".join(f'"{t}"' for t in targets)
        _, _, raw = self.execute_step(
            step_name="Fingerprint stack (whatweb)",
            command=f"whatweb -a 1 -q {joined} 2>/dev/null",
            timeout=timeout,
        )
        if not raw:
            return []
        low = raw.lower()
        return sorted({tok for tok in _PRODUCT_TOKENS if tok.lower() in low})

    def _probe_egress(self) -> bool:
        """Lightweight connectivity probe to the NVD host cvemap queries."""
        # -w prints EGRESS_OK on any HTTP response (even 403); NO_EGRESS on failure.
        cmd = (
            "curl -sS --max-time 6 -o /dev/null -w 'EGRESS_OK' "
            "'https://services.nvd.nist.gov/rest/json/cves/2.0?resultsPerPage=1' "
            "2>/dev/null || echo NO_EGRESS"
        )
        _, _, raw = self.execute_step(
            step_name="Probe outbound egress (NVD)",
            command=cmd,
            timeout=20,
            parse_json=False,
        )
        return "EGRESS_OK" in raw

    def _enrich_cves(
        self, cve_ids: List[str], max_n: int, timeout: int
    ) -> Dict[str, Dict[str, Any]]:
        """Query `cvemap -cve` for EPSS/KEV per confirmed CVE (bounded)."""
        out: Dict[str, Dict[str, Any]] = {}
        per = max(8, timeout // max(1, min(len(cve_ids), max_n)))
        for cid in cve_ids[:max_n]:
            _, _, raw = self.execute_step(
                step_name=f"cvemap triage {cid}",
                command=f"vulnx -cve {cid} 2>/dev/null",
                timeout=per,
                parse_json=False,
            )
            if not raw:
                continue
            epss = re.search(r"EPSS[^\d]*([0-9]*\.?[0-9]+)", raw, re.I)
            kevm = re.search(r"KEV\s*:\s*(yes|true|no|false)", raw, re.I)
            poc = bool(re.search(r"POC|exploit", raw, re.I))
            out[cid] = {
                "epss": float(epss.group(1)) if epss else None,
                "kev": bool(kevm and kevm.group(1).lower() in ("yes", "true")),
                "poc": poc,
            }
        return out

    def _product_triage(
        self, products: List[str], confirmed: set, timeout: int
    ) -> List[Dict[str, Any]]:
        """For each fingerprinted product, list cvemap CVEs lacking a nuclei match."""
        intel: List[Dict[str, Any]] = []
        per = max(10, timeout // max(1, len(products))) if products else timeout
        for p in products:
            _, _, raw = self.execute_step(
                step_name=f"cvemap product {p}",
                command=f"vulnx -product {p} 2>/dev/null",
                timeout=per,
                parse_json=False,
            )
            if not raw:
                continue
            for cid in _CVE_RE.findall(raw):
                cid = cid.upper()
                if cid not in confirmed:
                    intel.append({"cve": cid, "product": p, "status": "intel_only_unconfirmed"})
        seen = set()
        uniq = []
        for i in intel:
            if i["cve"] in seen:
                continue
            seen.add(i["cve"])
            uniq.append(i)
        return uniq
