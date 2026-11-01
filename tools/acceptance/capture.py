#!/usr/bin/env python3
"""Capture only outstanding workflow evidence; never infer complete API parity."""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit

from wire import request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SCENARIOS = {
    'scheduler': 'API03 post-fix interval defaults and preservation; disabled records only',
    'history': 'API05 bounded populated retained history; not mutation-journal equivalence',
    'events': 'API12 bounded JSON/SSE replay and cursor observations; not scan completion',
    'logs': 'API09 existing real run log collection/detail; does not launch an assessment',
    'publication': 'API08 post-fix real publication lookup; requires actual pipeline fixture IDs',
    'native-publication': 'REM02/API08 actual Docker/Gitea production pipeline and fork HTTP projection',
    'configured-model': 'REM02 actual configured generation/review, Docker and Gitea gate',
}
DEFAULT = ['scheduler', 'history', 'events', 'logs', 'publication']
EXCLUDED = {
    'auth': 'Earlier role/password/expiry matrix already used; offline regression remains in normal suite.',
    'evolution': 'Eight postfix producer comparisons already agreed; retain regressions instead of recapture.',
    'scm': 'Seven SCM forms and real checkout already observed; remaining providers need implementation.',
    'webhooks': 'Five real attempts across two restarts already observed; no repeated 5-minute capture.',
    'browser': 'Earlier direct-link checks already observed; full UI matrix is a separate existing browser gate.',
    'broad-route-sweep': 'Status/shape sweeps and empty collections do not establish workflow acceptance.',
    'failed-harness-fixtures': 'Incomplete summaries/setup failures are historical diagnostics, not useful reruns.',
}


class Unavailable(Exception):
    pass


def private_dir(path):
    path = Path(path).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('Capture output must be outside the repository')
    if path.exists():
        raise ValueError('Use a new output directory; old evidence is never overwritten')
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    path.chmod(0o600)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


class Journal:
    def __init__(self, out):
        self.out = out
        self.raw = out / 'captures.jsonl'
        self.raw.touch(mode=0o600, exist_ok=False)
        self.count = 0

    def record(self, side, case, method, path, body, result):
        self.count += 1
        row = {'sequence': self.count, 'at_unix': time.time(), 'side': side, 'case': case,
               'request': {'method': method, 'path': path, 'body': body}, 'response': result}
        with self.raw.open('a') as f:
            f.write(json.dumps(row, sort_keys=True) + '\n')
            f.flush()
        return result

    def finish(self, summary):
        write_json(self.out / 'summary.json', summary)
        # Original line bytes are hashed before any future redaction.
        write_json(self.out / 'capture-line-hashes.json', [hashlib.sha256(line).hexdigest()
                   for line in self.raw.read_bytes().splitlines(keepends=True)])
        write_manifest(self.out)


def write_manifest(out):
    manifest = {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(out.rglob('*')) if p.is_file() and p != out/'manifest.json'}
    write_json(out/'manifest.json', manifest)


def validate_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Endpoint must be an HTTP(S) origin without credentials, path or query')
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname == 'localhost'
    if parsed.scheme == 'http' and not loopback:
        raise ValueError('Remote endpoints require verified HTTPS')
    _ = parsed.port
    return value.rstrip('/')


