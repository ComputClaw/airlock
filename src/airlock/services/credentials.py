"""Credential management: CRUD operations with encryption."""

import re
import uuid
from typing import TypedDict

import aiosqlite

from airlock.crypto import decrypt_value, encrypt_value

_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NAME_MAX_LENGTH = 128


class CredentialInfo(TypedDict):
    """Credential metadata returned by list/get operations."""

    name: str
    description: str
    value_exists: bool
    created_at: str
    updated_at: str | None


def validate_credential_name(name: str) -> None:
    """Validate a credential name against naming rules.

    Raises ValueError if the name is invalid.
    """
    if not name:
        raise ValueError("Credential name cannot be empty")
    if len(name) > _NAME_MAX_LENGTH:
        raise ValueError(f"Credential name exceeds {_NAME_MAX_LENGTH} characters")
    if not _NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid credential name '{name}': must match [A-Za-z_][A-Za-z0-9_]*"
        )


async def list_credentials(db: aiosqlite.Connection) -> list[CredentialInfo]:
    """List all credentials with metadata. Never returns values."""
    cursor = await db.execute(
        "SELECT name, description, encrypted_value, created_at, updated_at "
        "FROM credentials ORDER BY name"
    )
    rows = await cursor.fetchall()
    return [
        CredentialInfo(
            name=row["name"],
            description=row["description"],
            value_exists=row["encrypted_value"] is not None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


async def get_credential(db: aiosqlite.Connection, name: str) -> CredentialInfo | None:
    """Get a single credential's metadata by name."""
    cursor = await db.execute(
        "SELECT name, description, encrypted_value, created_at, updated_at "
        "FROM credentials WHERE name = ?",
        (name,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return CredentialInfo(
        name=row["name"],
        description=row["description"],
        value_exists=row["encrypted_value"] is not None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# Sentinel for "not provided" (distinct from None which means "clear the value")
_UNSET = object()


async def create_credential(
    db: aiosqlite.Connection,
    name: str,
    description: str,
    value: str | None,
    master_key: bytes,
) -> CredentialInfo:
    """Create a credential. Value is optional (agent-created slots have no value).

    Raises ValueError if name already exists or is invalid.
    """
    validate_credential_name(name)

    existing = await get_credential(db, name)
    if existing is not None:
        raise ValueError(f"Credential '{name}' already exists")

    credential_id = f"cred_{uuid.uuid4().hex}"
    encrypted = encrypt_value(value, master_key) if value is not None else None

    await db.execute(
        "INSERT INTO credentials (id, name, encrypted_value, description) "
        "VALUES (?, ?, ?, ?)",
        (credential_id, name, encrypted, description),
    )
    await db.commit()

    return (await get_credential(db, name))  # type: ignore[return-value]


async def update_credential(
    db: aiosqlite.Connection,
    name: str,
    value: str | None | object = _UNSET,
    description: str | None = _UNSET,  # type: ignore[assignment]
    master_key: bytes | None = None,
) -> CredentialInfo:
    """Update a credential's value and/or description.

    - Only fields provided are updated
    - value=None explicitly clears the value (sets encrypted_value to NULL)
    - Raises ValueError if credential doesn't exist
    """
    existing = await get_credential(db, name)
    if existing is None:
        raise ValueError(f"Credential '{name}' not found")

    updates: list[str] = []
    params: list[str | bytes | None] = []

    if value is not _UNSET:
        if value is None:
            updates.append("encrypted_value = ?")
            params.append(None)
        else:
            if master_key is None:
                raise ValueError("master_key required to encrypt value")
            updates.append("encrypted_value = ?")
            params.append(encrypt_value(value, master_key))  # type: ignore[arg-type]

    if description is not _UNSET:
        updates.append("description = ?")
        params.append(description)

    if not updates:
        return existing

    updates.append("updated_at = datetime('now')")
    params.append(name)

    await db.execute(
        f"UPDATE credentials SET {', '.join(updates)} WHERE name = ?",
        params,
    )
    await db.commit()

    return (await get_credential(db, name))  # type: ignore[return-value]


async def delete_credential(db: aiosqlite.Connection, name: str) -> None:
    """Delete a credential by name.

    Raises ValueError if credential doesn't exist.
    Raises ValueError if credential is referenced by any locked profile.
    Unlocked profile references are removed automatically.
    """
    cursor = await db.execute("SELECT id FROM credentials WHERE name = ?", (name,))
    row = await cursor.fetchone()
    if row is None:
        raise ValueError(f"Credential '{name}' not found")
    credential_id = row["id"]

    # Check for locked profile references
    cursor = await db.execute(
        "SELECT p.id FROM profiles p "
        "JOIN profile_credentials pc ON p.id = pc.profile_id "
        "WHERE pc.credential_id = ? AND p.locked = 1",
        (credential_id,),
    )
    locked_profiles = [r["id"] for r in await cursor.fetchall()]
    if locked_profiles:
        profile_list = ", ".join(locked_profiles)
        raise ValueError(
            f"Cannot delete credential '{name}': referenced by locked profile(s): {profile_list}"
        )

    # Remove references from unlocked profiles
    await db.execute(
        "DELETE FROM profile_credentials "
        "WHERE credential_id = ? AND profile_id IN "
        "(SELECT id FROM profiles WHERE locked = 0)",
        (credential_id,),
    )

    # Delete the credential
    await db.execute("DELETE FROM credentials WHERE id = ?", (credential_id,))
    await db.commit()


async def decrypt_credential_value(
    db: aiosqlite.Connection, name: str, master_key: bytes
) -> str | None:
    """Decrypt and return a credential's value. Used internally for execution.

    Never exposed via API. Returns None if no value set.
    """
    cursor = await db.execute(
        "SELECT encrypted_value FROM credentials WHERE name = ?", (name,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    if row["encrypted_value"] is None:
        return None
    return decrypt_value(row["encrypted_value"], master_key)


async def resolve_profile_credentials(
    db: aiosqlite.Connection, profile_id: str, master_key: bytes
) -> dict[str, str]:
    """Resolve all credentials for a profile into a {name: value} dict.

    Used by the execution engine to inject settings.
    Only returns credentials that have values set.
    Raises ValueError if profile doesn't exist or isn't locked.
    """
    cursor = await db.execute(
        "SELECT id, locked FROM profiles WHERE id = ?", (profile_id,)
    )
    profile = await cursor.fetchone()
    if profile is None:
        raise ValueError(f"Profile '{profile_id}' not found")
    if not profile["locked"]:
        raise ValueError(f"Profile '{profile_id}' is not locked")

    cursor = await db.execute(
        "SELECT c.name, c.encrypted_value "
        "FROM credentials c "
        "JOIN profile_credentials pc ON c.id = pc.credential_id "
        "WHERE pc.profile_id = ?",
        (profile_id,),
    )
    rows = await cursor.fetchall()

    result: dict[str, str] = {}
    for row in rows:
        if row["encrypted_value"] is not None:
            result[row["name"]] = decrypt_value(row["encrypted_value"], master_key)
    return result
