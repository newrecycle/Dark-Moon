"""Execute the shipped GitLab job script with disposable CLI protocol fixtures.

This verifies the exact generated YAML script, not GitLab server/runner wiring.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml

root = Path(__file__).resolve().parents[2]
component = root / 'integrations/upstream/gitlab'
with tempfile.TemporaryDirectory(prefix='darkmoon-gitlab-') as temp:
    work = Path(temp)
    flat = work / 'pipeline.yml'
    subprocess.run([sys.executable, str(component / 'test/render_flat.py'), str(flat), 'target=owned.invalid', 'mode=pro', 'allow_failure_exit_codes=[2]', 'fail-on=none'], check=True, capture_output=True)
    pipeline = yaml.safe_load(flat.read_text())
    job = pipeline['darkmoon_scan']
    assert job['allow_failure'] == {'exit_codes': [2]}
    script = work / 'job.sh'
    script.write_text(job['script'][0])
    cli = work / 'darkmoon-ci'
    cli.write_text('''#!/usr/bin/env python3
import json,os,sys
case=os.environ['DM_TEST_CASE']
if sys.argv[1]=='run':
 if case=='missing-id': print('{}');sys.exit(0)
 if case=='run-error': sys.exit(1)
 gate = case=='gate'
 empty = case=='empty'
 print(json.dumps({'campaignId':'camp_fixture',
    'verdict':'fail' if gate else 'pass',
    'total':0 if empty else 1,
    'failOn':['critical','high'] if gate else [],
    'offending':{'high':1} if gate else {},
    'reason':'fixture'}))
 sys.exit(2 if gate else 0)
if sys.argv[1]=='findings':
 if case=='read-error':sys.exit(1)
 if case=='malformed':print('{');sys.exit(0)
 if case=='envelope':print('{}');sys.exit(0)
 if case=='bad-item':print('[null]');sys.exit(0)
 if case=='empty':print('[]');sys.exit(0)
 print(json.dumps([{'id':'finding_fixture','campaignId':'camp_fixture','severity':'high','title':'Loopback finding','remediation':'DO-NOT-LEAK-REMEDIATION','evidence':{'raw':'DO-NOT-LEAK-EVIDENCE'}}]))
 sys.exit(0)
sys.exit(1)
''')
    cli.chmod(0o700)
    for case, expected in [('valid', 0), ('gate', 2), ('empty', 0), ('read-error', 1), ('malformed', 1), ('envelope', 1), ('bad-item', 1), ('missing-id', 1), ('run-error', 1)]:
        case_dir = work / case
        case_dir.mkdir()
        env = {**os.environ, **{key: str(value) for key,value in job['variables'].items()}, 'PATH': str(work) + os.pathsep + os.environ['PATH'], 'DM_TEST_CASE': case, 'DM_FAIL_ON': 'critical,high' if case == 'gate' else 'none'}
        # A quote in a configured directory must remain data in the decoder.
        env['DM_OUTPUT_DIR'] = "output with ' quote"
        result = subprocess.run(['sh', str(script)], cwd=case_dir, env=env, text=True, capture_output=True, timeout=15)
        assert result.returncode == expected, (case, result.returncode, result.stdout, result.stderr)
        sast = case_dir / 'gl-sast-report.json'
        doc = json.loads(sast.read_text())
        assert doc['scan']['status'] == ('failure' if expected == 1 else 'success'), case
        text = sast.read_text() + (case_dir / 'gl-code-quality-report.json').read_text()
        assert 'DO-NOT-LEAK' not in text, case
        assert not (case_dir / env['DM_OUTPUT_DIR'] / 'findings.json').exists(), case
        subprocess.run([sys.executable, str(component / 'test/validate_schemas.py'), str(case_dir / 'gl-code-quality-report.json'), str(sast)], check=True, capture_output=True)
    # Omission has no synthetic success artifact and keeps the Code Quality gate.
    case_dir = work / 'sast-disabled'; case_dir.mkdir()
    env.update(DM_TEST_CASE='empty', DM_EMIT_SAST='false')
    result = subprocess.run(['sh', str(script)], cwd=case_dir, env=env, capture_output=True, timeout=15)
    assert result.returncode == 0
    assert not (case_dir / 'gl-sast-report.json').exists()
print('PASS shipped GitLab script: pass/gate/empty, six tool-error paths, failed SAST diagnostics, no sensitive bodies, quoted directory, disabled SAST and nonblocking exit-code contract')
