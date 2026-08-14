"""
Web Crawler Workflow

Fast web crawling for URL and endpoint discovery.
Uses katana for crawling and optional waybackurls for historical URLs.
"""

from typing import Dict, Any, List
from src.tools.workflows.base import BaseWorkflow


class WebCrawlerWorkflow(BaseWorkflow):
    """
    Fast web crawling for URL and endpoint discovery.

    Use cases:
    - URL discovery
    - API endpoint enumeration
    - Attack surface expansion
    """

    def crawl_website(
        self,
        urls: List[str],
        depth: int = 3,
        include_wayback: bool = True,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """
        Fast web crawling for URL and endpoint discovery.

        Workflow:
        1. Katana web crawling (240s)
        2. Optional: Waybackurls historical discovery (60s)

        Args:
            urls: Starting URLs for crawling
            depth: Crawl depth (default: 3)
            include_wayback: Include Wayback Machine URLs (default: True)
            timeout: Total timeout in seconds (default: 300s)

        Returns:
            Crawl results with discovered URLs and endpoints
        """
        steps = {}

        # ========================================
        # Calculate timeout distribution
        # ========================================
        setup_timeout = 10
        remaining_timeout = max(timeout - setup_timeout, 60)
        if include_wayback:
            katana_timeout = int(remaining_timeout * 0.75)  # 75% for crawling
            wayback_timeout = remaining_timeout - katana_timeout  # 25% for wayback
        else:
            katana_timeout = remaining_timeout
            wayback_timeout = 0

        # Create a safe workspace name from first URL
        first_url = urls[0] if urls else "unknown"
        safe_url = first_url.replace("https://", "").replace("http://", "").replace("/", "_").replace(":", "_")
        workspace_dir = f"/opt/darkmoon/out/web_crawler_{safe_url}"

        # ========================================
        # STEP 0: Create workspace
        # ========================================
        self.execute_step(
            step_name="Create workspace",
            command=f"mkdir -p {workspace_dir}",
            timeout=setup_timeout,
            parse_json=False,
        )

        # Write starting URLs to file (escape single quotes)
        urls_file = f"{workspace_dir}/start_urls.txt"
        escaped_urls = [u.replace("'", "'\\''") for u in urls]
        self.docker_client.execute_command(
            f"echo '{chr(10).join(escaped_urls)}' > {urls_file}",
            timeout=setup_timeout
        )

        # ========================================
        # STEP 1: Katana web crawling
        # ========================================
        katana_output = f"{workspace_dir}/katana_output.json"
        success, findings, output = self.execute_step(
            step_name=f"Katana web crawling ({len(urls)} starting URLs, depth {depth})",
            command=f"katana -list {urls_file} -d {depth} -j -eof raw,body,timestamp,date,content_length,headers -silent -o {katana_output} && cat {katana_output}",
            timeout=katana_timeout,
            parse_json=True,
        )

        # Extract endpoints from katana findings
        discovered_urls = []
        endpoints = []

        for finding in findings:
            url = finding.get("url", "")
            if url:
                discovered_urls.append(url)

                # Extract path/endpoint
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    if parsed.path and parsed.path != "/":
                        endpoints.append(parsed.path)
                except Exception:
                    pass

        steps["katana_crawl"] = {
            "success": success,
            "urls_discovered": len(discovered_urls),
            "endpoints": list(set(endpoints))[:50],  # Top 50 unique endpoints
            "findings": findings,
        }

        # ========================================
        # STEP 2: Optional Waybackurls
        # ========================================
        wayback_urls = []

        if include_wayback:
            # Extract domain from first URL
            try:
                from urllib.parse import urlparse
                parsed = urlparse(urls[0])
                domain = parsed.netloc
            except Exception:
                domain = urls[0].replace("https://", "").replace("http://", "").split("/")[0]

            wayback_output = f"{workspace_dir}/wayback_output.txt"
            # Escape domain for shell safety
            escaped_domain = domain.replace("'", "'\\''")
            success, findings, output = self.execute_step(
                step_name=f"Wayback URLs for {domain}",
                command=f"waybackurls '{escaped_domain}' > {wayback_output} && cat {wayback_output}",
                timeout=wayback_timeout,
                parse_json=False,
            )

            # Parse wayback URLs (one per line)
            wayback_urls = [line.strip() for line in output.strip().split("\n") if line.strip()]

            steps["wayback_urls"] = {
                "success": success,
                "historical_urls": len(wayback_urls),
                "urls": wayback_urls[:50],  # Top 50 to save tokens
            }
        else:
            steps["wayback_urls"] = {
                "success": True,
                "historical_urls": 0,
                "urls": [],
            }

        # ========================================
        # SUMMARY
        # ========================================
        # Categorize endpoints
        api_endpoints = [ep for ep in endpoints if "/api" in ep.lower()]
        js_files = [ep for ep in endpoints if ep.endswith(".js")]
        interesting_paths = [ep for ep in endpoints if any(keyword in ep.lower() for keyword in ["/admin", "/api", "/backup", "/config", "/dashboard"])]

        total_urls = len(discovered_urls) + len(wayback_urls)
        unique_endpoints = list(set(endpoints))

        summary = {
            "total_urls": total_urls,
            "api_endpoints": len(api_endpoints),
            "js_files": len(js_files),
            "interesting_paths": interesting_paths[:20],  # Top 20
            "unique_endpoints": unique_endpoints[:50],  # Top 50
        }

        return self.create_result_dict(
            workflow_name="crawl_website",
            target=urls,
            steps=steps,
            summary=summary,
        )
