"""Verify vendored consumer archives match the built, patched SDK snapshot."""
import base64
import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sources = json.loads((root / 'integrations/upstream/SOURCES.json').read_text())
for name in ('action', 'vscode'):
    source = next(item for item in sources if item['path'].endswith('/' + name))
    consumer = root / source['path']
    package = json.loads((consumer / 'package.json').read_text())
    deps = package['dependencies' if name == 'action' else 'devDependencies']
    archive = consumer / deps['@darkmoon/client'].removeprefix('file:')
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == source['client_snapshot']['tarball_sha256']
    lock = json.loads((consumer / 'package-lock.json').read_text())
    expected_integrity = 'sha512-' + base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
    assert lock['packages']['node_modules/@darkmoon/client']['integrity'] == expected_integrity, f'{name}: stale lockfile integrity'
    with tarfile.open(archive) as bundle:
        manifest = json.load(bundle.extractfile('package/package.json'))
        assert manifest['version'] == source['client_snapshot']['version']
        for entry in ('dist/index.cjs', 'dist/index.js', 'dist/cli/darkmoon-ci.cjs'):
            assert bundle.extractfile('package/' + entry).read() == (root / 'integrations/upstream/client' / entry).read_bytes(), f'{name}: stale SDK {entry}'
print('PASS Action and VS Code archives: provenance hash, fork version and built SDK/CLI contents')
