"""Offline complete workspace backup, verification and non-overwriting restore.

The dashboard lock is enforced; --writers-stopped also attests that MCP/engine
and external writers are stopped. It is not a live distributed snapshot service.
"""
import argparse
import fcntl
import hashlib
import json
import os
import secrets
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def sqlite_file(path):
    if path.suffix=='.sqlite3':return True
    with path.open('rb') as file:return file.read(16)==b'SQLite format 3\x00'


def inventory(roots):
    result={}
    for name,root in roots.items():
        for parent,dirs,files in os.walk(root,followlinks=False):
            parent=Path(parent)
            for child in list(dirs):
                path=parent/child
                if path.resolve() in [value for key,value in roots.items() if key!=name]:dirs.remove(child)
                elif path.is_symlink():raise ValueError('Backup source contains a symlink directory')
            for child in files:
                path=parent/child
                if child=='daemon.lock':continue
                if path.is_symlink():raise ValueError('Backup source contains a symlink file')
                info=path.stat()
                if not stat.S_ISREG(info.st_mode):raise ValueError('Backup source contains a special file')
                if child.endswith(('-wal','-shm')):
                    owner=path.with_name(child[:-4])
                    if owner.exists() and sqlite_file(owner):continue
                result[name+'/'+path.relative_to(root).as_posix()]=(path,(info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns),stat.S_IMODE(info.st_mode)&0o777)
    return result


def copy_source(source,target):
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if sqlite_file(source):
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid SQLite source')
    else:shutil.copyfile(source,target)
    target.chmod(0o600)
    with target.open('rb') as file:os.fsync(file.fileno())


def _sync_directory(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def legacy_binding(data_root):
    from api.finding_history_sqlite import _fingerprint
    database=data_root/'finding-history.sqlite3';legacy=data_root/'finding-history.jsonl'
    if not database.exists():return None
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute("SELECT value FROM meta WHERE key='legacy_fingerprint'").fetchone()
        if not row or row[0]!=_fingerprint(legacy):raise ValueError('Finding history legacy source disagrees; recover before backup')
        for item_id,target,stamp,payload,checksum in db.execute('SELECT id,target_id,recorded_at,payload,payload_sha FROM events'):
            item=json.loads(payload)
            if hashlib.sha256(payload.encode()).hexdigest()!=checksum or (item.get('id'),item.get('target_id'),item.get('recorded_at'))!=(item_id,target,stamp):
                raise ValueError('Finding history event integrity failed')
    return digest(legacy) if legacy.exists() else 'missing'


def rebind_restored_history(stage,expected):
    from api.finding_history_sqlite import _fingerprint
    database=stage/'data/finding-history.sqlite3';legacy=stage/'data/finding-history.jsonl'
    if not database.exists():return
    actual=digest(legacy) if legacy.exists() else 'missing'
    if expected is None or actual!=expected:raise ValueError('Restored legacy history does not match verified backup')
    with sqlite3.connect(database) as db:
        changed=db.execute("UPDATE meta SET value=? WHERE key='legacy_fingerprint'",(_fingerprint(legacy),)).rowcount
        if changed!=1:raise ValueError('Restored finding history metadata is missing')
        db.commit()


def create(data_dir,state_dir,reports_dir,destination,writers_stopped=False):
    if writers_stopped is not True:raise ValueError('Stop all dashboard/MCP/engine/external writers and attest writers_stopped')
    roots={name:Path(path).resolve() for name,path in [('data',data_dir),('state',state_dir),('reports',reports_dir)]}
    destination=Path(destination).resolve()
    if len(set(roots.values()))!=3 or any(not root.is_dir() for root in roots.values()):raise ValueError('Supply three distinct existing data/state/reports roots')
    if any(destination.is_relative_to(root) for root in roots.values()):raise ValueError('Backup destination must be outside source roots')
    if destination.exists():raise FileExistsError(destination)
    with (roots['state']/'daemon.lock').open('a+b') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Dashboard is running; stop it before backup') from None
        binding=legacy_binding(roots['data'])
        before=inventory(roots)
        with tempfile.TemporaryDirectory(prefix='.darkmoon-backup-',dir=destination.parent) as temporary:
            stage=Path(temporary)/'snapshot';stage.mkdir(mode=0o700)
            manifest={'version':1,'consistency':'offline_quiescent_writer_attestation','finding_history_legacy_sha256':binding,'files':[]}
            for name in roots:(stage/name).mkdir(mode=0o700)
            for relative,(source,_,mode) in sorted(before.items()):
                target=stage/relative;copy_source(source,target)
                manifest['files'].append({'path':relative,'sha256':digest(target),'mode':mode})
            after=inventory(roots)
            if ({key:value[1] for key,value in before.items()}!={key:value[1] for key,value in after.items()}
                    or legacy_binding(roots['data'])!=binding):
                raise ValueError('Workspace changed while backing up; no complete snapshot published')
            file=stage/'manifest.json'
            with file.open('x') as output:json.dump(manifest,output,sort_keys=True);output.flush();os.fsync(output.fileno())
            file.chmod(0o600)
            for parent,_,_ in os.walk(stage,topdown=False):_sync_directory(parent)
            if destination.exists():raise FileExistsError(destination)
            stage.rename(destination);_sync_directory(destination.parent)
    return {'files':len(manifest['files']),'consistency':manifest['consistency']}


def verify(snapshot):
    snapshot=Path(snapshot).resolve()
    manifest=json.loads((snapshot/'manifest.json').read_text())
    if manifest.get('version')!=1 or manifest.get('consistency')!='offline_quiescent_writer_attestation':raise ValueError('Unsupported backup manifest')
    seen=set()
    for row in manifest['files']:
        name=PurePosixPath(row['path'])
        if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] not in {'data','state','reports'} or str(name) in seen:raise ValueError('Invalid/duplicate backup path')
        seen.add(str(name));path=snapshot/str(name)
        if not path.resolve().is_relative_to(snapshot) or path.is_symlink() or not path.is_file():raise ValueError('Unsafe/missing backup file')
        if type(row['mode']) is not int or not 0<=row['mode']<=0o777 or digest(path)!=row['sha256']:raise ValueError('Backup file failed integrity verification')
        if sqlite_file(path):
            with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup database failed integrity verification')
    history=snapshot/'data/finding-history.sqlite3'
    if history.exists():
        legacy=snapshot/'data/finding-history.jsonl'
        if manifest.get('finding_history_legacy_sha256')!=(digest(legacy) if legacy.exists() else 'missing'):
            raise ValueError('Backup history source binding mismatch')
    return manifest


