"""Explicit administrator enumeration of operator-configured repositories."""
import hashlib
import os
from pathlib import Path

from .remediation import command


def repository_id(value):
    return 'repo_' + hashlib.sha256(value.encode('utf-8')).hexdigest()


def configured():
    # No filesystem probes: even grant admission may only inspect configuration.
    return {repository_id(value): value for value in os.environ.get(
        'DARKMOON_SOURCE_REPOSITORIES', '').split(os.pathsep) if value}


def scope(resource_id):
    if resource_id not in configured():
        raise PermissionError('Repository is not configured for browsing')
    return resource_id


def files(resource_id):
    raw = configured().get(scope(resource_id))
    root = Path(raw)
    if not root.is_absolute() or any(part == '..' for part in root.parts):
        raise ValueError('Configure an absolute repository path')
    current = root
    while current != current.parent:
        if current.is_symlink():
            raise PermissionError('Symlink repository paths are unsupported')
        current = current.parent
    if not root.is_dir():
        raise ValueError('Configured repository is unavailable')
    result = command(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(root),
                      'ls-files', '--stage', '-z'], timeout=5)
    if result['timed_out'] or result['exit_code'] != 0:
        raise ValueError('Tracked source listing unavailable')
    # command bounds output at 1 MiB; never present a partial terminal record.
    output = result['output']
    truncated = len(output.encode('utf-8')) >= 1024 * 1024
    entries = output.split('\0')[:-1]
    names = []
    for entry in entries:
        metadata, separator, name = entry.partition('\t')
        if not separator or metadata.split(' ')[0] not in {'100644', '100755'}:
            continue  # Never offer tracked symlinks or submodules.
        path = Path(name)
        if (not name or path.is_absolute() or '..' in path.parts or
                any(ord(c) < 32 or ord(c) == 127 for c in name)):
            continue
        names.append(name)
    names = sorted(set(names))
    return {'repository_id': resource_id, 'files': names[:5000],
            'truncated': truncated or len(names) > 5000}
