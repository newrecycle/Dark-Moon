#!/usr/bin/env python3
"""Disposable GitLab CE + registered modern Runner, synthetic local jobs only.

Creates no project or runner outside the container it owns. Does not enable an
Ultimate trial, accept paid terms, perform assessments or publish a component.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import yaml
from verify_ingestion import artifact_report, NoRedirect

ROOT = Path(__file__).resolve().parents[1]
SERVER_IMAGE = 'gitlab/gitlab-ce:19.5.1-ce.0'


def command(*args, env=None, timeout=600):
    result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Owned GitLab command failed: ' + args[0])
    return result.stdout.strip()


def eventually(action, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = action()
            if result:
                return result
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise RuntimeError('Owned GitLab acceptance deadline exceeded')


def pipeline_config(case):
    gate = 'critical,high' if case not in ('passing',) else ''
    allowed = [2] if case in ('nonblocking', 'read_error') else [250]
    inputs = {'target': 'owned-fixture.invalid', 'mode': 'oss', 'fail-on': gate,
              'timeout': '20', 'oss-data-dir': '$CI_PROJECT_DIR/.data',
              'oss-reports-dir': '$CI_PROJECT_DIR/.reports',
              'oss-script': '$CI_PROJECT_DIR/.fixture/engine.cjs'}
    return yaml.safe_dump({'workflow': {'rules': [{'if': '$CI_PIPELINE_SOURCE == "api"'}]},
        'include': [{'local': '/templates/scan/template.yml', 'inputs': inputs | {'allow_failure_exit_codes': allowed}}],
        'default': {'tags': ['owned-native'], 'before_script': [
            'export PATH="$CI_PROJECT_DIR/.fixture:$PATH"',
            'mkdir -p "$CI_PROJECT_DIR/.data/campaigns" "$CI_PROJECT_DIR/.data/vulnerabilities" "$CI_PROJECT_DIR/.reports"']},
        'variables': {'DM_ACCEPTANCE_CASE': case}}, sort_keys=False)


ENGINE = '''#!/usr/bin/env node
const fs=require('node:fs'), p=process.env.CI_PROJECT_DIR;
const id='camp_owned_'+process.env.CI_JOB_ID;
fs.writeFileSync(p+'/.data/campaigns/'+id+'.json',JSON.stringify({id,status:'completed',stats:{total_findings:0}}));
if(process.env.DM_ACCEPTANCE_CASE!=='read_error') fs.writeFileSync(p+'/.data/vulnerabilities/'+id+'.json',JSON.stringify(process.env.DM_ACCEPTANCE_CASE==='empty'?[]:[{id:'finding_owned_one',campaign_id:id,title:'Synthetic issue',severity:'high',status:'confirmed',category:'configuration',endpoint:'/fixture',description:'PRIVATE_EVIDENCE_OWNED_GITLAB'}]));
'''


def run():
    name = 'dm-gitlab-' + uuid.uuid4().hex[:12]
    token = secrets.token_urlsafe(36)
    opener = urllib.request.build_opener(NoRedirect)
    runner = None
    server_started = False
    with tempfile.TemporaryDirectory(prefix='dm-gitlab-owned-') as temp:
        work = Path(temp)
        try:
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            base = 'http://127.0.0.1:' + str(port)
            config = (f"external_url '{base}'; nginx['listen_port']=80; "
                      "puma['worker_processes']=2; sidekiq['max_concurrency']=5; "
                      "prometheus_monitoring['enable']=false; gitlab_rails['usage_ping_enabled']=false; "
                      "gitlab_rails['smtp_enable']=false")
            command('docker', 'run', '-d', '--name', name, '--shm-size=256m', '--memory=6g',
                    '-p', f'127.0.0.1:{port}:80', '-e', 'GITLAB_OMNIBUS_CONFIG=' + config, SERVER_IMAGE)
            server_started = True
            def request(path, data=None, method=None, raw=False):
                req = urllib.request.Request(base + '/api/v4/' + path,
                    data=json.dumps(data).encode() if data is not None else None,
                    method=method, headers={'PRIVATE-TOKEN': token, 'Content-Type': 'application/json'})
                with opener.open(req, timeout=30) as response:
                    body = response.read(8 * 1024 * 1024 + 1)
                    if len(body) > 8 * 1024 * 1024:
                        raise ValueError('GitLab response exceeds acceptance bound')
                    return body if raw else json.loads(body)
            def ready():
                with opener.open(base + '/-/readiness', timeout=10) as response:
                    return response.status == 200
            eventually(ready)
            print("owned_gitlab_ready=true", flush=True)
            ruby = "u=User.find_by_username('root'); t=u.personal_access_tokens.create!(name:'owned-fixture',scopes:['api'],expires_at:Date.today+1); t.set_token(ENV.fetch('DM_BOOTSTRAP_TOKEN')); t.save!; puts 'bootstrap-ready'"
            command('docker', 'exec', '-e', 'DM_BOOTSTRAP_TOKEN', name, 'gitlab-rails', 'runner', ruby,
                    env={**os.environ, 'DM_BOOTSTRAP_TOKEN': token})
            version = request('version')['version']
            project = request('projects', {'name': name, 'visibility': 'private', 'initialize_with_readme': True})
            pid = project['id']
            registration = request('user/runners', {'runner_type': 'project_type', 'project_id': pid,
                'description': name, 'tag_list': ['owned-native'], 'run_untagged': False})
            runner_token = registration['token']
            runner_binary = str(ROOT / 'test/vendor/gitlab-runner-modern')
            runner_config = str(work / 'runner.toml')
            clean_env = {k: os.environ[k] for k in ('PATH', 'HOME', 'LANG', 'TMPDIR') if k in os.environ}
            command(runner_binary, 'register', '--non-interactive', '--config', runner_config,
                    env=clean_env | {'CI_SERVER_URL': base, 'RUNNER_TOKEN': runner_token,
                        'RUNNER_EXECUTOR': 'shell', 'RUNNER_NAME': name})
            Path(runner_config).chmod(0o600)
            runner = subprocess.Popen([runner_binary, 'run', '--config', runner_config,
                '--working-directory', temp], env=clean_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            files = {'templates/scan/template.yml': (ROOT / 'templates/scan/template.yml').read_text(),
                     '.gitlab-ci.yml': pipeline_config('passing'),
                     '.fixture/engine.cjs': ENGINE,
                     '.fixture/darkmoon-ci': '#!/bin/sh\nexec node "$CI_PROJECT_DIR/.fixture/client.cjs" "$@"\n',
                     '.fixture/client.cjs': (ROOT / 'test/vendor/standalone-client.cjs').read_text()}
            actions = [{'action': 'create', 'file_path': path, 'content': value,
                        **({'execute_filemode': True} if path in ('.fixture/engine.cjs', '.fixture/darkmoon-ci') else {})}
                       for path, value in files.items()]
            request(f'projects/{pid}/repository/commits', {'branch': project['default_branch'],
                'commit_message': 'Owned component fixture', 'actions': actions})
            observed = []
            for case in ('passing', 'empty', 'blocking', 'nonblocking', 'read_error'):
                print('owned_pipeline_case=' + case, flush=True)
                branch = 'case-' + case
                commit = request(f'projects/{pid}/repository/commits', {'branch': branch,
                    'start_branch': project['default_branch'], 'commit_message': 'Owned case ' + case,
                    'actions': [{'action': 'update', 'file_path': '.gitlab-ci.yml', 'content': pipeline_config(case)}]})
                pipeline = request(f'projects/{pid}/pipeline', {'ref': branch})
                assert pipeline['sha'] == commit['id']
                def terminal():
                    item = request(f"projects/{pid}/pipelines/{pipeline['id']}")
                    return item if item['status'] in ('success', 'failed', 'canceled', 'skipped') else None
                result = eventually(terminal, timeout=300)
                jobs = request(f"projects/{pid}/pipelines/{pipeline['id']}/jobs")
                assert len(jobs) == 1
                job = jobs[0]
                assert job['name'] == 'darkmoon_scan' and job['pipeline']['id'] == pipeline['id']
                assert job['runner']['id'] == registration['id']
                expected_job = 'success' if case in ('passing', 'empty') else 'failed'
                expected_pipeline = 'failed' if case in ('blocking', 'read_error') else 'success'
                assert job['status'] == expected_job and result['status'] == expected_pipeline, case
                assert job['allow_failure'] == (case == 'nonblocking'), case
                assert any(a['file_type'] == 'sast' for a in job['artifacts']), case
                report = artifact_report(request(f"projects/{pid}/jobs/{job['id']}/artifacts/gl-sast-report.json", raw=True))
                assert len(report['vulnerabilities']) == (0 if case in ('empty', 'read_error') else 1)
                assert report['scan']['status'] == ('failure' if case == 'read_error' else 'success')
                trace = request(f"projects/{pid}/jobs/{job['id']}/trace", raw=True)
                assert b'PRIVATE_EVIDENCE_OWNED_GITLAB' not in trace
                assert token.encode() not in trace and runner_token.encode() not in trace
                for file in ('darkmoon/findings.json', 'darkmoon/run.json', 'darkmoon/darkmoon-report.md'):
                    try:
                        request(f"projects/{pid}/jobs/{job['id']}/artifacts/{file}", raw=True)
                    except urllib.error.HTTPError as exc:
                        assert exc.code == 404
                    else:
                        raise AssertionError('Private intermediate artifact was uploaded')
                observed.append({'case': case, 'job_status': job['status'], 'pipeline_status': result['status'],
                    'sast_uploaded': True, 'findings': len(report['vulnerabilities'])})
            print(json.dumps({'status': 'passed', 'gitlab_version': version, 'cases': observed,
                'security_ingestion': 'not_verified_CE_has_no_Ultimate_security_feature'}, indent=2))
        finally:
            if runner:
                runner.terminate()
                try: runner.wait(timeout=15)
                except subprocess.TimeoutExpired: runner.kill(); runner.wait()
            if server_started:
                command('docker', 'rm', '-f', '-v', name)


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        # Do not echo server bodies, tokens, root passwords or job traces.
        raise SystemExit('Owned GitLab acceptance FAILED: ' + type(exc).__name__ +
                         (' ' + str(exc) if isinstance(exc, (AssertionError, RuntimeError)) else ''))
