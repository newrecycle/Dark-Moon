"""Disposable actual Gitea HTTPS host; never writes to an external repository."""
import base64
import json
import os
import secrets
import sys
import socket
import ssl
import subprocess
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path
from unittest.mock import patch

from community.publish import publish
from community.remediation import git

IMAGE = 'gitea/gitea:1.24.6-rootless@sha256:91f2b27e080739f0d19dba716c3214f17257c632cf762e545b44ca577e37052c'


def command(*args, **kwargs):
    completed = subprocess.run(args, capture_output=True, text=True, timeout=120, **kwargs)
    if completed.returncode:
        raise RuntimeError(str(args[0]) + ' operation failed (credentials/output withheld)')
    return completed.stdout.strip()


def exercise(store, result, repo, root):
    """Publish one actual proposal and verify open PR, exact SHA, idempotency."""
    name = 'dm-forge-' + uuid.uuid4().hex[:12]
    certs = Path(root) / 'certs'
    certs.mkdir(mode=0o755)
    cert, key = certs / 'cert.pem', certs / 'key.pem'
    command('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
            '-keyout', str(key), '-out', str(cert))
    # Container reads only this disposable key; parent workspace remains private.
    key.chmod(0o444)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    base = f'https://127.0.0.1:{port}'
    password = secrets.token_urlsafe(32)
    token = None
    seed_notes = ''
    context = ssl.create_default_context(cafile=str(cert))

    def api(path, payload=None, basic=False, method=None):
        headers = {'Accept': 'application/json'}
        if basic:
            headers['Authorization'] = 'Basic ' + base64.b64encode(('fixture:' + password).encode()).decode()
        elif token:
            headers['Authorization'] = 'token ' + token
        body = None if payload is None else json.dumps(payload).encode()
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(base + '/api/v1' + path, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, context=context, timeout=10) as response:
            return json.loads(response.read(1024 * 1024))

    try:
        argv = ['docker', 'run', '-d', '--name', name, '--pull=missing',
                '-p', f'127.0.0.1:{port}:3000',
                '--tmpfs', '/var/lib/gitea:uid=1000,gid=1000,mode=755,exec',
                '--tmpfs', '/etc/gitea:uid=1000,gid=1000,mode=755',
                '-v', f'{certs}:/certs:ro', '-e', 'SSL_CERT_FILE=/certs/cert.pem']
        settings = {'security__INSTALL_LOCK': 'true', 'server__PROTOCOL': 'https',
                    'server__ROOT_URL': base + '/', 'server__HTTP_PORT': '3000',
                    'server__LOCAL_ROOT_URL': 'https://127.0.0.1:3000/',
                    'server__CERT_FILE': '/certs/cert.pem', 'server__KEY_FILE': '/certs/key.pem',
                    'server__OFFLINE_MODE': 'true', 'server__DISABLE_SSH': 'true',
                    'service__DISABLE_REGISTRATION': 'true', 'mailer__ENABLED': 'false',
                    'actions__ENABLED': 'false', 'repository__DEFAULT_BRANCH': 'main',
                    'database__DB_TYPE': 'sqlite3'}
        for setting, value in settings.items():
            argv.extend(['-e', 'GITEA__' + setting + '=' + value])
        command(*argv, IMAGE)
        ready = False
        for _ in range(60):
            try:
                api('/version')
                ready = True
                break
            except (OSError, ValueError):
                time.sleep(1)
        if not ready:
            raise RuntimeError('disposable Gitea did not become ready')
        command('docker', 'exec', name, 'gitea', 'admin', 'user', 'create',
                '--username', 'fixture', '--password', password, '--email', 'fixture@example.invalid',
                '--admin', '--must-change-password=false')
        token = api('/users/fixture/tokens', {'name': 'native-acceptance', 'scopes': ['all']}, basic=True)['sha1']
        api('/user/repos', {'name': 'owned-remediation', 'private': True, 'auto_init': False,
                           'default_branch': 'main'})
        api('/repos/fixture/owned-remediation', {'has_pull_requests': True}, method='PATCH')
        destination = base + '/fixture/owned-remediation.git'
        helper = Path(root) / 'askpass'
        helper.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s\\n" fixture;; *) printf "%s\\n" "$DARKMOON_FORGE_TOKEN";; esac\n')
        helper.chmod(0o700)
        env = {'DARKMOON_FORGE_TOKEN': token, 'DARKMOON_FORGE_USERNAME': 'fixture',
               'DARKMOON_ALLOW_PUBLISH': '1', 'SSL_CERT_FILE': str(cert),
               'GIT_SSL_CAINFO': str(cert), 'GIT_ASKPASS': str(helper), 'GIT_TERMINAL_PROMPT': '0'}
        with patch.dict(os.environ, env):
            seeded = subprocess.run(['git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
                    'push', '--no-verify', destination, 'HEAD:refs/heads/main'], cwd=repo,
                    capture_output=True, text=True, timeout=120)
            seed_notes = seeded.stderr[:4096]
            if seeded.returncode:
                raise RuntimeError('owned forge source seeding failed')
            for attempt in range(20):
                state = api('/repos/fixture/owned-remediation')
                if state.get('empty') is False and state.get('has_pull_requests') is True:
                    break
                time.sleep(.25)
            else:
                raise RuntimeError('seeded forge repository is not ready for pull requests')
            first = publish(store, result['id'], destination, forge='gitea', execute=True)
            second = publish(store, result['id'], destination, forge='gitea', execute=True)
        assert first == second
        publication = first['publication']
        pull = api('/repos/fixture/owned-remediation/pulls/' + str(publication['id']))
        assert pull['state'] == 'open' and not pull['merged']
        assert pull['head']['sha'] == publication['commit']
        assert pull['head']['ref'] == result['branch'] and pull['base']['ref'] == 'main'
        assert api('/repos/fixture/owned-remediation/branches/main')['commit']['id'] == result['base_commit']
        assert len(api('/repos/fixture/owned-remediation/pulls?state=all')) == 1
        assert git(repo, 'rev-parse', 'HEAD') == result['base_commit']
        assert not git(repo, 'status', '--porcelain')
        return {'forge': 'gitea', 'version': api('/version')['version'], 'https_verified': True,
                'exact_head_sha': True, 'open_unmerged_pr': True, 'idempotent': True,
                'original_source_unchanged': True, 'external_repository': False}
    except Exception as error:
        diagnostic = {'native_forge_error': type(error).__name__, 'seed_git_notes': seed_notes}
        if isinstance(error, urllib.error.HTTPError):
            diagnostic.update(status=error.code, body=error.read(4096).decode('utf-8', 'replace'))
        try:
            state = api('/repos/fixture/owned-remediation')
            diagnostic['repository'] = {key: state.get(key) for key in ('empty', 'has_pull_requests', 'default_branch')}
        except Exception:
            pass
        logs = subprocess.run(['docker', 'logs', '--tail', '60', name], capture_output=True, text=True, timeout=15)
        diagnostic['host_errors'] = [line for line in (logs.stdout + logs.stderr).splitlines()
                                     if any(word in line.lower() for word in ('error', 'fatal', 'hook'))][-12:]
        encoded = json.dumps(diagnostic).replace(password, '[redacted]')
        if token:
            encoded = encoded.replace(token, '[redacted]')
        print(encoded, file=sys.stderr, flush=True)
        raise
    finally:
        subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True, timeout=30)