class Endpoint:
    def __init__(self, side, spec, journal):
        self.side, self.spec, self.journal = side, spec, journal
        self.url = validate_url(spec.get('url', 'http://127.0.0.1:8000'))
        self.token = os.environ.get(spec.get('token_env', ''), '')
        if not self.token:
            raise Unavailable(side + ': configured bearer token environment variable is missing')
        self.container = spec.get('container')
        if self.container and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', self.container):
            raise ValueError('Invalid container name')
        if self.container and urlsplit(self.url).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Container transport connects only to container loopback')

    def call(self, case, path, method='GET', body=None, stream=False, headers=None):
        if not path.startswith('/api/') or path.startswith('//'):
            raise ValueError('Capture paths must be relative API paths')
        spec = {'url': self.url + path, 'method': method, 'body': body,
                'headers': {'Authorization': 'Bearer ' + self.token, **(headers or {})},
                'timeout': 3 if stream else 10, 'stream': stream}
        if self.container:
            # Script is our stdlib transport, not vendor code. Credentials use stdin, not argv.
            argv = ['docker', 'exec', '-i', '--user', self.spec.get('user', '10001'), self.container,
                    self.spec.get('python', '/opt/darkmoon/mcp/server/.venv/bin/python3'),
                    '-c', (HERE / 'wire.py').read_text()]
            try:
                proc = subprocess.run(argv, input=json.dumps(spec), text=True, capture_output=True, timeout=20)
                result = json.loads(proc.stdout) if proc.returncode == 0 else {'termination': 'container_transport_error', 'status': None, 'complete': False}
            except (OSError, subprocess.TimeoutExpired, ValueError):
                result = {'termination': 'container_transport_error', 'status': None, 'complete': False}
        else:
            result = request(spec)
        return self.journal.record(self.side, case, method, path, body, result)


def data(result, statuses=(200, 201)):
    if result.get('status') not in statuses or not result.get('complete'):
        raise AssertionError('HTTP request failed or was incomplete: ' + str(result.get('status')) + '/' + result.get('termination', 'unknown'))
    value = result.get('json')
    return value.get('data', value) if isinstance(value, dict) else value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', value):
        raise ValueError('Expected a safe fixture identifier')
    return value


def interval(item):
    return item.get('recurrence_interval', item.get('rule', {}).get('every'))


def scheduler(endpoint):
    observations = []
    for kind in ('daily', 'weekly', 'monthly'):
        path = '/api/v1/scheduler/'
        payload = {'name': 'capture-' + secrets.token_hex(6), 'target': 'owned.invalid',
                   'scheduled_at': '2099-01-31T16:00:00Z', 'recurrence': kind, 'enabled': False}
        item = data(endpoint.call(kind + '-create-default', path, 'POST', payload))
        if not isinstance(item, dict):
            raise AssertionError('Schedule create did not return a record')
        owned_id = identifier(item.get('id'))
        path += owned_id
        try:
            assert interval(item) == 1, 'omitted interval must default to1'
            edit = {'recurrence_interval': 3, 'version': item.get('version', 1)}
            item = data(endpoint.call(kind + '-set-interval', path, 'PUT', edit))
            assert interval(item) == 3
            edit = {'recurrence': 'daily' if kind == 'weekly' else 'weekly', 'version': item.get('version', 2)}
            changed = data(endpoint.call(kind + '-switch-type', path, 'PUT', edit))
            assert interval(changed) == 3, 'omitted interval must survive type change'
            assert changed.get('enabled') is False, 'capture must never enable a schedule'
            reread = data(endpoint.call(kind + '-readback', path))
            assert interval(reread) == 3
            observations.append({'initial_kind': kind, 'default_interval': 1, 'preserved_interval': 3})
        finally:
            deleted = endpoint.call(kind + '-cleanup', path, 'DELETE')
            if deleted.get('status') not in (200, 204):
                raise AssertionError('Owned schedule cleanup failed; inspect private captures')
    return {'assertions': observations, 'boundary': 'Disabled CRUD only; no dispatch/month arithmetic acceptance.'}


def history(endpoint):
    target = endpoint.spec.get('target_id')
    if not target:
        raise Unavailable('Set target_id for an owned populated campaign/history cohort')
    path = '/api/v1/vulnerabilities/history?'+urlencode({'target_id': identifier(target), 'limit': 1})
    pages = []
    for offset in (0, 1, 2):
        result = endpoint.call('history-page-' + str(offset), path + '&offset=' + str(offset))
        data(result)
        pages.append(result['json'])
    populated = any(p.get('data') or p.get('history') for p in pages if isinstance(p, dict))
    if not populated:
        raise Unavailable('Owned history cohort is empty; no populated acceptance claim')
    return {'observed_pages': len(pages), 'boundary': 'Retained snapshots and journals remain distinct; compare ordering manually.'}


