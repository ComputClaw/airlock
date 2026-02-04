"""Admin authentication: first-visit password setup + session tokens."""

import hashlib
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from airlock.crypto import decrypt_value
from airlock.db import get_db
from airlock.services.profiles import resolve_profile_by_key

_bearer = HTTPBearer(auto_error=False)

TOKEN_PREFIX = "atk_"
TOKEN_CHARS = string.ascii_letters + string.digits
TOKEN_LENGTH = 32


def _hash(value: str) -> str:
    """SHA-256 hash a string for storage."""
    return hashlib.sha256(value.encode()).hexdigest()


def _generate_token() -> str:
    """Generate a session token with atk_ prefix."""
    random_part = "".join(secrets.choice(TOKEN_CHARS) for _ in range(TOKEN_LENGTH))
    return f"{TOKEN_PREFIX}{random_part}"


async def is_setup_complete(db: aiosqlite.Connection) -> bool:
    """Check if admin password has been set."""
    cursor = await db.execute("SELECT value FROM admin WHERE key = 'admin_password_hash'")
    row = await cursor.fetchone()
    return row is not None


async def setup_admin(db: aiosqlite.Connection, password: str) -> str:
    """Set admin password on first visit. Returns a session token.

    Raises ValueError if password already set.
    """
    if await is_setup_complete(db):
        raise ValueError("Admin password already configured")

    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    password_hash = _hash(password)
    await db.execute(
        "INSERT INTO admin (key, value) VALUES ('admin_password_hash', ?)",
        (password_hash,),
    )

    token = _generate_token()
    token_hash = _hash(token)
    await db.execute(
        "INSERT OR REPLACE INTO admin (key, value) VALUES ('session_token_hash', ?)",
        (token_hash,),
    )
    await db.commit()
    return token


async def login_admin(db: aiosqlite.Connection, password: str) -> str:
    """Validate password and return a new session token.

    Raises ValueError if password is wrong or not set up yet.
    """
    cursor = await db.execute("SELECT value FROM admin WHERE key = 'admin_password_hash'")
    row = await cursor.fetchone()
    if row is None:
        raise ValueError("Admin password not configured — run setup first")

    if row["value"] != _hash(password):
        raise ValueError("Invalid password")

    token = _generate_token()
    token_hash = _hash(token)
    await db.execute(
        "INSERT OR REPLACE INTO admin (key, value) VALUES ('session_token_hash', ?)",
        (token_hash,),
    )
    await db.commit()
    return token


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency that requires a valid session token."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    token = credentials.credentials
    token_hash = _hash(token)

    db = await get_db()
    cursor = await db.execute("SELECT value FROM admin WHERE key = 'session_token_hash'")
    row = await cursor.fetchone()

    if row is None or row["value"] != token_hash:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    return token


# --- Profile authentication ---


@dataclass
class ProfileAuth:
    """Result of successful profile authentication."""

    profile_id: str
    key_id: str
    secret: str


async def require_profile(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> ProfileAuth:
    """FastAPI dependency: authenticate via profile key_id in Bearer header.

    Validates Bearer token is present, starts with ark_, profile exists,
    is locked, not revoked, and not expired. Returns ProfileAuth with
    decrypted secret for HMAC verification.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    token = credentials.credentials
    if not token.startswith("ark_"):
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    db = await get_db()
    profile = await resolve_profile_by_key(db, token)

    if profile is None:
        raise HTTPException(status_code=401, detail="Invalid profile key")

    if not profile["locked"]:
        raise HTTPException(status_code=401, detail="Profile is not locked")

    if profile["revoked"]:
        raise HTTPException(status_code=401, detail="Profile has been revoked")

    if profile["expires_at"]:
        expires = datetime.fromisoformat(profile["expires_at"])
        if expires <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Profile has expired")

    master_key = request.app.state.master_key
    secret = decrypt_value(profile["key_secret_encrypted"], master_key)

    await db.execute(
        "UPDATE profiles SET last_used_at = datetime('now') WHERE id = ?",
        (profile["id"],),
    )
    await db.commit()

    return ProfileAuth(
        profile_id=profile["id"],
        key_id=token,
        secret=secret,
    )
