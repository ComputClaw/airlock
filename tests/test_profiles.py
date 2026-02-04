"""Tests for the profile system: CRUD, lock, revoke, regenerate, auth, HMAC."""

import hashlib
import hmac as hmac_mod
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from airlock.services.profiles import verify_script_hmac


def _mock_worker_manager():
    """Create a mock WorkerManager that returns completed status."""
    mock = MagicMock()
    mock.is_running.return_value = True
    mock.execute = AsyncMock(return_value={
        "status": "completed",
        "result": None,
        "stdout": "",
        "stderr": "",
    })
    return mock


def _compute_hmac(secret: str, script: str) -> str:
    """Compute HMAC-SHA256 hex digest for a script."""
    return hmac_mod.new(
        secret.encode("utf-8"),
        script.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def _create_credential(client, admin_token, name, value=None, description=""):
    """Helper: create a credential via admin API."""
    body = {"name": name, "description": description}
    if value is not None:
        body["value"] = value
    resp = await client.post(
        "/api/admin/credentials",
        json=body,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_profile(client, description="test profile"):
    """Helper: create a profile via agent API."""
    resp = await client.post("/profiles", json={"description": description})
    assert resp.status_code == 201
    return resp.json()


async def _lock_profile(client, admin_token, profile_id):
    """Helper: lock a profile, return full response."""
    resp = await client.post(
        f"/api/admin/profiles/{profile_id}/lock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    return resp.json()


async def _create_and_lock_profile(client, admin_token, description="test"):
    """Helper: create + lock, return (profile_id, key_id, secret)."""
    profile = await _create_profile(client, description)
    lock_data = await _lock_profile(client, admin_token, profile["id"])
    key_id, secret = lock_data["key"].split(":", 1)
    return profile["id"], key_id, secret


# ============================================================
# Profile CRUD — Agent API
# ============================================================


async def test_create_profile(client):
    resp = await client.post("/profiles", json={"description": "My profile"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["locked"] is False
    assert data["key_id"] is None
    assert data["description"] == "My profile"
    assert data["revoked"] is False
    assert data["credentials"] == []
    # id should be a UUID (contains hyphens)
    assert "-" in data["id"]


async def test_create_profile_empty_description(client):
    resp = await client.post("/profiles", json={})
    assert resp.status_code == 201
    assert resp.json()["description"] == ""


async def test_list_profiles(client):
    await _create_profile(client, "Profile A")
    await _create_profile(client, "Profile B")

    resp = await client.get("/profiles")
    assert resp.status_code == 200
    profiles = resp.json()["profiles"]
    assert len(profiles) == 2


async def test_list_profiles_empty(client):
    resp = await client.get("/profiles")
    assert resp.status_code == 200
    assert resp.json() == {"profiles": []}


async def test_get_profile(client):
    created = await _create_profile(client, "Test")
    resp = await client.get(f"/profiles/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_get_profile_not_found(client):
    resp = await client.get("/profiles/nonexistent")
    assert resp.status_code == 404


async def test_add_credentials_to_profile(client, admin_token):
    await _create_credential(client, admin_token, "API_KEY", description="Key")
    profile = await _create_profile(client)

    resp = await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["API_KEY"]},
    )
    assert resp.status_code == 200
    creds = resp.json()["credentials"]
    assert len(creds) == 1
    assert creds[0]["name"] == "API_KEY"


async def test_add_credentials_duplicate_idempotent(client, admin_token):
    await _create_credential(client, admin_token, "API_KEY")
    profile = await _create_profile(client)

    # Add once
    await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["API_KEY"]},
    )
    # Add again — should be idempotent
    resp = await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["API_KEY"]},
    )
    assert resp.status_code == 200
    assert len(resp.json()["credentials"]) == 1


async def test_add_credentials_nonexistent_credential(client):
    profile = await _create_profile(client)
    resp = await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["DOES_NOT_EXIST"]},
    )
    assert resp.status_code == 404


async def test_add_credentials_locked_profile(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["SOMETHING"]},
    )
    assert resp.status_code == 409


async def test_add_credentials_revoked_profile(client, admin_token):
    profile = await _create_profile(client)
    await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["SOMETHING"]},
    )
    assert resp.status_code == 409


async def test_remove_credentials(client, admin_token):
    await _create_credential(client, admin_token, "API_KEY")
    await _create_credential(client, admin_token, "DB_HOST")
    profile = await _create_profile(client)

    await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["API_KEY", "DB_HOST"]},
    )

    resp = await client.request(
        "DELETE",
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["DB_HOST"]},
    )
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()["credentials"]]
    assert "API_KEY" in names
    assert "DB_HOST" not in names