def events(endpoint):
    since = endpoint.spec.get('event_cursor', 0)
    path = '/api/v1/events/stream?poll=1&limit=1&' + urlencode({'since': since})
    first = endpoint.call('events-first-page', path)
    if first.get('status') == 409:
        raise Unavailable('Cursor expired/unknown; choose a retained event_cursor for populated replay')
    rows = data(first)
    if not rows:
        raise Unavailable('No retained events after cursor; populate through normal owned producers')
    body = first['json']
    cursor = body.get('cursor') if isinstance(body, dict) else None
    if cursor is None:
        raise AssertionError('Poll did not return cursor')
    data(endpoint.call('events-next-page', '/api/v1/events/stream?poll=1&limit=1&'+urlencode({'since': cursor})))
    data(endpoint.call('events-filter', '/api/v1/events/stream?poll=1&limit=1&'+urlencode({'since': since, 'events': 'finding.discovered'})))
    missing = endpoint.call('events-unknown-cursor', '/api/v1/events/stream?poll=1&since=evt_capture_missing')
    stream = endpoint.call('events-sse-window', '/api/v1/events/stream?'+urlencode({'since': since}),
                           stream=True, headers={'Accept': 'text/event-stream'})
    if stream.get('status') != 200 or stream.get('termination') not in ('observation_window', 'eof'):
        raise AssertionError('SSE handshake/window failed')
    if 'text/event-stream' not in next((v for k,v in stream.get('headers', {}).items() if k.lower() == 'content-type'), ''):
        raise AssertionError('SSE response has wrong content type')
    text = base64.b64decode(stream['body_b64']).decode('utf-8', errors='replace')
    if 'data:' not in text:
        raise Unavailable('SSE contains no event data; handshake/heartbeat alone is insufficient')
    return {'unknown_cursor_status': missing.get('status'), 'stream_termination': stream['termination'],
            'boundary': 'Bounded replay observation only; no restart/eviction/scan-completion acceptance.'}


def logs(endpoint):
    run_id = endpoint.spec.get('run_id')
    if not run_id:
        raise Unavailable('Set run_id from an actual owned assessment; controlled fake launchers are not accepted')
    rid = identifier(run_id)
    records = []
    for offset in (0, 1):
        records.append(data(endpoint.call('run-logs-page-'+str(offset), '/api/v1/run/logs?'+
            urlencode({'run_id': rid, 'limit': 1, 'offset': offset}))))
    detail = data(endpoint.call('run-log-detail', '/api/v1/run/logs/'+rid+'?lines=10'))
    if not any(records) or not detail:
        raise Unavailable('Run/log cohort empty; no successful-engine claim')
    return {'boundary': 'Observed existing metadata only; no raw evidence grant or successful assessment inference.'}


def publication(endpoint):
    cfg = endpoint.spec.get('publication') or {}
    if cfg.get('provenance') != 'actual_pipeline' or not all(cfg.get(k) for k in ('campaign_id', 'finding_id', 'pr_id')):
        raise Unavailable('Set publication IDs from an actual production pipeline; direct state seeding is not accepted')
    cid, fid, pid = (identifier(cfg[k]) for k in ('campaign_id', 'finding_id', 'pr_id'))
    collection = data(endpoint.call('publication-collection', '/api/v1/pull-requests?'+urlencode({'campaign_id': cid})))
    detail = data(endpoint.call('publication-detail', '/api/v1/pull-requests/' + pid))
    links = data(endpoint.call('publication-finding', '/api/v1/pull-requests/finding/' + fid + '?' + urlencode({'campaign_id': cid})))
    if not isinstance(collection, list) or not collection or not links or not isinstance(detail, dict):
        raise AssertionError('Actual publication is absent from API projection')
    if not detail.get('provider') or not detail.get('state'):
        raise AssertionError('Actual publication provider/state missing')
    return {'provider': detail['provider'], 'state': detail['state'],
            'boundary': 'Lookup projection only; actual pipeline provenance is an operator precondition. No many-to-many claim.'}


