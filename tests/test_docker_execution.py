"""Integration tests for Docker-based script execution (requires Docker)."""

import shutil

import pytest
from httpx import ASGITransport, AsyncClient

from airlock.api.agent import set_worker_manager
from airlock.worker_manager import WorkerManager

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="Docker not available",
)


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
    """HTTP client with worker manager injected."""
    set_worker_manager(worker)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    set_worker_manager(None)


async def test_simple_execution(docker_client):
    """set_result(2 + 2) should produce result=4."""
    resp = await docker_client.post(
        "/execute",
        json={"profile_id": "ark_test", "script": "set_result(2 + 2)"},
    )
    assert resp.status_code == 202
    data = resp.json()
    poll_url = data["poll_url"]

    result = await docker_client.get(poll_url)
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert result.json()["result"] == 4


async def test_stdout_capture(docker_client):
    """print() output should appear in stdout."""
    resp = await docker_client.post(
        "/execute",
        json={"profile_id": "ark_test", "script": 'print("hello")'},
    )
    data = resp.json()
    result = await docker_client.get(data["poll_url"])
    assert result.json()["stdout"] == "hello\n"


async def test_execution_error(docker_client):
    """A script that raises should return status=error."""
    resp = await docker_client.post(
        "/execute",
        json={"profile_id": "ark_test", "script": 'raise ValueError("boom")'},
    )
    data = resp.json()
    result = await docker_client.get(data["poll_url"])
    body = result.json()
    assert body["status"] == "error"
    assert "boom" in body["error"]


async def test_execution_timeout(docker_client):
    """A long-running script should be reported as timeout."""
    resp = await docker_client.post(
        "/execute",
        json={
            "profile_id": "ark_test",
            "script": "import time; time.sleep(999)",
            "timeout": 2,
        },
    )
    data = resp.json()
    result = await docker_client.get(data["poll_url"])
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