def quiesce_restored(stage):
    from .store import Store
    store=Store(stage/'state')
    counts={}
    def pause(state):
        for collection in ('sessions','evidence_grants'):
            rows=state.setdefault(collection,{});counts[collection]=len(rows);rows.clear()
        for collection in ('jobs','schedules','webhooks','deliveries','retests'):
            changed=0
            for row in state.get(collection,{}).values():
                if collection in {'schedules','webhooks'} and row.get('enabled'):
                    row['enabled']=False;changed+=1
                elif collection in {'jobs','retests'} and row.get('status') in {'queued','running'}:
                    row['status']='interrupted';row['error']='Restored backup; explicit operator review required';changed+=1
                elif collection=='deliveries' and row.get('status')=='pending':
                    row['status']='failed';row['error']='Restored backup; delivery not replayed';changed+=1
            counts[collection]=changed
    store.update(pause)
    with store.connection() as db:
        for table in ('run_snapshot_rows','run_snapshot_headers'):
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():db.execute('DELETE FROM '+table)
        db.commit()
    recovery=stage/'state/access-token'
    fd=os.open(recovery,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as output:output.write(secrets.token_urlsafe(32)+'\n');output.flush();os.fsync(output.fileno())
    recovery.chmod(0o600)
    return counts


def restore(snapshot,destination):
    snapshot=Path(snapshot).resolve();destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError(destination)
    manifest=verify(snapshot)
    with tempfile.TemporaryDirectory(prefix='.darkmoon-restore-',dir=destination.parent) as temporary:
        stage=Path(temporary)/'workspace';stage.mkdir(mode=0o700)
        for name in ('data','state','reports'):(stage/name).mkdir(mode=0o700)
        for row in manifest['files']:
            target=stage/row['path'];target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            shutil.copyfile(snapshot/row['path'],target);target.chmod(row['mode'])
            if digest(target)!=row['sha256']:raise ValueError('Backup changed during restore')
            with target.open('rb') as file:os.fsync(file.fileno())
        rebind_restored_history(stage,manifest.get('finding_history_legacy_sha256'))
        paused=quiesce_restored(stage)
        report=stage/'restore-report.json'
        with report.open('x') as file:json.dump({'version':1,'quiesced':paused,'recovery_token_rotated':True},file);file.flush();os.fsync(file.fileno())
        report.chmod(0o600)
        for parent,_,_ in os.walk(stage,topdown=False):_sync_directory(parent)
        if destination.exists():raise FileExistsError(destination)
        stage.rename(destination);_sync_directory(destination.parent)
    return {'restored_files':len(manifest['files']),'quiesced':paused,'recovery_token_rotated':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    make=commands.add_parser('create')
    for key in ('data-dir','state-dir','reports-dir','destination'):make.add_argument('--'+key,type=Path,required=True)
    make.add_argument('--writers-stopped',action='store_true')
    check=commands.add_parser('verify');check.add_argument('snapshot',type=Path)
    load=commands.add_parser('restore');load.add_argument('snapshot',type=Path);load.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='create':result=create(args.data_dir,args.state_dir,args.reports_dir,args.destination,args.writers_stopped)
    elif args.command=='verify':result={'files':len(verify(args.snapshot)['files'])}
    else:result=restore(args.snapshot,args.destination)
    print(json.dumps(result))


if __name__=='__main__':main()
