# Spec 04: Profile System (Phase 3 → v0.3.0)

## Goal

Users and agents can create, configure, and manage profiles. Users lock profiles via the web UI, generating a two-part key (`ark_ID:SECRET`) for authenticated execution. Agents use the key ID in a Bearer header and prove code integrity with an HMAC-SHA256 hash of the script.

**Before:** Profile table exists but is empty. `POST /execute` takes `profile_id` in the request body. No real profile auth.
**After:** Full profile lifecycle (create → configure → lock → execute → revoke). `POST /execute` uses `Authorization: Bearer ark_...` + HMAC script hash. Profiles enforce credential scoping.

## Prerequisites

- Spec 01 (Foundation) ✅
- Spec 02 (Docker Execution) ✅
- Spec 03 (Credential Management) ✅ — profiles reference credentials

---

## Architecture

```
Agent API (unauthenticated)              Admin API (session token)
    │                                        │
    ├─ GET /profiles                         ├─ GET /api/admin/profiles
    ├─ GET /profiles/{id}                    ├─ GET /api/admin/profiles/{id}
    ├─ POST /profiles                        ├─ POST /api/admin/profiles
    │                                        ├─ PUT /api/admin/profiles/{id}
    ├─ POST /profiles/{id}/credentials       ├─ POST /api/admin/profiles/{id}/credentials
    ├─ DELETE /profiles/{id}/credentials     ├─ DELETE /api/admin/profiles/{id}/credentials
    │                                        │
    │                                        ├─ POST /api/admin/profiles/{id}/lock
    │                                        │  → returns ark_ID:SECRET (once!)
    │                                        ├─ POST /api/admin/profiles/{id}/revoke
    │                                        ├─ POST /api/admin/profiles/{id}/regenerate-key
    │                                        └─ DELETE /api/admin/profiles/{id}
    │                                        │
    └── POST /execute ◄────────────────────  │
        Authorization: Bearer ark_...        │
        Body: {script, hash, timeout}        │
                                             │
        ┌────────────────────────────────────┘
        │
        ▼
    ┌────────────────────────┐
    │  Profile Auth Flow     │
    │                        │
    │  1. Extract Bearer     │
    │     ark_... from header│
    │  2. Look up profile    │
    │     by key_id          │
    │  3. Check: locked,     │
    │     not revoked,       │
    │     not expired        │
    │  4. Decrypt secret     │
    │  5. Verify HMAC-SHA256 │
    │     (secret, script)   │
    │     == hash from body  │
    │  6. Resolve credentials│
    │     → inject into      │
    │       worker           │
    └────────────────────────┘
```

### Two-Part Key Model

```
Lock profile
    │
    ▼
Generate key_id:  ark_ + 24 alphanumeric chars
Generate secret:  48 alphanumeric chars
    │
    ▼
Store in DB:
    key_id = "ark_7f3x9kw2m4p1n5j8q..."   (plaintext, indexed)
    key_secret_encrypted = AES-256-GCM(master_key, secret)
    │
    ▼
Show to user ONCE:
    ┌─────────────────────────────────────────────────────┐
    │  ark_7f3x9kw2m4p1n5j8q...:dK9mP2qR7xN4vB6cY1fW... │
    │  [Copy to clipboard]                                 │
    │  ⚠ This won't be shown again.                       │
    └─────────────────────────────────────────────────────┘
    │
    ▼
Agent splits on ":"
    key_id  = "ark_7f3x9kw2m4p1n5j8q..."   → Authorization: Bearer ark_...
    secret  = "dK9mP2qR7xN4vB6cY1fW..."    → HMAC-SHA256(secret, script) → hash field
```

### Why Encrypted (Not Hashed) Secret Storage

The server must verify `HMAC-SHA256(secret, script) == hash`. This requires the raw secret, so we **encrypt** it (AES-256-GCM with the instance master key) rather than hash it. If we only stored a hash, the server couldn't recompute the HMAC. The master key is already used for credential encryption (Spec 03), so this adds no new key management burden.

---

## Tasks

### 1. Update Database Schema — `src/airlock/db.py`

Add two columns to the `profiles` table for the two-part key:

```sql
-- New columns (NULL when profile is unlocked, populated on lock)
ALTER TABLE profiles ADD COLUMN key_id TEXT UNIQUE;
ALTER TABLE profiles ADD COLUMN key_secret_encrypted BLOB;
```

