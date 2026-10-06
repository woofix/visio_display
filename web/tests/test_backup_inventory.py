"""SMB visibility and non-blocking inventory regression tests."""
import json
import subprocess
import threading
import unittest
from unittest.mock import MagicMock, patch

import fakeredis
from services import backup_inventory_svc as inventory

A = 'visio-backup-20261006-093522.tar.gz'
B = 'visio-backup-20261006-093802.tar.gz'
SETTINGS = {'enabled': True, 'url': 'smb://server/share/folder', 'username': 'user', 'password': 'secret'}


class BackupInventoryTests(unittest.TestCase):
    def test_merge_retains_smb_only_and_deduplicates_both_locations(self):
        result = inventory.merge_backup_inventory(
            [{'filename': B, 'size_bytes': 123}],
            [{'filename': A, 'size_bytes': 456}, {'filename': B, 'size_bytes': 123}], 'ready',
        )
        self.assertEqual([item['filename'] for item in result], [B, A])
        self.assertEqual((result[0]['local'], result[0]['smb']), (True, True))
        self.assertEqual((result[1]['local'], result[1]['smb']), (False, True))

    def test_uncertain_presence_is_not_reported_as_absence(self):
        for status in ('loading', 'error', 'disabled'):
            result = inventory.merge_backup_inventory([{'filename': A}], [], status)
            self.assertIsNone(result[0]['smb'])
            self.assertTrue(result[0]['local'])

    def test_parse_remote_files_ignores_directories_and_unrelated_names(self):
        output = f'  {A} A 456 Tue Oct 6 2026\n  {B} A 123 Tue Oct 6 2026\n'
        output += '  visio-backup-20261006-110000.tar.gz D 0 Tue Oct 6 2026\n'
        output += '  unrelated.tar.gz A 99 Tue Oct 6 2026\n'
        run = MagicMock(return_value=subprocess.CompletedProcess([], 0, output, ''))
        with patch.object(inventory.subprocess, 'run', run):
            result = inventory.list_smb_backups(SETTINGS)
        self.assertEqual([item['filename'] for item in result], [B, A])
        self.assertEqual(result[1]['size_bytes'], 456)
        self.assertEqual(result[1]['created_at_iso'], '2026-10-06T09:35:22+00:00')
        self.assertEqual(run.call_args.args[0][-1], 'ls visio-backup-*.tar.gz')
        self.assertEqual(run.call_args.kwargs['timeout'], 20)
        self.assertNotIn('secret', ' '.join(run.call_args.args[0]))

    def test_empty_directory_and_authentication_error_are_distinct(self):
        for output, empty in [('NT_STATUS_NO_SUCH_FILE listing \\visio-backup-*.tar.gz', True),
                              ('session setup failed: NT_STATUS_LOGON_FAILURE', False)]:
            with patch.object(inventory.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, output, '')):
                if empty:
                    self.assertEqual(inventory.list_smb_backups(SETTINGS), [])
                else:
                    with self.assertRaises(RuntimeError):
                        inventory.list_smb_backups(SETTINGS)

    def test_disabled_destination_never_contacts_redis_or_smb(self):
        with patch.object(inventory, 'get_redis') as redis, patch.object(inventory, 'list_smb_backups') as smb:
            self.assertEqual(inventory.get_smb_inventory({})['status'], 'disabled')
            redis.assert_not_called()
            smb.assert_not_called()

    def test_cache_prevents_repeated_scans_and_does_not_expose_credentials(self):
        redis = fakeredis.FakeRedis()
        redis.set(inventory._cache_key(SETTINGS), json.dumps({'status': 'ready', 'backups': [{'filename': A}]}))
        with patch.object(inventory, 'get_redis', return_value=redis), \
             patch.object(inventory.threading, 'Thread') as worker:
            result = inventory.get_smb_inventory(SETTINGS)
        self.assertEqual(result['backups'][0]['filename'], A)
        worker.assert_not_called()
        self.assertNotIn('secret', inventory._cache_key(SETTINGS))

    def test_background_scan_returns_before_smb_finishes_and_is_shared(self):
        redis = fakeredis.FakeRedis()
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        def slow_scan(settings):
            started.set()
            release.wait(timeout=5)
            return [{'filename': A}]
        def finish(_script, _keys, lock, key, token, payload, ttl):
            if redis.get(lock) == token.encode():
                redis.setex(key, ttl, payload)
                redis.delete(lock)
            finished.set()
        with patch.object(inventory, 'get_redis', return_value=redis), \
             patch.object(inventory, 'list_smb_backups', side_effect=slow_scan) as scan, \
             patch.object(redis, 'eval', side_effect=finish):
            try:
                self.assertEqual(inventory.get_smb_inventory(SETTINGS)['status'], 'loading')
                self.assertTrue(started.wait(timeout=1))
                self.assertEqual(inventory.get_smb_inventory(SETTINGS, refresh=True)['status'], 'loading')
                self.assertEqual(scan.call_count, 1)
            finally:
                release.set()
            self.assertTrue(finished.wait(timeout=1))
            self.assertEqual(inventory.get_smb_inventory(SETTINGS)['backups'][0]['filename'], A)

    def test_expired_scans_recover_and_errors_hide_credentials(self):
        redis = fakeredis.FakeRedis()
        redis.set(inventory._cache_key(SETTINGS), json.dumps({'status': 'loading', 'backups': []}))
        with patch.object(inventory, 'get_redis', return_value=redis), \
             patch.object(inventory.threading, 'Thread') as worker:
            self.assertEqual(inventory.get_smb_inventory(SETTINGS)['status'], 'loading')
            worker.return_value.start.assert_called_once()
        redis.get = MagicMock(side_effect=RuntimeError('password=secret'))
        with patch.object(inventory, 'get_redis', return_value=redis):
            result = inventory.get_smb_inventory(SETTINGS)
        self.assertEqual(result['status'], 'error')
        self.assertNotIn('secret', json.dumps(result))
