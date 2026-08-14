"""
Active Directory Enumeration Workflow

Active Directory enumeration with optional BloodHound collection.
Uses netexec for SMB, LDAP for directory queries, and bloodhound-python for graph data.
"""

from typing import Dict, Any, Optional
from src.tools.workflows.base import BaseWorkflow


class ADEnumerationWorkflow(BaseWorkflow):
    """
    Active Directory enumeration with optional BloodHound collection.

    Use cases:
    - AD reconnaissance
    - Domain enumeration
    - Attack path discovery with BloodHound
    """

    def enumerate_ad(
        self,
        dc_ip: str,
        domain: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        collect_bloodhound: bool = True,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """
        Active Directory enumeration with optional BloodHound collection.

        Workflow:
        1. NetExec SMB enumeration (180s)
        2. LDAP anonymous enumeration (120s)
        3. Optional: BloodHound data collection (300s)

        Args:
            dc_ip: Domain Controller IP address
            domain: Domain name (e.g., "CORP.LOCAL")
            username: Optional username for authenticated enumeration
            password: Optional password
            collect_bloodhound: Collect BloodHound data if creds provided (default: True)
            timeout: Total timeout in seconds (default: 600s)

        Returns:
            AD enumeration results with users, computers, shares, and optional BloodHound data
        """
        steps = {}

        # ========================================
        # Calculate timeout distribution
        # ========================================
        setup_timeout = 10
        remaining_timeout = max(timeout - setup_timeout, 120)
        has_credentials = username is not None and password is not None

        if has_credentials and collect_bloodhound:
            smb_timeout = int(remaining_timeout * 0.25)  # 25% for SMB
            ldap_timeout = int(remaining_timeout * 0.15)  # 15% for LDAP
            bloodhound_timeout = remaining_timeout - smb_timeout - ldap_timeout  # 60% for BloodHound
        else:
            smb_timeout = int(remaining_timeout * 0.5)  # 50% for SMB
            ldap_timeout = remaining_timeout - smb_timeout  # 50% for LDAP
            bloodhound_timeout = 0

        # Sanitize dc_ip for workspace
        safe_dc_ip = dc_ip.replace("'", "").replace(";", "").replace("&", "")
        workspace_dir = f"/opt/darkmoon/out/ad_enum_{safe_dc_ip.replace('.', '_')}"

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
        # STEP 1: NetExec SMB enumeration
        # ========================================
        # Escape credentials for shell safety
        if has_credentials:
            escaped_username = username.replace("'", "'\\''")
            escaped_password = password.replace("'", "'\\''")
            smb_command = f"netexec smb {dc_ip} -u '{escaped_username}' -p '{escaped_password}' --shares --users --groups"
        else:
            smb_command = f"netexec smb {dc_ip} --shares --users"

        smb_output_file = f"{workspace_dir}/netexec_output.txt"
        success, findings, output = self.execute_step(
            step_name=f"NetExec SMB enumeration ({'authenticated' if has_credentials else 'anonymous'})",
            command=f"{smb_command} > {smb_output_file} 2>&1 && cat {smb_output_file}",
            timeout=smb_timeout,
            parse_json=False,
        )

        # Parse SMB output (text-based parsing)
        shares = []
        users = []
        null_session = "NULL SESSION" in output.upper() or "STATUS_SUCCESS" in output

        # Simple parsing for shares and users
        for line in output.split("\n"):
            if "Share" in line or "SHARE" in line:
                # Extract share names (basic parsing)
                parts = line.split()
                if len(parts) > 1:
                    shares.append(parts[1])
            elif "User" in line or "USER" in line:
                # Extract usernames (basic parsing)
                parts = line.split()
                if len(parts) > 1:
                    users.append(parts[1])

        # Identify interesting shares (non-default)
        default_shares = ["ADMIN$", "C$", "IPC$", "NETLOGON", "SYSVOL"]
        interesting_shares = [s for s in shares if s not in default_shares]

        steps["smb_enum"] = {
            "success": success,
            "shares": list(set(shares)),
            "users": list(set(users))[:50],  # Top 50 users
            "null_session": null_session,
            "interesting_shares": interesting_shares,
        }

        # ========================================
        # STEP 2: LDAP enumeration
        # ========================================
        # Convert domain to LDAP base DN (e.g., "CORP.LOCAL" -> "DC=CORP,DC=LOCAL")
        # Sanitize domain parts
        domain_parts = domain.replace("'", "").replace(";", "").split(".")
        base_dn = ",".join([f"DC={part}" for part in domain_parts])

        ldap_output_file = f"{workspace_dir}/ldap_output.txt"
        success, findings, output = self.execute_step(
            step_name=f"LDAP enumeration for {domain}",
            command=f"ldapsearch -x -h {dc_ip} -b '{base_dn}' '(objectClass=*)' dn > {ldap_output_file} 2>&1 && cat {ldap_output_file}",
            timeout=ldap_timeout,
            parse_json=False,
        )

        # Count LDAP objects
        computers = output.count("CN=") if "CN=" in output else 0
        ldap_users = output.count("CN=Users") if "CN=Users" in output else 0
        groups = output.count("CN=Groups") if "CN=Groups" in output else 0

        steps["ldap_enum"] = {
            "success": success,
            "computers": computers,
            "users": ldap_users,
            "groups": groups,
            "domain_controllers": output.count("CN=Domain Controllers") if "CN=Domain Controllers" in output else 1,
        }

        # ========================================
        # STEP 3: Optional BloodHound collection
        # ========================================
        if has_credentials and collect_bloodhound:
            bloodhound_output = f"{workspace_dir}/bloodhound_data.zip"
            # Escape credentials (already done above)
            escaped_domain = domain.replace("'", "'\\''")
            success, findings, output = self.execute_step(
                step_name=f"BloodHound data collection",
                command=f"cd {workspace_dir} && bloodhound-python -c All -d '{escaped_domain}' -u '{escaped_username}' -p '{escaped_password}' -dc {dc_ip} -ns {dc_ip} --zip",
                timeout=bloodhound_timeout,
                parse_json=False,
            )

            # Check if ZIP file was created
            zip_created = "bloodhound" in output.lower() and ("zip" in output.lower() or success)

            steps["bloodhound"] = {
                "success": success and zip_created,
                "zip_file": bloodhound_output if success and zip_created else None,
                "files_collected": ["computers.json", "users.json", "groups.json", "domains.json"] if success and zip_created else [],
            }
        else:
            steps["bloodhound"] = {
                "success": False,
                "zip_file": None,
                "files_collected": [],
                "reason": "Credentials required" if not has_credentials else "BloodHound collection disabled",
            }

        # ========================================
        # SUMMARY
        # ========================================
        summary = {
            "total_users": len(steps["smb_enum"]["users"]),
            "total_computers": steps["ldap_enum"]["computers"],
            "total_groups": steps["ldap_enum"]["groups"],
            "interesting_shares": interesting_shares,
            "null_session_available": null_session,
            "bloodhound_ready": steps["bloodhound"]["success"],
            "authentication_status": "Authenticated" if has_credentials else "Anonymous",
        }

        return self.create_result_dict(
            workflow_name="enumerate_ad",
            target=dc_ip,
            steps=steps,
            summary=summary,
        )
