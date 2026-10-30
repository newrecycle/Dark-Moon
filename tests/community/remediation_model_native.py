"""Actual local-model generation/review, optionally Docker probes + local Gitea.

--model-only deliberately does NOT establish container or forge acceptance.
"""
import argparse
import json
import os
import selectors
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import test_community as fixtures
from api import json_storage as data
from community.remediation import git, remediate, judge_patch
from native_forge import exercise

SOURCE = '''import sqlite3

def allowed(name):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE users(name TEXT)")
    db.execute("INSERT INTO users VALUES ('admin')")
    return bool(db.execute("SELECT 1 FROM users WHERE name = '" + name + "'").fetchone())
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-only', action='store_true')
    args = parser.parse_args()
    python = os.environ.get('DARKMOON_NATIVE_MODEL_PYTHON')
    if not python:
        print('NATIVE UNAVAILABLE: set DARKMOON_NATIVE_MODEL_PYTHON to pinned model environment')
        return 3
    fixture = fixtures.Fixture()
    fixture.setUp()
    process = None
    try:
        cid = fixture.campaign()
        finding = {'id': 'vuln_fixture', 'status': 'confirmed', 'severity': 'high',
                   'category': 'sqli', 'title': 'SQL injection in allowed(name)',
                   'endpoint': 'app.py:allowed',
                   'description': 'Untrusted name is concatenated into the SELECT query, permitting authentication bypass.',
                   'remediation': 'Bind name as a query parameter; preserve normal admin and visitor results.'}
        data.save_vulnerabilities(cid, [finding])
        repo = fixture.root / 'owned-source'
        repo.mkdir()
        (repo / 'app.py').write_text(SOURCE)
        (repo / '.darkmoon').mkdir()
        exploit = ['python', '-c', 'import app; print(app.allowed("\' OR 1=1 --"))']
        normal = ['python', '-c', 'import app; assert app.allowed("admin"); assert not app.allowed("visitor"); print("normal")']
        plan = {'vuln_fixture': {'image': 'darkmoon-ui-lab', 'probes': [
            {'name': 'owned SQL injection', 'kind': 'exploit', 'argv': exploit,
             'before': {'exit_code': 0, 'contains': 'True'}, 'after': {'exit_code': 0, 'contains': 'False'}},
            {'name': 'normal users preserved', 'kind': 'normal', 'argv': normal,
             'before': {'exit_code': 0, 'contains': 'normal'}, 'after': {'exit_code': 0, 'contains': 'normal'}}]}}
        (repo / '.darkmoon/repro.json').write_text(json.dumps(plan))
        git(repo, 'init', '-b', 'main')
        git(repo, 'config', 'user.name', 'Disposable acceptance')
        git(repo, 'config', 'user.email', 'fixture@example.invalid')
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'Owned SQLi fixture')
        process = subprocess.Popen([python, str(Path(__file__).with_name('native_model_server.py'))],
                                   stdout=subprocess.PIPE, text=True)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(timeout=600):
                raise RuntimeError('model startup timeout; no acceptance claim')
            host = json.loads(process.stdout.readline())
        negative = None
        with patch.dict(os.environ, {'DARKMOON_REMEDIATION_BASE_URL': f'http://127.0.0.1:{host["port"]}/v1',
                                    'DARKMOON_REMEDIATION_MODEL': host['model'],
                                    'DARKMOON_REMEDIATION_API_KEY': ''}):
            result = remediate(repo, cid, 'vuln_fixture', files=['app.py'], generate=True,
                               validate=not args.model_only, store=fixture.service.store)
            if result['status'] == ('proposed' if args.model_only else 'validated'):
                # A comment-only change leaves the original injectable query.
                # The actual reviewer must reject it; never repair its verdict.
                lines = SOURCE.splitlines()
                unsafe_diff = '\n'.join(['diff --git a/app.py b/app.py', '--- a/app.py',
                    '+++ b/app.py', f'@@ -1,{len(lines)} +1,{len(lines)+1} @@',
                    '+# Review-only comment'] + [' ' + line for line in lines]) + '\n'
                negative = judge_patch(finding, unsafe_diff)
        patch_text = Path(result['patch_path']).read_text()[:16384] if result.get('patch_path') else None
        expected = 'proposed' if args.model_only else 'validated'
        if result['status'] != expected:
            print(json.dumps({'accepted': False, 'status': result['status'],
                              'error': result.get('error'), 'judge': result.get('judge'),
                              'generated_patch': patch_text}))
            return 1
        assert result['judge']['approved'] and result['judge']['confidence'] >= .75
        assert negative is not None and negative['approved'] is False, 'actual reviewer must reject unfixed negative control'
        assert not result['published'] and (repo / 'app.py').read_text() == SOURCE
        forge = None if args.model_only else exercise(fixture.service.store, result, repo, fixture.root)
        print(json.dumps({'accepted': True, 'model': host['model'], 'revision': host['revision'],
                          'quantization': host['quantization'], 'actual_generation_and_review': True,
                          'negative_control_rejected': True, 'negative_judge': negative,
                          'docker_probes': not args.model_only,
                          'status': result['status'], 'judge': result['judge'],
                          'generated_patch': patch_text, 'forge': forge}))
        return 0
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        fixture.tearDown()


if __name__ == '__main__':
    sys.exit(main())
