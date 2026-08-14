"""
Subdomain Discovery Workflow

Fast subdomain enumeration with live host verification.
Uses subfinder for passive enumeration and httpx for live host probing.
"""

from typing import Dict, Any
from src.tools.workflows.base import BaseWorkflow


class SubdomainDiscoveryWorkflow(BaseWorkflow):
    """
    Fast subdomain discovery and live host verification.

    Use cases:
    - Initial reconnaissance
    - Attack surface mapping
    - Target expansion
    """

    def discover_subdomains(
        self,
        domain: str,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """
        Discover subdomains and verify live hosts.

        Workflow:
        1. Subfinder passive enumeration (180s)
        2. httpx live host probing (120s)

        Args:
            domain: Target domain (e.g., "example.com")
            timeout: Total timeout in seconds (default: 300s)

        Returns:
            Subdomain enumeration results with live hosts
        """
        steps = {}

        # ========================================
        # Calculate timeout distribution
        # ========================================
        setup_timeout = 10
        remaining_timeout = max(timeout - setup_timeout, 60)
        subfinder_timeout = int(remaining_timeout * 0.6)  # 60% for subdomain enum
        httpx_timeout = remaining_timeout - subfinder_timeout  # 40% for live probing

        # Sanitize domain for workspace name
        safe_domain = domain.replace("'", "").replace(";", "").replace("&", "")
        workspace_dir = f"/opt/darkmoon/out/subdomain_discovery_{safe_domain}"

        # ========================================
        # STEP 0: Create workspace
        # ========================================
        self.execute_step(
            step_name="Create workspace",
            command=f"mkdir -p {workspace_dir}",
            timeout=setup_timeout,
            parse_json=False,
        )

        # ========================================
        # STEP 1: Subfinder enumeration
        # ========================================
        # Escape domain for shell safety
        escaped_domain = domain.replace("'", "'\\''")
        subfinder_output = f"{workspace_dir}/subdomains.txt"
        success, findings, output = self.execute_step(
            step_name=f"Subdomain enumeration for {domain}",
            command=f"subfinder -d '{escaped_domain}' -silent -o {subfinder_output} && cat {subfinder_output}",
            timeout=subfinder_timeout,
            parse_json=False,
        )

        # Parse subdomains (one per line)
        subdomains = [line.strip() for line in output.strip().split("\n") if line.strip()]

        steps["subdomain_enum"] = {
            "success": success,
            "subdomains_found": len(subdomains),
            "unique_domains": subdomains,
        }

        # ========================================
        # STEP 2: httpx live probing
        # ========================================
        live_urls = []

        if subdomains:
            # Write subdomains to file for httpx (already discovered, safe)
            httpx_input = f"{workspace_dir}/httpx_input.txt"
            self.docker_client.execute_command(
                f"echo '{chr(10).join(subdomains)}' > {httpx_input}",
                timeout=setup_timeout
            )

            httpx_output = f"{workspace_dir}/httpx_output.json"
            success, findings, output = self.execute_step(
                step_name=f"Live host probing ({len(subdomains)} targets)",
                command=f"httpx -l {httpx_input} -mc 200,201,301,302,303,307,308,401,403 -json -silent -o {httpx_output} && cat {httpx_output}",
                timeout=httpx_timeout,
                parse_json=True,
            )

            # Analyze results
            live_hosts = len(findings)
            by_status = {}

            for finding in findings:
                status = finding.get("status_code", "unknown")
                by_status[str(status)] = by_status.get(str(status), 0) + 1

                url = finding.get("url", "")
                if url:
                    live_urls.append(url)

            steps["live_probe"] = {
                "success": success,
                "live_hosts": live_hosts,
                "by_status": by_status,
                "findings": findings,
            }
        else:
            steps["live_probe"] = {
                "success": False,
                "live_hosts": 0,
                "error": "No subdomains found to probe",
            }

        # ========================================
        # SUMMARY
        # ========================================
        summary = {
            "total_subdomains": len(subdomains),
            "live_hosts": steps["live_probe"].get("live_hosts", 0),
            "live_urls": live_urls[:20],  # Top 20 to save tokens
            "subdomain_list": subdomains[:50],  # Top 50 to save tokens
        }

        return self.create_result_dict(
            workflow_name="discover_subdomains",
            target=domain,
            steps=steps,
            summary=summary,
        )
