"""Explicit read-only source checkout for an opted-in remediation run."""
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from .store import identifier


def checkout(service, source, campaign_id, credential_id="", run=subprocess.run, actor=None):
    if not str(source).startswith("https://"):
        path = Path(source).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("Local remediation source directory was not found")
        return path
    parsed = urlsplit(source)
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError("Source repository requires HTTPS without embedded credentials/query/fragment")
    target = service.store.root / "checkouts" / identifier(campaign_id)
    if target.exists():
        return target
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if credential_id:
        try:
            service.vault.require(credential_id, "source_checkout", actor=actor)
        except KeyError:
            raise ValueError("Source credential reference is unavailable") from None
    secret = service.vault.resolve(credential_id) if credential_id else ""
    credential = service.store.get("credentials", credential_id) if credential_id else {}
    with tempfile.TemporaryDirectory(prefix="darkmoon-source-auth-") as temporary:
        helper = Path(temporary)/"askpass"
        helper.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" "$DM_CHECKOUT_USER";; *) printf "%s\\n" "$DM_CHECKOUT_SECRET";; esac\n')
        helper.chmod(0o700)
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS=str(helper),
                   DM_CHECKOUT_SECRET=secret, DM_CHECKOUT_USER=(credential or {}).get("username") or "x-access-token")
        result = run(["git", "-c", "credential.helper=", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
                      "clone", "--depth", "1", "--no-recurse-submodules", source, str(target)],
                     env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if result.returncode:
            raise ValueError("Read-only source checkout failed; verify the URL and saved credential")
    return target
