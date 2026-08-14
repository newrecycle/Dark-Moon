"""
Kubernetes Security Audit Workflow

Kubernetes security audit and misconfiguration detection.
Uses kubescape, kubectl, kubeletctl, and RBAC analysis for comprehensive assessment.
"""

from typing import Dict, Any, Optional
from src.tools.workflows.base import BaseWorkflow


class KubernetesAuditWorkflow(BaseWorkflow):
    """
    Kubernetes security audit and misconfiguration detection.

    Use cases:
    - Kubernetes security assessment
    - Compliance checking (NSA, MITRE)
    - RBAC privilege analysis
    - Kubelet vulnerability testing
    """

    def audit_kubernetes(
        self,
        kubeconfig: Optional[str] = None,
        scan_type: str = "quick",
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """
        Kubernetes security audit and misconfiguration detection.

        Workflow:
        1. Kubescape security scan (300s)
        2. kubectl resource enumeration (120s)
        3. kubeletctl anonymous access test (120s)
        4. RBAC analysis (60s)

        Args:
            kubeconfig: Path to kubeconfig file (optional, uses in-cluster if not provided)
            scan_type: Scan depth (quick=NSA+MITRE, thorough=all frameworks)
            timeout: Total timeout in seconds (default: 600s)

        Returns:
            K8s audit results with compliance score, findings, and immediate actions
        """
        steps = {}

        # ========================================
        # Calculate timeout distribution
        # ========================================
        setup_timeout = 10
        remaining_timeout = max(timeout - setup_timeout, 120)

        # Distribution: kubescape 45%, kubectl 15%, kubelet 25%, rbac 15%
        kubescape_timeout = int(remaining_timeout * 0.45)
        kubectl_timeout = int(remaining_timeout * 0.15)
        kubelet_timeout = int(remaining_timeout * 0.25)
        rbac_timeout = remaining_timeout - kubescape_timeout - kubectl_timeout - kubelet_timeout

        workspace_dir = "/opt/darkmoon/out/kubernetes_audit"

        # ========================================
        # STEP 0: Create workspace
        # ========================================
        self.execute_step(
            step_name="Create workspace",
            command=f"mkdir -p {workspace_dir}",
            timeout=setup_timeout,
            parse_json=False,
        )

        # Set up kubeconfig environment variable if provided (escape path)
        if kubeconfig:
            escaped_kubeconfig = kubeconfig.replace("'", "'\\''")
            env_prefix = f"export KUBECONFIG='{escaped_kubeconfig}' && "
        else:
            env_prefix = ""

        # ========================================
        # STEP 1: Kubescape security scan
        # ========================================
        kubescape_output = f"{workspace_dir}/kubescape_output.json"

        if scan_type == "thorough":
            frameworks = "all"
        else:
            frameworks = "nsa,mitre"

        success, findings, output = self.execute_step(
            step_name=f"Kubescape security scan ({scan_type})",
            command=f"{env_prefix}kubescape scan framework {frameworks} --format json --output {kubescape_output} && cat {kubescape_output}",
            timeout=kubescape_timeout,
            parse_json=True,
        )

        # Parse kubescape results
        total_findings = len(findings) if findings else 0
        severity_breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        compliance_score = 100

        # Simplified parsing (adjust based on actual kubescape output format)
        if findings:
            for finding in findings:
                severity = finding.get("severity", "").lower()
                if severity in severity_breakdown:
                    severity_breakdown[severity] += 1

            # Extract compliance score if available
            if isinstance(findings, list) and len(findings) > 0:
                first_finding = findings[0]
                if isinstance(first_finding, dict):
                    compliance_score = first_finding.get("complianceScore", 100)

        top_issues = findings[:10] if findings else []  # Top 10

        steps["kubescape_scan"] = {
            "success": success,
            "findings": total_findings,
            "by_severity": severity_breakdown,
            "compliance_score": compliance_score,
            "frameworks": frameworks.split(","),
            "top_issues": top_issues,
        }

        # ========================================
        # STEP 2: kubectl resource enumeration
        # ========================================
        resource_commands = [
            f"{env_prefix}kubectl get namespaces --no-headers | wc -l",
            f"{env_prefix}kubectl get pods --all-namespaces --no-headers | wc -l",
            f"{env_prefix}kubectl get secrets --all-namespaces --no-headers | wc -l",
            f"{env_prefix}kubectl get services --all-namespaces --no-headers | wc -l",
        ]

        resource_output_file = f"{workspace_dir}/resources.txt"
        combined_command = " && ".join(resource_commands) + f" > {resource_output_file} 2>&1 && cat {resource_output_file}"

        success, findings, output = self.execute_step(
            step_name="kubectl resource enumeration",
            command=combined_command,
            timeout=kubectl_timeout,
            parse_json=False,
        )

        # Parse counts from output
        lines = output.strip().split("\n")
        namespaces = int(lines[0].strip()) if len(lines) > 0 and lines[0].strip().isdigit() else 0
        pods = int(lines[1].strip()) if len(lines) > 1 and lines[1].strip().isdigit() else 0
        secrets = int(lines[2].strip()) if len(lines) > 2 and lines[2].strip().isdigit() else 0
        services = int(lines[3].strip()) if len(lines) > 3 and lines[3].strip().isdigit() else 0

        steps["resource_enum"] = {
            "success": success,
            "namespaces": namespaces,
            "pods": pods,
            "secrets": secrets,
            "services": services,
        }

        # ========================================
        # STEP 3: kubeletctl anonymous access test
        # ========================================
        # Calculate per-node timeout (test max 3 nodes)
        node_fetch_timeout = 30
        per_node_timeout = max((kubelet_timeout - node_fetch_timeout) // 3, 30)

        # Get node IPs first
        node_ips_output = f"{workspace_dir}/node_ips.txt"
        success, findings, output = self.execute_step(
            step_name="Get node IPs for kubelet testing",
            command=f"{env_prefix}kubectl get nodes -o jsonpath='{{.items[*].status.addresses[?(@.type==\"InternalIP\")].address}}' > {node_ips_output} && cat {node_ips_output}",
            timeout=node_fetch_timeout,
            parse_json=False,
        )

        node_ips = output.strip().split() if output.strip() else []

        # Test kubelet on first 3 nodes (to save time)
        vulnerable_nodes = []
        anonymous_access = False

        if node_ips:
            for node_ip in node_ips[:3]:
                # Validate node_ip format (basic check)
                if not all(c.isdigit() or c == '.' for c in node_ip):
                    continue

                kubelet_test_output = f"{workspace_dir}/kubelet_{node_ip}.txt"
                success, findings, output = self.execute_step(
                    step_name=f"Kubelet anonymous access test ({node_ip})",
                    command=f"kubeletctl scan rce --server {node_ip} > {kubelet_test_output} 2>&1 && cat {kubelet_test_output}",
                    timeout=per_node_timeout,
                    parse_json=False,
                    print_progress=False,
                )

                if success and ("vulnerable" in output.lower() or "anonymous" in output.lower()):
                    vulnerable_nodes.append(node_ip)
                    anonymous_access = True

        steps["kubelet_test"] = {
            "success": True,
            "anonymous_access": anonymous_access,
            "vulnerable_nodes": len(vulnerable_nodes),
            "node_ips": vulnerable_nodes,
        }

        # ========================================
        # STEP 4: RBAC analysis
        # ========================================
        rbac_output = f"{workspace_dir}/rbac_bindings.json"
        success, findings, output = self.execute_step(
            step_name="RBAC analysis",
            command=f"{env_prefix}kubectl get clusterrolebindings -o json > {rbac_output} && cat {rbac_output}",
            timeout=rbac_timeout,
            parse_json=True,
        )

        # Parse RBAC bindings
        cluster_admin_users = 0
        overprivileged_sa = 0
        risky_bindings = []

        if findings and isinstance(findings, list):
            for binding in findings:
                if isinstance(binding, dict):
                    role_ref = binding.get("roleRef", {})
                    if role_ref.get("name") == "cluster-admin":
                        cluster_admin_users += 1
                        risky_bindings.append(binding.get("metadata", {}).get("name", "unknown"))

        steps["rbac_analysis"] = {
            "success": success,
            "cluster_admin_users": cluster_admin_users,
            "overprivileged_sa": overprivileged_sa,
            "risky_bindings": risky_bindings[:10],  # Top 10
        }

        # ========================================
        # SUMMARY
        # ========================================
        immediate_actions = []

        if anonymous_access:
            immediate_actions.append(f"Fix anonymous kubelet access on {len(vulnerable_nodes)} nodes")

        if cluster_admin_users > 3:
            immediate_actions.append("Review cluster-admin bindings")

        if severity_breakdown.get("critical", 0) > 0:
            immediate_actions.append(f"Address {severity_breakdown['critical']} critical kubescape findings")

        summary = {
            "total_findings": total_findings,
            "critical_issues": severity_breakdown.get("critical", 0),
            "compliance_score": compliance_score,
            "anonymous_kubelet_access": anonymous_access,
            "cluster_admin_count": cluster_admin_users,
            "immediate_actions": immediate_actions,
        }

        return self.create_result_dict(
            workflow_name="audit_kubernetes",
            target="Kubernetes Cluster",
            steps=steps,
            summary=summary,
        )
