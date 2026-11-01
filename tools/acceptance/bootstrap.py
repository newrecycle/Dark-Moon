#!/usr/bin/env python3
"""Recreate optional development dependencies; does not launch assessments."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(args, cwd=ROOT):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('component', choices=('python', 'node', 'browser', 'native-image'))
    args = p.parse_args()
    if args.component == 'python':
        if sys.version_info < (3, 11):
            p.error('Python3.11+ required; native acceptance uses3.12')
        run([sys.executable, '-m', 'venv', ROOT/'.venv'])
        run([ROOT/'.venv/bin/python', '-m', 'pip', 'install', '-r', ROOT/'requirements-dev.txt'])
    elif args.component == 'node':
        # Tracked lockfiles only: do not recurse into installed node_modules.
        files = subprocess.check_output(['git', 'ls-files', '*package-lock.json'], cwd=ROOT, text=True)
        for name in files.splitlines():
            run(['npm', 'ci'], (ROOT/name).parent)
    elif args.component == 'browser':
        run([ROOT/'.venv/bin/python', '-m', 'pip', 'install', 'playwright'])
        run([ROOT/'.venv/bin/python', '-m', 'playwright', 'install', 'chromium'])
    else:
        run(['docker', 'build', '-f', 'tools/lab/Dockerfile', '-t', 'darkmoon-ui-lab', '.'])


if __name__ == '__main__':
    main()
