"""Bounded, append-only recorded posture observations; no historical backfill."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid

from .posture import timestamp
from .store import Store

MAX_RECORDS = 4096
MAX_BYTES = 64 * 1024 * 1024
MAX_PAYLOAD = 2 * 1024 * 1024


def capture(store, posture):
    from .evidence_access import _posture
    payload = json.dumps(_posture(posture), sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(payload.encode()) > MAX_PAYLOAD:
        raise ValueError('Posture observation exceeds capacity; archive older observations')
    stamp = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    row = {'schema_version':1, 'id':'ph_' + uuid.uuid4().hex, 'created_at':stamp, 'posture':json.loads(payload)}
    def save(state):
        latest = state.db.execute("SELECT created_at FROM records WHERE collection='posture_history' ORDER BY created_at DESC,key DESC LIMIT 1").fetchone()
        if latest and latest[0] >= row['created_at']:
            row['created_at'] = (datetime.fromisoformat(latest[0]) + timedelta(microseconds=1)).isoformat(timespec='microseconds')
        row['digest'] = _digest(row)
        count, size = state.db.execute("SELECT count(*),coalesce(sum(length(payload)),0) FROM records WHERE collection='posture_history'").fetchone()
        if count >= MAX_RECORDS or size + len(json.dumps(row).encode()) > MAX_BYTES:
            raise ValueError('Posture history is full; archive before recording more observations')
        state.setdefault('posture_history', {})[row['id']] = row
        return {'id':row['id'], 'created_at':row['created_at']}
    return store.update(save)


def _digest(row):
    body = {key:row[key] for key in ('schema_version','id','created_at','posture')}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _verified(row):
    if (not isinstance(row,dict) or type(row.get('schema_version')) is not int or row['schema_version'] != 1 or
            _digest(row) != row.get('digest')):
        raise ValueError('Posture observation checksum/schema mismatch')
    return row


def read(store, as_of):
    stamp = timestamp(as_of)
    if not isinstance(as_of, str) or 'T' not in as_of or stamp is None:
        raise ValueError('Use a timezone-aware as_of timestamp')
    if stamp > datetime.now(timezone.utc).timestamp() + 1:
        raise ValueError('Posture observations cannot predict future state')
    normalized = datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec='microseconds')
    with store.connection() as db:
        row = db.execute("SELECT payload FROM records WHERE collection='posture_history' AND created_at<=? ORDER BY created_at DESC,key DESC LIMIT 1", (normalized,)).fetchone()
    if not row:
        raise KeyError('No recorded posture observation exists at or before this time')
    item = _verified(json.loads(row[0]))
    return {**item['posture'], 'cohort': 'recorded_posture_snapshot', 'historical': True,
            'captured_at': item['created_at'], 'requested_as_of': normalized,
            'capture_consistency': 'observed_cross_file_state'}


def observations(store):
    with store.connection() as db:
        rows = db.execute("SELECT key,created_at FROM records WHERE collection='posture_history' ORDER BY created_at DESC,key DESC LIMIT 100").fetchall()
        count = db.execute("SELECT count(*) FROM records WHERE collection='posture_history'").fetchone()[0]
    return {'data':[{'id':key,'created_at':stamp} for key,stamp in rows], 'total':count}


def archive(store, before, destination, prune=False):
    if timestamp(before) is None:
        raise ValueError('Use a timezone-aware archive boundary')
    boundary = datetime.fromtimestamp(timestamp(before), timezone.utc).isoformat(timespec='microseconds')
    destination = Path(destination)
    def save(state):
        rows = [_verified(json.loads(row[0])) for row in state.db.execute(
            "SELECT payload FROM records WHERE collection='posture_history' AND created_at<? ORDER BY created_at,key", (boundary,))]
        content = ''.join(json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n' for row in rows).encode()
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as file:
            file.write(content); file.flush(); os.fsync(file.fileno())
        directory = os.open(destination.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
        if prune:
            records = state.get('posture_history', {})
            for row in rows: del records[row['id']]
        return {'archived':len(rows), 'pruned':len(rows) if prune else 0,
                'sha256':hashlib.sha256(content).hexdigest()}
    return store.update(save)


def restore(store, source):
    source = Path(source)
    if source.stat().st_size > MAX_BYTES:
        raise ValueError('Posture archive exceeds capacity')
    rows = []
    with source.open('rb') as file:
        while True:
            line = file.readline(MAX_PAYLOAD + 2048)
            if not line: break
            if len(line) >= MAX_PAYLOAD + 2048 or not line.endswith(b'\n'):
                raise ValueError('Invalid archive line')
            rows.append(_verified(json.loads(line)))
            if len(rows) > MAX_RECORDS: raise ValueError('Too many archived observations')
    if len({r['id'] for r in rows}) != len(rows): raise ValueError('Duplicate archived observation')
    def load(state):
        collection = state.setdefault('posture_history', {})
        count, size = state.db.execute("SELECT count(*),coalesce(sum(length(payload)),0) FROM records WHERE collection='posture_history'").fetchone()
        restored = 0
        for row in rows:
            previous = collection.get(row['id'])
            if previous is not None:
                if previous != row: raise ValueError('Conflicting observation; restore refused')
                continue
            count += 1; size += len(json.dumps(row).encode())
            if count > MAX_RECORDS or size > MAX_BYTES: raise ValueError('Restored observations exceed capacity')
            collection[row['id']] = row; restored += 1
        return {'restored':restored}
    return store.update(load)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--archive-before')
    action.add_argument('--restore', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prune', action='store_true', help='Delete only successfully fsynced archived records')
    args = parser.parse_args()
    if args.restore:
        if args.prune or args.output: parser.error('Restore does not take prune/output')
        result=restore(Store(args.state_dir),args.restore)
    else:
        if not args.output: parser.error('Archive requires --output')
        result=archive(Store(args.state_dir),args.archive_before,args.output,args.prune)
    print(json.dumps(result))


if __name__ == '__main__': main()
