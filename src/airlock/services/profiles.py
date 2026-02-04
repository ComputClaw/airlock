"""Profile management: CRUD, locking, key generation, credential binding."""

import hashlib
import hmac as hmac_mod
import secrets
import string
import uuid
from typing import TypedDict

import aiosqlite

from airlock.crypto import decrypt_value, encrypt_value

KEY_ID_PREFIX = "ark_"
KEY_ID_CHARS = string.ascii_lowercase + string.digits
KEY_ID_LENGTH = 24
SECRET_CHARS = string.ascii_letters + string.digits
SECRET_LENGTH = 48


class CredentialRef(TypedDict):
    """Credential reference within a profile."""

    name: str
    description: str
    value_exists: bool


class ProfileInfo(TypedDict):
    """Profile metadata returned by list/get operations."""

    id: str
    description: str
    locked: bool
    key_id: str | None
    credentials: list[CredentialRef]
    expires_at: str | None
    revoked: bool
    created_at: str
    updated_at: str | None


class LockResult(TypedDict):
    """Returned when a profile is locked or key is regenerated."""

    profile: ProfileInfo
    key: str


def _generate_key_id() -> str:
    """Generate a new ark_ key ID."""
    random_part = "".join(secrets.choice(KEY_ID_CHARS) for _ in range(KEY_ID_LENGTH))
    return f"{KEY_ID_PREFIX}{random_part}"


def _generate_secret() -> str:
    """Generate a new secret string."""
    return "".join(secrets.choice(SECRET_CHARS) for _ in range(SECRET_LENGTH))