Update the `SCHEMA` constant so fresh databases get the new columns:

```sql
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,              -- internal UUID (stable, never changes)
    description TEXT DEFAULT '',
    locked INTEGER DEFAULT 0,
    key_id TEXT UNIQUE,               -- ark_... (generated on lock, NULL when unlocked)
    key_secret_encrypted BLOB,        -- AES-256-GCM encrypted secret (NULL when unlocked)
    expires_at TEXT,
    revoked INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    last_used_at TEXT
);
```

Add a migration runner for existing databases:

```python
MIGRATIONS = [
    "ALTER TABLE profiles ADD COLUMN key_id TEXT UNIQUE",
    "ALTER TABLE profiles ADD COLUMN key_secret_encrypted BLOB",
]

async def run_migrations(db: aiosqlite.Connection) -> None:
    """Run schema migrations, ignoring 'duplicate column' errors."""
    for sql in MIGRATIONS:
        try:
            await db.execute(sql)
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
    await db.commit()
```

Call `run_migrations(db)` in `init_db()` after `executescript(SCHEMA)`.

The profile `id` is now an **internal UUID** (not `ark_`-prefixed). It's stable and never changes — foreign keys in `executions` and `profile_credentials` reference it. The `key_id` (`ark_...`) is the external-facing identifier used for execution auth.

### 2. Profile Service — `src/airlock/services/profiles.py` (new file)

Business logic for profile management. Keeps API routes thin.

```python
"""Profile management: CRUD, locking, key generation, credential binding."""

import hmac as hmac_mod
import hashlib
import secrets
import string
import uuid
from datetime import datetime, timezone

KEY_ID_PREFIX = "ark_"
KEY_ID_CHARS = string.ascii_lowercase + string.digits
KEY_ID_LENGTH = 24       # 24 chars after prefix → ark_ + 24 = 28 chars total
SECRET_CHARS = string.ascii_letters + string.digits
SECRET_LENGTH = 48       # 48 alphanumeric chars → ~285 bits of entropy

class ProfileInfo(TypedDict):
    """Profile metadata returned by list/get operations."""
    id: str                          # internal UUID
    description: str
    locked: bool
    key_id: str | None               # ark_... (None when unlocked)
    credentials: list[CredentialRef] # [{name, description, value_exists}]
    expires_at: str | None
    revoked: bool
    created_at: str
    updated_at: str | None

class CredentialRef(TypedDict):
    """Credential reference within a profile."""
    name: str
    description: str
    value_exists: bool

class LockResult(TypedDict):
    """Returned when a profile is locked or key is regenerated."""
    profile: ProfileInfo
    key: str                         # Full ark_ID:SECRET (shown once)

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


async def list_profiles(db: Connection) -> list[ProfileInfo]:
    """List all profiles with metadata and credential references."""

async def get_profile(db: Connection, profile_id: str) -> ProfileInfo | None:
    """Get a single profile by internal ID."""

async def create_profile(db: Connection, description: str) -> ProfileInfo:
    """Create a new unlocked profile.

    - Generates a UUID as the internal id
    - Starts unlocked (locked=0, key_id=NULL, key_secret_encrypted=NULL)
    - Returns ProfileInfo with empty credentials list
    """

async def update_profile(
    db: Connection, profile_id: str,
    description: str | None = ...,
    expires_at: str | None = ...,
) -> ProfileInfo:
    """Update profile description and/or expiration.

    - Only works on non-revoked profiles
    - Expiration can be set on both locked and unlocked profiles
    - Raises ValueError if profile doesn't exist or is revoked
    """

async def delete_profile(db: Connection, profile_id: str) -> None:
    """Delete a profile and its credential references.

    - Cannot delete locked profiles (409) — revoke first, then delete
    - Removes all profile_credentials rows
    - Raises ValueError if profile doesn't exist
    """

async def lock_profile(
    db: Connection, profile_id: str, master_key: bytes
) -> LockResult:
    """Lock a profile, generating the two-part key.

    - Profile must be unlocked and not revoked
    - Generates key_id (ark_...) and secret
    - Encrypts secret with master key, stores both in DB
    - Sets locked=1
    - Returns LockResult with the full key string (shown once)
    - Raises ValueError if already locked, revoked, or not found
    """

async def revoke_profile(db: Connection, profile_id: str) -> ProfileInfo:
    """Revoke a profile. Instant, irreversible.

    - Sets revoked=1
    - Profile can be in any state (locked or unlocked)
    - Raises ValueError if already revoked or not found
    """

async def regenerate_key(
    db: Connection, profile_id: str, master_key: bytes
) -> LockResult:
    """Regenerate the key pair for a locked profile.

    - Profile must be locked and not revoked
    - Generates new key_id and new secret
    - Old key stops working immediately
    - All other profile state preserved (credentials, history, etc.)
    - Returns LockResult with the new full key string
    - Raises ValueError if not locked, revoked, or not found
    """

async def add_credentials(
    db: Connection, profile_id: str, credential_names: list[str]
) -> ProfileInfo:
    """Add credential references to an unlocked profile.

    - Profile must be unlocked and not revoked
    - Resolves credential names → IDs via the credentials table
    - Skips credentials already attached (idempotent)
    - Raises ValueError if profile is locked, revoked, or not found
    - Raises ValueError if any credential name doesn't exist
    """

async def remove_credentials(
    db: Connection, profile_id: str, credential_names: list[str]
) -> ProfileInfo:
    """Remove credential references from an unlocked profile.

    - Profile must be unlocked and not revoked
    - Silently ignores names not currently attached
    - Raises ValueError if profile is locked, revoked, or not found
    """

async def resolve_profile_by_key(
    db: Connection, key_id: str
) -> dict | None:
    """Look up a profile row by its ark_ key_id.

    Returns the full profile row (dict) or None if not found.
    Used by the auth dependency.
    """
```

