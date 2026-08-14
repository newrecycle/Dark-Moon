"""
TEMPLATE DE WORKFLOW - Copier ce fichier pour créer un nouveau workflow

Instructions :
1. Copier ce fichier et renommer (ex: ad_pentest.py)
2. Renommer la classe (ex: ADPentestWorkflow)
3. Implémenter vos méthodes de workflow
4. Utiliser self.execute_step() pour chaque commande
5. Importer dans server.py et exposer via @mcp.tool()

Exemple d'utilisation :
    workflow = MyWorkflow(docker_client)
    result = workflow.my_scan(target="example.com")
"""

from typing import List, Optional, Dict, Any
from src.tools.workflows.base import BaseWorkflow


class MyWorkflow(BaseWorkflow):
    """
    Description de votre workflow.

    Use cases:
    - Cas d'usage 1
    - Cas d'usage 2
    """

    def my_scan(
        self,
        target: str,
        # Ajoutez vos paramètres ici
        timeout: int = 1200,
    ) -> Dict[str, Any]:
        """
        Description de votre workflow.

        Workflow:
        1. Étape 1 : Description
        2. Étape 2 : Description
        3. Étape 3 : Description

        Args:
            target: Cible à scanner
            timeout: Timeout total en secondes

        Returns:
            Résultats du workflow
        """
        steps = {}

        # ========================================
        # ÉTAPE 1 : Description de l'étape
        # ========================================
        success, findings, output = self.execute_step(
            step_name="Description de l'étape",
            command=f"outil -flag {target}",
            timeout=timeout // 3,
            parse_json=True,  # True si l'outil retourne du JSON
        )

        steps["step1"] = {
            "success": success,
            "findings_count": len(findings),
            "findings": findings,
            # Ajoutez d'autres infos pertinentes
        }

        # ========================================
        # ÉTAPE 2 : Description de l'étape
        # ========================================
        success, findings, output = self.execute_step(
            step_name="Description de l'étape 2",
            command=f"autre_outil --option {target}",
            timeout=timeout // 3,
            parse_json=False,  # False si output texte brut
        )

        steps["step2"] = {
            "success": success,
            "raw_output": output,
        }

        # ========================================
        # ÉTAPE 3 : Description de l'étape (optionnelle)
        # ========================================
        # Vous pouvez avoir autant d'étapes que nécessaire

        # ========================================
        # RÉSUMÉ FINAL
        # ========================================
        summary = {
            "total_findings": steps["step1"]["findings_count"],
            "step2_success": steps["step2"]["success"],
            # Ajoutez vos métriques clés
        }

        return self.create_result_dict(
            workflow_name="my_scan",
            target=target,
            steps=steps,
            summary=summary,
        )

    # ========================================
    # MÉTHODES HELPERS (optionnel)
    # ========================================

    def _custom_parser(self, output: str) -> List[Dict[str, Any]]:
        """
        Parser personnalisé si l'outil ne retourne pas du JSON standard.

        Args:
            output: Output brut de l'outil

        Returns:
            Liste de findings parsés
        """
        # Votre logique de parsing
        findings = []
        # ...
        return findings


# ============================================================================
# EXEMPLES DE WORKFLOWS RÉELS
# ============================================================================


class ADPentestWorkflow(BaseWorkflow):
    """
    Exemple : Workflow Active Directory pentest.
    """

    def ad_enumeration(
        self,
        target: str,
        domain: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 1800,
    ) -> Dict[str, Any]:
        """
        Énumération Active Directory complète.

        Workflow:
        1. NetExec SMB enumeration
        2. BloodHound data collection
        3. Kerberoasting
        4. AS-REP Roasting

        Args:
            target: DC IP ou hostname
            domain: Nom du domaine
            username: Username (optionnel)
            password: Password (optionnel)
            timeout: Timeout total

        Returns:
            Résultats du pentest AD
        """
        steps = {}
        auth = f"-u {username} -p {password}" if username and password else ""

        # Étape 1: SMB Enumeration
        success, findings, output = self.execute_step(
            step_name="NetExec SMB enumeration",
            command=f"netexec smb {target} {auth} --shares --users",
            timeout=timeout // 4,
            parse_json=False,
        )
        steps["smb_enum"] = {"success": success, "output": output}

        # Étape 2: BloodHound
        if username and password:
            success, findings, output = self.execute_step(
                step_name="BloodHound data collection",
                command=f"bloodhound-python -d {domain} -u {username} -p {password} -ns {target} -c All",
                timeout=timeout // 4,
                parse_json=False,
            )
            steps["bloodhound"] = {"success": success, "output": output}

        # Étape 3: Kerberoasting
        success, findings, output = self.execute_step(
            step_name="Kerberoasting",
            command=f"GetUserSPNs.py {domain}/{username}:{password} -dc-ip {target} -request",
            timeout=timeout // 4,
            parse_json=False,
        )
        steps["kerberoasting"] = {"success": success, "output": output}

        # Résumé
        summary = {
            "smb_enum_success": steps["smb_enum"]["success"],
            "bloodhound_success": steps.get("bloodhound", {}).get("success", False),
            "kerberoasting_success": steps["kerberoasting"]["success"],
        }

        return self.create_result_dict("ad_enumeration", target, steps, summary)


class K8sAuditWorkflow(BaseWorkflow):
    """
    Exemple : Workflow audit sécurité Kubernetes.
    """

    def k8s_security_audit(
        self,
        kubeconfig: Optional[str] = None,
        timeout: int = 1200,
    ) -> Dict[str, Any]:
        """
        Audit sécurité Kubernetes complet.

        Workflow:
        1. Kubescape security scan
        2. RBAC analysis with kubectl-who-can
        3. Network policy check

        Args:
            kubeconfig: Chemin vers kubeconfig (optionnel)
            timeout: Timeout total

        Returns:
            Résultats de l'audit K8s
        """
        steps = {}
        kube_env = f"KUBECONFIG={kubeconfig}" if kubeconfig else ""

        # Étape 1: Kubescape scan
        success, findings, output = self.execute_step(
            step_name="Kubescape security scan",
            command=f"{kube_env} kubescape scan --format json",
            timeout=timeout // 3,
            parse_json=True,
        )
        steps["kubescape"] = {
            "success": success,
            "findings_count": len(findings),
            "findings": findings,
        }

        # Étape 2: RBAC analysis
        success, findings, output = self.execute_step(
            step_name="RBAC who-can analysis",
            command=f"{kube_env} kubectl-who-can list '*' '*'",
            timeout=timeout // 3,
            parse_json=False,
        )
        steps["rbac_analysis"] = {"success": success, "output": output}

        # Résumé
        summary = {
            "total_kubescape_findings": steps["kubescape"]["findings_count"],
            "rbac_analyzed": steps["rbac_analysis"]["success"],
        }

        return self.create_result_dict("k8s_security_audit", "kubernetes-cluster", steps, summary)
