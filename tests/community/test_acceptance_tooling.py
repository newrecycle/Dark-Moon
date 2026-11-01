"""Capture harness truthfulness, credential boundaries, cleanup and provenance."""
import base64
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

TOOLS = Path(__file__).resolve().parents[2] / 'tools/acceptance'
sys.path.insert(0, str(TOOLS))
import capture
import model_run
from reference_container import launch_args
from wire import request
sys.path.pop(0)


@contextmanager
def server():
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            seen.append((self.path, self.headers.get('Authorization')))
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', '/must-not-follow')
                self.end_headers()
            elif self.path == '/sse':
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(b'id: 1\ndata: {"actual": true}\n\n')
                self.wfile.flush()
                time.sleep(.4)
            else:
                self.send_response(404 if self.path == '/missing' else 200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'path': self.path, 'padding': 'a'*256}).encode())
    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(instance.server_port), seen
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join()


def test_http_exact_query_errors_redirect_and_bearer_boundary():
    with server() as (url, seen):
        result = request({'url': url+'/api/a?x=1&x=2'})
        assert result['complete'] and result['json']['path'] == '/api/a?x=1&x=2'
        missing = request({'url': url+'/missing'})
        assert missing['complete'] and missing['status'] == 404
        redirect = request({'url': url+'/redirect', 'headers': {'Authorization': 'Bearer private'}})
        assert redirect['status'] == 302
        assert seen[-1] == ('/redirect', 'Bearer private')
        assert not any(p == '/must-not-follow' for p, _ in seen)


def test_sse_preserves_partial_frames_without_claiming_completion():
    with server() as (url, _):
        result = request({'url': url+'/sse', 'stream': True, 'timeout': .1})
        raw = base64.b64decode(result['body_b64'])
        assert b'data:' in raw
        assert result['termination'] == 'observation_window'
        assert not result['complete']
        assert hashlib.sha256(raw).hexdigest() == result['body_sha256']


def test_body_limit_cannot_be_reported_as_complete():
    with server() as (url, _):
        result = request({'url': url+'/large', 'max_bytes': 30})
        assert result['bytes'] == 31
        assert not result['complete'] and result['termination'] == 'byte_limit'


@pytest.mark.parametrize('url', ['https://name:secret@example.test', 'http://example.test',
                                'https://example.test/path', 'https://example.test?token=a'])
def test_endpoint_rejects_secret_urls_and_remote_cleartext(url):
    with pytest.raises(ValueError):
        capture.validate_url(url)


def test_output_never_overwrites_evidence_or_enters_repo(tmp_path):
    with pytest.raises(ValueError):
        capture.private_dir(capture.ROOT/'new-captures')
    with pytest.raises(ValueError):
        capture.private_dir(tmp_path)
    out = capture.private_dir(tmp_path/'new')
    assert out.stat().st_mode & 0o777 == 0o700


def test_journal_preserves_raw_body_and_hashes_without_bearer(tmp_path):
    journal = capture.Journal(tmp_path)
    journal.record('fork', 'case', 'GET', '/api/v1/test', None, {'json': {'key': 'severity', 'secret': 'raw-value'}})
    journal.finish({'full_reference_acceptance': False})
    raw = journal.raw.read_bytes()
    assert b'raw-value' in raw and b'Authorization' not in raw
    hashes = json.loads((tmp_path/'capture-line-hashes.json').read_text())
    assert hashes == [hashlib.sha256(raw).hexdigest()]
    for name, digest in json.loads((tmp_path/'manifest.json').read_text()).items():
        assert hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() == digest


def test_missing_endpoints_exit_unavailable_and_deduplicate_selection(tmp_path):
    out = tmp_path/'run'
    assert capture.main(['--out', str(out), '--only', 'scheduler', 'scheduler']) == 3
    summary = json.loads((out/'summary.json').read_text())
    assert summary['selected'] == ['scheduler']
    assert len(summary['results']) == 2
    assert {r['status'] for r in summary['results']} == {'unavailable'}
    assert summary['full_reference_acceptance'] is False