### 3. Profile Auth — Update `src/airlock/auth.py`

Add profile-based authentication for the execute endpoint:

```python
"""Profile authentication for agent execution requests."""

from dataclasses import dataclass

@dataclass
class ProfileAuth:
    """Result of successful profile authentication."""
    profile_id: str       # internal UUID
    key_id: str           # ark_...
    secret: str           # decrypted secret (for HMAC verification in endpoint)

async def require_profile(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> ProfileAuth:
    """FastAPI dependency: authenticate via profile key_id in Bearer header.

    Validates:
    - Bearer token is present
    - Token starts with 'ark_'
    - Profile exists with matching key_id
    - Profile is locked (locked=1)
    - Profile is not revoked (revoked=0)
    - Profile is not expired (expires_at is NULL or in the future)

    Returns ProfileAuth with decrypted secret for HMAC verification.
    Raises HTTPException(401) on any failure.
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

    # Decrypt the secret for HMAC verification
    master_key = request.app.state.master_key
    secret = decrypt_value(profile["key_secret_encrypted"], master_key)

    # Update last_used_at
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
```

### 4. Pydantic Models — Update `src/airlock/models.py`

Add profile request/response models and update `ExecutionRequest`:

```python
# --- Profile Requests ---

class CreateProfileRequest(BaseModel):
    """Create a new profile (used by both admin and agent API)."""
    description: str = ""

class UpdateProfileRequest(BaseModel):
    """Update profile description and/or expiration (admin only)."""
    description: str | None = None
    expires_at: str | None = None   # ISO datetime string, or null to clear

class ProfileCredentialsRequest(BaseModel):
    """Add or remove credential references from a profile."""
    credentials: list[str]          # Credential names

# --- Profile Responses ---

class CredentialRefResponse(BaseModel):
    """Credential reference within a profile."""
    name: str
    description: str
    value_exists: bool

class ProfileResponse(BaseModel):
    """Profile metadata (returned by most endpoints)."""
    id: str
    description: str
    locked: bool
    key_id: str | None = None       # ark_... (None when unlocked)
    credentials: list[CredentialRefResponse] = []
    expires_at: str | None = None
    revoked: bool = False
    created_at: str
    updated_at: str | None = None

class ProfileLockedResponse(BaseModel):
    """Returned by lock and regenerate-key (includes full key, shown once)."""
    id: str
    description: str
    locked: bool = True
    key_id: str                      # ark_...
    key: str                         # ark_ID:SECRET — SHOWN ONCE
    credentials: list[CredentialRefResponse] = []
    expires_at: str | None = None
    revoked: bool = False
    created_at: str
    updated_at: str | None = None

# --- Updated Execution Request ---

class ExecutionRequest(BaseModel):
    """Request to execute a Python script.

    Profile authentication is via Authorization: Bearer ark_... header.
    The hash field proves code integrity via HMAC-SHA256(secret, script).
    """
    script: str                      # Python code to execute
    hash: str                        # HMAC-SHA256(secret, script) hex digest
    timeout: int = 60                # Max execution time (seconds)
```

