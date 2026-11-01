#!/usr/bin/env python3
"""Run an owned disposable fork with normal synthetic producers, no scan launches.

Prints a private config path only. Ctrl-C stops normally; state remains for review.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root/'mcp')]
    from capture import private_dir, write_json
    os.umask(0o077)
    state = private_dir(args.state)
    os.environ.update(DARKMOON_DATA_DIR=str(state/'data'), DARKMOON_SHARED_DIR=str(state/'shared'),
                      DARKMOON_DASHBOARD_TOKEN=secrets.token_urlsafe(32))
    # Import after setting data paths; do not patch production modules or verdicts.
    from seed_cohort import create_cohort
    from community.service import Service
    from community.server import HTTPServer, handler_for
    service = Service(root, state/'control')
    server = HTTPServer(('127.0.0.1', 0), handler_for(service, {'127.0.0.1'}))
    try:
        cohort = create_cohort()
        for campaign_id in cohort['campaign_ids']:
            service.operations.emit('finding.discovered', {'campaign_id': campaign_id,
                                    'finding_id': cohort['namespace'] + '_finding_0'})
        write_json(state/'cohort.json', cohort)
        write_json(state/'config.json', {'fork': {'url': f'http://127.0.0.1:{server.server_port}',
            'token_env': 'FORK_CAPTURE_TOKEN', 'target_id': cohort['target_id'], 'event_cursor': 0}})
        (state/'token').write_text(service.token + '\n')
        (state/'token').chmod(0o600)
        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        service.start()  # normal workers; capture creates only disabled future schedules
        print(str(state/'config.json'), flush=True)
        server.serve_forever()
    finally:
        service.close()
        server.server_close()


if __name__ == '__main__':
    main()
