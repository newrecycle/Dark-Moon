#!/usr/bin/env python3
"""Run the actual built SDK CLI against the same producer used by native GitLab.

From repo root after npm run build --prefix integrations/upstream/client:
python integrations/upstream/gitlab/test/fixture_cli_acceptance.py
No server, Docker, model inference, target or external notification is used.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from server_acceptance import ENGINE

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / 'integrations/upstream/client/dist/cli/darkmoon-ci.cjs'


def main():
    for index, (case, expected) in enumerate((('passing', 0), ('empty', 0),
            ('blocking', 2), ('nonblocking', 2), ('read_error', 1))):
        with tempfile.TemporaryDirectory(prefix='dm-gitlab-cli-') as directory:
            root = Path(directory)
            for child in ('.data/campaigns', '.data/vulnerabilities', '.reports'):
                (root / child).mkdir(parents=True)
            engine = root / 'engine.cjs'
            engine.write_text(ENGINE)
            engine.chmod(0o755)
            env = dict(os.environ, CI_PROJECT_DIR=str(root), CI_JOB_ID=str(index), DM_ACCEPTANCE_CASE=case)
            argv = ['node', str(CLI), 'run', '--mode', 'oss', '--target', 'owned-fixture.invalid',
                    '--oss-data-dir', str(root / '.data'), '--oss-reports-dir', str(root / '.reports'),
                    '--oss-script', str(engine), '--timeout', '10', '--json']
            argv += ['--fail-on', 'none' if case == 'passing' else 'critical,high']
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=20)
            assert result.returncode == expected, (case, result.returncode, result.stderr)
            assert 'PRIVATE_EVIDENCE' not in result.stdout + result.stderr
            if case != 'read_error':
                payload = json.loads(result.stdout)
                assert payload['campaignId'] == 'camp_owned_' + str(index), payload
    print('PASS actual built OSS CLI: five native GitLab producer fixtures, exact session attribution and failure/severity exits')


if __name__ == '__main__':
    main()
