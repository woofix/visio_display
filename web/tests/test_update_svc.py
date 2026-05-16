import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import system_lock_svc
from services import update_svc


class UpdateServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self._env_backup = {
            "VISIO_GIT_ROOT": os.environ.get("VISIO_GIT_ROOT"),
            "VISIO_UPDATE_REMOTE": os.environ.get("VISIO_UPDATE_REMOTE"),
            "VISIO_UPDATE_BRANCH": os.environ.get("VISIO_UPDATE_BRANCH"),
            "VISIO_UPDATER_ROLE": os.environ.get("VISIO_UPDATER_ROLE"),
            "UPDATER_API_URL": os.environ.get("UPDATER_API_URL"),
            "UPDATER_API_TOKEN": os.environ.get("UPDATER_API_TOKEN"),
        }
        os.environ["VISIO_GIT_ROOT"] = str(self.root / "repo")
        os.environ.pop("VISIO_UPDATE_REMOTE", None)
        os.environ.pop("VISIO_UPDATE_BRANCH", None)
        os.environ.pop("VISIO_UPDATER_ROLE", None)
        os.environ.pop("UPDATER_API_URL", None)
        os.environ.pop("UPDATER_API_TOKEN", None)
        self.compose_patch = patch.object(update_svc, "_docker_compose_command", return_value=(["docker", "compose"], ""))
        self.compose_patch.start()

    def tearDown(self):
        self.compose_patch.stop()
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def _git(self, repo, *args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

    def _init_repo(self, *, with_update_script=True, with_remote=True):
        repo = self.root / "repo"
        repo.mkdir()
        self._git(repo, "init")
        self._git(repo, "checkout", "-b", "main")
        self._git(repo, "config", "user.email", "tests@example.invalid")
        self._git(repo, "config", "user.name", "Tests")
        (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        if with_update_script:
            scripts = repo / "scripts"
            scripts.mkdir()
            update_script = scripts / "update.sh"
            update_script.write_text("#!/usr/bin/env bash\necho update\n", encoding="utf-8")
            update_script.chmod(0o755)
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", "initial")
        if with_remote:
            remote = self.root / "remote.git"
            subprocess.run(["git", "clone", "--bare", str(repo), str(remote)], check=True, capture_output=True, text=True)
            self._git(repo, "remote", "add", "origin", str(remote))
            self._git(repo, "push", "-u", "origin", "main")
        return repo

    def _advance_remote(self):
        remote_work = self.root / "remote-work"
        subprocess.run(
            ["git", "clone", str(self.root / "remote.git"), str(remote_work)],
            check=True,
            capture_output=True,
            text=True,
        )
        self._git(remote_work, "config", "user.email", "tests@example.invalid")
        self._git(remote_work, "config", "user.name", "Tests")
        (remote_work / "VERSION").write_text("1.1.0\n", encoding="utf-8")
        self._git(remote_work, "add", "VERSION")
        self._git(remote_work, "commit", "-m", "remote update")
        self._git(remote_work, "push", "origin", "main")

    def _advance_remote_same_version(self):
        remote_work = self.root / "remote-work"
        subprocess.run(
            ["git", "clone", str(self.root / "remote.git"), str(remote_work)],
            check=True,
            capture_output=True,
            text=True,
        )
        self._git(remote_work, "config", "user.email", "tests@example.invalid")
        self._git(remote_work, "config", "user.name", "Tests")
        (remote_work / "remote.txt").write_text("remote change\n", encoding="utf-8")
        self._git(remote_work, "add", "remote.txt")
        self._git(remote_work, "commit", "-m", "remote same-version update")
        self._git(remote_work, "push", "origin", "main")

    def test_missing_git_directory_is_incompatible(self):
        repo = self.root / "repo"
        repo.mkdir()

        status = update_svc.get_update_status()

        self.assertEqual(status["status"], "incompatible")
        self.assertIn("Git", status["reason"])
        self.assertFalse(status["compatible"])

    def test_missing_remote_is_incompatible(self):
        self._init_repo(with_remote=False)

        status = update_svc.get_update_status()

        self.assertEqual(status["status"], "incompatible")
        self.assertIn("remote", status["reason"].lower())
        self.assertFalse(status["compatible"])

    def test_dirty_repository_is_incompatible(self):
        repo = self._init_repo()
        (repo / "local.txt").write_text("local change\n", encoding="utf-8")

        status = update_svc.get_update_status()

        self.assertEqual(status["status"], "incompatible")
        self.assertEqual(status["git_state"], "dirty")
        self.assertIn("changements locaux", status["reason"])

    def test_restart_stack_allows_dirty_repository(self):
        repo = self._init_repo()
        (repo / "local.txt").write_text("local change\n", encoding="utf-8")

        with (
            patch.object(update_svc, "_current_compose_project_name", return_value="visio_display"),
            patch.object(update_svc, "_start_restart_helper") as helper,
        ):
            result = update_svc.restart_stack()

        helper.assert_called_once()
        self.assertEqual(result["status"], "restart_scheduled")
        self.assertEqual(result["git_state"], "dirty")

    def test_missing_update_script_is_incompatible(self):
        self._init_repo(with_update_script=False)

        status = update_svc.get_update_status()

        self.assertEqual(status["status"], "incompatible")
        self.assertIn("scripts/update.sh", status["reason"])

    def test_fetch_detects_update_available_from_remote_branch(self):
        self._init_repo()
        self._advance_remote()

        status = update_svc.get_update_status(fetch_remote=True)

        self.assertEqual(status["status"], "update_available")
        self.assertTrue(status["compatible"])
        self.assertTrue(status["can_apply"])
        self.assertEqual(status["branch"], "main")
        self.assertEqual(status["target_branch"], "main")
        self.assertEqual(status["local_version"], "1.0.0")
        self.assertEqual(status["remote_version"], "1.1.0")
        self.assertNotEqual(status["local_commit"], status["remote_commit"])

    def test_same_version_remote_ahead_is_update_available(self):
        self._init_repo()
        self._advance_remote_same_version()

        status = update_svc.get_update_status(fetch_remote=True)

        self.assertEqual(status["status"], "update_available")
        self.assertTrue(status["can_apply"])
        self.assertEqual(status["local_version"], "1.0.0")
        self.assertEqual(status["remote_version"], "1.0.0")
        self.assertNotEqual(status["local_commit"], status["remote_commit"])

    def test_same_version_local_ahead_is_not_update_available(self):
        repo = self._init_repo()
        (repo / "local.txt").write_text("local change\n", encoding="utf-8")
        self._git(repo, "add", "local.txt")
        self._git(repo, "commit", "-m", "local same-version change")

        status = update_svc.get_update_status(fetch_remote=True)

        self.assertEqual(status["status"], "local_ahead")
        self.assertFalse(status["can_apply"])
        self.assertEqual(status["local_version"], "1.0.0")
        self.assertEqual(status["remote_version"], "1.0.0")
        self.assertIn("commit local", status["reason"])

    def test_same_version_diverged_is_not_update_available(self):
        repo = self._init_repo()
        (repo / "local.txt").write_text("local change\n", encoding="utf-8")
        self._git(repo, "add", "local.txt")
        self._git(repo, "commit", "-m", "local same-version change")
        self._advance_remote_same_version()

        status = update_svc.get_update_status(fetch_remote=True)

        self.assertEqual(status["status"], "diverged")
        self.assertFalse(status["can_apply"])
        self.assertEqual(status["local_version"], "1.0.0")
        self.assertEqual(status["remote_version"], "1.0.0")
        self.assertIn("identique", status["reason"])

    def test_status_targets_main_even_when_current_branch_is_dev(self):
        repo = self._init_repo()
        (repo / "VERSION").write_text("1.6.12\n", encoding="utf-8")
        self._git(repo, "add", "VERSION")
        self._git(repo, "commit", "-m", "main release")
        self._git(repo, "push", "origin", "main")
        self._git(repo, "checkout", "-b", "dev")
        (repo / "VERSION").write_text("1.6.13\n", encoding="utf-8")
        self._git(repo, "add", "VERSION")
        self._git(repo, "commit", "-m", "dev release")

        status = update_svc.get_update_status(fetch_remote=True)

        self.assertEqual(status["status"], "local_ahead")
        self.assertFalse(status["can_apply"])
        self.assertEqual(status["branch"], "dev")
        self.assertEqual(status["target_branch"], "main")
        self.assertEqual(status["local_version"], "1.6.13")
        self.assertEqual(status["remote_version"], "1.6.12")

    def test_same_commit_on_wrong_branch_requires_branch_switch(self):
        repo = self._init_repo()
        self._git(repo, "checkout", "-b", "dev")

        status = update_svc.get_update_status(fetch_remote=True)

        self.assertEqual(status["status"], "branch_switch_required")
        self.assertTrue(status["can_apply"])
        self.assertEqual(status["branch"], "dev")
        self.assertEqual(status["target_branch"], "main")
        self.assertEqual(status["local_version"], "1.0.0")
        self.assertEqual(status["remote_version"], "1.0.0")
        self.assertEqual(status["local_commit"], status["remote_commit"])
        self.assertIn("branche cible", status["reason"])

    def test_compose_project_is_injected_for_restart_commands(self):
        docker_compose = update_svc._with_compose_project(["docker", "compose"], "visio_display")
        legacy_compose = update_svc._with_compose_project(["docker-compose"], "visio_display")

        self.assertEqual(docker_compose, ["docker", "compose", "--project-name", "visio_display"])
        self.assertEqual(legacy_compose, ["docker-compose", "--project-name", "visio_display"])

    def test_restart_stack_schedules_detached_helper(self):
        status = {
            "compatible": True,
            "repo_dir": str(self.root / "repo"),
            "can_apply": False,
            "can_restart": True,
            "reason": "",
        }
        messages = []

        with (
            patch.object(update_svc, "get_update_status", return_value=status.copy()),
            patch.object(update_svc, "_docker_compose_command", return_value=(["docker-compose"], "")),
            patch.object(update_svc, "_current_compose_project_name", return_value="visio_display"),
            patch.object(update_svc, "_start_restart_helper") as helper,
        ):
            result = update_svc.restart_stack(progress_callback=messages.append)

        helper.assert_called_once_with(
            ["docker-compose", "--project-name", "visio_display", "up", "-d", "--build"],
            repo_dir=str(self.root / "repo"),
            compose_cmd=["docker-compose"],
            project_name="visio_display",
            progress_callback=messages.append,
            lock_token=None,
            verify_runtime=True,
        )
        self.assertEqual(result["status"], "restart_scheduled")
        self.assertEqual(result["status_label"], "Redémarrage lancé")
        self.assertFalse(result["can_restart"])
        self.assertIn("arrière-plan", result["reason"])

    def test_restart_stack_refreshes_updater_after_primary_services(self):
        repo = self.root / "repo"
        repo.mkdir()
        (repo / ".env").write_text(
            "VISIO_HOST_ROOT=/host/repo\nMEDIA_DIR=/host/media\nPRIVATE_DIR=/host/private\nCOMPOSE_PROJECT_NAME=visio_display\n",
            encoding="utf-8",
        )
        status = {
            "compatible": True,
            "repo_dir": str(repo),
            "can_apply": False,
            "can_restart": True,
            "reason": "",
        }

        with (
            patch.dict(os.environ, {"VISIO_UPDATER_ROLE": "1"}, clear=False),
            patch.object(update_svc, "get_update_status", return_value=status.copy()),
            patch.object(update_svc, "_docker_compose_command", return_value=(["docker", "compose"], "")),
            patch.object(update_svc, "_current_compose_project_name", return_value="visio_display"),
            patch.object(update_svc, "_compose_services", return_value=["postgres", "redis", "updater", "app", "worker"]),
            patch.object(update_svc, "_stream_command") as stream_command,
            patch.object(update_svc, "wait_for_runtime_ready") as wait_ready,
            patch.object(update_svc, "release_lock") as release,
        ):
            result = update_svc.restart_stack(lock_token="lock-token")

        stream_command.assert_called_once()
        self.assertEqual(
            stream_command.call_args.args[0],
            ["docker", "compose", "--project-name", "visio_display", "up", "-d", "--build", "--no-deps", "app", "worker"],
        )
        self.assertEqual(stream_command.call_args.kwargs["cwd"], str(repo))
        self.assertIsNone(stream_command.call_args.kwargs["progress_callback"])
        self.assertEqual(stream_command.call_args.kwargs["env"]["MEDIA_DIR"], "/host/media")
        self.assertEqual(stream_command.call_args.kwargs["env"]["PRIVATE_DIR"], "/host/private")
        wait_ready.assert_called_once_with(lock_token="lock-token", project_name="visio_display")
        release.assert_called_once_with("lock-token")
        self.assertEqual(result["status"], "restart_scheduled")

    def test_restart_helper_uses_updated_repo_code_for_runtime_checks(self):
        repo_dir = str(self.root / "repo")

        with patch.object(update_svc, "_run", return_value=update_svc.CommandResult(True)) as run:
            update_svc._start_restart_helper(
                ["docker-compose", "up", "-d", "--build"],
                repo_dir=repo_dir,
                compose_cmd=["docker-compose"],
                project_name="visio_display",
                lock_token="lock-token",
                verify_runtime=True,
            )

        helper_script = run.call_args.args[0][-1]
        self.assertIn(f"PYTHONPATH={repo_dir}/web:/app", helper_script)
        self.assertNotIn("PYTHONPATH=/app python -c", helper_script)
        self.assertIn("wait_for_runtime_ready", helper_script)
        self.assertIn("project_name=", helper_script)
        self.assertIn("visio_display", helper_script)
        self.assertIn("release_lock", helper_script)
        self.assertIn("_read_lock_raw", helper_script)
        self.assertIn("already_detailed", helper_script)
        self.assertIn("lock-token", helper_script)

    def test_restart_helper_uses_updater_service_inside_updater(self):
        repo_dir = str(self.root / "repo")

        with (
            patch.dict(os.environ, {"VISIO_UPDATER_ROLE": "1", "VISIO_HOST_PRIVATE_DIR": "/host/private"}, clear=False),
            patch.object(update_svc, "_current_container_image", return_value="visio_display-updater"),
            patch.object(update_svc, "_run", return_value=update_svc.CommandResult(True)) as run,
        ):
            update_svc._start_restart_helper(
                ["docker", "compose", "up", "-d", "--build"],
                repo_dir=repo_dir,
                compose_cmd=["docker", "compose"],
                project_name="visio_display",
            )

        helper_command = run.call_args.args[0]
        self.assertIn("run", helper_command)
        self.assertTrue(any("updater" in part for part in helper_command))
        self.assertIn("/host/private:/app/data", helper_command)
        self.assertIn("COMPOSE_PROJECT_NAME=visio_display", helper_command)
        self.assertIn("VISIO_COMPOSE_PROJECT_NAME=visio_display", helper_command)
        self.assertNotIn("app", helper_command)

    def test_delegated_status_uses_updater_client(self):
        remote_status = {"status": "up_to_date"}
        with (
            patch.dict(os.environ, {"UPDATER_API_URL": "http://updater:8090", "UPDATER_API_TOKEN": "token"}, clear=False),
            patch.object(update_svc.updater_client, "get_json", return_value={"ok": True, "status": remote_status}) as get_json,
        ):
            status = update_svc.get_update_status(fetch_remote=True)

        get_json.assert_called_once()
        self.assertEqual(status["status"], "up_to_date")

    def test_delegated_restart_streams_through_updater_client(self):
        delegated = {"status": "restart_scheduled", "can_restart": False}
        messages = []
        with (
            patch.dict(os.environ, {"UPDATER_API_URL": "http://updater:8090", "UPDATER_API_TOKEN": "token"}, clear=False),
            patch.object(update_svc.updater_client, "stream_operation", return_value=delegated) as stream_operation,
        ):
            result = update_svc.restart_stack(progress_callback=messages.append, lock_token=None)

        stream_operation.assert_called_once_with("/restart-stack", progress_callback=messages.append, payload=None)
        self.assertEqual(result["status"], "restart_scheduled")

    def test_delegated_restart_sends_lock_token_to_updater(self):
        delegated = {"status": "restart_scheduled", "can_restart": False}
        with (
            patch.dict(os.environ, {"UPDATER_API_URL": "http://updater:8090", "UPDATER_API_TOKEN": "token"}, clear=False),
            patch.object(update_svc.updater_client, "stream_operation", return_value=delegated) as stream_operation,
        ):
            result = update_svc.restart_stack(lock_token="lock-token")

        stream_operation.assert_called_once_with(
            "/restart-stack",
            progress_callback=None,
            payload={"lock_token": "lock-token"},
        )
        self.assertEqual(result["status"], "restart_scheduled")


    def test_system_lock_prevents_parallel_tasks(self):
        lock_file = str(self.root / "system_task.lock")
        with patch.object(system_lock_svc, "LOCK_FILE", lock_file):
            token = system_lock_svc.acquire_lock("update", "Mise à jour en cours...")

            with self.assertRaises(system_lock_svc.SystemTaskAlreadyRunning):
                system_lock_svc.acquire_lock("reboot", "Redémarrage en cours...")

            status = system_lock_svc.get_system_status()
            self.assertTrue(status["active"])
            self.assertEqual(status["type"], "update")

            self.assertTrue(system_lock_svc.release_lock(token))
            self.assertFalse(system_lock_svc.get_system_status()["active"])

    def test_system_lock_cleans_expired_lock(self):
        lock_file = str(self.root / "system_task.lock")
        with patch.object(system_lock_svc, "LOCK_FILE", lock_file):
            system_lock_svc.acquire_lock("update", "Ancienne tâche", timeout_seconds=30)
            data = system_lock_svc._read_lock_raw()
            data["expires_at_ts"] = 1
            system_lock_svc._write_lock(data)

            status = system_lock_svc.get_system_status()

            self.assertFalse(status["active"])
            self.assertFalse(os.path.exists(lock_file))


if __name__ == "__main__":
    unittest.main()
