"""Tests for credential management: encryption, admin CRUD, agent API, service layer."""

import os

import pytest


# --- Encryption ---


class TestEncryption:
    """AES-256-GCM encryption round-trip and error handling."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt a value then decrypt it — matches original."""
        from airlock.crypto import decrypt_value, encrypt_value

        key = os.urandom(32)
        plaintext = "sk-live-abc123"
        encrypted = encrypt_value(plaintext, key)
        result = decrypt_value(encrypted, key)
        assert result == plaintext

    def test_encrypt_same_value_different_ciphertext(self):
        """Encrypting the same value twice produces different ciphertexts (random nonce)."""
        from airlock.crypto import encrypt_value

        key = os.urandom(32)
        a = encrypt_value("secret", key)
        b = encrypt_value("secret", key)
        assert a != b

    def test_decrypt_wrong_key_raises(self):
        """Decrypt with wrong key raises an error."""
        from cryptography.exceptions import InvalidTag

        from airlock.crypto import decrypt_value, encrypt_value

        key1 = os.urandom(32)
        key2 = os.urandom(32)
        encrypted = encrypt_value("secret", key1)
        with pytest.raises(InvalidTag):
            decrypt_value(encrypted, key2)

    def test_decrypt_tampered_data_raises(self):
        """Decrypt tampered data raises an error."""
        from cryptography.exceptions import InvalidTag

        from airlock.crypto import decrypt_value, encrypt_value

        key = os.urandom(32)
        encrypted = bytearray(encrypt_value("secret", key))
        encrypted[-1] ^= 0xFF  # Flip last byte
        with pytest.raises(InvalidTag):
            decrypt_value(bytes(encrypted), key)

    def test_master_key_creation(self, tmp_path):
        """Master key is created on first call and reused on second."""
        from airlock.crypto import get_or_create_master_key

        key1 = get_or_create_master_key(tmp_path)
        key2 = get_or_create_master_key(tmp_path)
        assert key1 == key2
        assert len(key1) == 32

    def test_master_key_file_permissions(self, tmp_path):
        """Master key file has 0o600 permissions."""
        from airlock.crypto import get_or_create_master_key

        get_or_create_master_key(tmp_path)
        secret_path = tmp_path / ".secret"
        mode = secret_path.stat().st_mode & 0o777
        assert mode == 0o600


# --- Helpers ---


def _auth(token: str) -> dict:
    """Build authorization header."""
    return {"Authorization": f"Bearer {token}"}


# --- Admin API: Credential CRUD ---


