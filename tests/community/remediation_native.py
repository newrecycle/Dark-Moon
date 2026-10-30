"""Real offline Docker SQLi probes and disposable HTTPS forge acceptance.

No model inference or external repository writes. Missing Docker/image is
unavailable (exit 3), never skipped-success. Uses production Sandbox/publish.
"""
import json
import shutil
import subprocess
import sys

import test_community as fixtures
from api import json_storage as data
from community.remediation import git, remediate
from native_forge import exercise
from remediation_model_native import SOURCE


def main():
    image = 'darkmoon-ui-lab'
    if not shutil.which('docker') or not shutil.which('openssl'):
        print('NATIVE UNAVAILABLE: Docker and OpenSSL required')
        return 3
    for argv in (['docker', 'info'], ['docker', 'image', 'inspect', image]):
        if subprocess.run(argv, capture_output=True, timeout=30).returncode:
            print('NATIVE UNAVAILABLE: running Docker and prebuilt darkmoon-ui-lab required')
            return 3
    fixture = fixtures.Fixture()
    fixture.setUp()
    try:
        cid = fixture.campaign()
        data.save_vulnerabilities(cid, [{'id': 'vuln_fixture', 'status': 'confirmed',
            'title': 'SQL injection in owned fixture', 'category': 'sqli', 'severity': 'high'}])
        repo = fixture.root / 'owned-source'
        repo.mkdir()
        (repo / 'app.py').write_text(SOURCE)
        (repo / '.darkmoon').mkdir()
        exploit = ['python', '-c', 'import app; print(app.allowed("\' OR 1=1 --"))']
        variant = ['python', '-c', 'import app; print(app.allowed("x\' OR name=\'admin\' --"))']
        normal = ['python', '-c', 'import app, os; assert app.allowed("admin"); assert not app.allowed("visitor"); '
                  'assert os.getuid() == 65534; assert os.statvfs("/").f_flag & os.ST_RDONLY; '
                  'assert len(open("/proc/net/route").read().splitlines()) <= 1; print("normal")']
        plan = {'vuln_fixture': {'image': image, 'probes': [
            {'name': 'owned SQL injection', 'kind': 'exploit', 'argv': exploit,
             'before': {'exit_code': 0, 'contains': 'True'}, 'after': {'exit_code': 0, 'contains': 'False'}},
            {'name': 'owned SQL injection variant', 'kind': 'variant', 'argv': variant,
             'before': {'exit_code': 0, 'contains': 'True'}, 'after': {'exit_code': 0, 'contains': 'False'}},
            {'name': 'normal behavior and sandbox restrictions', 'kind': 'normal', 'argv': normal,
             'before': {'exit_code': 0, 'contains': 'normal'}, 'after': {'exit_code': 0, 'contains': 'normal'}}]}}
        (repo / '.darkmoon/repro.json').write_text(json.dumps(plan))
        git(repo, 'init', '-b', 'main')
        git(repo, 'config', 'user.name', 'Disposable validation')
        git(repo, 'config', 'user.email', 'fixture@example.invalid')
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'Owned SQLi fixture')
        old = 'db.execute("SELECT 1 FROM users WHERE name = \'" + name + "\'")'
        fixed = 'db.execute("SELECT 1 FROM users WHERE name = ?", [name])'
        unsafe = 'db.execute("SELECT 1 FROM users WHERE name = \'" + str(name) + "\'")'
        outcomes, forge = [], None
        for expected, replacement in [('validated', fixed), ('validation_failed', unsafe)]:
            result = remediate(repo, cid, 'vuln_fixture',
                               edits=[{'path': 'app.py', 'old': old, 'new': replacement}],
                               validate=True, store=fixture.service.store)
            assert result['status'] == expected, result.get('error', result['status'])
            assert result['published'] is False
            assert all(probe['passed'] for probe in result['validation']['before'])
            assert (repo / 'app.py').read_text() == SOURCE and not git(repo, 'status', '--porcelain')
            if expected == 'validated':
                forge = exercise(fixture.service.store, result, repo, fixture.root)
            outcomes.append({'status': result['status'], 'before': len(result['validation']['before']),
                             'after': len(result['validation']['after']), 'published': expected == 'validated'})
        plan['vuln_fixture']['image'] = 'darkmoon-native-fixture-intentionally-absent:never-pull'
        (repo / '.darkmoon/repro.json').write_text(json.dumps(plan))
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'Unavailable image fixture')
        result = remediate(repo, cid, 'vuln_fixture',
                           edits=[{'path': 'app.py', 'old': old, 'new': fixed}],
                           validate=True, store=fixture.service.store)
        assert result['status'] == 'unreproduced' and not result.get('patch_path')
        assert any(probe.get('infrastructure_error') for probe in result['validation']['before'])
        outcomes.append({'status': 'unreproduced', 'infrastructure_error': True, 'patch_applied': False})
        print(json.dumps({'native_docker': True, 'cases': outcomes, 'model_inference': False,
                          'forge_publication': True, 'forge': forge}))
        return 0
    finally:
        fixture.tearDown()


if __name__ == '__main__':
    sys.exit(main())