async def test_remove_credentials_not_attached(client, admin_token):
    await _create_credential(client, admin_token, "API_KEY")
    profile = await _create_profile(client)

    # Remove something not attached — should succeed silently
    resp = await client.request(
        "DELETE",
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["API_KEY"]},
    )
    assert resp.status_code == 200


async def test_remove_credentials_locked_profile(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.request(
        "DELETE",
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["SOMETHING"]},
    )
    assert resp.status_code == 409


async def test_remove_credentials_revoked_profile(client, admin_token):
    profile = await _create_profile(client)
    await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await client.request(
        "DELETE",
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["SOMETHING"]},
    )
    assert resp.status_code == 409


# ============================================================
# Profile CRUD — Admin API
# ============================================================


async def test_admin_create_profile(client, admin_token):
    resp = await client.post(
        "/api/admin/profiles",
        json={"description": "Admin created"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["description"] == "Admin created"


async def test_admin_list_profiles(client, admin_token):
    await _create_profile(client, "P1")
    resp = await client.get(
        "/api/admin/profiles",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["profiles"]) == 1


async def test_admin_get_profile(client, admin_token):
    profile = await _create_profile(client)
    resp = await client.get(
        f"/api/admin/profiles/{profile['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == profile["id"]


async def test_admin_update_profile_description(client, admin_token):
    profile = await _create_profile(client, "Original")
    resp = await client.put(
        f"/api/admin/profiles/{profile['id']}",
        json={"description": "Updated"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated"


async def test_admin_update_profile_expiration(client, admin_token):
    profile = await _create_profile(client)
    expires = "2099-12-31T23:59:59"
    resp = await client.put(
        f"/api/admin/profiles/{profile['id']}",
        json={"expires_at": expires},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["expires_at"] == expires


async def test_admin_update_revoked_profile(client, admin_token):
    profile = await _create_profile(client)
    await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp = await client.put(
        f"/api/admin/profiles/{profile['id']}",
        json={"description": "Nope"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


async def test_admin_delete_unlocked_profile(client, admin_token):
    profile = await _create_profile(client)
    resp = await client.delete(
        f"/api/admin/profiles/{profile['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204


async def test_admin_delete_locked_profile(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.delete(
        f"/api/admin/profiles/{profile['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


async def test_admin_delete_revoked_profile(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])
    await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await client.delete(
        f"/api/admin/profiles/{profile['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204


async def test_admin_endpoints_require_auth(client):
    resp = await client.get("/api/admin/profiles")
    assert resp.status_code == 401

    resp = await client.get("/api/admin/profiles/some-id")
    assert resp.status_code == 401

    resp = await client.post("/api/admin/profiles", json={"description": "x"})
    assert resp.status_code == 401


async def test_admin_add_credentials(client, admin_token):
    await _create_credential(client, admin_token, "MY_KEY")
    profile = await _create_profile(client)

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/credentials",
        json={"credentials": ["MY_KEY"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["credentials"]) == 1


async def test_admin_remove_credentials(client, admin_token):
    await _create_credential(client, admin_token, "MY_KEY")
    profile = await _create_profile(client)
    await client.post(
        f"/api/admin/profiles/{profile['id']}/credentials",
        json={"credentials": ["MY_KEY"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await client.request(
        "DELETE",
        f"/api/admin/profiles/{profile['id']}/credentials",
        json={"credentials": ["MY_KEY"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["credentials"]) == 0


# ============================================================
# Lock
# ============================================================


async def test_lock_profile(client, admin_token):
    profile = await _create_profile(client)
    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/lock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "key" in data
    assert "key_id" in data
    assert data["locked"] is True

    # Key format: ark_...:secret
    assert ":" in data["key"]
    key_id, secret = data["key"].split(":", 1)
    assert key_id == data["key_id"]
    assert key_id.startswith("ark_")
    assert len(key_id) == 28  # ark_ + 24 chars
    assert len(secret) == 48


async def test_lock_shows_locked_on_get(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.get(f"/profiles/{profile['id']}")
    assert resp.json()["locked"] is True


async def test_lock_already_locked(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/lock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


async def test_lock_revoked_profile(client, admin_token):
    profile = await _create_profile(client)
    await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/lock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


async def test_lock_nonexistent(client, admin_token):
    resp = await client.post(
        "/api/admin/profiles/nonexistent/lock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


async def test_lock_freezes_credentials(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["SOMETHING"]},
    )
    assert resp.status_code == 409


# ============================================================
# Revoke
# ============================================================


async def test_revoke_profile(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["revoked"] is True


async def test_revoke_already_revoked(client, admin_token):
    profile = await _create_profile(client)
    await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


async def test_revoke_nonexistent(client, admin_token):
    resp = await client.post(
        "/api/admin/profiles/nonexistent/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


async def test_revoke_blocks_execution(client, admin_token):
    profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)
    script = "print('hello')"
    script_hash = _compute_hmac(secret, script)

    # Revoke the profile
    await client.post(
        f"/api/admin/profiles/{profile_id}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Try to execute — should fail
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 401


# ============================================================
# Regenerate Key
# ============================================================


async def test_regenerate_key(client, admin_token):
    profile = await _create_profile(client)
    lock_data = await _lock_profile(client, admin_token, profile["id"])
    old_key_id = lock_data["key_id"]
    old_key = lock_data["key"]

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/regenerate-key",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["key_id"] != old_key_id
    assert data["key"] != old_key
    assert data["locked"] is True


async def test_regenerate_old_key_fails(client, admin_token):
    profile_id, old_key_id, old_secret = await _create_and_lock_profile(
        client, admin_token
    )
    script = "print('hello')"
    old_hash = _compute_hmac(old_secret, script)

    # Regenerate
    await client.post(
        f"/api/admin/profiles/{profile_id}/regenerate-key",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Old key should fail
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": old_hash},
        headers={"Authorization": f"Bearer {old_key_id}"},
    )
    assert resp.status_code == 401


async def test_regenerate_new_key_works(app, client, admin_token):
    app.state.worker_manager = _mock_worker_manager()
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/regenerate-key",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    new_key_id, new_secret = data["key"].split(":", 1)

    script = "print('test')"
    script_hash = _compute_hmac(new_secret, script)

    resp = await client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {new_key_id}"},
    )
    assert resp.status_code == 202


async def test_regenerate_unlocked_profile(client, admin_token):
    profile = await _create_profile(client)
    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/regenerate-key",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


async def test_regenerate_revoked_profile(client, admin_token):
    profile = await _create_profile(client)
    await _lock_profile(client, admin_token, profile["id"])
    await client.post(
        f"/api/admin/profiles/{profile['id']}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/regenerate-key",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


async def test_regenerate_nonexistent(client, admin_token):
    resp = await client.post(
        "/api/admin/profiles/nonexistent/regenerate-key",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


async def test_regenerate_preserves_state(client, admin_token):
    await _create_credential(client, admin_token, "REGEN_KEY", "val", "desc")
    profile = await _create_profile(client, "Preserved description")
    await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["REGEN_KEY"]},
    )
    await _lock_profile(client, admin_token, profile["id"])

    resp = await client.post(
        f"/api/admin/profiles/{profile['id']}/regenerate-key",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert data["description"] == "Preserved description"
    assert data["locked"] is True
    assert len(data["credentials"]) == 1
    assert data["credentials"][0]["name"] == "REGEN_KEY"


# ============================================================
# Profile Auth + Execution
# ============================================================


async def test_execute_no_auth(client):
    resp = await client.post(
        "/execute",
        json={"script": "x=1", "hash": "abc"},
    )
    assert resp.status_code == 401


async def test_execute_invalid_bearer(client):
    resp = await client.post(
        "/execute",
        json={"script": "x=1", "hash": "abc"},
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert resp.status_code == 401


async def test_execute_unlocked_profile(client, admin_token):
    profile = await _create_profile(client)
    # Can't execute against unlocked profile — it has no key_id anyway
    resp = await client.post(
        "/execute",
        json={"script": "x=1", "hash": "abc"},
        headers={"Authorization": "Bearer ark_fake00000000000000000000"},
    )
    assert resp.status_code == 401


async def test_execute_revoked_profile(client, admin_token):
    profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)
    await client.post(
        f"/api/admin/profiles/{profile_id}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    script = "x=1"
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": _compute_hmac(secret, script)},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 401


async def test_execute_expired_profile(client, admin_token):
    profile = await _create_profile(client)
    # Set expiration in the past
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await client.put(
        f"/api/admin/profiles/{profile['id']}",
        json={"expires_at": past},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    lock_data = await _lock_profile(client, admin_token, profile["id"])
    key_id, secret = lock_data["key"].split(":", 1)

    script = "x=1"
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": _compute_hmac(secret, script)},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 401


async def test_execute_correct_hmac(app, client, admin_token):
    app.state.worker_manager = _mock_worker_manager()
    profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)
    script = "result = 42"
    script_hash = _compute_hmac(secret, script)

    resp = await client.post(
        "/execute",
        json={"script": script, "hash": script_hash},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 202


async def test_execute_wrong_hmac(client, admin_token):
    profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)
    script = "result = 42"

    resp = await client.post(
        "/execute",
        json={"script": script, "hash": "0" * 64},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 403


async def test_execute_empty_hash(client, admin_token):
    profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)

    resp = await client.post(
        "/execute",
        json={"script": "x=1", "hash": ""},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 403


# ============================================================
# HMAC Verification Unit Tests
# ============================================================


def test_verify_hmac_correct():
    secret = "mysecret"
    script = "print('hello')"
    h = _compute_hmac(secret, script)
    assert verify_script_hmac(secret, script, h) is True


def test_verify_hmac_wrong_hash():
    assert verify_script_hmac("secret", "script", "wronghash") is False


def test_verify_hmac_modified_script():
    secret = "mysecret"
    original = "print('hello')"
    modified = "print('hacked')"
    h = _compute_hmac(secret, original)
    assert verify_script_hmac(secret, modified, h) is False


def test_verify_hmac_different_secret():
    script = "print('hello')"
    h = _compute_hmac("secret1", script)
    assert verify_script_hmac("secret2", script, h) is False


def test_hmac_digest_length():
    h = _compute_hmac("secret", "script")
    assert len(h) == 64


# ============================================================
# Credential Resolution
# ============================================================


async def test_credential_resolution_with_values(app, client, admin_token):
    app.state.worker_manager = _mock_worker_manager()
    await _create_credential(client, admin_token, "CRED_A", "value_a")
    await _create_credential(client, admin_token, "CRED_B", "value_b")
    profile = await _create_profile(client)

    await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["CRED_A", "CRED_B"]},
    )
    lock_data = await _lock_profile(client, admin_token, profile["id"])
    key_id, secret = lock_data["key"].split(":", 1)

    script = "x=1"
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": _compute_hmac(secret, script)},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 202


async def test_credential_resolution_missing_value(app, client, admin_token):
    app.state.worker_manager = _mock_worker_manager()
    # Create credential without value
    await _create_credential(client, admin_token, "NO_VAL")
    profile = await _create_profile(client)

    await client.post(
        f"/profiles/{profile['id']}/credentials",
        json={"credentials": ["NO_VAL"]},
    )
    lock_data = await _lock_profile(client, admin_token, profile["id"])
    key_id, secret = lock_data["key"].split(":", 1)

    # Should still execute — credential without value is just omitted
    script = "x=1"
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": _compute_hmac(secret, script)},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 202


async def test_profile_no_credentials_empty_settings(app, client, admin_token):
    app.state.worker_manager = _mock_worker_manager()
    profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)
    script = "x=1"
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": _compute_hmac(secret, script)},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 202


# ============================================================
# Expiration
# ============================================================


async def test_future_expiration_succeeds(app, client, admin_token):
    app.state.worker_manager = _mock_worker_manager()
    profile = await _create_profile(client)
    future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    await client.put(
        f"/api/admin/profiles/{profile['id']}",
        json={"expires_at": future},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    lock_data = await _lock_profile(client, admin_token, profile["id"])
    key_id, secret = lock_data["key"].split(":", 1)

    script = "x=1"
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": _compute_hmac(secret, script)},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 202


async def test_past_expiration_fails(client, admin_token):
    profile = await _create_profile(client)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    await client.put(
        f"/api/admin/profiles/{profile['id']}",
        json={"expires_at": past},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    lock_data = await _lock_profile(client, admin_token, profile["id"])
    key_id, secret = lock_data["key"].split(":", 1)

    script = "x=1"
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": _compute_hmac(secret, script)},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 401


async def test_null_expiration_always_valid(app, client, admin_token):
    app.state.worker_manager = _mock_worker_manager()
    # Default is null expiration
    profile_id, key_id, secret = await _create_and_lock_profile(client, admin_token)
    script = "x=1"
    resp = await client.post(
        "/execute",
        json={"script": script, "hash": _compute_hmac(secret, script)},
        headers={"Authorization": f"Bearer {key_id}"},
    )
    assert resp.status_code == 202
