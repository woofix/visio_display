"""Regression tests for event-driven overnight encoding scheduling."""
from contextlib import nullcontext
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import unittest

import fakeredis

from services import queue_svc


class EncoderSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.context = patch.object(queue_svc, '_app_context_for_background_work', return_value=nullcontext())
        self.feature = patch.object(queue_svc, 'is_feature_enabled', return_value=True)
        self.context.start()
        self.feature.start()
        self.addCleanup(self.context.stop)
        self.addCleanup(self.feature.stop)

    def test_empty_queue_waits_indefinitely_without_reading_clock(self):
        with patch.object(queue_svc, 'load_queue', return_value=[]), \
             patch.object(queue_svc, 'get_queue_now') as clock:
            self.assertIsNone(queue_svc._scheduler_tick())
            clock.assert_not_called()

    def test_disabled_feature_waits_for_config_notification(self):
        with patch.object(queue_svc, 'is_feature_enabled', return_value=False), \
             patch.object(queue_svc, 'load_queue') as queue:
            self.assertIsNone(queue_svc._scheduler_tick())
            queue.assert_not_called()

    def test_pending_video_waits_until_twenty(self):
        now = datetime(2026, 10, 6, 8, 30, tzinfo=ZoneInfo('Europe/Paris'))
        with patch.object(queue_svc, 'load_queue', return_value=[{'status': 'pending'}]), \
             patch.object(queue_svc, 'get_queue_now', return_value=now), \
             patch.object(queue_svc, 'get_redis') as redis:
            self.assertEqual(queue_svc._scheduler_tick(), 11.5 * 3600)
            redis.assert_not_called()

    def test_window_boundaries(self):
        for hour, delay in [(6, 14 * 3600), (19, 3600)]:
            now = datetime(2026, 10, 6, hour, tzinfo=ZoneInfo('Europe/Paris'))
            with self.subTest(hour=hour), \
                 patch.object(queue_svc, 'load_queue', return_value=[{'status': 'pending'}]), \
                 patch.object(queue_svc, 'get_queue_now', return_value=now):
                self.assertEqual(queue_svc._scheduler_tick(), delay)

    def test_elapsed_wait_accounts_for_dst_transition(self):
        tz = ZoneInfo('Europe/Paris')
        for now, hours in [(datetime(2026, 3, 29, 0, tzinfo=tz), 19),
                           (datetime(2026, 10, 25, 0, tzinfo=tz), 21)]:
            self.assertEqual(queue_svc._seconds_until_encoding_window(now), hours * 3600)

    def test_startup_with_pending_work_dispatches_in_open_window(self):
        for hour in (0, 5, 20, 23):
            job = {'id': 'video1', 'filename': 'video.mp4', 'status': 'pending'}
            redis = MagicMock()
            redis.set.return_value = True
            compress = MagicMock()
            with self.subTest(hour=hour), \
                 patch.object(queue_svc, 'load_queue', return_value=[job]), \
                 patch.object(queue_svc, 'get_queue_now', return_value=datetime(2026, 10, 6, hour)), \
                 patch.object(queue_svc, 'get_redis', return_value=redis), \
                 patch.object(queue_svc, 'save_queue'), \
                 patch.object(queue_svc, '_compress_q', return_value=compress):
                self.assertEqual(queue_svc._scheduler_tick(), 0)
                self.assertEqual(job['status'], 'processing')
                compress.enqueue.assert_called_once_with(queue_svc._rq_compress_job, 'video1', job_timeout=3600)
                redis.eval.assert_called_once()

    def test_lock_contention_and_stale_snapshot_do_not_duplicate_jobs(self):
        for locked in (False, True):
            redis = MagicMock()
            redis.set.return_value = locked
            with patch.object(queue_svc, 'load_queue', side_effect=[[{'status': 'pending'}], []]), \
                 patch.object(queue_svc, 'get_queue_now', return_value=datetime(2026, 10, 6, 20)), \
                 patch.object(queue_svc, 'get_redis', return_value=redis), \
                 patch.object(queue_svc, '_compress_q') as compress:
                self.assertEqual(queue_svc._scheduler_tick(), None if locked else 90)
                compress.assert_not_called()

    def test_enqueue_failure_restores_pending_and_releases_lock(self):
        job = {'id': 'video1', 'filename': 'video.mp4', 'status': 'pending'}
        redis = MagicMock()
        redis.set.return_value = True
        compress = MagicMock()
        compress.enqueue.side_effect = RuntimeError('unavailable')
        with patch.object(queue_svc, 'load_queue', return_value=[job]), \
             patch.object(queue_svc, 'get_queue_now', return_value=datetime(2026, 10, 6, 20)), \
             patch.object(queue_svc, 'get_redis', return_value=redis), \
             patch.object(queue_svc, 'save_queue'), \
             patch.object(queue_svc, '_compress_q', return_value=compress):
            with self.assertRaises(RuntimeError):
                queue_svc._scheduler_tick()
            self.assertEqual(job['status'], 'pending')
            self.assertIsNone(job['started'])
            redis.eval.assert_called_once()

    def test_notification_reaches_all_scheduler_processes(self):
        redis = fakeredis.FakeRedis()
        subscribers = [redis.pubsub(ignore_subscribe_messages=True) for _ in range(2)]
        self.addCleanup(redis.close)
        for subscriber in subscribers:
            self.addCleanup(subscriber.close)
            subscriber.subscribe(queue_svc._SCHEDULER_CHANNEL)
            subscriber.get_message(timeout=1)
        with patch.object(queue_svc, 'get_redis', return_value=redis):
            queue_svc.notify_encoder_scheduler()
        for subscriber in subscribers:
            self.assertEqual(subscriber.get_message(timeout=1)['data'], b'changed')

    def test_loop_subscribes_before_recovery_and_blocks_when_empty(self):
        subscriber = MagicMock()
        subscriber.get_message.side_effect = [None, KeyboardInterrupt]
        redis = MagicMock()
        redis.pubsub.return_value.__enter__.return_value = subscriber
        def tick():
            subscriber.subscribe.assert_called_once_with(queue_svc._SCHEDULER_CHANNEL)
            return None
        with patch.object(queue_svc, 'get_redis', return_value=redis), \
             patch.object(queue_svc, '_scheduler_tick', side_effect=tick), \
             patch.object(queue_svc.time, 'sleep') as sleep:
            with self.assertRaises(KeyboardInterrupt):
                queue_svc._scheduler_loop()
            self.assertEqual(subscriber.get_message.call_count, 2)
            subscriber.get_message.assert_called_with(timeout=None)
            sleep.assert_not_called()

    def test_loop_uses_window_deadline_instead_of_minute_poll(self):
        subscriber = MagicMock()
        subscriber.get_message.side_effect = [None, KeyboardInterrupt]
        redis = MagicMock()
        redis.pubsub.return_value.__enter__.return_value = subscriber
        with patch.object(queue_svc, 'get_redis', return_value=redis), \
             patch.object(queue_svc, '_scheduler_tick', return_value=41400), \
             patch.object(queue_svc.time, 'sleep') as sleep:
            with self.assertRaises(KeyboardInterrupt):
                queue_svc._scheduler_loop()
            subscriber.get_message.assert_called_with(timeout=41400)
            sleep.assert_not_called()

    def test_commit_notifications_do_not_fail_if_redis_is_down(self):
        redis = MagicMock()
        redis.publish.side_effect = ConnectionError('offline')
        with patch.object(queue_svc, 'get_redis', return_value=redis):
            queue_svc.notify_encoder_scheduler()