def native(name, out):
    child = out / name
    child.mkdir(mode=0o700)
    cmd = [sys.executable, str(HERE / 'native_capture.py'), '--out', str(child)] if name == 'native-publication' else [sys.executable, str(ROOT/'tests/community/remediation_model_native.py'), '--configured-models']
    env = {**os.environ, 'PYTHONPATH': str(ROOT/'mcp')}
    # Logs are private, bounded by process deadline. No credentials printed to console.
    with (child/'stdout.log').open('wb') as stdout, (child/'stderr.log').open('wb') as stderr:
        process = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            code = process.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            # Let Python finally blocks remove owned fixtures/containers before a forced stop.
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            raise AssertionError('Native deadline exceeded; cleanup attempted, inspect owned resources privately')
    if code == 3:
        raise Unavailable('Native prerequisites missing; see private logs')
    if code != 0:
        raise AssertionError('Native workflow failed; see private logs')
    return {'exit_code': code, 'boundary': 'Owned fixture only; reference runtime pipeline equivalence remains open.'}


def main(argv=None):
    if not __debug__:
        raise SystemExit('Run without -O; acceptance assertions must remain enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='Private endpoint/fixture configuration; tokens are environment variable names')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--only', nargs='+', choices=SCENARIOS, default=DEFAULT)
    parser.add_argument('--plan', action='store_true', help='Print selected gaps and exclusions without requests')
    args = parser.parse_args(argv)
    if args.plan:
        print(json.dumps({'selected': {k: SCENARIOS[k] for k in dict.fromkeys(args.only)}, 'excluded': EXCLUDED}, indent=2))
        return 0
    if not args.out:
        parser.error('--out is required')
    os.umask(0o077)
    cfg = json.loads(args.config.read_text()) if args.config else {}
    out = private_dir(args.out)
    journal = Journal(out)
    summary = {'schema_version': 1, 'head': git('rev-parse', 'HEAD'), 'dirty': bool(git('status', '--porcelain')),
               'selected': list(dict.fromkeys(args.only)), 'excluded': EXCLUDED, 'results': [],
               'full_reference_acceptance': False, 'captures_are_private': True}
    write_json(out/'plan.json', {k: v for k,v in summary.items() if k != 'results'})
    source_paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).split(b'\0')
    source_hashes = {}
    for name in sorted(set(source_paths)):
        if name:
            path = ROOT / os.fsdecode(name)
            if path.is_file() and not path.is_symlink():
                source_hashes[os.fsdecode(name)] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(out/'source-hashes.json', source_hashes)

    try:
        for name in dict.fromkeys(args.only):
            sides = ('local',) if name in ('native-publication', 'configured-model') else ('reference', 'fork')
            for side in sides:
                row = {'scenario': name, 'side': side}
                try:
                    if side == 'local':
                        result = native(name, out)
                    else:
                        if side not in cfg:
                            raise Unavailable('Endpoint configuration missing for ' + side)
                        result = globals()[name](Endpoint(side, cfg[side], journal))
                    row.update(status='observed', detail=result)
                except Unavailable as exc:
                    row.update(status='unavailable', reason=str(exc))
                except (AssertionError, ValueError, KeyError, OSError) as exc:
                    row.update(status='failed', reason=str(exc))
                summary['results'].append(row)
                # Only fixed labels/status leave the private report.
                print(side + '/' + name + ': ' + row['status'], flush=True)
    finally:
        journal.finish(summary)
    statuses = {r['status'] for r in summary['results']}
    return 1 if 'failed' in statuses else 3 if 'unavailable' in statuses else 0


if __name__ == '__main__':
    sys.exit(main())