def verify_script_hmac(secret: str, script: str, provided_hash: str) -> bool:
    """Verify HMAC-SHA256(secret, script) matches the provided hash."""
    expected = hmac_mod.new(
        secret.encode("utf-8"),
        script.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac_mod.compare_digest(expected, provided_hash)


async def _get_profile_credentials(
    db: aiosqlite.Connection, profile_id: str
) -> list[CredentialRef]:
    """Fetch credential references for a profile."""
    cursor = await db.execute(
        "SELECT c.name, c.description, c.encrypted_value "
        "FROM credentials c "
        "JOIN profile_credentials pc ON c.id = pc.credential_id "
        "WHERE pc.profile_id = ? ORDER BY c.name",
        (profile_id,),
    )
    rows = await cursor.fetchall()
    return [
        CredentialRef(
            name=row["name"],
            description=row["description"],
            value_exists=row["encrypted_value"] is not None,
        )
        for row in rows
    ]


async def _row_to_profile_info(
    db: aiosqlite.Connection, row: aiosqlite.Row
) -> ProfileInfo:
    """Convert a DB row to ProfileInfo with credentials."""
    credentials = await _get_profile_credentials(db, row["id"])
    return ProfileInfo(
        id=row["id"],
        description=row["description"],
        locked=bool(row["locked"]),
        key_id=row["key_id"],
        credentials=credentials,
        expires_at=row["expires_at"],
        revoked=bool(row["revoked"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def list_profiles(db: aiosqlite.Connection) -> list[ProfileInfo]:
    """List all profiles with metadata and credential references."""
    cursor = await db.execute(
        "SELECT id, description, locked, key_id, expires_at, revoked, "
        "created_at, updated_at FROM profiles ORDER BY created_at"
    )
    rows = await cursor.fetchall()
    return [await _row_to_profile_info(db, row) for row in rows]


async def get_profile(db: aiosqlite.Connection, profile_id: str) -> ProfileInfo | None:
    """Get a single profile by internal ID."""
    cursor = await db.execute(
        "SELECT id, description, locked, key_id, expires_at, revoked, "
        "created_at, updated_at FROM profiles WHERE id = ?",
        (profile_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return await _row_to_profile_info(db, row)


async def create_profile(db: aiosqlite.Connection, description: str) -> ProfileInfo:
    """Create a new unlocked profile.

    Generates a UUID as the internal id. Starts unlocked with no key.
    """
    profile_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO profiles (id, description) VALUES (?, ?)",
        (profile_id, description),
    )
    await db.commit()
    return (await get_profile(db, profile_id))  # type: ignore[return-value]


async def update_profile(
    db: aiosqlite.Connection,
    profile_id: str,
    description: str | None = None,
    expires_at: str | None = ...,  # type: ignore[assignment]
) -> ProfileInfo:
    """Update profile description and/or expiration.

    Only works on non-revoked profiles.
    Raises ValueError if profile doesn't exist or is revoked.
    """
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise ValueError(f"Profile '{profile_id}' not found")
    if profile["revoked"]:
        raise ValueError(f"Profile '{profile_id}' is revoked")

    updates: list[str] = []
    params: list[str | None] = []

    if description is not None:
        updates.append("description = ?")
        params.append(description)

    if expires_at is not ...:
        updates.append("expires_at = ?")
        params.append(expires_at)

    if not updates:
        return profile

    updates.append("updated_at = datetime('now')")
    params.append(profile_id)

    await db.execute(
        f"UPDATE profiles SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    await db.commit()
    return (await get_profile(db, profile_id))  # type: ignore[return-value]


async def delete_profile(db: aiosqlite.Connection, profile_id: str) -> None:
    """Delete a profile and its credential references.

    Cannot delete locked (non-revoked) profiles. Revoke first, then delete.
    Raises ValueError if profile doesn't exist.
    Raises ValueError if profile is locked and not revoked.
    """
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise ValueError(f"Profile '{profile_id}' not found")
    if profile["locked"] and not profile["revoked"]:
        raise ValueError(
            f"Cannot delete locked profile '{profile_id}' — revoke it first"
        )

    await db.execute(
        "DELETE FROM profile_credentials WHERE profile_id = ?", (profile_id,)
    )
    await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    await db.commit()


async def lock_profile(
    db: aiosqlite.Connection, profile_id: str, master_key: bytes
) -> LockResult:
    """Lock a profile, generating the two-part key.

    Profile must be unlocked and not revoked. Returns LockResult with
    the full key string (shown once).
    """
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise ValueError(f"Profile '{profile_id}' not found")
    if profile["locked"]:
        raise ValueError(f"Profile '{profile_id}' is already locked")
    if profile["revoked"]:
        raise ValueError(f"Profile '{profile_id}' is revoked")

    key_id = _generate_key_id()
    secret = _generate_secret()
    encrypted_secret = encrypt_value(secret, master_key)

    await db.execute(
        "UPDATE profiles SET locked = 1, key_id = ?, key_secret_encrypted = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (key_id, encrypted_secret, profile_id),
    )
    await db.commit()

    updated_profile = await get_profile(db, profile_id)
    full_key = f"{key_id}:{secret}"
    return LockResult(profile=updated_profile, key=full_key)  # type: ignore[arg-type]


async def revoke_profile(db: aiosqlite.Connection, profile_id: str) -> ProfileInfo:
    """Revoke a profile. Instant, irreversible.

    Raises ValueError if already revoked or not found.
    """
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise ValueError(f"Profile '{profile_id}' not found")
    if profile["revoked"]:
        raise ValueError(f"Profile '{profile_id}' is already revoked")

    await db.execute(
        "UPDATE profiles SET revoked = 1, updated_at = datetime('now') WHERE id = ?",
        (profile_id,),
    )
    await db.commit()
    return (await get_profile(db, profile_id))  # type: ignore[return-value]


async def regenerate_key(
    db: aiosqlite.Connection, profile_id: str, master_key: bytes
) -> LockResult:
    """Regenerate the key pair for a locked profile.

    Profile must be locked and not revoked. Old key stops working immediately.
    """
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise ValueError(f"Profile '{profile_id}' not found")
    if not profile["locked"]:
        raise ValueError(f"Profile '{profile_id}' is not locked")
    if profile["revoked"]:
        raise ValueError(f"Profile '{profile_id}' is revoked")

    key_id = _generate_key_id()
    secret = _generate_secret()
    encrypted_secret = encrypt_value(secret, master_key)

    await db.execute(
        "UPDATE profiles SET key_id = ?, key_secret_encrypted = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (key_id, encrypted_secret, profile_id),
    )
    await db.commit()

    updated_profile = await get_profile(db, profile_id)
    full_key = f"{key_id}:{secret}"
    return LockResult(profile=updated_profile, key=full_key)  # type: ignore[arg-type]


async def add_credentials(
    db: aiosqlite.Connection, profile_id: str, credential_names: list[str]
) -> ProfileInfo:
    """Add credential references to an unlocked profile.

    Resolves credential names to IDs. Skips already-attached credentials.
    Raises ValueError if profile is locked, revoked, or not found.
    Raises ValueError if any credential name doesn't exist.
    """
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise ValueError(f"Profile '{profile_id}' not found")
    if profile["locked"]:
        raise ValueError("Cannot modify credentials on a locked profile")
    if profile["revoked"]:
        raise ValueError(f"Profile '{profile_id}' is revoked")

    for name in credential_names:
        cursor = await db.execute(
            "SELECT id FROM credentials WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"Credential '{name}' not found")
        credential_id = row["id"]

        await db.execute(
            "INSERT OR IGNORE INTO profile_credentials (profile_id, credential_id) "
            "VALUES (?, ?)",
            (profile_id, credential_id),
        )

    await db.commit()
    return (await get_profile(db, profile_id))  # type: ignore[return-value]


async def remove_credentials(
    db: aiosqlite.Connection, profile_id: str, credential_names: list[str]
) -> ProfileInfo:
    """Remove credential references from an unlocked profile.

    Silently ignores names not currently attached.
    Raises ValueError if profile is locked, revoked, or not found.
    """
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise ValueError(f"Profile '{profile_id}' not found")
    if profile["locked"]:
        raise ValueError("Cannot modify credentials on a locked profile")
    if profile["revoked"]:
        raise ValueError(f"Profile '{profile_id}' is revoked")

    for name in credential_names:
        cursor = await db.execute(
            "SELECT id FROM credentials WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        if row is None:
            continue
        credential_id = row["id"]

        await db.execute(
            "DELETE FROM profile_credentials WHERE profile_id = ? AND credential_id = ?",
            (profile_id, credential_id),
        )

    await db.commit()
    return (await get_profile(db, profile_id))  # type: ignore[return-value]


async def resolve_profile_by_key(
    db: aiosqlite.Connection, key_id: str
) -> dict | None:
    """Look up a profile row by its ark_ key_id.

    Returns the full profile row (dict) or None if not found.
    """
    cursor = await db.execute(
        "SELECT id, description, locked, key_id, key_secret_encrypted, "
        "expires_at, revoked, created_at, updated_at, last_used_at "
        "FROM profiles WHERE key_id = ?",
        (key_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)
