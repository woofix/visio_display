import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT = ROOT_DIR / "scripts" / "security_bootstrap.sh"


class SecurityBootstrapTests(unittest.TestCase):
    def run_bootstrap(self, mode, install_dir):
        return subprocess.run(
            [str(SCRIPT), mode, str(install_dir)],
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
            check=False,
        )

    def read_env(self, env_file):
        values = {}
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            values[key] = value
        return values

    def test_install_generates_missing_secrets_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp)
            private_dir = install_dir / "private"
            env_file = install_dir / ".env"
            env_file.write_text(f"PRIVATE_DIR={private_dir}\n", encoding="utf-8")

            result = self.run_bootstrap("install", install_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            values = self.read_env(env_file)
            self.assertTrue(values["SECRET_KEY"])
            self.assertTrue(values["POSTGRES_PASSWORD"])
            self.assertTrue(values["DISPLAY_API_TOKEN"])
            self.assertTrue(values["CLIENT_HEARTBEAT_TOKEN"])
            self.assertEqual(values["MEDIA_DIR"], str(install_dir / "media"))
            self.assertEqual(values["PRIVATE_DIR"], str(private_dir))
            self.assertEqual(stat.S_IMODE(env_file.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(private_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((private_dir / "backups").stat().st_mode), 0o700)

    def test_update_does_not_overwrite_existing_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp)
            env_file = install_dir / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "SECRET_KEY=existing-secret-key",
                        "POSTGRES_PASSWORD=existing-postgres-password",
                        "DISPLAY_API_TOKEN=existing-screen-token",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_bootstrap("update", install_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            values = self.read_env(env_file)
            self.assertEqual(values["SECRET_KEY"], "existing-secret-key")
            self.assertEqual(values["POSTGRES_PASSWORD"], "existing-postgres-password")
            self.assertEqual(values["DISPLAY_API_TOKEN"], "existing-screen-token")
            self.assertTrue(values["CLIENT_HEARTBEAT_TOKEN"])

    def test_install_rejects_weak_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp)
            env_file = install_dir / ".env"
            env_file.write_text(
                "SECRET_KEY=remplace_par_une_chaine_aleatoire\nPOSTGRES_PASSWORD=visio\n",
                encoding="utf-8",
            )

            result = self.run_bootstrap("install", install_dir)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("erreur:", result.stderr)

    def test_update_warns_about_weak_values_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp)
            env_file = install_dir / ".env"
            env_file.write_text("SECRET_KEY=\nPOSTGRES_PASSWORD=visio\nDISPLAY_API_TOKEN=screen-token\n", encoding="utf-8")

            result = self.run_bootstrap("update", install_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            values = self.read_env(env_file)
            self.assertEqual(values["SECRET_KEY"], "")
            self.assertEqual(values["POSTGRES_PASSWORD"], "visio")
            self.assertEqual(values["DISPLAY_API_TOKEN"], "screen-token")
            self.assertIn("warning:", result.stderr)

    def test_check_rejects_empty_display_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            install_dir = Path(tmp)
            env_file = install_dir / ".env"
            env_file.write_text(
                "SECRET_KEY=strong-secret\nPOSTGRES_PASSWORD=strong-postgres-password\nDISPLAY_API_TOKEN=\n",
                encoding="utf-8",
            )

            result = self.run_bootstrap("check", install_dir)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DISPLAY_API_TOKEN is mandatory", result.stderr)


if __name__ == "__main__":
    unittest.main()
