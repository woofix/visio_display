import os
import unittest
from unittest.mock import patch

from services import updater_server


class UpdaterServerTests(unittest.TestCase):
    def setUp(self):
        self._env_backup = {"UPDATER_API_TOKEN": os.environ.get("UPDATER_API_TOKEN")}
        os.environ["UPDATER_API_TOKEN"] = "server-token"
        self.app = updater_server.create_app().test_client()

    def tearDown(self):
        if self._env_backup["UPDATER_API_TOKEN"] is None:
            os.environ.pop("UPDATER_API_TOKEN", None)
        else:
            os.environ["UPDATER_API_TOKEN"] = self._env_backup["UPDATER_API_TOKEN"]

    def _headers(self):
        return {"Authorization": "Bearer server-token"}

    def test_rejects_missing_token(self):
        response = self.app.get("/status")
        self.assertEqual(response.status_code, 403)

    def test_operations_are_fixed_allowlist(self):
        response = self.app.get("/operations", headers=self._headers())
        self.assertEqual(response.status_code, 200)
        operations = response.get_json()["operations"]
        self.assertEqual(set(operations), updater_server.ALLOWED_OPERATIONS)
        self.assertNotIn("command", operations)

    def test_status_route_calls_fixed_service_function(self):
        with patch.object(updater_server.update_svc, "get_update_status", return_value={"status": "up_to_date"}) as status:
            response = self.app.get("/status?fetch=1", headers=self._headers())

        self.assertEqual(response.status_code, 200)
        status.assert_called_once_with(fetch_remote=True)
        self.assertEqual(response.get_json()["status"]["status"], "up_to_date")

    def test_status_route_returns_controlled_json_on_failure(self):
        with patch.object(updater_server.update_svc, "get_update_status", side_effect=RuntimeError("git exploded")):
            response = self.app.get("/status?fetch=1", headers=self._headers())

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"]["status"], "unavailable")
        self.assertEqual(payload["status"]["reason"], updater_server.update_svc.PUBLIC_UPDATER_UNAVAILABLE_MESSAGE)
        self.assertNotIn("git exploded", str(payload))

    def test_unknown_command_route_does_not_exist(self):
        response = self.app.post("/command", headers=self._headers(), json={"command": "docker ps"})
        self.assertEqual(response.status_code, 404)

    def test_stream_route_ignores_lock_token(self):
        with patch.object(
            updater_server.update_svc,
            "restart_stack",
            return_value={"status": "restart_scheduled"},
        ) as restart_stack:
            response = self.app.post(
                "/restart-stack",
                headers=self._headers(),
                json={"lock_token": "lock-token"},
            )
            body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "done"', body)
        restart_stack.assert_called_once()
        self.assertIsNone(restart_stack.call_args.kwargs["lock_token"])


if __name__ == "__main__":
    unittest.main()
