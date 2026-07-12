# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import sys
import tempfile
import types
import unittest
from importlib import import_module
from unittest.mock import patch

import flask


class FakeRedis:
    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        if isinstance(value, str):
            value = value.encode("utf-8")
        self.store[key] = value
        return True

    def setex(self, key, seconds, value):
        return self.set(key, value, ex=seconds)

    def delete(self, key):
        self.store.pop(key, None)
        return True

    def exists(self, key):
        return 1 if key in self.store else 0

    def incr(self, key, amount=1):
        current = int(self.store.get(key) or 0) + amount
        self.store[key] = str(current).encode("utf-8")
        return current

    def expire(self, key, seconds):
        return key in self.store

    def ttl(self, key):
        return -1


class GuardsTests(unittest.TestCase):
    """Direct unit tests for blueprints/guards.py, the RBAC gate used by every
    protected route. Exercises admin_guard, superadmin_guard, perm_guard and
    feature_guard (redirect and _json variants) against the real is_admin/
    is_superadmin/has_permission/is_feature_enabled implementations, so a
    regression in the access-control chain fails a test instead of shipping
    silently.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fake_redis = FakeRedis()
        self._env_backup = {key: os.environ.get(key) for key in (
            "PRIVATE_DIR",
            "MEDIA_DIR",
            "ADMIN_USER",
            "ADMIN_PASSWORD",
            "SECRET_KEY",
            "DATABASE_URL",
            "CLIENT_HEARTBEAT_TOKEN",
            "DISPLAY_API_TOKEN",
        )}
        os.environ["PRIVATE_DIR"] = os.path.join(self.temp_dir.name, "private")
        os.environ["MEDIA_DIR"] = os.path.join(self.temp_dir.name, "media")
        os.environ["ADMIN_USER"] = "admin"
        os.environ["ADMIN_PASSWORD"] = "supersecure123"
        os.environ["SECRET_KEY"] = "test-secret-key"
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(self.temp_dir.name, 'test.sqlite')}"
        os.environ["CLIENT_HEARTBEAT_TOKEN"] = "heartbeat-secret"
        os.environ["DISPLAY_API_TOKEN"] = "screen-secret"

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

        for module_name in list(sys.modules):
            if (
                module_name in {"app", "app_bootstrap", "constants", "db"}
                or module_name.startswith("blueprints.")
                or module_name.startswith("services.")
            ):
                sys.modules.pop(module_name, None)

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
            test_config={"TESTING": True},
        )
        self.guards = import_module("blueprints.guards")
        self.config_svc = import_module("services.config_svc")

        with self.app.app_context():
            from services.users_svc import create_user

            create_user("operator", "operator-pass-123", permissions=["announcements"])

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
        for module_name in list(sys.modules):
            if (
                module_name in {"app", "app_bootstrap", "constants", "db"}
                or module_name.startswith("blueprints.")
                or module_name.startswith("services.")
            ):
                sys.modules.pop(module_name, None)
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    # -- admin_guard / admin_guard_json ---------------------------------

    def test_admin_guard_redirects_anonymous_to_login(self):
        with self.app.test_request_context("/"):
            result = self.guards.admin_guard()
            self.assertIsNotNone(result)
            self.assertEqual(result.status_code, 302)
            self.assertIn("/login", result.headers["Location"])

    def test_admin_guard_allows_logged_in_user(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "operator"
            self.assertIsNone(self.guards.admin_guard())

    def test_admin_guard_json_returns_401_for_anonymous(self):
        with self.app.test_request_context("/"):
            result = self.guards.admin_guard_json()
            self.assertIsNotNone(result)
            body, status = result
            self.assertEqual(status, 401)
            self.assertEqual(body.get_json(), {"error": "unauthorized"})

    def test_admin_guard_json_allows_logged_in_user(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "operator"
            self.assertIsNone(self.guards.admin_guard_json())

    # -- superadmin_guard / superadmin_guard_json ------------------------

    def test_superadmin_guard_redirects_anonymous_to_login(self):
        with self.app.test_request_context("/"):
            result = self.guards.superadmin_guard()
            self.assertIsNotNone(result)
            self.assertIn("/login", result.headers["Location"])

    def test_superadmin_guard_redirects_non_superadmin_to_admin_page(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "operator"
            result = self.guards.superadmin_guard()
            self.assertIsNotNone(result)
            self.assertEqual(result.status_code, 302)
            self.assertNotIn("/login", result.headers["Location"])

    def test_superadmin_guard_allows_superadmin(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "admin"
            self.assertIsNone(self.guards.superadmin_guard())

    def test_superadmin_guard_json_returns_403_for_non_superadmin(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "operator"
            result = self.guards.superadmin_guard_json()
            self.assertIsNotNone(result)
            body, status = result
            self.assertEqual(status, 403)
            self.assertEqual(body.get_json(), {"error": "superadmin required"})

    def test_superadmin_guard_json_returns_401_for_anonymous(self):
        with self.app.test_request_context("/"):
            result = self.guards.superadmin_guard_json()
            body, status = result
            self.assertEqual(status, 401)

    def test_superadmin_guard_json_allows_superadmin(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "admin"
            self.assertIsNone(self.guards.superadmin_guard_json())

    # -- perm_guard --------------------------------------------------------

    def test_perm_guard_returns_401_for_anonymous(self):
        with self.app.test_request_context("/"):
            result = self.guards.perm_guard("announcements")
            body, status = result
            self.assertEqual(status, 401)

    def test_perm_guard_returns_403_when_permission_missing(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "operator"
            result = self.guards.perm_guard("menus")
            self.assertIsNotNone(result)
            body, status = result
            self.assertEqual(status, 403)
            self.assertEqual(body.get_json(), {"error": "permission denied"})

    def test_perm_guard_allows_user_with_permission(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "operator"
            self.assertIsNone(self.guards.perm_guard("announcements"))

    def test_perm_guard_allows_superadmin_regardless_of_permission_list(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "admin"
            self.assertIsNone(self.guards.perm_guard("some-unrelated-permission"))

    # -- permission_redirect_guard ------------------------------------------

    def test_permission_redirect_guard_redirects_anonymous_to_login(self):
        with self.app.test_request_context("/"):
            result = self.guards.permission_redirect_guard("announcements", "admin.admin_page")
            self.assertIsNotNone(result)
            self.assertIn("/login", result.headers["Location"])

    def test_permission_redirect_guard_redirects_when_permission_missing(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "operator"
            result = self.guards.permission_redirect_guard("menus", "admin.admin_page")
            self.assertIsNotNone(result)
            self.assertEqual(result.status_code, 302)

    def test_permission_redirect_guard_allows_user_with_permission(self):
        with self.app.test_request_context("/"):
            flask.session["user"] = "operator"
            self.assertIsNone(self.guards.permission_redirect_guard("announcements", "admin.admin_page"))

    # -- feature_guard / feature_guard_json ---------------------------------

    def test_feature_guard_allows_when_feature_enabled_by_default(self):
        with self.app.test_request_context("/"):
            self.assertIsNone(self.guards.feature_guard("meteo"))

    def test_feature_guard_redirects_when_feature_disabled(self):
        with self.app.app_context(), patch.object(self.config_svc, "is_feature_enabled", return_value=False):
            with self.app.test_request_context("/"):
                result = self.guards.feature_guard("meteo")
                self.assertIsNotNone(result)
                self.assertEqual(result.status_code, 302)

    def test_feature_guard_json_returns_403_when_feature_disabled(self):
        with self.app.app_context(), patch.object(self.config_svc, "is_feature_enabled", return_value=False):
            with self.app.test_request_context("/"):
                result = self.guards.feature_guard_json("meteo")
                self.assertIsNotNone(result)
                body, status = result
                self.assertEqual(status, 403)
                self.assertEqual(body.get_json(), {"error": "feature disabled"})

    def test_feature_guard_json_allows_when_feature_enabled(self):
        with self.app.test_request_context("/"):
            self.assertIsNone(self.guards.feature_guard_json("meteo"))


if __name__ == "__main__":
    unittest.main()