**Breaking change**: `ExecutionRequest` no longer has `profile_id`. The profile is identified by the Bearer header, and code integrity is verified by the `hash` field.

### 5. Admin API — Update `src/airlock/api/admin.py`

Replace the stub `list_profiles` endpoint with full profile management:

#### `GET /api/admin/profiles` → 200

List all profiles.

```json
{
  "profiles": [
    {
      "id": "a1b2c3d4-...",
      "description": "Oracle reporting — read only",
      "locked": true,
      "key_id": "ark_7f3x9kw2m4p1n5j8q6r2t0",
      "credentials": [
        {"name": "SIMPHONY_API_KEY", "description": "Simphony REST API key", "value_exists": true}
      ],
      "expires_at": "2026-12-31T23:59:59",
      "revoked": false,
      "created_at": "2026-02-01T22:00:00",
      "updated_at": null
    }
  ]
}
```

#### `GET /api/admin/profiles/{id}` → 200

Get a single profile by internal ID.

- 404 if not found

#### `POST /api/admin/profiles` → 201

Create a new profile.

```json
Request:
{
  "description": "Oracle reporting — read only"
}

Response:
{
  "id": "a1b2c3d4-...",
  "description": "Oracle reporting — read only",
  "locked": false,
  "key_id": null,
  "credentials": [],
  "revoked": false,
  "created_at": "2026-02-01T22:00:00"
}
```

#### `PUT /api/admin/profiles/{id}` → 200

Update a profile's description and/or expiration date.

```json
Request:
{
  "description": "Updated description",
  "expires_at": "2026-12-31T23:59:59"
}

Response:
{
  "id": "a1b2c3d4-...",
  "description": "Updated description",
  "locked": false,
  "expires_at": "2026-12-31T23:59:59",
  ...
}
```

- Both fields optional — omit to leave unchanged
- 404 if not found
- 409 if revoked

#### `POST /api/admin/profiles/{id}/credentials` → 200

Add credential references to a profile. Same as agent endpoint but requires admin auth.

```json
Request:
{"credentials": ["SIMPHONY_API_KEY", "DB_HOST"]}

Response:
{ /* full ProfileResponse with updated credentials list */ }
```

- 409 if profile is locked ("Cannot modify credentials on a locked profile")
- 409 if profile is revoked
- 404 if profile or any credential name not found

#### `DELETE /api/admin/profiles/{id}/credentials` → 200

Remove credential references from a profile.

```json
Request:
{"credentials": ["DB_HOST"]}

Response:
{ /* full ProfileResponse with updated credentials list */ }
```

- 409 if locked or revoked
- 404 if profile not found

#### `POST /api/admin/profiles/{id}/lock` → 200

Lock a profile and generate the two-part key. **This is the critical endpoint.**

```json
Response:
{
  "id": "a1b2c3d4-...",
  "description": "Oracle reporting",
  "locked": true,
  "key_id": "ark_7f3x9kw2m4p1n5j8q6r2t0",
  "key": "ark_7f3x9kw2m4p1n5j8q6r2t0:dK9mP2qR7xN4vB6cY1fW3hJ5kL8nT0pS2uV4wX6zA8bD0eF",
  "credentials": [...],
  "created_at": "2026-02-01T22:00:00"
}
```

- The `key` field contains the **full key string** — `ark_ID:SECRET`. Shown **once**.
- 409 if already locked
- 409 if revoked
- 404 if not found

#### `POST /api/admin/profiles/{id}/revoke` → 200

Revoke a profile. Instant, irreversible.

```json
Response:
{
  "id": "a1b2c3d4-...",
  "revoked": true,
  ...
}
```

- 409 if already revoked
- 404 if not found

#### `POST /api/admin/profiles/{id}/regenerate-key` → 200

Generate a new key pair for a locked profile. Old key stops working immediately.

```json
Response:
{
  "id": "a1b2c3d4-...",
  "key_id": "ark_NEW_KEY_ID_HERE_000000",
  "key": "ark_NEW_KEY_ID_HERE_000000:newSecretHere...",
  "locked": true,
  ...
}
```

