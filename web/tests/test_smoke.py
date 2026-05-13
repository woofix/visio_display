import os
import shutil
import sys
import tarfile
import tempfile
import types
import unittest
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
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
        self._env_backup = {key: os.environ.get(key) for key in (
            "PRIVATE_DIR",
            "MEDIA_DIR",
            "ADMIN_USER",
            "ADMIN_PASSWORD",
            "SECRET_KEY",
            "DATABASE_URL",
            "CLIENT_HEARTBEAT_TOKEN",
            "DISPLAY_API_TOKEN",
            "TRUST_PROXY_COUNT",
        )}
        os.environ["PRIVATE_DIR"] = os.path.join(self.temp_dir.name, "private")
        os.environ["MEDIA_DIR"] = os.path.join(self.temp_dir.name, "media")
        os.environ["ADMIN_USER"] = "admin"
        os.environ["ADMIN_PASSWORD"] = "supersecure123"
        os.environ["SECRET_KEY"] = "test-secret-key"
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(self.temp_dir.name, 'test.sqlite')}"
        os.environ["CLIENT_HEARTBEAT_TOKEN"] = "heartbeat-secret"
        os.environ["DISPLAY_API_TOKEN"] = "screen-secret"
        os.environ.pop("TRUST_PROXY_COUNT", None)

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
            test_config={
                "TESTING": True,
            },
        )
        self.auth_module = import_module("blueprints.auth")
        self.auth_module._login_attempts.clear()
        self.client = self.app.test_client()

    def tearDown(self):
        if hasattr(self, "app"):
            with self.app.app_context():
                from db import db

                db.session.remove()
                db.engine.dispose()
        for patcher in reversed(self.patchers):
            patcher.stop()
        if hasattr(self, "auth_module"):
            self.auth_module._login_attempts.clear()
        for name in ("redis", "rq", "rq.job", "rq.registry"):
            sys.modules.pop(name, None)
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
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

    def test_rate_limited_login_rejects_before_password_check(self):
        self.auth_module._login_attempts["127.0.0.1::admin"] = {
            "failures": [],
            "blocked_until": self.auth_module.time.time() + 60,
        }

        with (
            patch("blueprints.auth.verify_user_password", side_effect=AssertionError("password checked")),
            patch("blueprints.auth.log_activity") as log_activity,
        ):
            response = self.client.post(
                "/login",
                data={
                    "username": "admin",
                    "password": "supersecure123",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 429)
        log_activity.assert_called_once_with("admin", "login", details="rate_limited ip=127.0.0.1")
        with self.client.session_transaction() as session:
            self.assertNotIn("user", session)

    def test_rate_limited_login_ignores_untrusted_forwarded_for(self):
        self.auth_module._login_attempts["127.0.0.1::admin"] = {
            "failures": [],
            "blocked_until": self.auth_module.time.time() + 60,
        }

        with patch("blueprints.auth.verify_user_password", side_effect=AssertionError("password checked")):
            response = self.client.post(
                "/login",
                data={
                    "username": "admin",
                    "password": "supersecure123",
                },
                headers={"X-Forwarded-For": "203.0.113.10"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 429)

    def test_superadmin_can_view_version_page(self):
        self._login()
        version_status = {
            "status": "up_to_date",
            "status_label": "Up to date",
            "status_tone": "success",
            "local_version": "1.0.0",
            "remote_version": "1.0.0",
            "fetch_error": "",
        }
        with patch("blueprints.version.get_update_status", return_value=version_status), patch(
            "services.version_svc.get_version_status",
            return_value=version_status,
        ):
            response = self.client.get("/admin/version")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"1.0.0", response.data)

    def test_settings_admin_nav_links_stay_accessible(self):
        self._login()
        from services.settings_sections import settings_nav_groups

        links = [
            item["href"]
            for group in settings_nav_groups("/admin", superadmin=True)
            for item in group["items"]
        ]
        version_status = {
            "status": "up_to_date",
            "status_label": "Up to date",
            "status_tone": "success",
            "local_version": "1.0.0",
            "remote_version": "1.0.0",
            "fetch_error": "",
        }
        with patch("blueprints.version.get_update_status", return_value=version_status), patch(
            "services.version_svc.get_version_status",
            return_value=version_status,
        ):
            admin_page = self.client.get("/admin")
            html = admin_page.get_data(as_text=True)
            for link in links:
                self.assertIn(f'href="{link}"', html)
                response = self.client.get(link)
                self.assertEqual(response.status_code, 200, link)

    def test_admin_system_status_reports_active_lock(self):
        self._login()
        from services import system_lock_svc

        token = system_lock_svc.acquire_lock("update", "Mise à jour en cours...", progress=25)
        try:
            response = self.client.get("/api/system/status")
        finally:
            system_lock_svc.release_lock(token)

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["system"]["active"])
        self.assertEqual(payload["system"]["type"], "update")
        self.assertEqual(payload["system"]["progress"], 25)

    def test_restart_stream_releases_system_lock_after_scheduling(self):
        self._login()
        from services import system_lock_svc

        with self.client.session_transaction() as session:
            token = session["_csrf_token"]

        def fake_restart(*, progress_callback=None, lock_token=None):
            if progress_callback:
                progress_callback("Redémarrage Docker lancé.")
            return {
                "status": "restart_scheduled",
                "status_label": "Redémarrage lancé",
                "status_tone": "success",
                "can_apply": False,
                "can_restart": False,
                "reason": "La stack Docker redémarre en arrière-plan.",
            }

        with patch("blueprints.version.restart_stack", side_effect=fake_restart):
            response = self.client.post(
                "/admin/version/update/restart-stream",
                headers={
                    "Accept": "application/x-ndjson",
                    "X-CSRF-Token": token,
                },
            )
            body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "done"', body)
        self.assertFalse(system_lock_svc.get_system_status()["active"])

    def test_admin_update_alert_appears_only_when_update_available(self):
        self._login()
        with patch("services.version_svc.get_version_status", return_value={
            "status": "update_available",
            "status_label": "Update available",
            "status_tone": "warning",
            "local_version": "1.0.0",
            "remote_version": "1.1.0",
            "fetch_error": "",
        }):
            response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Mise à jour Visio-Display disponible".encode("utf-8"), response.data)
        self.assertIn(b"1.1.0", response.data)

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
        self.assertTrue(response.headers["Location"].endswith("/admin/settings/theme"))

        with self.app.app_context():
            from services.users_svc import get_user

            self.assertEqual(get_user("admin").theme, "bleu")

            from services.activity_svc import get_activity_log

            logs = get_activity_log(limit=10)
            self.assertTrue(any(
                entry["action"] == "config" and entry["details"] == "theme:bleu"
                for entry in logs
            ))

    def test_superadmin_can_reset_user_password(self):
        with self.app.app_context():
            from services.users_svc import create_user

            create_user("operator", "initial-pass-123", permissions=[])

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "reset-token"
            token = session["_csrf_token"]

        response = self.client.post(
            "/admin/users/reset_password/operator",
            data={"new_password": "updated-pass-123", "_csrf_token": token},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/settings/comptes-permissions"))

        with self.app.app_context():
            from services.users_svc import verify_user_password

            self.assertFalse(verify_user_password("operator", "initial-pass-123"))
            self.assertTrue(verify_user_password("operator", "updated-pass-123"))

    def test_superadmin_can_reset_selected_user_password(self):
        with self.app.app_context():
            from services.users_svc import create_user

            create_user("operator", "initial-pass-123", permissions=[])

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "reset-token"
            token = session["_csrf_token"]

        response = self.client.post(
            "/admin/users/reset_password",
            data={
                "username": "operator",
                "new_password": "selected-pass-123",
                "_csrf_token": token,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            from services.users_svc import verify_user_password

            self.assertTrue(verify_user_password("operator", "selected-pass-123"))

    def test_superadmin_user_routes_redirect_to_settings_sections(self):
        with self.client.session_transaction() as session:
            session["user"] = "admin"

        list_response = self.client.get("/admin/users", follow_redirects=False)
        self.assertEqual(list_response.status_code, 302)
        self.assertTrue(list_response.headers["Location"].endswith("/admin/settings/comptes-permissions"))

        for path in ("/admin/users/add", "/admin/users/create", "/admin/users/new"):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].endswith("/admin/settings/ajouter-compte"))

    def test_superadmin_can_create_user_from_alias_routes(self):
        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "create-token"
            token = session["_csrf_token"]

        response = self.client.post(
            "/admin/users/create",
            data={
                "username": "operator",
                "password": "operator-pass-123",
                "_csrf_token": token,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/settings/comptes-permissions"))

        with self.app.app_context():
            from services.users_svc import get_user, verify_user_password

            self.assertIsNotNone(get_user("operator"))
            self.assertTrue(verify_user_password("operator", "operator-pass-123"))

    def test_superadmin_can_create_user_with_role_permissions_visible(self):
        with self.app.app_context():
            from services.rbac_svc import get_role_by_name

            admin_role = get_role_by_name("admin")
            self.assertIsNotNone(admin_role)

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "create-role-token"
            token = session["_csrf_token"]

        response = self.client.post(
            "/admin/users/add",
            data={
                "username": "operator",
                "password": "operator-pass-123",
                "role_id": str(admin_role.id),
                "_csrf_token": token,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            from constants import ALL_PERMISSIONS
            from services.rbac_svc import get_effective_permissions_for_user

            expected_permissions = {key for key, _ in ALL_PERMISSIONS}
            self.assertEqual(get_effective_permissions_for_user("operator"), expected_permissions)

        page = self.client.get("/admin/settings/comptes-permissions")
        self.assertEqual(page.status_code, 200)
        body = page.get_data(as_text=True)
        self.assertIn(f"{len(expected_permissions)} permission(s) active(s)", body)
        self.assertIn("via rôle", body)

    def test_search_hides_superadmin_links_for_regular_users(self):
        with self.app.app_context():
            from services.users_svc import create_user

            create_user("operator", "operator-pass-123", permissions=[])

        with self.client.session_transaction() as session:
            session["user"] = "operator"

        response = self.client.get("/api/search?q=utilisateurs")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        urls = {item["url"] for item in payload["pages"]}
        config_urls = {item["url"] for item in payload["config"]}

        self.assertNotIn("/admin/settings/comptes-permissions", urls)
        self.assertNotIn("/admin/roles", urls)
        self.assertNotIn("/admin/settings/gestion-ecrans", config_urls)

    def test_save_config_normalizes_missing_sections(self):
        with self.app.app_context():
            from services.config_svc import load_config, save_config

            save_config({"features": {"upload": False}, "screens": {"hall": {"order": ["a.jpg"]}}})
            cfg = load_config()

            self.assertIn("disabled", cfg)
            self.assertIn("campaigns", cfg)
            self.assertIn("activity_log", cfg)
            self.assertIn("hall", cfg["screens"])
            self.assertIn("disabled", cfg["screens"]["hall"])
            self.assertFalse(cfg["features"]["upload"])
            self.assertTrue(cfg["features"]["videos"])
            self.assertTrue(cfg["activity_log"]["auto_delete_enabled"])

    def test_get_all_media_hides_videos_when_feature_disabled(self):
        with self.app.app_context():
            from constants import UPLOAD_FOLDER
            from services.config_svc import save_config
            from services.media_svc import get_all_media

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            with open(os.path.join(UPLOAD_FOLDER, "poster.jpg"), "wb") as handle:
                handle.write(b"jpg")
            with open(os.path.join(UPLOAD_FOLDER, "clip.mp4"), "wb") as handle:
                handle.write(b"mp4")

            save_config({"features": {"videos": False, "ephemeris": False}, "order": ["clip.mp4", "poster.jpg"]})
            self.assertEqual(get_all_media(), ["poster.jpg"])

    def test_upload_rejects_video_when_video_feature_disabled(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({"features": {"videos": False}})

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "upload-token"
            token = session["_csrf_token"]

        response = self.client.post(
            "/upload",
            data={"file": (BytesIO(b"fake-video"), "clip.mp4"), "_csrf_token": token},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "unsupported file type")

    def test_api_images_omits_videos_when_video_feature_disabled(self):
        with self.app.app_context():
            from constants import UPLOAD_FOLDER
            from services.config_svc import save_config

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            image_path = os.path.join(UPLOAD_FOLDER, "poster.jpg")
            with open(image_path, "wb") as handle:
                handle.write(b"jpg")
            with open(os.path.join(UPLOAD_FOLDER, "clip.mp4"), "wb") as handle:
                handle.write(b"mp4")

            save_config({"features": {"videos": False, "ephemeris": False}, "order": ["clip.mp4", "poster.jpg"]})

        response = self.client.get("/api/images", headers={"X-Screen-Token": "screen-secret"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["type"], "image")

    def test_queue_worker_can_check_video_feature_outside_app_context(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({"features": {"videos": False}})

        queue_svc = import_module("services.queue_svc")

        queue_svc._rq_compress_job("job-123")

    def test_mp4_upload_is_saved_and_queued_for_nightly_encoding(self):
        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "upload-token"
            token = session["_csrf_token"]

        with patch("services.upload_svc.enqueue_compress_job", return_value="job-123") as enqueue_job:
            response = self.client.post(
                "/upload",
                data={"file": (BytesIO(b"fake-video"), "clip.mp4"), "_csrf_token": token},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["queued_files"], ["clip.mp4"])
        enqueue_job.assert_called_once()

        with self.app.app_context():
            from constants import UPLOAD_FOLDER
            from services.config_svc import load_config

            self.assertTrue(os.path.exists(os.path.join(UPLOAD_FOLDER, "clip.mp4")))
            cfg = load_config()
            self.assertIn("clip.mp4", cfg.get("disabled", []))

    def test_image_upload_is_saved_and_renditions_are_generated(self):
        from PIL import Image

        image = Image.new("RGB", (24, 16), "blue")
        payload = BytesIO()
        image.save(payload, format="JPEG")
        payload.seek(0)

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "upload-token"
            token = session["_csrf_token"]

        response = self.client.post(
            "/upload",
            data={"file": (payload, "photo.jpg"), "_csrf_token": token},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["redirect"], "/admin/media")

        with self.app.app_context():
            from constants import UPLOAD_FOLDER
            from services.media_svc import get_existing_image_rendition_url

            self.assertTrue(os.path.exists(os.path.join(UPLOAD_FOLDER, "photo.jpg")))
            self.assertIsNotNone(get_existing_image_rendition_url("photo.jpg", "thumb"))

    def test_pdf_upload_is_converted_to_document_pages(self):
        from PIL import Image

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "upload-token"
            token = session["_csrf_token"]

        pages = [
            Image.new("RGB", (24, 16), "white"),
            Image.new("RGB", (24, 16), "black"),
        ]
        with patch("pdf2image.convert_from_path", return_value=pages):
            response = self.client.post(
                "/upload",
                data={"file": (BytesIO(b"%PDF-1.4 fake"), "document.pdf"), "_csrf_token": token},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["redirect"], "/admin/media")

        with self.app.app_context():
            from constants import UPLOAD_FOLDER
            from services.media_svc import get_existing_image_rendition_url

            self.assertFalse(os.path.exists(os.path.join(UPLOAD_FOLDER, "document.pdf")))
            self.assertTrue(os.path.exists(os.path.join(UPLOAD_FOLDER, "document_page_1.jpg")))
            self.assertTrue(os.path.exists(os.path.join(UPLOAD_FOLDER, "document_page_2.jpg")))
            self.assertIsNotNone(get_existing_image_rendition_url("document_page_1.jpg", "thumb"))

    def test_encoding_window_uses_configured_application_timezone(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({"meteo_tz": "Europe/Paris"})

        queue_svc = import_module("services.queue_svc")

        class FixedDateTime:
            @classmethod
            def now(cls, tz=None):
                value = datetime(2026, 1, 1, 19, 30, 0, tzinfo=timezone.utc)
                if tz is None:
                    return value.replace(tzinfo=None)
                return value.astimezone(tz)

        with patch.object(queue_svc, "datetime", FixedDateTime):
            self.assertTrue(queue_svc.is_encoding_window())

        with self.app.app_context():
            from services.config_svc import save_config

            save_config({"meteo_tz": "UTC"})

        with patch.object(queue_svc, "datetime", FixedDateTime):
            self.assertFalse(queue_svc.is_encoding_window())

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
            headers={"X-Client-Token": "heartbeat-secret"},
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

    def test_client_heartbeat_requires_configured_token(self):
        response = self.client.post(
            "/api/client-heartbeat",
            json={"machine_id": "screen-01"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "invalid_client_token")

    def test_client_heartbeat_rejects_when_server_token_missing(self):
        os.environ.pop("CLIENT_HEARTBEAT_TOKEN", None)

        response = self.client.post(
            "/api/client-heartbeat",
            json={"machine_id": "screen-01", "token": "anything"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "client_heartbeat_token_required")

    def test_api_images_tolerates_ephemeris_generation_failure(self):
        with self.app.app_context():
            from constants import UPLOAD_FOLDER

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            media_path = os.path.join(UPLOAD_FOLDER, "fallback.jpg")
            gif_bytes = (
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
                b"\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
                b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            )
            with open(media_path, "wb") as handle:
                handle.write(gif_bytes)

        with patch("blueprints.api.generate_ephemeride_image", side_effect=RuntimeError("boom")):
            response = self.client.get("/api/images", headers={"X-Screen-Token": "screen-secret"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(any(item["name"] == "fallback.jpg" for item in payload))

    def test_api_images_serves_ephemeris_original_not_stale_variant(self):
        with self.app.app_context():
            from constants import IMAGE_VARIANT_FOLDER, UPLOAD_FOLDER
            from services.config_svc import save_config
            from services.media_svc import get_image_rendition_name

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            os.makedirs(IMAGE_VARIANT_FOLDER, exist_ok=True)
            filename = "ephemeride_2026-05-13_12h.jpg"
            with open(os.path.join(UPLOAD_FOLDER, filename), "wb") as handle:
                handle.write(b"fresh-ephemeris")
            stale_variant = get_image_rendition_name(filename, "large")
            with open(os.path.join(IMAGE_VARIANT_FOLDER, stale_variant), "wb") as handle:
                handle.write(b"stale-variant")
            save_config({"features": {"ephemeris": True}, "order": [filename]})

        with patch("blueprints.api.generate_ephemeride_image", return_value=None):
            response = self.client.get(
                "/api/images?w=1920&h=1080",
                headers={"X-Screen-Token": "screen-secret"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        ephemeris_item = next(item for item in payload if item["name"] == filename)
        self.assertIn("/static/data/original/ephemeride_2026-05-13_12h.jpg", ephemeris_item["path"])
        self.assertNotIn("/static/data/variants/", ephemeris_item["path"])

    def test_ephemeris_slot_uses_configured_timezone(self):
        with self.app.app_context():
            from services.config_svc import save_config
            from services import ephemeris_svc

            class FixedDateTime:
                @classmethod
                def now(cls, tz=None):
                    value = datetime(2026, 1, 1, 23, 30, 0, tzinfo=timezone.utc)
                    if tz is None:
                        return value.replace(tzinfo=None)
                    return value.astimezone(tz)

            save_config({"meteo_tz": "Europe/Paris"})
            with patch.object(ephemeris_svc, "datetime", FixedDateTime):
                self.assertEqual(ephemeris_svc.get_ephemeride_slot(), "2026-01-02_00h")

            save_config({"meteo_tz": "UTC"})
            with patch.object(ephemeris_svc, "datetime", FixedDateTime):
                self.assertEqual(ephemeris_svc.get_ephemeride_slot(), "2026-01-01_22h")

    def test_ephemeris_uses_nameday_instead_of_generic_nominis_celebration(self):
        with self.app.app_context():
            from services import ephemeris_svc

            class FakeResponse:
                def __init__(self, payload):
                    self.payload = payload
                    self.text = ""

                def raise_for_status(self):
                    return None

                def json(self):
                    return self.payload

            responses = [
                FakeResponse({
                    "success": True,
                    "data": {"fr": "Rolande"},
                }),
                FakeResponse({
                    "response": {
                        "saintdujour": {
                            "nom": "Notre-Dame de Fatima",
                            "description": "Mémoire de Notre-Dame de Fatima",
                            "contenu": "Notre-Dame de Fatima.",
                        }
                    }
                }),
            ]

            with patch.object(ephemeris_svc.requests, "get", side_effect=responses):
                name, description = ephemeris_svc.get_ephemeride_nominis(date(2026, 5, 13))

        self.assertEqual(name, "Rolande")
        self.assertIn("Fatima", description)

    def test_nameday_cache_is_used_when_online_sources_fail(self):
        with self.app.app_context():
            from services import ephemeris_svc

            target_date = date(2026, 5, 18)
            ephemeris_svc._update_cached_nameday(target_date, "Eric", "test")

            with patch.object(ephemeris_svc.requests, "get", side_effect=RuntimeError("offline")):
                name = ephemeris_svc.get_nameday_for_date(target_date)

        self.assertEqual(name, "Eric")

    def test_ephemeris_existing_file_is_stale_when_nameday_cache_is_newer(self):
        with self.app.app_context():
            from constants import UPLOAD_FOLDER
            from services import ephemeris_svc

            target_date = date(2026, 5, 13)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            image_path = os.path.join(UPLOAD_FOLDER, "ephemeride_2026-05-13_14h.jpg")
            with open(image_path, "wb") as handle:
                handle.write(b"old-card")
            os.utime(image_path, (1, 1))

            ephemeris_svc._update_cached_nameday(target_date, "Rolande", "test")

            self.assertFalse(ephemeris_svc._ephemeride_file_is_current(image_path, target_date))

    def test_ephemeris_does_not_use_notre_dame_when_nameday_sources_fail(self):
        with self.app.app_context():
            from services import ephemeris_svc

            class FakeResponse:
                text = ""

                def raise_for_status(self):
                    return None

                def json(self):
                    return {
                        "response": {
                            "saintdujour": {
                                "nom": "Notre-Dame de Fatima",
                                "description": "",
                                "contenu": "Notre-Dame de Fatima.",
                            }
                        }
                    }

            responses = [
                RuntimeError("nameday offline"),
                RuntimeError("fetedujour offline"),
                FakeResponse(),
            ]

            with patch.object(ephemeris_svc.requests, "get", side_effect=responses):
                name, _description = ephemeris_svc.get_ephemeride_nominis(date(2026, 5, 14))

        self.assertIsNone(name)

    def test_ephemeris_generation_writes_current_card(self):
        from PIL import Image

        with self.app.app_context():
            from constants import UPLOAD_FOLDER
            from services import ephemeris_svc
            from services.config_svc import save_config

            save_config({
                "meteo_ville": "Paris",
                "meteo_lat": 48.8566,
                "meteo_lng": 2.3522,
                "meteo_tz": "Europe/Paris",
                "events": [],
            })
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            with (
                patch.object(ephemeris_svc, "get_ephemeride_nominis", return_value=("Rolande", "Description courte")),
                patch.object(ephemeris_svc, "get_sun_times", return_value=("06:12", "21:34")),
                patch.object(ephemeris_svc, "get_meteo", return_value={
                    "temp": "20°C",
                    "ressenti": "19°C",
                    "condition": "CIEL CLAIR",
                    "vent": "8 km/h",
                    "precip": "0.0 mm",
                    "code": 0,
                }),
                patch.object(ephemeris_svc, "get_next_school_holiday", return_value=None),
            ):
                ephemeris_svc.generate_ephemeride_image(force=True)

            filename = f"ephemeride_{ephemeris_svc.get_ephemeride_slot()}.jpg"
            path = os.path.join(UPLOAD_FOLDER, filename)
            self.assertTrue(os.path.exists(path))
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                self.assertEqual(image.size, (1920, 1080))

    def test_superadmin_can_force_ephemeris_regeneration_from_admin(self):
        self._login()
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]

        with patch("blueprints.ephemeris.generate_ephemeride_image") as generate:
            response = self.client.post(
                "/regen_ephemeride",
                data={"_csrf_token": token},
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin/settings/meteo")
        generate.assert_called_once_with(force=True)

    def test_meteo_settings_page_has_ephemeris_regeneration_button(self):
        self._login()

        response = self.client.get("/admin/settings/meteo")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'action="/regen_ephemeride"', response.data)
        self.assertIn("Régénérer l".encode("utf-8"), response.data)

    def test_api_halo_returns_effective_screen_halo(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({
                "default_halo_color": "#112233",
                "screens": {
                    "hall": {
                        "halo_color": "#abcdef",
                    }
                },
            })

        default_response = self.client.get("/api/halo", headers={"X-Screen-Token": "screen-secret"})
        hall_response = self.client.get("/api/halo?screen=hall", headers={"X-Screen-Token": "screen-secret"})

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(hall_response.status_code, 200)
        self.assertEqual(default_response.get_json(), {
            "color": "#112233",
            "rgb": "17, 34, 51",
        })
        self.assertEqual(hall_response.get_json(), {
            "color": "#abcdef",
            "rgb": "171, 205, 239",
        })

    def test_public_display_endpoints_require_screen_token(self):
        blocked = self.client.get("/api/screens")
        allowed = self.client.get("/api/screens", headers={"X-Screen-Token": "screen-secret"})
        blocked_page = self.client.get("/")
        allowed_page = self.client.get("/?screen_token=screen-secret")

        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.get_json()["error"], "screen_token_required")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(blocked_page.status_code, 403)
        self.assertEqual(allowed_page.status_code, 200)

    def test_admin_preview_links_include_display_token(self):
        self._login()

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/?screen_token=screen-secret"', response.data)

    def test_app_refuses_to_start_without_display_api_token(self):
        from app import create_app

        os.environ.pop("DISPLAY_API_TOKEN", None)

        with self.assertRaisesRegex(RuntimeError, "DISPLAY_API_TOKEN absent"):
            create_app(start_scheduler=False, test_config={"TESTING": True})

    def test_server_stats_service_parses_cpu_and_memory(self):
        from services.server_stats_svc import get_server_stats

        meminfo = (
            "MemTotal:       2097152 kB\n"
            "MemAvailable:   1048576 kB\n"
        )
        with patch("services.server_stats_svc.os.getloadavg", return_value=(1.0, 0.5, 0.25)):
            with patch("services.server_stats_svc.os.cpu_count", return_value=2):
                with patch("builtins.open", unittest.mock.mock_open(read_data=meminfo)):
                    stats = get_server_stats()

        self.assertEqual(stats["cpu_percent"], 50.0)
        self.assertEqual(stats["memory_percent"], 50.0)
        self.assertEqual(stats["memory_used_gb"], 1.0)
        self.assertEqual(stats["memory_total_gb"], 2.0)

    def test_api_halo_falls_back_to_configured_default_for_screen_without_custom_color(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({
                "default_halo_color": "#112233",
                "screens": {
                    "reception": {},
                },
            })

        response = self.client.get("/api/halo?screen=reception", headers={"X-Screen-Token": "screen-secret"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "color": "#112233",
            "rgb": "17, 34, 51",
        })

    def test_build_media_preview_map_uses_precomputed_lightweight_admin_renditions(self):
        media_dir = os.path.join(self.temp_dir.name, "media")
        thumb_dir = os.path.join(media_dir, "thumbnails")
        variant_dir = os.path.join(media_dir, "variants")
        poster_dir = os.path.join(media_dir, "video_posters")
        video_variant_dir = os.path.join(media_dir, "video_variants")
        os.makedirs(thumb_dir, exist_ok=True)
        os.makedirs(variant_dir, exist_ok=True)
        os.makedirs(poster_dir, exist_ok=True)
        os.makedirs(video_variant_dir, exist_ok=True)

        video_path = os.path.join(media_dir, "clip.mp4")
        image_path = os.path.join(media_dir, "poster.jpg")
        with open(video_path, "wb") as handle:
            handle.write(b"video")
        from PIL import Image
        Image.new("RGB", (1600, 900), "#336699").save(image_path, "JPEG")

        from services import media_svc

        def fake_ffmpeg(cmd, capture_output=False, check=False):
            thumb_path = cmd[-1]
            with open(thumb_path, "wb") as handle:
                handle.write(b"thumb")
            class Result:
                returncode = 0
            return Result()

        with patch.object(media_svc, "UPLOAD_FOLDER", media_dir), \
             patch.object(media_svc, "VIDEO_THUMB_FOLDER", thumb_dir), \
             patch.object(media_svc, "IMAGE_VARIANT_FOLDER", variant_dir), \
             patch.object(media_svc, "VIDEO_POSTER_FOLDER", poster_dir), \
             patch.object(media_svc, "VIDEO_VARIANT_FOLDER", video_variant_dir), \
             patch.object(media_svc.subprocess, "run", side_effect=fake_ffmpeg):
            media_svc.generate_standard_renditions("clip.mp4")
            media_svc.generate_standard_renditions("poster.jpg")
            previews = media_svc.build_media_preview_map(["clip.mp4", "poster.jpg"])

        self.assertTrue(previews["clip.mp4"].startswith("/static/data/video_posters/clip__mp4__thumb.jpg?v="))
        self.assertTrue(previews["poster.jpg"].startswith("/static/data/variants/poster__jpg__thumb.jpg?v="))

    def test_delete_media_thumbnail_removes_cached_poster(self):
        media_dir = os.path.join(self.temp_dir.name, "media")
        thumb_dir = os.path.join(media_dir, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        thumb_path = os.path.join(thumb_dir, "clip__mp4.jpg")
        with open(thumb_path, "wb") as handle:
            handle.write(b"thumb")

        from services import media_svc

        with patch.object(media_svc, "VIDEO_THUMB_FOLDER", thumb_dir):
            media_svc.delete_media_thumbnail("clip.mp4")

        self.assertFalse(os.path.exists(thumb_path))

    def test_api_images_uses_precomputed_display_variant_for_images_when_bounds_are_provided(self):
        with self.app.app_context():
            from PIL import Image
            from constants import UPLOAD_FOLDER

            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            filename = "screen.jpg"
            Image.new("RGB", (2200, 1400), "#336699").save(os.path.join(UPLOAD_FOLDER, filename), "JPEG")
            from services import media_svc
            media_svc.generate_standard_renditions(filename)

        response = self.client.get("/api/images?w=1280&h=720", headers={"X-Screen-Token": "screen-secret"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        target = next(item for item in payload if item["name"] == filename)
        self.assertIn("/static/data/variants/screen__jpg__medium.jpg", target["path"])

    def test_group_metadata_is_removed_when_last_media_leaves_group(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({
                "groups": {"poster.jpg": ["Menu"]},
                "group_pools": {"Menu": 2},
                "group_screens": {"Menu": ["hall"]},
                "disabled_groups": ["Menu"],
                "screens": {
                    "hall": {"disabled_groups": ["Menu"]},
                },
            })

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "group-token"

        response = self.client.post(
            "/set_groups/poster.jpg",
            json={"groups": [], "_csrf_token": "group-token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

        with self.app.app_context():
            from services.config_svc import load_config

            cfg = load_config()
            self.assertNotIn("poster.jpg", cfg["groups"])
            self.assertNotIn("Menu", cfg["group_pools"])
            self.assertNotIn("Menu", cfg["group_screens"])
            self.assertNotIn("Menu", cfg["disabled_groups"])
            self.assertNotIn("Menu", cfg["screens"]["hall"]["disabled_groups"])

    def test_recreated_group_name_does_not_inherit_deleted_group_state(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({
                "groups": {"poster.jpg": ["Menu"]},
                "group_pools": {"Menu": 2},
                "group_screens": {"Menu": ["hall"]},
                "disabled_groups": ["Menu"],
                "screens": {
                    "hall": {"disabled_groups": ["Menu"]},
                },
            })

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "group-token"

        remove_response = self.client.post(
            "/set_groups/poster.jpg",
            json={"groups": [], "_csrf_token": "group-token"},
        )
        create_response = self.client.post(
            "/set_groups/poster.jpg",
            json={"groups": ["Menu"], "_csrf_token": "group-token"},
        )

        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(create_response.status_code, 200)

        with self.app.app_context():
            from services.config_svc import load_config
            from services.media_svc import collect_group_states

            cfg = load_config()
            self.assertEqual(cfg["groups"]["poster.jpg"], ["Menu"])
            self.assertEqual(cfg["group_pools"], {})
            self.assertEqual(cfg["group_screens"], {})
            self.assertEqual(cfg["disabled_groups"], [])
            self.assertEqual(cfg["screens"]["hall"]["disabled_groups"], [])
            self.assertEqual(
                collect_group_states(["poster.jpg"], cfg, screen=""),
                [{"name": "Menu", "count": 1, "disabled": False, "pool_size": 0, "screens": []}],
            )

    def test_add_screen_inherits_current_default_halo_color(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({
                "default_halo_color": "#224466",
                "screens": {},
            })

        with self.client.session_transaction() as session:
            session["user"] = "admin"
            session["_csrf_token"] = "screen-token"

        response = self.client.post(
            "/admin/screens/add",
            data={"screen_name": "cantine", "_csrf_token": "screen-token"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("?screen=cantine", response.headers["Location"])

        with self.app.app_context():
            from services.config_svc import load_config

            cfg = load_config()
            self.assertEqual(cfg["screens"]["cantine"]["halo_color"], "#224466")

    def test_simple_admin_can_update_halo_for_assigned_screen(self):
        with self.app.app_context():
            from services.config_svc import save_config
            from services.users_svc import create_user

            save_config({
                "default_halo_color": "#112233",
                "screens": {
                    "hall": {"halo_color": "#abcdef"},
                    "lobby": {"halo_color": "#123456"},
                },
            })
            create_user(
                "editor",
                "editorsecure123",
                superadmin=False,
                permissions=[],
                screens=["hall"],
            )

        with self.client.session_transaction() as session:
            session["user"] = "editor"
            session["_csrf_token"] = "halo-token"
            token = session["_csrf_token"]

        response = self.client.post(
            "/admin/screens/halo",
            data={"screen_name": "hall", "halo_color": "#fedcba", "_csrf_token": token},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/settings/application"))

        with self.app.app_context():
            from services.config_svc import load_config

            cfg = load_config()
            self.assertEqual(cfg["screens"]["hall"]["halo_color"], "#fedcba")
            self.assertEqual(cfg["screens"]["lobby"]["halo_color"], "#123456")

    def test_simple_admin_cannot_update_halo_for_unassigned_screen(self):
        with self.app.app_context():
            from services.config_svc import save_config
            from services.users_svc import create_user

            save_config({
                "default_halo_color": "#112233",
                "screens": {
                    "hall": {"halo_color": "#abcdef"},
                    "lobby": {"halo_color": "#123456"},
                },
            })
            create_user(
                "editor",
                "editorsecure123",
                superadmin=False,
                permissions=[],
                screens=["hall"],
            )

        with self.client.session_transaction() as session:
            session["user"] = "editor"
            session["_csrf_token"] = "halo-token"
            token = session["_csrf_token"]

        response = self.client.post(
            "/admin/screens/halo",
            data={"screen_name": "lobby", "halo_color": "#fedcba", "_csrf_token": token},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/settings/application"))

        with self.app.app_context():
            from services.config_svc import load_config

            cfg = load_config()
            self.assertEqual(cfg["screens"]["lobby"]["halo_color"], "#123456")

    def test_simple_admin_can_open_application_settings_tab(self):
        with self.app.app_context():
            from services.config_svc import save_config
            from services.users_svc import create_user

            save_config({
                "default_halo_color": "#112233",
                "screens": {
                    "hall": {"halo_color": "#abcdef"},
                },
            })
            create_user(
                "editor",
                "editorsecure123",
                superadmin=False,
                permissions=[],
                screens=["hall"],
            )

        with self.client.session_transaction() as session:
            session["user"] = "editor"

        response = self.client.get("/admin/settings/application")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="application" class="admin-section"', html)
        self.assertIn('href="/admin/settings/application"', html)

    def test_activity_log_retention_trims_old_and_excess_rows(self):
        with self.app.app_context():
            from db import ActivityLog, db
            from services import activity_svc

            now = datetime.now(timezone.utc)
            rows = [
                ActivityLog(
                    timestamp=(now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S"),
                    username="admin",
                    action="config",
                    details="old",
                ),
                ActivityLog(
                    timestamp=(now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
                    username="admin",
                    action="config",
                    details="keep-1",
                ),
                ActivityLog(
                    timestamp=(now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
                    username="admin",
                    action="config",
                    details="keep-2",
                ),
                ActivityLog(
                    timestamp=(now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
                    username="admin",
                    action="config",
                    details="drop-overflow",
                ),
            ]
            db.session.add_all(rows)
            db.session.commit()

            deleted = activity_svc._trim_activity_log(
                now,
                settings={
                    "auto_delete_enabled": True,
                    "retention_days": 1,
                    "max_rows": 2,
                },
            )

            self.assertEqual(deleted, 2)

            remaining = ActivityLog.query.order_by(ActivityLog.id.asc()).all()
            self.assertEqual(len(remaining), 2)
            self.assertEqual([row.details for row in remaining], ["keep-2", "drop-overflow"])

    def test_activity_log_is_rendered_in_configured_timezone(self):
        with self.app.app_context():
            from db import ActivityLog, db
            from services.config_svc import save_config
            from services.activity_svc import get_activity_log

            save_config({"meteo_tz": "Europe/Paris"})
            db.session.add(
                ActivityLog(
                    timestamp="2026-01-15T12:30:00",
                    username="admin",
                    action="config",
                    details="timezone-check",
                )
            )
            db.session.commit()

            logs = get_activity_log(limit=1)

            self.assertEqual(logs[0]["timestamp"], "2026-01-15T12:30:00")
            self.assertEqual(logs[0]["timestamp_display"], "2026-01-15 13:30:00")

    def test_superadmin_can_update_activity_log_settings_from_single_page(self):
        self._login()
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]

        response = self.client.post(
            "/admin/activity/settings",
            data={
                "_csrf_token": token,
                "auto_delete_enabled": "1",
                "retention_days": "45",
                "max_rows": "3000",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/activity"))

        with self.app.app_context():
            from services.config_svc import load_config
            from services.activity_svc import get_activity_log

            cfg = load_config()
            self.assertEqual(cfg["activity_log"]["retention_days"], 45)
            self.assertEqual(cfg["activity_log"]["max_rows"], 3000)
            self.assertTrue(cfg["activity_log"]["auto_delete_enabled"])

            logs = get_activity_log(limit=5)
            self.assertTrue(any(
                entry["action"] == "config" and "activity log:" in (entry["details"] or "")
                for entry in logs
            ))

    def test_activity_page_hides_sensitive_controls_for_non_superadmin(self):
        with self.app.app_context():
            from services.users_svc import create_user

            create_user("manager", "managerpass123", superadmin=False, permissions=["upload"])

        with self.client.session_transaction() as session:
            session["user"] = "manager"
            session["_csrf_token"] = "activity-token"

        response = self.client.get("/admin/activity")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Historique détaillé", body)
        self.assertNotIn("Gestion des logs", body)
        self.assertNotIn("Actions sensibles", body)

    def test_superadmin_can_create_and_restore_backup_from_admin(self):
        media_dir = os.path.join(self.temp_dir.name, "media")
        backup_dir = os.path.join(self.temp_dir.name, "private", "backups-test")
        os.makedirs(media_dir, exist_ok=True)
        os.makedirs(backup_dir, exist_ok=True)

        with self.app.app_context():
            from db import db
            from services import backup_svc
            from services.config_svc import save_config, load_config

            def fake_dump(output_path):
                with open(output_path, "w", encoding="utf-8") as handle:
                    handle.write("pg-dump-before")

            def fake_restore(input_path):
                with open(input_path, "r", encoding="utf-8") as handle:
                    restored = handle.read()
                self.assertEqual(restored, "pg-dump-before")
                save_config({"app_name": "Before restore"})

            with patch.object(backup_svc.C, "STATIC_MEDIA_DIR", media_dir), \
                 patch.object(backup_svc, "BACKUP_DIR", backup_dir), \
                 patch.object(backup_svc, "_ensure_supported_runtime", return_value={
                     "supported_postgres_major": backup_svc.SUPPORTED_POSTGRES_MAJOR,
                     "supported_postgres_image": backup_svc.SUPPORTED_POSTGRES_IMAGE,
                     "server_version": "16.13",
                     "server_major": backup_svc.SUPPORTED_POSTGRES_MAJOR,
                     "pg_dump_version": "pg_dump (PostgreSQL) 16.13",
                     "pg_restore_version": "pg_restore (PostgreSQL) 16.13",
                 }), \
                 patch.object(backup_svc, "_dump_postgres_database", side_effect=fake_dump), \
                 patch.object(backup_svc, "_restore_postgres_database", side_effect=fake_restore):
                with open(os.path.join(media_dir, "hello.txt"), "w", encoding="utf-8") as handle:
                    handle.write("before")
                with open(os.path.join(os.environ["PRIVATE_DIR"], "note.txt"), "w", encoding="utf-8") as handle:
                    handle.write("private-before")
                save_config({"app_name": "Before restore"})

                self._login()
                with self.client.session_transaction() as session:
                    token = session["_csrf_token"]

                response = self.client.post(
                    "/admin/settings/backups/create",
                    data={"_csrf_token": token},
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 302)
                backups = backup_svc.list_backups()
                self.assertEqual(len(backups), 1)
                archive_path = os.path.join(backup_dir, backups[0]["filename"])
                with tempfile.TemporaryDirectory() as archive_dir:
                    shutil.unpack_archive(archive_path, archive_dir)
                    self.assertTrue(os.path.isfile(os.path.join(archive_dir, "postgres.dump")))
                    self.assertTrue(os.path.isfile(os.path.join(archive_dir, "media.tar.gz")))
                    self.assertTrue(os.path.isfile(os.path.join(archive_dir, "private.tar.gz")))
                    self.assertTrue(os.path.isfile(os.path.join(archive_dir, "manifest.json")))

                with open(os.path.join(media_dir, "hello.txt"), "w", encoding="utf-8") as handle:
                    handle.write("after")
                with open(os.path.join(os.environ["PRIVATE_DIR"], "note.txt"), "w", encoding="utf-8") as handle:
                    handle.write("private-after")
                save_config({"app_name": "After change"})

                db.session.remove()
                db.engine.dispose()

                with open(archive_path, "rb") as handle:
                    response = self.client.post(
                        "/admin/settings/backups/restore",
                        data={
                            "_csrf_token": token,
                            "backup_file": (BytesIO(handle.read()), backups[0]["filename"]),
                        },
                        content_type="multipart/form-data",
                        follow_redirects=False,
                    )
                self.assertEqual(response.status_code, 302)

                restored_cfg = load_config()
                self.assertEqual(restored_cfg.get("app_name"), "Before restore")
                with open(os.path.join(media_dir, "hello.txt"), "r", encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "before")
                with open(os.path.join(os.environ["PRIVATE_DIR"], "note.txt"), "r", encoding="utf-8") as handle:
                    self.assertEqual(handle.read(), "private-before")

    def test_backup_service_keeps_only_five_most_recent_archives(self):
        backup_dir = os.path.join(self.temp_dir.name, "private", "backups-test")
        os.makedirs(backup_dir, exist_ok=True)

        with self.app.app_context():
            from services import backup_svc

            with patch.object(backup_svc, "BACKUP_DIR", backup_dir):
                now = datetime.now(timezone.utc)
                filenames = []
                for index in range(7):
                    filename = f"visio-backup-20260101-00000{index}.tar.gz"
                    path = os.path.join(backup_dir, filename)
                    with open(path, "wb") as handle:
                        handle.write(f"backup-{index}".encode("utf-8"))
                    ts = (now + timedelta(seconds=index)).timestamp()
                    os.utime(path, (ts, ts))
                    filenames.append(filename)

                backup_svc._prune_old_backups()

                remaining = [item["filename"] for item in backup_svc.list_backups()]
                self.assertEqual(remaining, list(reversed(filenames[-5:])))

    def test_superadmin_settings_backups_tab_renders_existing_backups(self):
        backup_dir = os.path.join(self.temp_dir.name, "private", "backups-test")
        os.makedirs(backup_dir, exist_ok=True)

        with self.app.app_context():
            from services import backup_svc

            with patch.object(backup_svc, "BACKUP_DIR", backup_dir):
                backup_path = os.path.join(backup_dir, "visio-backup-20260101-010203.tar.gz")
                with open(backup_path, "wb") as handle:
                    handle.write(b"backup")

                fixed_dt = datetime(2026, 1, 1, 1, 2, 3, tzinfo=timezone.utc)
                ts = fixed_dt.timestamp()
                os.utime(backup_path, (ts, ts))

                self._login()
                response = self.client.get("/admin/settings/sauvegardes")

                self.assertEqual(response.status_code, 200)
                body = response.get_data(as_text=True)
                self.assertIn("visio-backup-20260101-010203.tar.gz", body)
                self.assertIn("2026-01-01 01:02:03", body)

    def test_superadmin_can_delete_backup_from_admin(self):
        backup_dir = os.path.join(self.temp_dir.name, "private", "backups-test")
        os.makedirs(backup_dir, exist_ok=True)

        with self.app.app_context():
            from services import backup_svc

            with patch.object(backup_svc, "BACKUP_DIR", backup_dir):
                backup_path = os.path.join(backup_dir, "visio-backup-20260101-010203.tar.gz")
                with open(backup_path, "wb") as handle:
                    handle.write(b"backup")

                self._login()
                with self.client.session_transaction() as session:
                    token = session["_csrf_token"]

                response = self.client.post(
                    "/admin/settings/backups/delete/visio-backup-20260101-010203.tar.gz",
                    data={"_csrf_token": token},
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 302)
                self.assertFalse(os.path.exists(backup_path))

    def test_superadmin_can_save_backup_smb_destination(self):
        with self.app.app_context():
            from services.config_svc import load_config

            self._login()
            with self.client.session_transaction() as session:
                token = session["_csrf_token"]

            response = self.client.post(
                "/admin/settings/backups/remote",
                data={
                    "_csrf_token": token,
                    "enabled": "on",
                    "url": "smb://nas/backup/visio",
                    "username": "DOMAIN\\backupuser",
                    "password": "secret123",
                },
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 302)
            cfg = load_config()
            self.assertEqual(cfg["backup_remote"]["url"], "smb://nas/backup/visio")
            self.assertEqual(cfg["backup_remote"]["username"], "DOMAIN\\backupuser")
            self.assertEqual(cfg["backup_remote"]["password"], "secret123")
            self.assertTrue(cfg["backup_remote"]["enabled"])

    def test_backup_smb_password_is_preserved_but_not_rendered(self):
        with self.app.app_context():
            from services.config_svc import load_config, save_config

            cfg = load_config()
            cfg["backup_remote"] = {
                "enabled": True,
                "url": "smb://nas/backup/visio",
                "username": "backupuser",
                "password": "secret123",
            }
            save_config(cfg)

            self._login()
            with self.client.session_transaction() as session:
                token = session["_csrf_token"]

            page = self.client.get("/admin/settings/sauvegardes")
            self.assertEqual(page.status_code, 200)
            self.assertNotIn(b"secret123", page.data)

            response = self.client.post(
                "/admin/settings/backups/remote",
                data={
                    "_csrf_token": token,
                    "enabled": "on",
                    "url": "smb://nas/backup/visio-updated",
                    "username": "backupuser2",
                    "password": "",
                },
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 302)
            cfg = load_config()
            self.assertEqual(cfg["backup_remote"]["url"], "smb://nas/backup/visio-updated")
            self.assertEqual(cfg["backup_remote"]["username"], "backupuser2")
            self.assertEqual(cfg["backup_remote"]["password"], "secret123")

    def test_superadmin_can_copy_backup_to_smb_from_admin(self):
        backup_dir = os.path.join(self.temp_dir.name, "private", "backups-test")
        os.makedirs(backup_dir, exist_ok=True)

        with self.app.app_context():
            from services import backup_svc
            from services.config_svc import load_config, save_config

            with patch.object(backup_svc, "BACKUP_DIR", backup_dir), \
                 patch("blueprints.settings.copy_backup_to_smb") as copy_mock:
                backup_path = os.path.join(backup_dir, "visio-backup-20260101-010203.tar.gz")
                with open(backup_path, "wb") as handle:
                    handle.write(b"backup")

                cfg = load_config()
                cfg["backup_remote"] = {
                    "enabled": True,
                    "url": "smb://nas/backup/visio",
                    "username": "backupuser",
                    "password": "secret123",
                }
                save_config(cfg)

                self._login()
                with self.client.session_transaction() as session:
                    token = session["_csrf_token"]

                response = self.client.post(
                    "/admin/settings/backups/copy/visio-backup-20260101-010203.tar.gz",
                    data={"_csrf_token": token},
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 302)
                copy_mock.assert_called_once()
                args = copy_mock.call_args[0]
                self.assertEqual(args[0], backup_path)
                self.assertEqual(args[1], "visio-backup-20260101-010203.tar.gz")

    def test_safe_extract_tar_rejects_dangerous_entries(self):
        from services.backup_svc import _safe_extract_tar

        dangerous_members = [
            tarfile.TarInfo("../outside.txt"),
            tarfile.TarInfo("/tmp/outside.txt"),
            tarfile.TarInfo("link-out"),
            tarfile.TarInfo("hardlink-out"),
            tarfile.TarInfo("device-out"),
        ]
        dangerous_members[2].type = tarfile.SYMTYPE
        dangerous_members[2].linkname = "/tmp/outside.txt"
        dangerous_members[3].type = tarfile.LNKTYPE
        dangerous_members[3].linkname = "safe.txt"
        dangerous_members[4].type = tarfile.CHRTYPE

        for member in dangerous_members:
            with self.subTest(member=member.name):
                payload = BytesIO()
                with tarfile.open(fileobj=payload, mode="w:gz") as archive:
                    archive.addfile(member)
                payload.seek(0)

                with tempfile.TemporaryDirectory() as target_dir:
                    with tarfile.open(fileobj=payload, mode="r:gz") as archive:
                        with self.assertRaises(ValueError):
                            _safe_extract_tar(archive, target_dir)

    def test_safe_extract_tar_allows_regular_backup_files(self):
        from services.backup_svc import _safe_extract_tar

        payload = BytesIO()
        data = b"backup-data"
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            directory = tarfile.TarInfo("media")
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
            regular = tarfile.TarInfo("media/safe.txt")
            regular.size = len(data)
            archive.addfile(regular, BytesIO(data))
        payload.seek(0)

        with tempfile.TemporaryDirectory() as target_dir:
            with tarfile.open(fileobj=payload, mode="r:gz") as archive:
                _safe_extract_tar(archive, target_dir)
            with open(os.path.join(target_dir, "media", "safe.txt"), "rb") as handle:
                self.assertEqual(handle.read(), data)

    def test_uploaded_phone_photo_rendition_honors_exif_orientation(self):
        from PIL import Image
        import services.media_svc as media_svc

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "phone.jpg")
            rendition_dir = os.path.join(tmp_dir, "variants")
            os.makedirs(rendition_dir)

            image = Image.new("RGB", (40, 20), "red")
            exif = Image.Exif()
            exif[274] = 6
            image.save(source_path, "JPEG", exif=exif)

            with patch.object(media_svc, "IMAGE_VARIANT_FOLDER", rendition_dir):
                rendition_path = media_svc.generate_image_rendition(source_path, "phone.jpg", "thumb")

            self.assertIsNotNone(rendition_path)
            with Image.open(rendition_path) as rendered:
                self.assertEqual(rendered.size, (20, 40))


if __name__ == "__main__":
    unittest.main()
