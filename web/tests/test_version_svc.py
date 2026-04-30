import json
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
            "source_url": version_svc.DEFAULT_VERSION_URL,
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
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
            "source_url": version_svc.DEFAULT_VERSION_URL,
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
            "source_url": version_svc.DEFAULT_VERSION_URL,
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

        with patch.object(version_svc, "VERSION_CACHE_FILE", self.cache_file), patch.object(
            version_svc,
            "_read_remote_version",
            side_effect=AssertionError("recent failure cache should not be refreshed"),
        ):
            status = version_svc.get_version_status()

        self.assertEqual(status["status"], "check_failed")
        self.assertEqual(status["remote_version"], "")
        self.assertEqual(status["fetch_error"], "source de version inaccessible")
        self.assertTrue(status["fetched_from_cache"])

    def test_force_refresh_ignores_success_cache(self):
        os.environ["VISIO_VERSION_CHECK_TTL_SECONDS"] = "300"
        payload = {
            "remote_version": "1.0.0",
            "fetch_error": "",
            "fetched_at": int(time.time()),
            "source_url": version_svc.DEFAULT_VERSION_URL,
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

        with patch.object(version_svc, "VERSION_CACHE_FILE", self.cache_file), patch.object(
            version_svc,
            "_read_remote_version",
            return_value=("1.2.0", ""),
        ):
            status = version_svc.get_version_status(force_refresh=True)

        self.assertEqual(status["status"], "update_available")
        self.assertEqual(status["remote_version"], "1.2.0")
        self.assertFalse(status["fetched_from_cache"])

    def test_future_cache_timestamp_is_refreshed(self):
        payload = {
            "remote_version": "1.0.0",
            "fetch_error": "",
            "fetched_at": int(time.time()) + 3600,
            "source_url": version_svc.DEFAULT_VERSION_URL,
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
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

    def test_invalid_cache_timestamp_is_refreshed(self):
        payload = {
            "remote_version": "1.0.0",
            "fetch_error": "",
            "fetched_at": "not-a-timestamp",
            "source_url": version_svc.DEFAULT_VERSION_URL,
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
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

    def test_cache_from_old_source_is_refreshed(self):
        payload = {
            "remote_version": "1.6.6",
            "fetch_error": "",
            "fetched_at": int(time.time()),
        }
        with open(self.cache_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

        with patch.object(version_svc, "VERSION_CACHE_FILE", self.cache_file), patch.object(
            version_svc,
            "_read_remote_version",
            return_value=("1.5.6", ""),
        ):
            status = version_svc.get_version_status()

        self.assertEqual(status["remote_version"], "1.5.6")
        self.assertFalse(status["fetched_from_cache"])

    def test_invalid_remote_version_is_reported_as_failure(self):
        with patch.object(version_svc, "urlopen") as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.read.return_value = b"not a version"

            remote_version, fetch_error = version_svc._read_remote_version()

        self.assertEqual(remote_version, "")
        self.assertEqual(fetch_error, "version distante illisible")

    def test_remote_version_reads_github_release_tag(self):
        with patch.object(version_svc, "urlopen") as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.read.return_value = b'{"tag_name": "v1.5.6", "name": "Release 1.5.6"}'

            remote_version, fetch_error = version_svc._read_remote_version()

        self.assertEqual(remote_version, "1.5.6")
        self.assertEqual(fetch_error, "")

    def test_remote_version_still_accepts_plain_version_file(self):
        with patch.object(version_svc, "urlopen") as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.read.return_value = b"1.5.6\n"

            remote_version, fetch_error = version_svc._read_remote_version()

        self.assertEqual(remote_version, "1.5.6")
        self.assertEqual(fetch_error, "")

    def test_cache_write_failure_does_not_break_status(self):
        with patch.object(version_svc, "VERSION_CACHE_FILE", "/dev/null/version_check.json"), patch.object(
            version_svc,
            "_read_remote_version",
            return_value=("1.2.0", ""),
        ):
            status = version_svc.get_version_status(force_refresh=True)

        self.assertEqual(status["status"], "update_available")
        self.assertEqual(status["remote_version"], "1.2.0")

    def test_remote_version_falls_back_to_curl(self):
        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": '{"tag_name": "v1.3.0"}\n'},
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
