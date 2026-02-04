"""Tests for the agent-facing API endpoints."""

import hashlib
import hmac as hmac_mod


def _compute_hmac(secret: str, script: str) -> str:
    """Compute HMAC-SHA256 hex digest for a script."""
    return hmac_mod.new(
        secret.encode("utf-8"),
        script.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def _create_and_lock_profile(client, admin_token):
    """Helper: create a profile, lock it, return (key_id, secret)."""
    # Create profile via admin API
    resp = await client.post(
        "/api/admin/profiles",
        json={"description": "test profile"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    profile_id = resp.json()["id"]

    # Lock it
    resp = await client.post(
        f"/api/admin/profiles/{profile_id}/lock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    full_key = data["key"]
    key_id, secret = full_key.split(":", 1)
    return key_id, secret


async def test_execute_valid_profile(client, admin_token):
    key_id, secret = await _create_and_lock_profile(client, admin_token)
    script = "print('hello')"
    script_hash = _compute_hmac(secret, script)

    response = await client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["execution_id"].startswith("exec_")
    assert "poll_url" in data


async def test_execute_invalid_profile(client):
    response = await client.post(
        "/execute",
        json={"script": "print('hello')", "hash": "abc123"},
        headers={"Authorization": "Bearer bad_prefix"},
    )
    assert response.status_code == 401


async def test_execute_missing_auth(client):
    response = await client.post(
        "/execute",
        json={"script": "print('hello')", "hash": "abc123"},
    )
    assert response.status_code == 401


async def test_poll_execution(client, admin_token):
    key_id, secret = await _create_and_lock_profile(client, admin_token)
    script = "print('hello')"
    script_hash = _compute_hmac(secret, script)

    # Create an execution
    create_resp = await client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    execution_id = create_resp.json()["execution_id"]

    # Poll it
    poll_resp = await client.get(f"/executions/{execution_id}")
    assert poll_resp.status_code == 200
    data = poll_resp.json()
    assert data["status"] == "completed"
    assert data["result"] == {"echo": "print('hello')"}


async def test_poll_missing_execution(client):
    response = await client.get("/executions/exec_nonexistent")
    assert response.status_code == 404


async def test_respond_to_completed_execution(client, admin_token):
    key_id, secret = await _create_and_lock_profile(client, admin_token)
    script = "print('hello')"
    script_hash = _compute_hmac(secret, script)

    # Create an execution (mock immediately completes)
    create_resp = await client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    execution_id = create_resp.json()["execution_id"]

    # Try to respond — should fail because status is 'completed', not 'awaiting_llm'
    respond_resp = await client.post(
        f"/executions/{execution_id}/respond",
        json={"response": "some llm text"},
    )
    assert respond_resp.status_code == 409


async def test_respond_to_missing_execution(client):
    response = await client.post(
        "/executions/exec_nonexistent/respond",
        json={"response": "some text"},
    )
    assert response.status_code == 404


async def test_skill_md(client):
    response = await client.get("/skill.md")
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "Airlock" in response.text
