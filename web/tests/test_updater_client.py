import json
import os
import unittest
from unittest.mock import Mock, patch

from services import updater_client


class UpdaterClientTests(unittest.TestCase):
    def setUp(self):
        self._env_backup = {
            "UPDATER_API_URL": os.environ.get("UPDATER_API_URL"),
            "UPDATER_API_TOKEN": os.environ.get("UPDATER_API_TOKEN"),
        }
        os.environ["UPDATER_API_URL"] = "http://updater:8090"
        os.environ["UPDATER_API_TOKEN"] = "secret-token"

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_get_json_sends_bearer_token(self):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True, "status": {"status": "up_to_date"}}

        with patch.object(updater_client.requests, "get", return_value=response) as get:
            payload = updater_client.get_json("/status")

        headers = get.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer secret-token")
        self.assertEqual(payload["status"]["status"], "up_to_date")

    def test_stream_operation_rejects_error_event(self):
        response = Mock(status_code=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [
            json.dumps({"type": "log", "message": "start"}),
            json.dumps({"type": "error", "message": "boom"}),
        ]

        with patch.object(updater_client.requests, "post", return_value=response):
            with self.assertRaises(updater_client.UpdaterClientError):
                updater_client.stream_operation("/restart-stack")

    def test_stream_operation_returns_done_status(self):
        response = Mock(status_code=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [
            json.dumps({"type": "log", "message": "start"}),
            json.dumps({"type": "done", "status": {"status": "restart_scheduled"}}),
        ]
        logs = []

        with patch.object(updater_client.requests, "post", return_value=response) as post:
            status = updater_client.stream_operation(
                "/restart-stack",
                progress_callback=logs.append,
                payload={"lock_token": "abc"},
            )

        self.assertEqual(logs, ["start"])
        self.assertEqual(status["status"], "restart_scheduled")
        self.assertEqual(post.call_args.kwargs["json"], {"lock_token": "abc"})


if __name__ == "__main__":
    unittest.main()
