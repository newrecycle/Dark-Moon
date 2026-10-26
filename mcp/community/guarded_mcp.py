"""Opt-in MCP launcher with sealed vault persistence and local audit events.

Configure this module as your MCP command instead of src.server. The underlying
tool implementation is upstream src.server, unmodified by this feature branch.
"""
def main():
    import runpy
    import src.privacy
    import src.privacy.vault
    from .privacy_audit import SealedPrivacyVault
    src.privacy.PrivacyVault = SealedPrivacyVault
    src.privacy.vault.PrivacyVault = SealedPrivacyVault
    runpy.run_module("src.server", run_name="__main__")


if __name__ == "__main__":main()
