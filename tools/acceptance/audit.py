#!/usr/bin/env python3
"""Audit tracked paths, exact duplicates, JSON and handoff integrity without mutation."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('Duplicate JSON key: ' + key)
        out[key] = value
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='Optional report outside repository')
    args = parser.parse_args()
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).split(b'\0')
    groups = collections.defaultdict(list)
    errors, reviewed = [], 0
    for raw in files:
        if not raw:
            continue
        name = raw.decode()
        path = ROOT/name
        if not path.exists():
            errors.append(name + ': tracked file missing')
            continue
        if path.is_symlink():
            if ROOT not in path.resolve().parents:
                errors.append(name + ': symlink escapes repository')
            continue
        content = path.read_bytes()
        reviewed += 1
        if content:
            groups[hashlib.sha256(content).hexdigest()].append(name)
        if path.suffix == '.json' and path.name not in {'tsconfig.json', 'jsconfig.json'}:
            try:
                json.loads(content, object_pairs_hook=unique_object)
            except (ValueError, UnicodeError) as exc:
                errors.append(name + ': ' + str(exc))
        parts = set(path.relative_to(ROOT).parts)
        if parts & {'node_modules', '.venv', '__pycache__'} or name.endswith(('.pyc', '.env')):
            errors.append(name + ': generated dependency/private environment tracked')
        if name.endswith(('raw-observations.jsonl', 'captures.jsonl', 'accounts-private.json', 'install-darkmoon-preact.sh')):
            errors.append(name + ': private runtime material tracked')
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', content):
            errors.append(name + ': embedded private key requires review')
    tasks = json.loads((ROOT/'docs/handoff/api-task-progress.json').read_text())
    ids = [t['task'] for t in tasks['tasks']]
    if len(ids) != len(set(ids)):
        errors.append('Duplicate task IDs')
    for item in tasks['commits']:
        if subprocess.run(['git', 'cat-file', '-e', item['commit']+'^{commit}'], cwd=ROOT, capture_output=True).returncode:
            errors.append('Missing task checkpoint commit: '+item['commit'])
    duplicates = [v for v in groups.values() if len(v) > 1]
    report = {'tracked_files': reviewed, 'errors': errors, 'exact_duplicate_groups': duplicates,
              'duplicate_policy': 'Review path contracts before removal: licenses, packaged assets and cross-consumer fixtures require copies.',
              'jsonc_exclusions': ['tsconfig.json', 'jsconfig.json (compiler JSON-with-comments configuration)'],
              'scope': 'Deterministic repository hygiene and handoff audit; not a complete security review.'}
    if args.out:
        dest = args.out.expanduser().resolve()
        if dest == ROOT or ROOT in dest.parents:
            parser.error('--out must be outside repository')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'tracked_files': reviewed, 'duplicate_groups': len(duplicates), 'errors': errors}, indent=2))
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
