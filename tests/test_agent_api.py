"""Tests for the agent-facing API endpoints."""


async def test_execute_valid_profile(client):
    response = await client.post(
        "/execute",
        json={"profile_id": "ark_test123", "script": "print('hello')"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["execution_id"].startswith("exec_")
    assert "poll_url" in data


async def test_execute_invalid_profile(client):
    response = await client.post(
        "/execute",
        json={"profile_id": "bad_prefix", "script": "print('hello')"},
    )
    assert response.status_code == 401


async def test_execute_missing_profile(client):
    response = await client.post(
        "/execute",
        json={"script": "print('hello')"},
    )
    assert response.status_code == 422


async def test_poll_execution(client):
    # Create an execution
    create_resp = await client.post(
        "/execute",
        json={"profile_id": "ark_test123", "script": "print('hello')"},
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


async def test_respond_to_completed_execution(client):
    # Create an execution (mock immediately completes)
    create_resp = await client.post(
        "/execute",
        json={"profile_id": "ark_test123", "script": "print('hello')"},
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