- Returns new full key string (shown once, like lock)
- 409 if not locked (must be locked to regenerate)
- 409 if revoked
- 404 if not found

#### `DELETE /api/admin/profiles/{id}` → 204

Delete a profile.

- Cannot delete **locked** profiles — revoke first, then delete
- Deleting unlocked or revoked profiles is fine
- Removes all `profile_credentials` rows for the profile
- 409 if locked and not revoked
- 404 if not found

### 6. Agent API — Update `src/airlock/api/agent.py`

Add profile management endpoints. These are **unauthenticated** — agents can discover and configure profiles freely. The security boundary is the lock step (user-only via admin API).

#### `GET /profiles` → 200

List all profiles with metadata.

```json
{
  "profiles": [
    {
      "id": "a1b2c3d4-...",
      "description": "Oracle reporting — read only",
      "locked": true,
      "key_id": "ark_7f3x9kw2m4p1n5j8q6r2t0",
      "credentials": [
        {"name": "SIMPHONY_API_KEY", "description": "Simphony REST API key", "value_exists": true}
      ],
      "expires_at": "2026-12-31T23:59:59",
      "revoked": false,
      "created_at": "2026-02-01T22:00:00"
    }
  ]
}
```

Note: `key_id` is visible (agents need it to correlate profiles with keys they've been given). The **secret** is never exposed via any API.

#### `GET /profiles/{id}` → 200

Get a single profile by internal ID.

```json
{
  "id": "a1b2c3d4-...",
  "description": "Oracle reporting — read only",
  "locked": true,
  "key_id": "ark_7f3x9kw2m4p1n5j8q6r2t0",
  "credentials": [
    {"name": "SIMPHONY_API_KEY", "description": "Simphony REST API key", "value_exists": true},
    {"name": "DB_HOST", "description": "Oracle DB hostname", "value_exists": true}
  ]
}
```

- 404 if not found

#### `POST /profiles` → 201

Create a new unlocked profile.

```json
Request:
{
  "description": "Oracle reporting — read only"
}

Response:
{
  "id": "a1b2c3d4-...",
  "description": "Oracle reporting — read only",
  "locked": false,
  "key_id": null,
  "credentials": [],
  "created_at": "2026-02-01T22:00:00"
}
```

#### `POST /profiles/{id}/credentials` → 200

Add credential references to an unlocked profile.

```json
Request:
{"credentials": ["SIMPHONY_API_KEY", "DB_HOST"]}

Response:
{ /* full ProfileResponse with updated credentials list */ }
```

- 409 if profile is locked
- 409 if profile is revoked
- 404 if profile not found
- 404 if any credential name doesn't exist

#### `DELETE /profiles/{id}/credentials` → 200

Remove credential references from an unlocked profile.

```json
Request:
{"credentials": ["DB_HOST"]}

Response:
{ /* full ProfileResponse with updated credentials list */ }
```

- 409 if profile is locked or revoked
- 404 if profile not found
- Silently ignores credential names not currently attached

### 7. Update `POST /execute` — Bearer Auth + HMAC

Replace the current `profile_id`-in-body approach with Bearer auth + script hash verification.

**Before:**
```
POST /execute
Body: {"profile_id": "ark_...", "script": "...", "timeout": 60}
```

**After:**
```
POST /execute
Authorization: Bearer ark_7f3x9kw2m4p1n5j8q6r2t0
Body: {"script": "...", "hash": "a1b2c3d4e5f6...", "timeout": 60}
```

Updated endpoint:

```python
@router.post("/execute", status_code=202, response_model=ExecutionCreated)
async def execute(
    request: ExecutionRequest,
    background: BackgroundTasks,
    profile: ProfileAuth = Depends(require_profile),
) -> ExecutionCreated:
    """Accept a script for execution. Authenticated by profile key."""

    # Verify script integrity via HMAC
    if not verify_script_hmac(profile.secret, request.script, request.hash):
        raise HTTPException(
            status_code=403,
            detail="Script hash verification failed — HMAC mismatch",
        )

    execution_id = f"exec_{uuid.uuid4().hex}"
    poll_url = f"/executions/{execution_id}"

    _executions[execution_id] = ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.pending,
    )

    # Resolve credentials for this profile
    from airlock.services.credentials import resolve_profile_credentials
    db = await get_db()
    master_key = request.app.state.master_key  # via FastAPI Request, not Pydantic model
    settings = await resolve_profile_credentials(db, profile.profile_id, master_key)

    background.add_task(
        _run_execution, execution_id, request.script, settings, request.timeout
    )

    return ExecutionCreated(
        execution_id=execution_id,
        poll_url=poll_url,
        status=ExecutionStatus.pending,
    )
```

Note: The `require_profile` dependency handles all auth checks (valid key, locked, not revoked, not expired). The endpoint only needs to verify the HMAC and dispatch the execution.

To access the raw `Request` object for `app.state.master_key` alongside the Pydantic body, use a separate `Request` parameter:

```python
async def execute(
    body: ExecutionRequest,
    raw_request: Request,
    background: BackgroundTasks,
    profile: ProfileAuth = Depends(require_profile),
) -> ExecutionCreated:
    master_key = raw_request.app.state.master_key
    ...
```

### 8. Profile Lifecycle Flow

```
Agent                          User (Web UI)                  Airlock DB
  │                                │                              │
  │ POST /profiles                 │                              │
  │ {description: "Reporting"}     │                              │
  │───────────────────────────────────────────────────────────────▶│
  │◀──────────────────────────────────────────────────────────────│
  │ {id: "uuid-1", locked: false}  │                              │
  │                                │                              │
  │ POST /profiles/uuid-1/creds    │                              │
  │ {credentials: ["API_KEY"]}     │                              │
  │───────────────────────────────────────────────────────────────▶│
  │◀──────────────────────────────────────────────────────────────│
  │ {credentials: [{name: "API_KEY", value_exists: false}]}       │
  │                                │                              │
  │ "Please open Airlock, fill     │                              │
  │  in API_KEY, then lock the     │                              │
  │  profile"                      │                              │
  │──────────▶│                    │                              │
  │           │                    │                              │
  │           │ PUT /api/admin/credentials/API_KEY                │
  │           │ {value: "sk-live-abc123"}                          │
  │           │───────────────────────────────────────────────────▶│
  │           │                                                   │
  │           │ POST /api/admin/profiles/uuid-1/lock              │
  │           │───────────────────────────────────────────────────▶│
  │           │◀──────────────────────────────────────────────────│
  │           │ {key: "ark_abc...:secret123...",                   │
  │           │  key_id: "ark_abc...", locked: true}               │
  │           │                                                   │
  │           │ Copies ark_abc...:secret123...                     │
  │           │ Gives to agent                                    │
  │◀──────────│                                                   │
  │                                                               │
  │ POST /execute                                                 │
  │ Authorization: Bearer ark_abc...                              │
  │ {script: "...", hash: "hmac..."}                              │
  │───────────────────────────────────────────────────────────────▶│
  │◀──────────────────────────────────────────────────────────────│
  │ {execution_id: "exec_...", status: "pending"}                 │
```

---

## Tests

### Unit Tests — `tests/test_profiles.py` (new file)

#### Profile CRUD — Agent API

- `POST /profiles` → 201, profile created with UUID id, `locked: false`, `key_id: null`
- `POST /profiles` with description → description stored correctly
- `GET /profiles` → 200, lists all profiles
- `GET /profiles` on empty DB → `{"profiles": []}`
- `GET /profiles/{id}` → 200, returns single profile with credentials
- `GET /profiles/nonexistent` → 404
- `POST /profiles/{id}/credentials` with valid names → credentials attached
- `POST /profiles/{id}/credentials` with duplicate names → idempotent (no error)
- `POST /profiles/{id}/credentials` with nonexistent credential → 404
- `POST /profiles/{id}/credentials` on locked profile → 409
- `POST /profiles/{id}/credentials` on revoked profile → 409
- `DELETE /profiles/{id}/credentials` → credentials removed
- `DELETE /profiles/{id}/credentials` with name not attached → no error (silent)
- `DELETE /profiles/{id}/credentials` on locked profile → 409
- `DELETE /profiles/{id}/credentials` on revoked profile → 409

#### Profile CRUD — Admin API

- `POST /api/admin/profiles` → 201, requires admin auth
- `GET /api/admin/profiles` → 200, requires admin auth, lists all
- `GET /api/admin/profiles/{id}` → 200, requires admin auth
- `PUT /api/admin/profiles/{id}` → 200, updates description
- `PUT /api/admin/profiles/{id}` with expires_at → expiration set
- `PUT /api/admin/profiles/{id}` on revoked profile → 409
- `DELETE /api/admin/profiles/{id}` on unlocked profile → 204
- `DELETE /api/admin/profiles/{id}` on locked (not revoked) → 409
- `DELETE /api/admin/profiles/{id}` on revoked profile → 204
- All admin profile endpoints without token → 401
- `POST /api/admin/profiles/{id}/credentials` → adds credentials (admin auth)
- `DELETE /api/admin/profiles/{id}/credentials` → removes credentials (admin auth)

#### Lock

- `POST /api/admin/profiles/{id}/lock` → 200 with `key` and `key_id` in response
- Response `key` format matches `ark_...:...` (colon-separated, key_id prefix)
- Response `key_id` starts with `ark_` and is 28 chars (4 prefix + 24 random)
- Profile now shows `locked: true` on subsequent GET
- Lock same profile again → 409
- Lock revoked profile → 409
- Lock nonexistent profile → 404
- After lock: `POST /profiles/{id}/credentials` → 409 (credentials frozen)

#### Revoke

- `POST /api/admin/profiles/{id}/revoke` → 200 with `revoked: true`
- Revoke same profile again → 409
- Revoke nonexistent profile → 404
- After revoke: execution with old key → 401

#### Regenerate Key

- `POST /api/admin/profiles/{id}/regenerate-key` → 200 with new `key` and `key_id`
- New `key_id` differs from old `key_id`
- New `key` differs from old `key`
- Old key_id no longer works for execution → 401
- New key_id works for execution
- Regenerate on unlocked profile → 409
- Regenerate on revoked profile → 409
- Regenerate nonexistent → 404
- Profile state (credentials, description, lock, history) preserved after regenerate

#### Profile Auth + Execution

- `POST /execute` without Authorization header → 401
- `POST /execute` with `Authorization: Bearer invalid` → 401
- `POST /execute` with valid Bearer key but profile not locked → 401
- `POST /execute` with valid Bearer key but profile revoked → 401
- `POST /execute` with valid Bearer key but profile expired → 401
- `POST /execute` with valid Bearer key + correct HMAC → 202
- `POST /execute` with valid Bearer key + wrong HMAC → 403
- `POST /execute` with valid Bearer key + empty hash → 403

#### HMAC Verification

- `verify_script_hmac(secret, script, correct_hash)` → True
- `verify_script_hmac(secret, script, wrong_hash)` → False
- `verify_script_hmac(secret, modified_script, original_hash)` → False (integrity check)
- HMAC computed with different secret → verification fails
- HMAC hex digest is exactly 64 characters

#### Credential Resolution

- Locked profile with credentials that have values → settings dict populated
- Locked profile with credential missing value → that key omitted from settings
- Credential value updated → next execution gets new value
- Profile with no credentials → empty settings dict

#### Expiration

- Profile with `expires_at` in the future → execution succeeds
- Profile with `expires_at` in the past → execution returns 401
- Profile with `expires_at` = null → no expiration, always valid

### Existing Tests

All existing tests must continue to pass. The `POST /execute` tests in `test_agent_api.py` will need updating to use Bearer auth + hash instead of `profile_id` in body. Update the mock tests to match the new request format.

---

## What Does NOT Change

- Web UI (Svelte) — UI profile pages already exist as shells
- Worker/execution engine — still receives `(script, settings, timeout)`, unchanged
- Credential encryption (`src/airlock/crypto.py`) — reused for secret encryption
- Credential service (`src/airlock/services/credentials.py`) — `resolve_profile_credentials` already written
- Health endpoint
- `GET /skill.md` (dynamic content comes in Phase 7)
- LLM pause/resume
- Output sanitization
- Admin setup/login auth flow

## What This Enables

After this spec:
- Users can create profiles, attach credentials, and lock them for production use
- Agents can self-onboard: create profiles, declare needed credentials, wait for user to lock
- Execution is authenticated with a two-part key (Bearer + HMAC)
- Code integrity is verified — scripts can't be tampered with in transit
- Keys can be rotated without recreating profiles
- Profiles can be revoked instantly in an emergency
- The credential resolution pipeline is complete: profile → credentials → decrypted values → worker

---

## Acceptance Criteria

- [ ] `POST /profiles` → creates profile with UUID id, `locked: false`, `key_id: null`
- [ ] `POST /profiles/{id}/credentials` → attaches credentials to unlocked profile
- [ ] `DELETE /profiles/{id}/credentials` → removes credentials from unlocked profile
- [ ] Adding/removing credentials on locked profile → 409
- [ ] `POST /api/admin/profiles/{id}/lock` → sets locked=1, returns `key` (ark_ID:SECRET) once
- [ ] `POST /api/admin/profiles/{id}/revoke` → sets revoked=1, irreversible
- [ ] `POST /api/admin/profiles/{id}/regenerate-key` → new key pair, old key dead
- [ ] `POST /execute` uses `Authorization: Bearer ark_...` (no more `profile_id` in body)
- [ ] `POST /execute` body includes `hash` = HMAC-SHA256(secret, script)
- [ ] HMAC mismatch → 403
- [ ] Missing/invalid Bearer → 401
- [ ] Revoked profile → 401
- [ ] Expired profile → 401
- [ ] Unlocked profile → 401 (can't execute)
- [ ] Profile secret stored encrypted in SQLite (AES-256-GCM, same master key as credentials)
- [ ] All agent API profile endpoints unauthenticated (like credential endpoints)
- [ ] All admin API profile endpoints require session token
- [ ] `resolve_profile_credentials` integrates with execution (settings injected into worker)
- [ ] All new tests pass
- [ ] All existing tests updated and pass

---

## Implementation Order

1. Update `src/airlock/db.py` — add `key_id` + `key_secret_encrypted` columns to profiles, add migration runner
2. `src/airlock/services/profiles.py` — profile service (CRUD, lock, revoke, regenerate, credential binding, HMAC verification)
3. Update `src/airlock/models.py` — add profile request/response models, update `ExecutionRequest`
4. Update `src/airlock/auth.py` — add `ProfileAuth` dataclass + `require_profile` dependency
5. Update `src/airlock/api/admin.py` — replace profile stub with full CRUD + lock + revoke + regenerate
6. Update `src/airlock/api/agent.py` — add profile endpoints + rewrite `POST /execute` with Bearer auth + HMAC
7. Update `src/airlock/app.py` — no changes expected (master key already loaded from Spec 03)
8. Update `tests/test_agent_api.py` — fix existing execute tests to use new request format
9. `tests/test_profiles.py` — all new tests from above
10. Verify all existing tests still pass

---

## Notes for CC

- The `profiles` table already exists in `db.py` — add the two new columns via ALTER TABLE migration AND update the CREATE TABLE statement for fresh DBs.
- Use `src/airlock/crypto.py` (from Spec 03) for encrypting/decrypting the profile secret. Same `encrypt_value` / `decrypt_value` functions.
- The master key is already on `app.state.master_key` (Spec 03 wired this up).
- `resolve_profile_credentials` in `src/airlock/services/credentials.py` (from Spec 03) already handles profile → credential resolution. Use it in the execute endpoint.
- The `profile_credentials` join table uses `credential_id` (UUID), not credential name. Your service layer must resolve name → id when adding credentials.
- `key_id` format: `ark_` + 24 lowercase alphanumeric chars. Secret: 48 mixed-case alphanumeric chars.
- The HMAC uses the raw secret string (UTF-8 encoded) as the key, and the raw script string (UTF-8 encoded) as the message. Output is a hex digest (64 chars).
- Use `hmac.compare_digest()` for timing-safe comparison.
- For the `require_profile` dependency, reuse the existing `_bearer = HTTPBearer(auto_error=False)` from `auth.py`.
- **Update existing mock execution tests** — they use `profile_id` in the body. Change them to use `Authorization: Bearer ark_...` + `hash` field. For mock tests where you don't have a real locked profile, you may need to create and lock a profile in the test fixture, or mock the auth dependency.
- The `DELETE /api/admin/profiles/{id}` endpoint requires the profile to be either unlocked or revoked. A locked-and-active profile cannot be deleted — revoke it first. This prevents accidental deletion of live profiles.
- Agent API does **not** have lock, revoke, regenerate, update, or delete endpoints. Those are admin-only.
- In the agent API, `key_id` is visible in profile responses so agents can correlate "this profile uses key ark_..." — but the secret is **never** exposed via any API endpoint.
- **HTTPS**: Airlock v1 does not implement TLS. Document in the SKILL.md and README that HTTPS should be handled by infrastructure (reverse proxy, cloud platform, etc.). The HMAC protects code integrity but does not replace transport encryption for confidentiality.
