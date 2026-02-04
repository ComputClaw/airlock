"""Tests for admin setup, login, and authenticated routes."""


async def test_status_setup_required(client):
    """Fresh instance should require setup."""
    resp = await client.get("/api/admin/status")
    assert resp.status_code == 200
    assert resp.json()["setup_required"] is True


async def test_setup_creates_admin(client):
    """First setup call should succeed and return a token."""
    resp = await client.post(
        "/api/admin/setup",
        json={"password": "mypassword123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token"].startswith("atk_")


async def test_setup_only_once(client):
    """Second setup call should fail with 409."""
    await client.post("/api/admin/setup", json={"password": "mypassword123"})
    resp = await client.post("/api/admin/setup", json={"password": "anotherpassword"})
    assert resp.status_code == 409


async def test_setup_short_password(client):
    """Password under 8 chars should be rejected."""
    resp = await client.post("/api/admin/setup", json={"password": "short"})
    assert resp.status_code == 409


async def test_status_after_setup(client, admin_token):
    """After setup, status should show setup complete."""
    resp = await client.get("/api/admin/status")
    assert resp.status_code == 200
    assert resp.json()["setup_required"] is False


async def test_login_valid_password(client):
    """Login with correct password returns a token."""
    await client.post("/api/admin/setup", json={"password": "mypassword123"})
    resp = await client.post("/api/admin/login", json={"password": "mypassword123"})
    assert resp.status_code == 200
    assert resp.json()["token"].startswith("atk_")


async def test_login_wrong_password(client):
    """Login with wrong password returns 401."""
    await client.post("/api/admin/setup", json={"password": "mypassword123"})
    resp = await client.post("/api/admin/login", json={"password": "wrongpassword"})
    assert resp.status_code == 401


async def test_admin_no_token(client, admin_token):
    """Admin routes without token return 401."""
    resp = await client.get("/api/admin/credentials")
    assert resp.status_code == 401


async def test_admin_valid_token(client, admin_token):
    """Admin routes with valid token return 200."""
    resp = await client.get(
        "/api/admin/credentials",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"credentials": []}


async def test_admin_invalid_token(client, admin_token):
    """Admin routes with invalid token return 401."""
    resp = await client.get(
        "/api/admin/credentials",
        headers={"Authorization": "Bearer atk_invalid_token_here"},
    )
    assert resp.status_code == 401


async def test_admin_stats(client, admin_token):
    """Stats endpoint returns zeroed counters."""
    resp = await client.get(
        "/api/admin/stats",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_executions"] == 0
    assert data["active_profiles"] == 0
    assert data["stored_credentials"] == 0
