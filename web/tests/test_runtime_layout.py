from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT_DIR / "web"


def test_runtime_source_tree_is_web_only():
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY web/ /app" in dockerfile
    assert "COPY services" not in dockerfile
    assert "COPY templates" not in dockerfile
    assert "COPY translations.py" not in dockerfile


def test_root_application_paths_are_not_runtime_shortcuts():
    removed_shortcuts = ("services", "templates", "translations.py", "tools")

    for name in removed_shortcuts:
        path = ROOT_DIR / name
        assert not path.exists(), f"{name} must live under web/, not at the repository root"
        assert not path.is_symlink(), f"{name} must not be a root-level runtime symlink"


def test_persistent_paths_are_env_source_of_truth():
    constants = (WEB_DIR / "constants.py").read_text(encoding="utf-8")
    compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")

    assert "_resolve_required_env_path('MEDIA_DIR')" in constants
    assert "_resolve_required_env_path('PRIVATE_DIR')" in constants
    assert "VISIO_STATIC_MEDIA_DIR" not in constants
    assert "VISIO_DATA_DIR" not in constants

    assert "${MEDIA_DIR:?" in compose
    assert "${PRIVATE_DIR:?" in compose
    assert "VISIO_STATIC_MEDIA_DIR" not in compose
    assert "VISIO_DATA_DIR" not in compose


def test_postgres_url_uses_the_installed_driver():
    compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    requirements = (WEB_DIR / "requirements.txt").read_text(encoding="utf-8")

    assert "psycopg2-binary" in requirements
    assert "postgresql+psycopg2://" in compose
