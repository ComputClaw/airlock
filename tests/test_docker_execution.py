"""Integration tests for Docker-based script execution (requires Docker)."""

import hashlib
import hmac as hmac_mod
import shutil

import pytest
from httpx import ASGITransport, AsyncClient

from airlock.worker_manager import WorkerManager

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="Docker not available",
)


def _compute_hmac(secret: str, script: str) -> str:
    """Compute HMAC-SHA256 hex digest for a script."""
    return hmac_mod.new(
        secret.encode("utf-8"),
        script.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def _create_and_lock_profile(client, admin_token):
    """Helper: create a profile, lock it, return (key_id, secret)."""
    resp = await client.post(
        "/api/admin/profiles",
        json={"description": "docker test profile"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    profile_id = resp.json()["id"]

    resp = await client.post(
        f"/api/admin/profiles/{profile_id}/lock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    full_key = data["key"]
    key_id, secret = full_key.split(":", 1)
    return key_id, secret


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for session-scoped async fixtures."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
async def worker():
    """Start worker container once for the entire test session."""
    wm = WorkerManager()
    await wm.start()
    yield wm
    await wm.stop()


@pytest.fixture
async def docker_client(app, worker):
    """HTTP client with worker manager on app.state."""
    app.state.worker_manager = worker
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def docker_admin_token(docker_client) -> str:
    """Set up admin and return a valid session token."""
    resp = await docker_client.post(
        "/api/admin/setup",
        json={"password": "testpassword123"},
    )
    assert resp.status_code == 200
    return resp.json()["token"]


async def test_simple_execution(docker_client, docker_admin_token):
    """set_result(2 + 2) should produce result=4."""
    key_id, secret = await _create_and_lock_profile(docker_client, docker_admin_token)
    script = "set_result(2 + 2)"
    script_hash = _compute_hmac(secret, script)

    resp = await docker_client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 202
    exec_id = resp.json()["execution_id"]

    # Manually dispatch since background tasks don't run in test client
    from airlock.db import get_db
    from airlock.api.agent import _dispatch_to_worker
    db = await get_db()
    await _dispatch_to_worker(
        db, docker_client.app.state.worker_manager, exec_id, script, {}, 60
    )

    result = await docker_client.get(f"/executions/{exec_id}")
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert result.json()["result"] == 4


async def test_stdout_capture(docker_client, docker_admin_token):
    """print() output should appear in stdout."""
    key_id, secret = await _create_and_lock_profile(docker_client, docker_admin_token)
    script = 'print("hello")'
    script_hash = _compute_hmac(secret, script)

    resp = await docker_client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    exec_id = resp.json()["execution_id"]

    from airlock.db import get_db
    from airlock.api.agent import _dispatch_to_worker
    db = await get_db()
    await _dispatch_to_worker(
        db, docker_client.app.state.worker_manager, exec_id, script, {}, 60
    )

    result = await docker_client.get(f"/executions/{exec_id}")
    assert result.json()["stdout"] == "hello\n"


async def test_execution_error(docker_client, docker_admin_token):
    """A script that raises should return status=error."""
    key_id, secret = await _create_and_lock_profile(docker_client, docker_admin_token)
    script = 'raise ValueError("boom")'
    script_hash = _compute_hmac(secret, script)

    resp = await docker_client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    exec_id = resp.json()["execution_id"]

    from airlock.db import get_db
    from airlock.api.agent import _dispatch_to_worker
    db = await get_db()
    await _dispatch_to_worker(
        db, docker_client.app.state.worker_manager, exec_id, script, {}, 60
    )

    result = await docker_client.get(f"/executions/{exec_id}")
    body = result.json()
    assert body["status"] == "error"
    assert "boom" in body["error"]


async def test_execution_timeout(docker_client, docker_admin_token):
    """A long-running script should be reported as timeout."""
    key_id, secret = await _create_and_lock_profile(docker_client, docker_admin_token)
    script = "import time; time.sleep(999)"
    script_hash = _compute_hmac(secret, script)

    resp = await docker_client.post(
        "/execute",
        json={"script": script, "hash": script_hash, "timeout": 2},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    exec_id = resp.json()["execution_id"]

    from airlock.db import get_db
    from airlock.api.agent import _dispatch_to_worker
    db = await get_db()
    await _dispatch_to_worker(
        db, docker_client.app.state.worker_manager, exec_id, script, {}, 2
    )

    result = await docker_client.get(f"/executions/{exec_id}")
    assert result.json()["status"] == "timeout"


async def test_settings_access(worker):
    """Worker should make settings available to the script."""
    result = await worker.execute(
        script='set_result(settings.get("KEY"))',
        settings={"KEY": "val"},
    )
    assert result["status"] == "completed"
    assert result["result"] == "val"


async def test_settings_keys(worker):
    """settings.keys() should return available keys."""
    result = await worker.execute(
        script="set_result(settings.keys())",
        settings={"A": "1", "B": "2"},
    )
    assert result["status"] == "completed"
    assert sorted(result["result"]) == ["A", "B"]
