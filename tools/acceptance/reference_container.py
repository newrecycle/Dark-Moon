#!/usr/bin/env python3
"""Start/stop a disposable authorized reference image without changing its entrypoint."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

from capture import private_dir, write_json

TMPFS = {
    '/tmp': 'rw,size=512m,mode=1777', '/run': 'rw,size=128m,mode=755',
    '/root/.cache': 'rw,size=256m,mode=700,uid=10001,gid=10001',
    '/root/.local': 'rw,size=512m,mode=700,uid=10001,gid=10001',
    '/root/.local/state': 'rw,size=256m,mode=700,uid=10001,gid=10001',
    '/root/.config': 'rw,size=128m,mode=700,uid=10001,gid=10001',
    '/root/.config/opencode': 'rw,size=64m,mode=700,uid=10001,gid=10001',
    '/root/.local/share': 'rw,size=1024m,mode=700,uid=10001,gid=10001',
    '/root/.local/share/opencode': 'rw,size=1024m,mode=700,uid=10001,gid=10001',
    '/root/.local/state/opencode': 'rw,size=128m,mode=700,uid=10001,gid=10001',
    '/root/.cache/opencode': 'rw,size=128m,mode=700,uid=10001,gid=10001',
    '/root/.opencode': 'rw,size=256m,mode=700,uid=10001,gid=10001',
    '/opt/darkmoon/mcp/server/data': 'rw,size=1024m,mode=700,uid=10001,gid=10001',
    '/opt/darkmoon/mcp/server/src/tools/workflows': 'rw,size=256m,mode=700,uid=10001,gid=10001',
    '/run/darkmoon': 'rw,size=128m,mode=700,uid=10001,gid=10001',
}
VOLUMES = {'sealed': '/var/lib/darkmoon-sealed', 'sessions': '/mnt/darkmoon-share/sessions',
           'reports': '/mnt/darkmoon-share/reports', 'pentest': '/mnt/darkmoon-share/pentest'}


def docker(*args):
    proc = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=120)
    if proc.returncode:
        raise RuntimeError('Docker operation failed: ' + args[0] + '; inspect the owned runtime privately')
    return proc.stdout.strip()


def launch_args(name, image, policy, env_file):
    argv = ['run', '-d', '--name', name, '--label', 'darkmoon.capture.owner='+name,
            '--network', 'none', '--read-only', '--cap-drop', 'NET_RAW',
            '--security-opt', 'no-new-privileges:true', '--pids-limit', '512']
    for path, options in TMPFS.items():
        argv += ['--tmpfs', path+':'+options]
    for suffix, target in VOLUMES.items():
        argv += ['--mount', f'type=volume,src={name}-{suffix},dst={target}']
    argv += ['--mount', f'type=bind,src={policy},dst=/run/darkmoon/policy/docker-compose-dev.yml,readonly',
             '--env-file', str(env_file), image]
    return argv  # no command/entrypoint override, host socket, ports, extra caps or host networking


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    start = sub.add_parser('start')
    start.add_argument('--image', required=True, help='Already prepared and authorized image')
    start.add_argument('--policy', required=True, type=Path, help='Private original runtime policy')
    start.add_argument('--state', required=True, type=Path)
    start.add_argument('--name', default='darkmoon-capture-'+secrets.token_hex(5))
    stop = sub.add_parser('stop')
    stop.add_argument('--receipt', required=True, type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.action == 'stop':
        receipt = json.loads(a.receipt.read_text())
        name = receipt['container']
        if not re.fullmatch(r'darkmoon-capture-[a-zA-Z0-9_.-]+', name):
            p.error('Not a capture-owned container')
        inspect = json.loads(docker('inspect', name))[0]
        if inspect['Config'].get('Labels', {}).get('darkmoon.capture.owner') != name:
            p.error('Container ownership label does not match receipt')
        if inspect['Id'] != receipt['container_id']:
            p.error('Container was replaced since receipt creation')
        docker('rm', '-f', name)
        for suffix in VOLUMES:
            volume = name+'-'+suffix
            meta = json.loads(docker('volume', 'inspect', volume))[0]
            if (meta.get('Labels') or {}).get('darkmoon.capture.owner') != name:
                raise RuntimeError('Volume ownership mismatch; refusing deletion')
            docker('volume', 'rm', volume)
        print('Removed the owned container and its four volumes; image and private files retained.')
        return
    if not re.fullmatch(r'darkmoon-capture-[a-zA-Z0-9_.-]+', a.name):
        p.error('--name must start darkmoon-capture-')
    if subprocess.run(['docker', 'inspect', a.name], capture_output=True).returncode == 0:
        p.error('Refusing an existing container name')
    policy = a.policy.expanduser().resolve(strict=True)
    if ',' in str(policy):
        p.error('Policy mount path cannot contain commas')
    image = json.loads(docker('image', 'inspect', a.image))[0]
    if not image['Config'].get('Entrypoint'):
        p.error('Reference image must retain its normal guarded entrypoint')
    state = private_dir(a.state)
    env = state/'fixture.env'
    env.write_text('JWT_SECRET='+secrets.token_urlsafe(48)+'\n')
    volumes = []
    try:
        for suffix in VOLUMES:
            name = a.name+'-'+suffix
            if subprocess.run(['docker', 'volume', 'inspect', name], capture_output=True).returncode == 0:
                raise RuntimeError('Refusing existing volume '+name)
            docker('volume', 'create', '--label', 'darkmoon.capture.owner='+a.name, name)
            volumes.append(name)
        container_id = docker(*launch_args(a.name, image['Id'], policy, env))
        write_json(state/'receipt.json', {'container': a.name, 'container_id': container_id,
            'image_id': image['Id'], 'volumes': volumes, 'state': 'started_not_health_verified'})
        write_json(state/'config.json', {'reference': {'container': a.name, 'url': 'http://127.0.0.1:8000',
            'token_env': 'REFERENCE_CAPTURE_TOKEN'}})
        print(str(state/'receipt.json'))
    except Exception:
        # Do not remove a container we did not create. Failed docker run may have created ours.
        proc = subprocess.run(['docker', 'inspect', a.name], capture_output=True, text=True)
        if proc.returncode == 0:
            meta = json.loads(proc.stdout)[0]
            if meta['Config'].get('Labels', {}).get('darkmoon.capture.owner') == a.name:
                docker('rm', '-f', a.name)
        for volume in volumes:
            docker('volume', 'rm', volume)
        raise


if __name__ == '__main__':
    main()
