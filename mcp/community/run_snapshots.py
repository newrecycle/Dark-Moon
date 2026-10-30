"""Bounded short-lived frozen lifecycle metadata in the existing control SQLite DB."""
import hashlib
import json
import re
import time
import uuid

TTL=300
MAX_ROWS=100000
MAX_BYTES=64*1024*1024
MAX_SNAPSHOTS=128


def page(store, query, principal, snapshot=None, offset=0, limit=50):
    if not isinstance(principal,str) or not 1<=len(principal)<=200:raise PermissionError('Authenticated principal required')
    fingerprint=hashlib.sha256(json.dumps(query,sort_keys=True,default=sorted).encode()).hexdigest()
    stamp=time.time()
    with store.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS run_snapshot_headers(id TEXT PRIMARY KEY,principal TEXT NOT NULL,filters TEXT NOT NULL,expires REAL NOT NULL,total INTEGER NOT NULL,bytes INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS run_snapshot_rows(snapshot TEXT NOT NULL,ordinal INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(snapshot,ordinal))')
        if snapshot is None:
            if offset:raise ValueError('Start a frozen snapshot at offset zero')
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM run_snapshot_rows WHERE snapshot IN (SELECT id FROM run_snapshot_headers WHERE expires<=?)',(stamp,))
            db.execute('DELETE FROM run_snapshot_headers WHERE expires<=?',(stamp,))
            count,used=db.execute('SELECT count(*),coalesce(sum(bytes),0) FROM run_snapshot_headers').fetchone()
            if count>=MAX_SNAPSHOTS:raise ValueError('Frozen run snapshot capacity reached; retry after expiry')
            clauses=["collection='jobs'"];args=[]
            if query.get('statuses') is not None:
                statuses=sorted(query['statuses']);clauses.append('status IN ('+','.join('?' for _ in statuses)+')');args+=statuses
            for name,column in [('state','state'),('campaign_id','campaign_id'),('run_id','key')]:
                if query.get(name) is not None:clauses.append(column+'=?');args.append(query[name])
            where=' AND '.join(clauses)
            total=db.execute('SELECT count(*) FROM records WHERE '+where,args).fetchone()[0]
            if total>MAX_ROWS:raise ValueError('Frozen snapshot exceeds row capacity; narrow filters')
            snapshot='rs_'+uuid.uuid4().hex;expires=stamp+TTL;size=0
            from .run_views import public_run
            for ordinal,(raw,) in enumerate(db.execute('SELECT payload FROM records WHERE '+where+' ORDER BY created_at DESC,key DESC',args)):
                payload=json.dumps(public_run(json.loads(raw)),separators=(',',':'))
                size+=len(payload.encode())
                if used+size>MAX_BYTES:raise ValueError('Frozen run snapshot byte capacity reached')
                db.execute('INSERT INTO run_snapshot_rows VALUES(?,?,?)',(snapshot,ordinal,payload))
            db.execute('INSERT INTO run_snapshot_headers VALUES(?,?,?,?,?,?)',(snapshot,principal,fingerprint,expires,total,size))
            db.commit()
        else:
            if not isinstance(snapshot,str) or not re.fullmatch(r'rs_[a-f0-9]{32}',snapshot):raise ValueError('Invalid frozen snapshot')
        db.execute('BEGIN')
        header=db.execute('SELECT principal,filters,expires,total FROM run_snapshot_headers WHERE id=?',(snapshot,)).fetchone()
        if not header or header[2]<=stamp:raise ValueError('Frozen snapshot is unavailable or expired; reset pages')
        if header[0]!=principal:raise PermissionError('Frozen snapshot belongs to another principal')
        if header[1]!=fingerprint:raise ValueError('Frozen snapshot filters changed; reset pages')
        records=[json.loads(row[0]) for row in db.execute('SELECT payload FROM run_snapshot_rows WHERE snapshot=? AND ordinal>=? ORDER BY ordinal LIMIT ?',(snapshot,offset,limit))]
        end=offset+len(records);more=end<header[3]
        return records,{'total':header[3],'limit':limit,'offset':offset,'has_more':more,
            'next_offset':end if more else None,'paging_limit_reached':False,'ordering':'created_at_desc,id_desc',
            'page_consistency':'frozen_run_metadata','snapshot':snapshot,'snapshot_expires_at':header[2]}
