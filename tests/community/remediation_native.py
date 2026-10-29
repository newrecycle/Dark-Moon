"""Actual Docker remediation acceptance; no model inference or forge writes.

Run PYTHONPATH=mcp .venv/bin/python tests/community/remediation_native.py
after building tools/lab/Dockerfile as darkmoon-ui-lab. Missing Docker/image is
unavailable (exit 3), never a skipped-success test. Uses production Sandbox.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import test_community as fixtures
from community.remediation import git, remediate


def main():
    image = 'darkmoon-ui-lab'
    if not shutil.which('docker'):
        print('NATIVE UNAVAILABLE: Docker required')
        return 3
    for argv in (['docker', 'info'], ['docker', 'image', 'inspect', image]):
        result = subprocess.run(argv, capture_output=True, timeout=30)
        if result.returncode:
            print('NATIVE UNAVAILABLE: running Docker and prebuilt darkmoon-ui-lab required')
            return 3
    fixture = fixtures.Fixture()
    fixture.setUp()
    try:
        cid = fixture.campaign()
        repo = fixture.root / 'owned-source'
        repo.mkdir()
        (repo / 'app.py').write_text('state = "vulnerable"\n')
        (repo / '.darkmoon').mkdir()
        exploit = ['python', '-c', 'import app; print(app.state)']
        normal = ['python', '-c', 'import os; assert os.getuid() == 65534; '
                  'assert os.statvfs("/").f_flag & os.ST_RDONLY; '
                  'assert len(open("/proc/net/route").read().splitlines()) <= 1; print("normal")']
        plan = {'vuln_fixture': {'image': image, 'probes': [
            {'name': 'owned exploit marker', 'kind': 'exploit', 'argv': exploit,
             'before': {'exit_code': 0, 'contains': 'vulnerable'},
             'after': {'exit_code': 0, 'contains': 'fixed'}},
            {'name': 'normal and sandbox restrictions', 'kind': 'normal', 'argv': normal,
             'before': {'exit_code': 0, 'contains': 'normal'},
             'after': {'exit_code': 0, 'contains': 'normal'}}]}}
        (repo / '.darkmoon/repro.json').write_text(json.dumps(plan))
        git(repo, 'init')
        git(repo, 'config', 'user.name', 'Disposable validation')
        git(repo, 'config', 'user.email', 'fixture@example.invalid')
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'Owned fixture')
        edits = [{'path': 'app.py', 'old': 'vulnerable', 'new': 'fixed'}]
        outcomes = []
        for expected, replacement in [('validated', 'fixed'), ('validation_failed', 'still_unsafe')]:
            result = remediate(repo, cid, 'vuln_fixture', edits=[dict(edits[0], new=replacement)],
                               validate=True, store=fixture.service.store)
            assert result['status'] == expected, result.get('error', result['status'])
            assert result['published'] is False
            assert all(p['passed'] for p in result['validation']['before'])
            assert (repo / 'app.py').read_text() == 'state = "vulnerable"\n'
            assert not git(repo, 'status', '--porcelain')
            outcomes.append({'status': result['status'], 'before': len(result['validation']['before']),
                             'after': len(result['validation']['after']), 'published': False})
        # A missing local image cannot become successful blocked-exploit evidence.
        plan['vuln_fixture']['image'] = 'darkmoon-native-fixture-intentionally-absent:never-pull'
        (repo / '.darkmoon/repro.json').write_text(json.dumps(plan))
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'Unavailable image fixture')
        result = remediate(repo, cid, 'vuln_fixture', edits=edits, validate=True, store=fixture.service.store)
        assert result['status'] == 'unreproduced', result['status']
        assert not result.get('patch_path')
        assert any(p.get('infrastructure_error') for p in result['validation']['before'])
        outcomes.append({'status': 'unreproduced', 'infrastructure_error': True, 'patch_applied': False})
        print(json.dumps({'native_docker': True, 'cases': outcomes,
                          'model_inference': False, 'forge_publication': False}))
        return 0
    finally:
        fixture.tearDown()


if __name__ == '__main__':
    sys.exit(main())
