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
        }
        os.environ["VISIO_GIT_ROOT"] = str(self.root / "repo")
        os.environ.pop("VISIO_UPDATE_REMOTE", None)
        os.environ.pop("VISIO_UPDATE_BRANCH", None)
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
