"""Tests for the execution engine (Spec 4.1)."""

import hashlib
import hmac as hmac_mod
from unittest.mock import AsyncMock, MagicMock

import pytest

from airlock.services.executions import (
    create_execution,
    get_execution,
    list_executions,
    update_execution,
)


def _compute_hmac(secret: str, script: str) -> str:
    """Compute HMAC-SHA256 hex digest for a script."""
    return hmac_mod.new(
        secret.encode("utf-8"),
        script.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def _create_and_lock_profile(client, admin_token):
    """Helper: create a profile, lock it, return (profile_id, key_id, secret)."""
    resp = await client.post(
        "/api/admin/profiles",
        json={"description": "test profile"},
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
    return profile_id, key_id, secret


def _mock_worker_manager():
    """Create a mock WorkerManager that returns completed status."""
    mock = MagicMock()
    mock.is_running.return_value = True
    mock.execute = AsyncMock(return_value={
        "status": "completed",
        "result": {"answer": 42},
        "stdout": "hello\n",
        "stderr": "",
    })
    return mock


# ============================================================
# Execution Service (SQLite persistence)
# ============================================================


class TestExecutionService:
    """Tests for the execution service CRUD functions."""

    async def test_create_execution_returns_exec_id(self, app):
        from airlock.db import get_db
        db = await get_db()

        # Need a profile for the FK constraint
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.commit()

        exec_id = await create_execution(db, "prof_1", "print('hello')")
        assert exec_id.startswith("exec_")
        assert len(exec_id) == 5 + 16  # "exec_" + 16 hex chars

    async def test_create_execution_record_exists(self, app):
        from airlock.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.commit()

        exec_id = await create_execution(db, "prof_1", "print('hello')")
        record = await get_execution(db, exec_id)
        assert record is not None
        assert record["status"] == "pending"
        assert record["profile_id"] == "prof_1"

    async def test_update_execution_completed(self, app):
        from airlock.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.commit()

        exec_id = await create_execution(db, "prof_1", "x = 1")
        await update_execution(
            db, exec_id, status="completed", result={"x": 1},
            stdout="out", stderr="", execution_time_ms=100,
        )
        record = await get_execution(db, exec_id)
        assert record["status"] == "completed"
        assert record["result"] == {"x": 1}
        assert record["completed_at"] is not None

    async def test_update_execution_error(self, app):
        from airlock.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.commit()

        exec_id = await create_execution(db, "prof_1", "raise Exception")
        await update_execution(
            db, exec_id, status="error", error="Something broke",
            execution_time_ms=50,
        )
        record = await get_execution(db, exec_id)
        assert record["status"] == "error"
        assert record["error"] == "Something broke"
        assert record["completed_at"] is not None

    async def test_update_execution_running_no_completed_at(self, app):
        from airlock.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.commit()

        exec_id = await create_execution(db, "prof_1", "x = 1")
        await update_execution(db, exec_id, status="running")
        record = await get_execution(db, exec_id)
        assert record["status"] == "running"
        assert record["completed_at"] is None

    async def test_get_execution_nonexistent(self, app):
        from airlock.db import get_db
        db = await get_db()
        record = await get_execution(db, "exec_nonexistent")
        assert record is None

    async def test_list_executions_newest_first(self, app):
        from airlock.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.commit()

        # Insert with explicit timestamps to guarantee ordering
        await db.execute(
            """INSERT INTO executions (id, profile_id, script, status, created_at)
               VALUES ('exec_first', 'prof_1', 'script1', 'pending', '2024-01-01 00:00:00')"""
        )
        await db.execute(
            """INSERT INTO executions (id, profile_id, script, status, created_at)
               VALUES ('exec_second', 'prof_1', 'script2', 'pending', '2024-01-01 00:00:01')"""
        )
        await db.commit()

        records = await list_executions(db)
        assert len(records) == 2
        # Newest first
        assert records[0]["id"] == "exec_second"
        assert records[1]["id"] == "exec_first"

    async def test_list_executions_filter_by_profile(self, app):
        from airlock.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_2', 'test2')"
        )
        await db.commit()

        await create_execution(db, "prof_1", "script1")
        await create_execution(db, "prof_2", "script2")

        records = await list_executions(db, profile_id="prof_1")
        assert len(records) == 1
        assert records[0]["profile_id"] == "prof_1"

    async def test_list_executions_filter_by_status(self, app):
        from airlock.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.commit()

        id1 = await create_execution(db, "prof_1", "script1")
        await create_execution(db, "prof_1", "script2")
        await update_execution(db, id1, status="completed", result={"ok": True})

        records = await list_executions(db, status="completed")
        assert len(records) == 1
        assert records[0]["status"] == "completed"

    async def test_list_executions_pagination(self, app):
        from airlock.db import get_db
        db = await get_db()
        await db.execute(
            "INSERT INTO profiles (id, description) VALUES ('prof_1', 'test')"
        )
        await db.commit()

        for i in range(5):
            await create_execution(db, "prof_1", f"script{i}")

        page1 = await list_executions(db, limit=2, offset=0)
        page2 = await list_executions(db, limit=2, offset=2)
        page3 = await list_executions(db, limit=2, offset=4)

        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1

    async def test_list_executions_empty_db(self, app):
        from airlock.db import get_db
        db = await get_db()
        records = await list_executions(db)
        assert records == []


# ============================================================
# Execute Endpoint (mock worker)
# ============================================================


class TestExecuteEndpointMockWorker:
    """Tests for POST /execute with a mocked WorkerManager."""

    async def test_execute_returns_202(self, app, client, admin_token):
        app.state.worker_manager = _mock_worker_manager()
        profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "print('hello')"
        script_hash = _compute_hmac(secret, script)

        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["execution_id"].startswith("exec_")
        assert data["status"] == "pending"

    async def test_execute_poll_url_is_full_url(self, app, client, admin_token):
        app.state.worker_manager = _mock_worker_manager()
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "x = 1"
        script_hash = _compute_hmac(secret, script)

        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        data = resp.json()
        assert data["poll_url"].startswith("http")
        assert "/executions/" in data["poll_url"]

    async def test_execute_creates_sqlite_record(self, app, client, admin_token):
        app.state.worker_manager = _mock_worker_manager()
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "x = 1"
        script_hash = _compute_hmac(secret, script)

        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        exec_id = resp.json()["execution_id"]

        from airlock.db import get_db
        db = await get_db()
        record = await get_execution(db, exec_id)
        assert record is not None

    async def test_execute_without_auth(self, client):
        resp = await client.post(
            "/execute",
            json={"script": "x = 1", "hash": "abc"},
        )
        assert resp.status_code == 401

    async def test_execute_wrong_hmac(self, app, client, admin_token):
        app.state.worker_manager = _mock_worker_manager()
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)

        resp = await client.post(
            "/execute",
            json={"script": "x = 1", "hash": "wrong_hash"},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        assert resp.status_code == 403

    async def test_execute_worker_unavailable(self, app, client, admin_token):
        # Worker is None (not started)
        app.state.worker_manager = None
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "x = 1"
        script_hash = _compute_hmac(secret, script)

        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"]

    async def test_execute_worker_not_running(self, app, client, admin_token):
        mock = MagicMock()
        mock.is_running.return_value = False
        app.state.worker_manager = mock
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "x = 1"
        script_hash = _compute_hmac(secret, script)

        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        assert resp.status_code == 503

    async def test_poll_after_completion(self, app, client, admin_token):
        """After worker completes, GET /executions/{id} returns the result."""
        mock_worker = _mock_worker_manager()
        app.state.worker_manager = mock_worker
        profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "x = 42"
        script_hash = _compute_hmac(secret, script)

        # Submit
        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        exec_id = resp.json()["execution_id"]

        # Manually run the background task (TestClient doesn't run background tasks automatically)
        from airlock.db import get_db
        from airlock.api.agent import _dispatch_to_worker
        db = await get_db()
        settings = {}
        await _dispatch_to_worker(db, mock_worker, exec_id, script, settings, 60)

        # Poll
        poll_resp = await client.get(f"/executions/{exec_id}")
        assert poll_resp.status_code == 200
        data = poll_resp.json()
        assert data["status"] == "completed"
        assert data["result"] == {"answer": 42}
        assert data["stdout"] == "hello\n"
        assert data["execution_time_ms"] is not None


# ============================================================
# Execution History
# ============================================================


class TestExecutionHistory:
    """Tests for execution history endpoints."""

    async def test_agent_list_executions(self, app, client, admin_token):
        """GET /executions returns summary list for authenticated profile."""
        mock_worker = _mock_worker_manager()
        app.state.worker_manager = mock_worker
        profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)

        # Create an execution
        script = "x = 1"
        script_hash = _compute_hmac(secret, script)
        await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )

        # List
        resp = await client.get(
            "/executions",
            headers={"Authorization": f"Bearer {key_id}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["executions"]) == 1
        assert "execution_id" in data["executions"][0]
        assert "status" in data["executions"][0]
        # Summary should NOT include result/stdout/stderr
        assert "result" not in data["executions"][0]

    async def test_agent_list_executions_status_filter(self, app, client, admin_token):
        mock_worker = _mock_worker_manager()
        app.state.worker_manager = mock_worker
        profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)

        script = "x = 1"
        script_hash = _compute_hmac(secret, script)
        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        exec_id = resp.json()["execution_id"]

        # Run the worker task to set status to completed
        from airlock.db import get_db
        from airlock.api.agent import _dispatch_to_worker
        db = await get_db()
        await _dispatch_to_worker(db, mock_worker, exec_id, script, {}, 60)

        # Filter by completed
        resp = await client.get(
            "/executions?status=completed",
            headers={"Authorization": f"Bearer {key_id}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["executions"]) == 1

        # Filter by pending — should be empty now
        resp = await client.get(
            "/executions?status=pending",
            headers={"Authorization": f"Bearer {key_id}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["executions"]) == 0

    async def test_agent_list_excludes_other_profiles(self, app, client, admin_token):
        """Agents should only see their own profile's executions."""
        mock_worker = _mock_worker_manager()
        app.state.worker_manager = mock_worker

        # Create two profiles
        _, key_id_1, secret_1 = await _create_and_lock_profile(client, admin_token)
        _, key_id_2, secret_2 = await _create_and_lock_profile(client, admin_token)

        # Execute under profile 1
        script = "x = 1"
        await client.post(
            "/execute",
            json={"script": script, "hash": _compute_hmac(secret_1, script)},
            headers={"Authorization": f"Bearer {key_id_1}"},
        )

        # List from profile 2 — should be empty
        resp = await client.get(
            "/executions",
            headers={"Authorization": f"Bearer {key_id_2}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["executions"]) == 0

    async def test_admin_list_executions(self, app, client, admin_token):
        """Admin can see all executions with full details."""
        mock_worker = _mock_worker_manager()
        app.state.worker_manager = mock_worker
        profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)

        script = "x = 1"
        script_hash = _compute_hmac(secret, script)
        await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )

        resp = await client.get(
            "/api/admin/executions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["executions"]) == 1
        # Admin list includes full details
        assert "profile_id" in data["executions"][0]
        assert "result" in data["executions"][0]

    async def test_admin_list_executions_filter_by_profile(self, app, client, admin_token):
        mock_worker = _mock_worker_manager()
        app.state.worker_manager = mock_worker
        profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)

        script = "x = 1"
        script_hash = _compute_hmac(secret, script)
        await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )

        resp = await client.get(
            f"/api/admin/executions?profile_id={profile_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["executions"]) == 1

        # Filter by nonexistent profile
        resp = await client.get(
            "/api/admin/executions?profile_id=nonexistent",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["executions"]) == 0

    async def test_admin_get_execution_includes_script(self, app, client, admin_token):
        mock_worker = _mock_worker_manager()
        app.state.worker_manager = mock_worker
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)

        script = "x = 42"
        script_hash = _compute_hmac(secret, script)
        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        exec_id = resp.json()["execution_id"]

        resp = await client.get(
            f"/api/admin/executions/{exec_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["script"] == "x = 42"
        assert data["execution_id"] == exec_id

    async def test_admin_get_execution_not_found(self, app, client, admin_token):
        resp = await client.get(
            "/api/admin/executions/exec_nonexistent",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    async def test_admin_endpoints_require_auth(self, client):
        resp = await client.get("/api/admin/executions")
        assert resp.status_code == 401

        resp = await client.get("/api/admin/executions/exec_123")
        assert resp.status_code == 401


# ============================================================
# poll_url
# ============================================================


class TestPollUrl:
    """Tests for poll_url behavior."""

    async def test_poll_url_is_valid_full_url(self, app, client, admin_token):
        app.state.worker_manager = _mock_worker_manager()
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "x = 1"
        script_hash = _compute_hmac(secret, script)

        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        poll_url = resp.json()["poll_url"]
        assert poll_url.startswith("http")
        assert "/executions/" in poll_url

    async def test_poll_url_returns_execution_status(self, app, client, admin_token):
        app.state.worker_manager = _mock_worker_manager()
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "x = 1"
        script_hash = _compute_hmac(secret, script)

        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        poll_url = resp.json()["poll_url"]
        exec_id = resp.json()["execution_id"]

        # Extract relative path from poll_url
        from urllib.parse import urlparse
        path = urlparse(poll_url).path
        poll_resp = await client.get(path)
        assert poll_resp.status_code == 200
        assert poll_resp.json()["execution_id"] == exec_id

    async def test_poll_url_matches_execution_pattern(self, app, client, admin_token):
        app.state.worker_manager = _mock_worker_manager()
        _, key_id, secret = await _create_and_lock_profile(client, admin_token)
        script = "x = 1"
        script_hash = _compute_hmac(secret, script)

        resp = await client.post(
            "/execute",
            json={"script": script, "hash": script_hash},
            headers={"Authorization": f"Bearer {key_id}"},
        )
        data = resp.json()
        assert data["poll_url"].endswith(f"/executions/{data['execution_id']}")


# ============================================================
# Misc
# ============================================================


async def test_poll_missing_execution(client):
    """GET /executions/{nonexistent} returns 404."""
    resp = await client.get("/executions/exec_nonexistent")
    assert resp.status_code == 404


async def test_respond_missing_execution(client):
    """POST /executions/{nonexistent}/respond returns 404."""
    resp = await client.post(
        "/executions/exec_nonexistent/respond",
        json={"response": "hello"},
    )
    assert resp.status_code == 404
