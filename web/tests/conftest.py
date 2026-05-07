import os
import shutil
import sys
import tempfile
from pathlib import Path


WEB_DIR = Path(__file__).resolve().parents[1]
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

_TEST_MEDIA_DIR = tempfile.mkdtemp(prefix="visio-test-media-")
_TEST_PRIVATE_DIR = tempfile.mkdtemp(prefix="visio-test-private-")

os.environ.setdefault("MEDIA_DIR", _TEST_MEDIA_DIR)
os.environ.setdefault("PRIVATE_DIR", _TEST_PRIVATE_DIR)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_MEDIA_DIR, ignore_errors=True)
    shutil.rmtree(_TEST_PRIVATE_DIR, ignore_errors=True)
