import os
import tempfile
import time
import unittest
from unittest.mock import patch

from services import version_svc


class VersionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = os.path.join(self.temp_dir.name, "version_check.json")
        self._env_backup = {
            "APP_VERSION": os.environ.get("APP_VERSION"),
            "VISIO_VERSION_CHECK_TTL_SECONDS": os.environ.get("VISIO_VERSION_CHECK_TTL_SECONDS"),
        }
        os.environ["APP_VERSION"] = "1.0.0"

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_version_check_uses_cache(self):
        os.environ["VISIO_VERSION_CHECK_TTL_SECONDS"] = "300"
        payload = {
            "remote_version": "1.2.0",
            "fetch_error": "",
            "fetched_at": int(time.time()),
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
            import json

            json.dump(payload, handle)

        with patch.object(version_svc, "VERSION_CACHE_FILE", self.cache_file), patch.object(
            version_svc,
            "_read_remote_version",
            side_effect=AssertionError("network should not be called"),
        ):
            status = version_svc.get_version_status()

        self.assertEqual(status["status"], "update_available")
        self.assertEqual(status["remote_version"], "1.2.0")
        self.assertTrue(status["fetched_from_cache"])

    def test_failed_refresh_keeps_previous_remote_version(self):
        os.environ["VISIO_VERSION_CHECK_TTL_SECONDS"] = "300"
        payload = {
            "remote_version": "1.2.0",
            "fetch_error": "",
            "fetched_at": int(time.time()) - 600,
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
            import json

            json.dump(payload, handle)

        with patch.object(version_svc, "VERSION_CACHE_FILE", self.cache_file), patch.object(
            version_svc,
            "_read_remote_version",
            return_value=("", "source de version inaccessible"),
        ):
            status = version_svc.get_version_status()

        self.assertEqual(status["status"], "update_available")
        self.assertEqual(status["remote_version"], "1.2.0")
        self.assertEqual(status["fetch_error"], "source de version inaccessible")
        self.assertFalse(status["fetched_from_cache"])

    def test_empty_failure_cache_is_refreshed_immediately(self):
        os.environ["VISIO_VERSION_CHECK_TTL_SECONDS"] = "300"
        payload = {
            "remote_version": "",
            "fetch_error": "source de version inaccessible",
            "fetched_at": int(time.time()),
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
            import json

            json.dump(payload, handle)

        with patch.object(version_svc, "VERSION_CACHE_FILE", self.cache_file), patch.object(
            version_svc,
            "_read_remote_version",
            return_value=("1.2.0", ""),
        ):
            status = version_svc.get_version_status()

        self.assertEqual(status["status"], "update_available")
        self.assertEqual(status["remote_version"], "1.2.0")
        self.assertFalse(status["fetched_from_cache"])

    def test_remote_version_falls_back_to_curl(self):
        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "1.3.0\n"},
        )()
        with patch.object(version_svc, "urlopen", side_effect=version_svc.URLError("dns")), patch.object(
            version_svc.shutil,
            "which",
            return_value="/usr/bin/curl",
        ), patch.object(version_svc.subprocess, "run", return_value=completed):
            remote_version, fetch_error = version_svc._read_remote_version()

        self.assertEqual(remote_version, "1.3.0")
        self.assertEqual(fetch_error, "")


if __name__ == "__main__":
    unittest.main()
