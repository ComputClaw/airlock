"""Shared test fixtures for Airlock."""

import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

# Set data dir and disable worker before any imports that read them
_tmpdir = tempfile.mkdtemp()
os.environ["AIRLOCK_DATA_DIR"] = _tmpdir
os.environ["AIRLOCK_WORKER_ENABLED"] = "false"


@pytest.fixture(autouse=True)
def _reset_db_module():
    """Reset the db module state between tests."""
    from airlock import db
    db._db = None


@pytest.fixture(autouse=True)
def _clear_executions():
    """Clear in-memory executions and reset worker manager between tests."""
    from airlock.api.agent import _executions, set_worker_manager
    _executions.clear()
    set_worker_manager(None)


@pytest.fixture
async def app(tmp_path):
    """Create a fresh app instance with a clean temp database."""
    import airlock.db as db_module

    os.environ["AIRLOCK_DATA_DIR"] = str(tmp_path)
    db_module.DATA_DIR = tmp_path
    db_module.DB_PATH = tmp_path / "airlock.db"
    db_module._db = None

    from airlock.app import create_app
    application = create_app()

    async with application.router.lifespan_context(application):
        yield application

    db_module._db = None


@pytest.fixture
async def client(app):
    """HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def admin_token(client) -> str:
    """Set up admin and return a valid session token."""
    resp = await client.post(
        "/api/admin/setup",
        json={"password": "testpassword123"},
    )
    assert resp.status_code == 200
    return resp.json()["token"]