def test_scheduler_cleans_owned_record_when_semantic_assertion_fails():
    class Endpoint:
        calls = []
        def call(self, case, path, method='GET', body=None):
            self.calls.append((method, path))
            return {'status': 200 if method == 'DELETE' else 201, 'complete': True,
                    'json': {'data': {'id': 'owned', 'recurrence_interval': 999}}}
    endpoint = Endpoint()
    with pytest.raises(AssertionError):
        capture.scheduler(endpoint)
    assert endpoint.calls == [('POST', '/api/v1/scheduler/'), ('DELETE', '/api/v1/scheduler/owned')]


def test_isolated_launch_preserves_guard_and_excludes_socket_and_extra_caps():
    args = launch_args('darkmoon-capture-test', 'sha256:abc', '/private/policy', '/private/env')
    assert args[-1] == 'sha256:abc'
    assert '--entrypoint' not in args and '--cap-add' not in args
    assert '--publish' not in args and '-p' not in args
    assert args[args.index('--network')+1] == 'none'
    assert '--read-only' in args and '--cap-drop' in args
    assert not any('docker.sock' in x for x in args)


def test_missing_container_token_is_unavailable_without_running_docker(tmp_path):
    journal = capture.Journal(tmp_path)
    with patch.dict(os.environ, {}, clear=True), patch.object(subprocess, 'run') as run:
        with pytest.raises(capture.Unavailable):
            capture.Endpoint('reference', {'container': 'owned', 'token_env': 'ABSENT'}, journal)
        run.assert_not_called()


def test_model_alias_requires_unique_actual_provider_id():
    sys.path.insert(0, str(TOOLS))
    try:
        from model_run import choose_model
    finally:
        sys.path.pop(0)
    payload = {'data': [{'id': 'provider-flash'}, {'id': 'provider-reasoner'}]}
    assert choose_model(payload) == 'provider-flash'
    assert choose_model(payload, explicit='provider-reasoner') == 'provider-reasoner'
    for bad in ({'data': []}, {'data': [{'id': 'flash-a'}, {'id': 'flash-b'}]}):
        with pytest.raises(ValueError):
            choose_model(bad)
    with pytest.raises(ValueError):
        choose_model(payload, explicit='invented-id')


def test_missing_model_key_records_unavailable_without_network(tmp_path):
    sys.path.insert(0, str(TOOLS))
    try:
        import model_run
    finally:
        sys.path.pop(0)
    config = tmp_path/'config.json'
    config.write_text(json.dumps({'api_key': ''}))
    output = tmp_path/'capture'
    with patch.object(sys, 'argv', ['model_run', '--config', str(config), '--out', str(output), '--reason', 'initial-ready']), patch.object(model_run, 'request') as transport:
        assert model_run.main() == 3
        transport.assert_not_called()
    summary = json.loads((output/'summary.json').read_text())
    assert summary['status'] == 'unavailable' and summary['inference_requests'] == 0
    assert not summary['full_reference_acceptance']


def test_blocked_model_discovery_records_failure_without_inference(tmp_path):
    import model_run
    config = tmp_path/'config.json'
    config.write_text(json.dumps({'api_key': 'private-test-key', 'api_base_url': 'https://api.example.invalid'}))
    output = tmp_path/'capture'
    with patch.object(sys, 'argv', ['model_run', '--config', str(config), '--out', str(output), '--reason', 'initial-ready']), patch.object(model_run, 'request', return_value={'status': 403, 'complete': True}) as transport, patch.object(subprocess, 'run') as process:
        assert model_run.main() == 3
        transport.assert_called_once()
        process.assert_not_called()
    assert 'private-test-key' not in ''.join(p.read_text() for p in output.iterdir() if p.is_file())


def test_native_deadline_interrupts_owned_process_group_before_forced_kill(tmp_path):
    from unittest.mock import Mock
    process = Mock(pid=987654)
    process.wait.side_effect = [subprocess.TimeoutExpired('native', 1800), 0]
    with patch.object(subprocess, 'Popen', return_value=process), patch.object(os, 'killpg') as interrupt:
        with pytest.raises(AssertionError, match='cleanup attempted'):
            capture.native('native-publication', tmp_path)
        interrupt.assert_called_once_with(process.pid, capture.signal.SIGINT)
        assert process.wait.call_count == 2
