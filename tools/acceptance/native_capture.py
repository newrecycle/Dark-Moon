#!/usr/bin/env python3
"""Observe real publication over HTTP before the existing native fixture is removed."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'mcp'), str(ROOT/'tests/community')]
from community.server import HTTPServer, handler_for
from remediation_native import main as run_native
from capture import Endpoint, Journal, publication


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    journal = Journal(args.out)
    summary = {'pipeline': 'actual_operator_edits_docker_gitea', 'model_inference': False, 'observed': False}

    def observe(fixture, result, forge):
        server = HTTPServer(('127.0.0.1', 0), handler_for(fixture.service, {'127.0.0.1'}))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = Endpoint('fork', {'url': f'http://127.0.0.1:{server.server_port}',
                'token_env': 'DARKMOON_DASHBOARD_TOKEN', 'publication': {
                    'provenance': 'actual_pipeline', 'campaign_id': result['campaign_id'],
                    'finding_id': result['finding_id'], 'pr_id': result['id']}}, journal)
            detail = publication(endpoint)
            # Actual production records must expose all executed probe kinds, without repaired state.
            raw = endpoint.call('publication-probe-kinds', '/api/v1/pull-requests/' + result['id'])
            record = raw['json']['data']
            assert record['provider'] == 'gitea' and record['state'] == 'open'
            for phase in ('before', 'after'):
                assert {p['kind'] for p in record['validation'][phase]} == {'exploit', 'variant', 'normal'}
            summary.update(observed=True, detail=detail, forge=forge)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    try:
        code = run_native(observer=observe)
        summary['exit_code'] = code
        return code
    finally:
        journal.finish(summary)


if __name__ == '__main__':
    sys.exit(main())
