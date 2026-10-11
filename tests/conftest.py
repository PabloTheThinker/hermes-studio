"""Shared fixtures for the Hermes Studio test suite.

``home`` gives every test a scratch editor folder; ``desk`` a real desk on a
loopback port. They live here so any test file can use them by name without
importing across modules.
"""

import pytest


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_STUDIO_EDITOR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def desk(home):
    import threading
    from http.server import ThreadingHTTPServer

    from hermes_studio.studio import StudioHandler

    srv = ThreadingHTTPServer(("127.0.0.1", 0), StudioHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
