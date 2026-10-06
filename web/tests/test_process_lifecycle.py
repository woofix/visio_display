"""Check preloaded web worker isolation and dedicated scheduler startup."""
from contextlib import nullcontext
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


WEB_DIR = Path(__file__).resolve().parents[1]


class ProcessLifecycleTests(unittest.TestCase):
    def setUp(self):
        spec = spec_from_file_location('visio_gunicorn_config', WEB_DIR / 'gunicorn.conf.py')
        self.config = module_from_spec(spec)
        spec.loader.exec_module(self.config)

    def test_master_closes_its_connections_before_fork(self):
        self._check_hook(self.config.pre_fork, close=True)

    def test_child_replaces_pool_without_closing_parent_connections(self):
        self._check_hook(self.config.post_fork, close=False)

    def _check_hook(self, hook, *, close):
        session = MagicMock()
        engine = MagicMock()
        other_engine = MagicMock()
        fake_db = types.SimpleNamespace(db=types.SimpleNamespace(
            session=session, engines={None: engine, 'other': other_engine},
        ))
        app = MagicMock()
        app.app_context.return_value = nullcontext()
        server = MagicMock()
        server.app.wsgi.return_value = app
        with patch.dict(sys.modules, {'db': fake_db}):
            hook(server, MagicMock())
        session.remove.assert_called_once()
        engine.dispose.assert_called_once_with(close=close)
        other_engine.dispose.assert_called_once_with(close=close)

    def test_wsgi_preload_starts_no_background_threads(self):
        create_app = MagicMock()
        with patch.dict(sys.modules, {'app': types.SimpleNamespace(create_app=create_app)}):
            runpy.run_path(str(WEB_DIR / 'wsgi.py'))
        create_app.assert_called_once_with(start_scheduler=False)

    def test_dedicated_scheduler_starts_tasks_and_stays_alive(self):
        from services import scheduler_server
        create_app = MagicMock()
        with patch.dict(sys.modules, {'app': types.SimpleNamespace(create_app=create_app)}), \
             patch.object(scheduler_server.threading, 'Event') as event:
            scheduler_server.main()
        create_app.assert_called_once_with(start_scheduler=True)
        event.return_value.wait.assert_called_once_with()

    def test_web_image_loads_pool_isolation_hooks(self):
        dockerfile = (WEB_DIR.parent / 'Dockerfile').read_text()
        self.assertIn('--preload --config /app/gunicorn.conf.py wsgi:app', dockerfile)