class TestAdminCredentialCRUD:
    """Admin credential endpoints require auth and perform full CRUD."""

    async def test_create_credential_with_value(self, client, admin_token):
        """POST /api/admin/credentials with value → 201, has_value: true."""
        resp = await client.post(
            "/api/admin/credentials",
            json={"name": "API_KEY", "value": "sk-live-123", "description": "Test key"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "API_KEY"
        assert data["description"] == "Test key"
        assert data["has_value"] is True
        assert "created_at" in data

    async def test_create_credential_without_value(self, client, admin_token):
        """POST /api/admin/credentials without value → 201, has_value: false."""
        resp = await client.post(
            "/api/admin/credentials",
            json={"name": "EMPTY_SLOT", "description": "No value yet"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 201
        assert resp.json()["has_value"] is False

    async def test_create_credential_duplicate_name(self, client, admin_token):
        """POST /api/admin/credentials with same name → 409."""
        await client.post(
            "/api/admin/credentials",
            json={"name": "DUP_KEY"},
            headers=_auth(admin_token),
        )
        resp = await client.post(
            "/api/admin/credentials",
            json={"name": "DUP_KEY"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 409

    async def test_create_credential_invalid_name_starts_with_digit(self, client, admin_token):
        """POST /api/admin/credentials with name starting with digit → 422."""
        resp = await client.post(
            "/api/admin/credentials",
            json={"name": "123bad"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422

    async def test_create_credential_invalid_name_has_spaces(self, client, admin_token):
        """POST /api/admin/credentials with spaces in name → 422."""
        resp = await client.post(
            "/api/admin/credentials",
            json={"name": "has spaces"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422

    async def test_create_credential_empty_name(self, client, admin_token):
        """POST /api/admin/credentials with empty name → 422."""
        resp = await client.post(
            "/api/admin/credentials",
            json={"name": ""},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422

    async def test_list_credentials(self, client, admin_token):
        """GET /api/admin/credentials lists all, never returns values."""
        await client.post(
            "/api/admin/credentials",
            json={"name": "KEY_A", "value": "secret_a", "description": "A"},
            headers=_auth(admin_token),
        )
        await client.post(
            "/api/admin/credentials",
            json={"name": "KEY_B", "description": "B"},
            headers=_auth(admin_token),
        )
        resp = await client.get("/api/admin/credentials", headers=_auth(admin_token))
        assert resp.status_code == 200
        creds = resp.json()["credentials"]
        assert len(creds) == 2
        names = {c["name"] for c in creds}
        assert names == {"KEY_A", "KEY_B"}
        # Values never returned
        for c in creds:
            assert "value" not in c
            assert "encrypted_value" not in c

    async def test_update_credential_value(self, client, admin_token):
        """PUT /api/admin/credentials/{name} with value → has_value: true, updated_at set."""
        await client.post(
            "/api/admin/credentials",
            json={"name": "UPD_KEY"},
            headers=_auth(admin_token),
        )
        resp = await client.put(
            "/api/admin/credentials/UPD_KEY",
            json={"value": "new-secret"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_value"] is True
        assert data["updated_at"] is not None

    async def test_update_credential_description_only(self, client, admin_token):
        """PUT with description only → description updated, value unchanged."""
        await client.post(
            "/api/admin/credentials",
            json={"name": "DESC_KEY", "value": "original"},
            headers=_auth(admin_token),
        )
        resp = await client.put(
            "/api/admin/credentials/DESC_KEY",
            json={"description": "Updated desc"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Updated desc"
        assert data["has_value"] is True  # Value unchanged

    async def test_update_nonexistent_credential(self, client, admin_token):
        """PUT /api/admin/credentials/nonexistent → 404."""
        resp = await client.put(
            "/api/admin/credentials/DOES_NOT_EXIST",
            json={"value": "whatever"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 404

    async def test_delete_credential(self, client, admin_token):
        """DELETE /api/admin/credentials/{name} → 204."""
        await client.post(
            "/api/admin/credentials",
            json={"name": "DEL_KEY", "value": "gone"},
            headers=_auth(admin_token),
        )
        resp = await client.delete(
            "/api/admin/credentials/DEL_KEY", headers=_auth(admin_token)
        )
        assert resp.status_code == 204

        # Verify it's gone
        resp = await client.get("/api/admin/credentials", headers=_auth(admin_token))
        names = [c["name"] for c in resp.json()["credentials"]]
        assert "DEL_KEY" not in names

    async def test_delete_nonexistent_credential(self, client, admin_token):
        """DELETE /api/admin/credentials/nonexistent → 404."""
        resp = await client.delete(
            "/api/admin/credentials/NOPE", headers=_auth(admin_token)
        )
        assert resp.status_code == 404

    async def test_admin_endpoints_require_token(self, client):
        """All admin credential endpoints without token → 401."""
        # Setup admin first so we don't get 'not configured' errors
        await client.post("/api/admin/setup", json={"password": "testpassword123"})

        resp = await client.get("/api/admin/credentials")
        assert resp.status_code == 401

        resp = await client.post(
            "/api/admin/credentials", json={"name": "X", "value": "Y"}
        )
        assert resp.status_code == 401

        resp = await client.put(
            "/api/admin/credentials/X", json={"value": "Y"}
        )
        assert resp.status_code == 401

        resp = await client.delete("/api/admin/credentials/X")
        assert resp.status_code == 401


# --- Agent API: Credential Discovery ---


class TestAgentCredentialAPI:
    """Agent credential endpoints are unauthenticated."""

    async def test_list_credentials_empty(self, client):
        """GET /credentials on empty DB → empty list."""
        resp = await client.get("/credentials")
        assert resp.status_code == 200
        assert resp.json() == {"credentials": []}

    async def test_list_credentials_with_data(self, client, admin_token):
        """GET /credentials lists all credentials with value_exists."""
        # Create via admin API
        await client.post(
            "/api/admin/credentials",
            json={"name": "WITH_VAL", "value": "secret", "description": "Has value"},
            headers=_auth(admin_token),
        )
        await client.post(
            "/api/admin/credentials",
            json={"name": "NO_VAL", "description": "No value"},
            headers=_auth(admin_token),
        )

        resp = await client.get("/credentials")
        assert resp.status_code == 200
        creds = resp.json()["credentials"]
        assert len(creds) == 2

        by_name = {c["name"]: c for c in creds}
        assert by_name["WITH_VAL"]["value_exists"] is True
        assert by_name["NO_VAL"]["value_exists"] is False
        # Agent API does not include timestamps
        assert "created_at" not in by_name["WITH_VAL"]

    async def test_create_credential_slots(self, client):
        """POST /credentials with two new names → both created."""
        resp = await client.post(
            "/credentials",
            json={
                "credentials": [
                    {"name": "DB_PASS", "description": "Database password"},
                    {"name": "SMTP_KEY", "description": "SendGrid key"},
                ]
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert set(data["created"]) == {"DB_PASS", "SMTP_KEY"}
        assert data["skipped"] == []

    async def test_create_credential_slots_existing_skipped(self, client):
        """POST /credentials with existing name → skipped, no error."""
        # Create first
        await client.post(
            "/credentials",
            json={"credentials": [{"name": "EXISTING"}]},
        )
        # Try again
        resp = await client.post(
            "/credentials",
            json={"credentials": [{"name": "EXISTING"}, {"name": "NEW_ONE"}]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == ["NEW_ONE"]
        assert data["skipped"] == ["EXISTING"]

    async def test_create_credential_slots_invalid_name(self, client):
        """POST /credentials with invalid name → 422."""
        resp = await client.post(
            "/credentials",
            json={"credentials": [{"name": "123bad"}]},
        )
        assert resp.status_code == 422

    async def test_create_credential_slots_ignores_value(self, client):
        """POST /credentials ignores value field if provided."""
        resp = await client.post(
            "/credentials",
            json={
                "credentials": [
                    {"name": "SNEAKY", "description": "test", "value": "should-be-ignored"}
                ]
            },
        )
        assert resp.status_code == 201
        assert resp.json()["created"] == ["SNEAKY"]

        # Verify no value was stored
        resp = await client.get("/credentials")
        creds = resp.json()["credentials"]
        sneaky = [c for c in creds if c["name"] == "SNEAKY"][0]
        assert sneaky["value_exists"] is False


# --- Credential Deletion with Profile References ---


class TestCredentialDeletionWithProfiles:
    """Deletion behavior when credentials are referenced by profiles."""

    async def test_delete_unreferenced_credential(self, client, admin_token):
        """Delete credential not referenced by any profile → succeeds."""
        await client.post(
            "/api/admin/credentials",
            json={"name": "SOLO_KEY", "value": "x"},
            headers=_auth(admin_token),
        )
        resp = await client.delete(
            "/api/admin/credentials/SOLO_KEY", headers=_auth(admin_token)
        )
        assert resp.status_code == 204

    async def test_delete_credential_referenced_by_unlocked_profile(self, client, admin_token):
        """Delete credential referenced by unlocked profile → succeeds, reference removed."""
        from airlock.db import get_db

        # Create credential
        await client.post(
            "/api/admin/credentials",
            json={"name": "UNREF_KEY", "value": "x"},
            headers=_auth(admin_token),
        )

        db = await get_db()
        # Get credential ID
        cursor = await db.execute("SELECT id FROM credentials WHERE name = 'UNREF_KEY'")
        cred_row = await cursor.fetchone()
        cred_id = cred_row["id"]

        # Create an unlocked profile directly in DB
        await db.execute(
            "INSERT INTO profiles (id, description, locked) VALUES ('ark_test1', 'test', 0)"
        )
        await db.execute(
            "INSERT INTO profile_credentials (profile_id, credential_id) VALUES ('ark_test1', ?)",
            (cred_id,),
        )
        await db.commit()

        # Delete should succeed
        resp = await client.delete(
            "/api/admin/credentials/UNREF_KEY", headers=_auth(admin_token)
        )
        assert resp.status_code == 204

        # Verify profile_credentials reference was removed
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM profile_credentials WHERE credential_id = ?",
            (cred_id,),
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    async def test_delete_credential_referenced_by_locked_profile(self, client, admin_token):
        """Delete credential referenced by locked profile → 409 with profile IDs."""
        from airlock.db import get_db

        # Create credential
        await client.post(
            "/api/admin/credentials",
            json={"name": "LOCKED_KEY", "value": "x"},
            headers=_auth(admin_token),
        )

        db = await get_db()
        cursor = await db.execute("SELECT id FROM credentials WHERE name = 'LOCKED_KEY'")
        cred_row = await cursor.fetchone()
        cred_id = cred_row["id"]

        # Create a locked profile directly in DB
        await db.execute(
            "INSERT INTO profiles (id, description, locked) VALUES ('ark_locked1', 'locked', 1)"
        )
        await db.execute(
            "INSERT INTO profile_credentials (profile_id, credential_id) VALUES ('ark_locked1', ?)",
            (cred_id,),
        )
        await db.commit()

        # Delete should fail
        resp = await client.delete(
            "/api/admin/credentials/LOCKED_KEY", headers=_auth(admin_token)
        )
        assert resp.status_code == 409
        assert "ark_locked1" in resp.json()["detail"]


# --- Service Layer ---


class TestServiceLayer:
    """Direct tests of the credential service functions."""

    async def test_resolve_profile_credentials(self, client, admin_token):
        """resolve_profile_credentials returns {name: decrypted_value} dict."""
        from airlock.db import get_db
        from airlock.services.credentials import resolve_profile_credentials

        db = await get_db()
        master_key: bytes = client._transport.app.state.master_key  # type: ignore[attr-defined]

        # Create credentials
        await client.post(
            "/api/admin/credentials",
            json={"name": "RESOLVE_A", "value": "secret_a"},
            headers=_auth(admin_token),
        )
        await client.post(
            "/api/admin/credentials",
            json={"name": "RESOLVE_B", "value": "secret_b"},
            headers=_auth(admin_token),
        )

        # Get credential IDs
        cursor = await db.execute(
            "SELECT id FROM credentials WHERE name = 'RESOLVE_A'"
        )
        cred_a_id = (await cursor.fetchone())["id"]
        cursor = await db.execute(
            "SELECT id FROM credentials WHERE name = 'RESOLVE_B'"
        )
        cred_b_id = (await cursor.fetchone())["id"]

        # Create locked profile
        await db.execute(
            "INSERT INTO profiles (id, description, locked) VALUES ('ark_resolve', 'test', 1)"
        )
        await db.execute(
            "INSERT INTO profile_credentials (profile_id, credential_id) VALUES ('ark_resolve', ?)",
            (cred_a_id,),
        )
        await db.execute(
            "INSERT INTO profile_credentials (profile_id, credential_id) VALUES ('ark_resolve', ?)",
            (cred_b_id,),
        )
        await db.commit()

        result = await resolve_profile_credentials(db, "ark_resolve", master_key)
        assert result == {"RESOLVE_A": "secret_a", "RESOLVE_B": "secret_b"}

    async def test_resolve_skips_credentials_without_value(self, client, admin_token):
        """resolve_profile_credentials skips credentials with no value set."""
        from airlock.db import get_db
        from airlock.services.credentials import resolve_profile_credentials

        db = await get_db()
        master_key: bytes = client._transport.app.state.master_key  # type: ignore[attr-defined]

        # Create one with value, one without
        await client.post(
            "/api/admin/credentials",
            json={"name": "HAS_VAL", "value": "present"},
            headers=_auth(admin_token),
        )
        await client.post(
            "/api/admin/credentials",
            json={"name": "NO_VAL_SLOT"},
            headers=_auth(admin_token),
        )

        cursor = await db.execute("SELECT id FROM credentials WHERE name = 'HAS_VAL'")
        has_val_id = (await cursor.fetchone())["id"]
        cursor = await db.execute("SELECT id FROM credentials WHERE name = 'NO_VAL_SLOT'")
        no_val_id = (await cursor.fetchone())["id"]

        await db.execute(
            "INSERT INTO profiles (id, description, locked) VALUES ('ark_skip', 'test', 1)"
        )
        await db.execute(
            "INSERT INTO profile_credentials VALUES ('ark_skip', ?)", (has_val_id,)
        )
        await db.execute(
            "INSERT INTO profile_credentials VALUES ('ark_skip', ?)", (no_val_id,)
        )
        await db.commit()

        result = await resolve_profile_credentials(db, "ark_skip", master_key)
        assert result == {"HAS_VAL": "present"}
        assert "NO_VAL_SLOT" not in result

    async def test_resolve_nonexistent_profile_raises(self, client):
        """resolve_profile_credentials on non-existent profile → raises ValueError."""
        from airlock.db import get_db
        from airlock.services.credentials import resolve_profile_credentials

        db = await get_db()
        master_key: bytes = client._transport.app.state.master_key  # type: ignore[attr-defined]

        with pytest.raises(ValueError, match="not found"):
            await resolve_profile_credentials(db, "ark_nonexistent", master_key)

    async def test_resolve_unlocked_profile_raises(self, client):
        """resolve_profile_credentials on unlocked profile → raises ValueError."""
        from airlock.db import get_db
        from airlock.services.credentials import resolve_profile_credentials

        db = await get_db()
        master_key: bytes = client._transport.app.state.master_key  # type: ignore[attr-defined]

        await db.execute(
            "INSERT INTO profiles (id, description, locked) VALUES ('ark_unlocked', 'test', 0)"
        )
        await db.commit()

        with pytest.raises(ValueError, match="not locked"):
            await resolve_profile_credentials(db, "ark_unlocked", master_key)
