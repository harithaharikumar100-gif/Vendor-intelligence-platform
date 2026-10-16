import os
import sys

# Modules under test live at the repo root, one level above this tests/ dir.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import pytest

@pytest.fixture(autouse=True)
def shutdown_test_workers():
    yield
    server = sys.modules.get('server')
    if server:
        server.close_workers()
