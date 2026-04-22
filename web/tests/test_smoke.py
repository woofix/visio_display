import os
import sys
import tempfile
import types
import unittest
from importlib import import_module
from unittest.mock import patch

from sqlalchemy import text


class FakeRedis:
    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        if isinstance(value, str):
            value = value.encode("utf-8")
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)
        return True


class AppSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_redis = FakeRedis()
        os.environ["VISIO_DATA_DIR"] = os.path.join(self.temp_dir.name, "private")
        os.environ["ADMIN_USER"] = "admin"
        os.environ["ADMIN_PASSWORD"] = "supersecure123"
        os.environ["SECRET_KEY"] = "test-secret-key"

        redis_module = types.ModuleType("redis")

        class RedisStub:
            @staticmethod
            def from_url(_url):
                return self.fake_redis

        redis_module.Redis = RedisStub
        sys.modules["redis"] = redis_module

        rq_module = types.ModuleType("rq")

        class QueueStub:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def enqueue(self, *args, **kwargs):
                return None

        rq_module.Queue = QueueStub
        rq_module.get_current_job = lambda: None
        sys.modules["rq"] = rq_module

        rq_job_module = types.ModuleType("rq.job")
        rq_job_module.Job = object
        sys.modules["rq.job"] = rq_job_module

        rq_registry_module = types.ModuleType("rq.registry")
        rq_registry_module.StartedJobRegistry = object
        sys.modules["rq.registry"] = rq_registry_module

        queue_svc = import_module("services.queue_svc")
        users_svc = import_module("services.users_svc")
        self.patchers = [
            patch.object(queue_svc, "get_redis", return_value=self.fake_redis),
            patch.object(users_svc, "get_redis", return_value=self.fake_redis),
        ]
        for patcher in self.patchers:
            patcher.start()

        from app import create_app

        self.app = create_app(
            start_scheduler=False,
            test_config={
                "TESTING": True,
            },
        )
        self.client = self.app.test_client()

    def tearDown(self):
        if hasattr(self, "app"):
            with self.app.app_context():
                from db import db

                db.session.remove()
                db.engine.dispose()
        for patcher in reversed(self.patchers):
            patcher.stop()
        for name in ("redis", "rq", "rq.job", "rq.registry"):
            sys.modules.pop(name, None)
        self.temp_dir.cleanup()

    def _login(self):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        return self.client.post(
            "/login",
            data={
                "username": "admin",
                "password": "supersecure123",
                "_csrf_token": token,
            },
            follow_redirects=False,
        )

    def test_login_redirects_to_admin(self):
        response = self._login()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin"))

    def test_theme_update_persists_for_logged_user(self):
        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "theme-token"
            token = session["_csrf_token"]
        response = self.client.post(
            "/admin/settings/theme",
            data={"theme": "bleu", "_csrf_token": token},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("?tab=theme", response.headers["Location"])

        with self.app.app_context():
            from services.users_svc import get_user

            self.assertEqual(get_user("admin").theme, "bleu")

    def test_save_config_normalizes_missing_sections(self):
        with self.app.app_context():
            from services.config_svc import load_config, save_config

            save_config({"features": {"upload": False}, "screens": {"hall": {"order": ["a.jpg"]}}})
            cfg = load_config()

            self.assertIn("disabled", cfg)
            self.assertIn("campaigns", cfg)
            self.assertIn("hall", cfg["screens"])
            self.assertIn("disabled", cfg["screens"]["hall"])
            self.assertFalse(cfg["features"]["upload"])

    def test_client_heartbeat_schema_contains_extended_columns(self):
        with self.app.app_context():
            from db import db

            rows = db.session.execute(text("PRAGMA table_info(client_heartbeats)")).mappings().all()
            columns = {row["name"] for row in rows}

        self.assertIn("client_version", columns)
        self.assertIn("cpu_load_percent", columns)
        self.assertIn("last_error", columns)
        self.assertIn("resolution", columns)

    def test_client_heartbeat_api_accepts_machine_status_fields(self):
        response = self.client.post(
            "/api/client-heartbeat",
            json={
                "machine_id": "screen-01",
                "hostname": "screen-01",
                "client_name": "Hall",
                "screen_name": "hall",
                "server_url": "https://example.test",
                "client_version": "2026.04",
                "uptime_seconds": 3661,
                "cpu_load_percent": 81.2,
                "ram_used_mb": 512,
                "ram_total_mb": 1024,
                "temperature_c": 72.5,
                "disk_free_mb": 2048,
                "disk_total_mb": 8192,
                "resolution": "1920x1080",
                "last_error": "Kiosk browser not running",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])

        with self.app.app_context():
            from services.clients_svc import list_known_clients

            clients = list_known_clients()

        self.assertEqual(len(clients), 1)
        client = clients[0]
        self.assertEqual(client["client_version"], "2026.04")
        self.assertEqual(client["resolution"], "1920x1080")
        self.assertEqual(client["health_status"], "critical")
        self.assertEqual(client["last_error"], "Kiosk browser not running")


if __name__ == "__main__":
    unittest.main()
