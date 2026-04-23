import os
import sys
import tempfile
import types
import unittest
from io import BytesIO
from datetime import datetime, timedelta, timezone
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

            from services.activity_svc import get_activity_log

            logs = get_activity_log(limit=10)
            self.assertTrue(any(
                entry["action"] == "config" and entry["details"] == "thème:bleu"
                for entry in logs
            ))

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

    def test_api_images_tolerates_ephemeris_generation_failure(self):
        with self.app.app_context():
            upload_dir = os.path.join(self.app.root_path, "static", "data")
            os.makedirs(upload_dir, exist_ok=True)
            media_path = os.path.join(upload_dir, "fallback.jpg")
            gif_bytes = (
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
                b"\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
                b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            )
            with open(media_path, "wb") as handle:
                handle.write(gif_bytes)

        with patch("blueprints.api.generate_ephemeride_image", side_effect=RuntimeError("boom")):
            response = self.client.get("/api/images")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(any(item["path"].endswith("/fallback.jpg") for item in payload))

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

        default_response = self.client.get("/api/halo")
        hall_response = self.client.get("/api/halo?screen=hall")

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

    def test_api_halo_falls_back_to_configured_default_for_screen_without_custom_color(self):
        with self.app.app_context():
            from services.config_svc import save_config

            save_config({
                "default_halo_color": "#112233",
                "screens": {
                    "reception": {},
                },
            })

        response = self.client.get("/api/halo?screen=reception")

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
            upload_dir = os.path.join(self.app.root_path, "static", "data")
            os.makedirs(upload_dir, exist_ok=True)
            from PIL import Image
            filename = "screen.jpg"
            Image.new("RGB", (2200, 1400), "#336699").save(os.path.join(upload_dir, filename), "JPEG")
            from services import media_svc
            media_svc.generate_standard_renditions(filename)

        response = self.client.get("/api/images?w=1280&h=720")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        target = next(item for item in payload if item["path"])
        self.assertIn("/static/data/variants/screen__jpg__medium.jpg", target["path"])

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
        self.assertIn("?tab=application", response.headers["Location"])

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
        self.assertIn("?tab=application", response.headers["Location"])

        with self.app.app_context():
            from services.config_svc import load_config

            cfg = load_config()
            self.assertEqual(cfg["screens"]["lobby"]["halo_color"], "#123456")

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

            with patch.object(activity_svc.C, "ACTIVITY_LOG_RETENTION_DAYS", 1), patch.object(
                activity_svc.C, "ACTIVITY_LOG_MAX_ROWS", 2
            ):
                deleted = activity_svc._trim_activity_log(now)

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

    def test_superadmin_can_create_and_restore_backup_from_admin(self):
        media_dir = os.path.join(self.temp_dir.name, "media")
        backup_dir = os.path.join(self.temp_dir.name, "private", "backups-test")
        os.makedirs(media_dir, exist_ok=True)
        os.makedirs(backup_dir, exist_ok=True)

        with self.app.app_context():
            from services import backup_svc
            from services.config_svc import save_config, load_config

            with patch.object(backup_svc.C, "UPLOAD_FOLDER", media_dir), patch.object(backup_svc, "BACKUP_DIR", backup_dir):
                with open(os.path.join(media_dir, "hello.txt"), "w", encoding="utf-8") as handle:
                    handle.write("before")
                with open(os.path.join(os.environ["VISIO_DATA_DIR"], "note.txt"), "w", encoding="utf-8") as handle:
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

                with open(os.path.join(media_dir, "hello.txt"), "w", encoding="utf-8") as handle:
                    handle.write("after")
                with open(os.path.join(os.environ["VISIO_DATA_DIR"], "note.txt"), "w", encoding="utf-8") as handle:
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
                with open(os.path.join(os.environ["VISIO_DATA_DIR"], "note.txt"), "r", encoding="utf-8") as handle:
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


if __name__ == "__main__":
    unittest.main()
