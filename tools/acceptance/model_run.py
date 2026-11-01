#!/usr/bin/env python3
"""Explicit private configured-model gate; never called by bootstrap, CI or commits."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from capture import ROOT, private_dir, validate_url, write_json, write_manifest
from wire import request


def choose_model(models, explicit='', match='flash'):
    ids = [r.get('id') for r in models.get('data', []) if isinstance(r, dict) and isinstance(r.get('id'), str)]
    if explicit:
        if explicit not in ids:
            raise ValueError('Configured model is not in the provider model list')
        return explicit
    matches = sorted(set(name for name in ids if match.lower() in name.lower()))
    if len(matches) != 1:
        raise ValueError('Expected one current Flash alias; set model explicitly from the provider list')
    return matches[0]


def main():
    if not __debug__:
        raise SystemExit('Run without -O; acceptance assertions must remain enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Private JSON outside Git; includes API key')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reason', choices=['initial-ready', 'relevant-change', 'failure-investigation'], required=True)
    args = parser.parse_args()
    config_path = args.config.expanduser().resolve()
    if config_path == ROOT or ROOT in config_path.parents:
        parser.error('Model credentials must be outside the repository')
    out = args.out.expanduser().resolve()
    if out == ROOT or ROOT in out.parents or out.exists():
        parser.error('Use a new private output directory outside the repository')
    os.umask(0o077)
    def unavailable(reason, discovery=None):
        private_dir(out)
        write_json(out/'summary.json', {'status': 'unavailable', 'phase': 'model_discovery',
            'reason': reason, 'inference_requests': 0, 'full_reference_acceptance': False})
        if discovery is not None:
            write_json(out/'model-discovery.json', discovery)
        write_manifest(out)
        print('UNAVAILABLE: '+reason)
        return 3
    cfg = json.loads(config_path.read_text())
    key = cfg.get('api_key', '').strip()
    if not key or key == 'PASTE_YOUR_DEEPSEEK_API_KEY_HERE':
        return unavailable('Fill the private API-key file; no model request made')
    # The supplied configuration uses an origin. Resolve /models first; no guessed ID.
    base = validate_url(cfg.get('api_base_url', 'https://api.deepseek.com'))
    result = request({'url': base+'/models', 'headers': {'Authorization': 'Bearer '+key}})
    if result.get('status') != 200 or not result.get('complete') or not isinstance(result.get('json'), dict):
        return unavailable('Verified provider model discovery failed; check endpoint/network/key privately', result)
    try:
        model = choose_model(result['json'], cfg.get('model', ''), cfg.get('model_match', 'flash'))
        review = choose_model(result['json'], cfg.get('review_model') or model)
    except ValueError as error:
        return unavailable(str(error), result)
    env = {**os.environ, 'DARKMOON_REMEDIATION_BASE_URL': base,
           'DARKMOON_REMEDIATION_MODEL': model, 'DARKMOON_REMEDIATION_API_KEY': key,
           'DARKMOON_REMEDIATION_JUDGE_BASE_URL': base,
           'DARKMOON_REMEDIATION_JUDGE_MODEL': review, 'DARKMOON_REMEDIATION_JUDGE_API_KEY': key}
    proc = subprocess.run([sys.executable, str(Path(__file__).with_name('capture.py')),
        '--only', 'configured-model', '--out', str(out)], cwd=ROOT, env=env)
    if out.is_dir():
        # Regenerate manifest after adding provider identity and explicit reason; never save key.
        write_json(out/'model-discovery.json', result)
        write_json(out/'model-selection.json', {'base_url': base, 'generation_model': model,
            'review_model': review, 'reason': args.reason,
            'model_list_body_sha256': result['body_sha256'],
            'policy': 'Once ready; rerun only relevant changes or failures. NEVER every commit.'})
        write_manifest(out)
    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
