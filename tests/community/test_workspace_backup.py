"""Actual private files and SQLite backup/restore, lock and corruption failures."""
import fcntl
from pathlib import Path
from unittest.mock import patch
import test_community as fixtures
from api import json_storage as data
from community import backup
from community.auth import CredentialVault
from community.store import Store


class WorkspaceBackupTests(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        data.REPORTS_DIR.mkdir(parents=True,exist_ok=True)
    def test_complete_restore_preserves_keys_records_and_refuses_overwrites(self):
        self.campaign()
        vault=CredentialVault(self.service.store)
        credential=vault.save({'name':'fixture key','provider':'github','secret':'private-backup-fixture-token'})
        self.service.store.save('events',{'id':'event_fixture','seq':1,'event':'finding.created'})
        self.service.store.save('jobs',{'id':'job_backup','status':'queued','campaign_id':'camp_backup'})
        self.service.store.save('schedules',{'id':'schedule_backup','enabled':True})
        self.service.store.save('webhooks',{'id':'webhook_backup','enabled':True})
        self.service.store.save('sessions',{'id':'session_backup','user_id':'user_backup'})
        destination=self.root/'snapshot'
        roots=(data.DATA_DIR,self.service.store.root,data.REPORTS_DIR)
        with self.assertRaises(ValueError):backup.create(*roots,destination)
        backup.create(*roots,destination,writers_stopped=True)
        self.assertTrue(backup.verify(destination)['files'])
        restored=self.root/'restored'
        backup.restore(destination,restored)
        store=Store(restored/'state')
        self.assertEqual(CredentialVault(store).resolve(credential['id']),'private-backup-fixture-token')
        self.assertEqual(store.get('events','event_fixture')['seq'],1)
        self.assertEqual(store.get('jobs','job_backup')['status'],'interrupted')
        self.assertFalse(store.get('schedules','schedule_backup')['enabled'])
        self.assertFalse(store.get('webhooks','webhook_backup')['enabled'])
        self.assertEqual(store.items('sessions'),[])
        self.assertTrue((restored/'state/access-token').exists())
        self.assertTrue(list((restored/'data/campaigns').glob('*.json')))
        expected_events=data.load_finding_history()['events']
        with patch.multiple(data,FINDING_HISTORY_FILE=restored/'data/finding-history.jsonl',
                            VULNERABILITIES_DIR=restored/'data/vulnerabilities'):
            self.assertEqual(data.load_finding_history()['events'],expected_events)

        self.assertEqual(destination.stat().st_mode&0o777,0o700)
        with self.assertRaises(FileExistsError):backup.restore(destination,restored)
        with self.assertRaises(FileExistsError):backup.create(*roots,destination,writers_stopped=True)
        manifest=backup.verify(destination)
        (destination/manifest['files'][0]['path']).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):backup.restore(destination,self.root/'corrupt-restore')
        self.assertFalse((self.root/'corrupt-restore').exists())

    def test_running_daemon_and_source_mutation_refuse_complete_snapshot(self):
        self.campaign();roots=(data.DATA_DIR,self.service.store.root,data.REPORTS_DIR)
        lock=(self.service.store.root/'daemon.lock').open('a+b')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(ValueError):backup.create(*roots,self.root/'locked',writers_stopped=True)
        finally:lock.close()
        real=backup.copy_source
        def changing(source,target):
            real(source,target)
            if source==data.PROJECTS_FILE:source.write_text(source.read_text()+' ')
        with patch.object(backup,'copy_source',side_effect=changing),self.assertRaises(ValueError):
            backup.create(*roots,self.root/'changed',writers_stopped=True)
        self.assertFalse((self.root/'changed').exists())
