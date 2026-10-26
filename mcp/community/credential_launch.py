"""Inject saved target credentials through upstream's local privacy socket.

Plaintext crosses only the local Docker exec stdin pipe. Only the returned
placeholders enter the assessment argv. There is no plaintext fallback.
"""
import json
import re
import subprocess


SOCKET_CLIENT = r'''
import json,os,socket,sys
try:
    request=json.load(sys.stdin)
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    client.settimeout(15)
    client.connect(os.environ.get("DARKMOON_PRIVACY_SOCK","/tmp/darkmoon-privacy.sock"))
    client.sendall((json.dumps({"text":request["text"]})+"\n").encode())
    reply=client.makefile("rb").readline(1024*1024)
    client.close()
    sys.stdout.buffer.write(reply)
except Exception:
    print(json.dumps({"error":"Local privacy tokenization unavailable"}))
    sys.exit(1)
'''


def prepare(repo, store, prompt, spec, run=subprocess.run):
    from .auth import CredentialVault
    vault = CredentialVault(store)
    secrets = []
    fields = []
    for key, flag in (("assessment_credential_id", "CREDS"), ("assessment_token_id", "TOKEN")):
        reference = spec.get(key)
        if not reference:
            continue
        record = store.get("credentials", reference)
        if not record:
            raise ValueError("Target credential reference was not found")
        value = vault.resolve(reference)
        if not value or any(c.isspace() or c in '\"\'' for c in value):
            raise ValueError("The upstream scope parser requires a single-token target secret")
        secrets.append(value)
        if flag == "CREDS":
            username = record.get("username")
            if not username or any(c.isspace() or c in '\"\':' for c in username):
                raise ValueError("Target login credential needs a single-token username")
            fields.append("CREDS="+username+":"+value)
        else:
            fields.append("TOKEN="+value)
    if not fields:
        return prompt
    version = run(["docker", "compose", "version"], cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    compose = ["docker", "compose"] if version.returncode == 0 else ["docker-compose"]
    result = run([*compose, "exec", "-T", "opencode", "python3", "-c", SOCKET_CLIENT], cwd=repo,
                 input=json.dumps({"text": prompt+"\n"+" ".join(fields)}), capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise ValueError("Local privacy tokenization failed; target credentials were withheld")
    try:
        tokenized = json.loads(result.stdout).get("tokenized")
    except (ValueError, TypeError):
        tokenized = None
    if not isinstance(tokenized, str) or any(value in tokenized for value in secrets) or not re.search(r"\bCRED_\d+\b", tokenized):
        raise ValueError("The tokenizer did not hide every target secret; launch was refused")
    return tokenized
