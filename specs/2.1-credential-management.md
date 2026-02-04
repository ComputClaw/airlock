# Spec 03: Credential Management (Phase 2 → v0.2.0)

## Goal

Users can create, view, edit, and delete credentials through the web UI. Agents can create credential slots (name + description only, never values) and list credentials with `value_exists` flags via the API. All credential values are encrypted at rest.

**Before:** Admin API returns `[]` for credentials. No storage, no encryption.
**After:** Full credential CRUD in both web UI (via admin API) and agent API. Values encrypted in SQLite with AES-256.

## Prerequisites

- Spec 01 (Foundation) ✅
- Spec 02 (Docker Execution) ✅

---

## Architecture

```
Web UI (admin)                          Agent API
    │                                       │
    ├─ POST /api/admin/credentials          ├─ POST /credentials
    │  {name, value, description}           │  [{name, description}]  ← no value
    │                                       │
    ├─ GET /api/admin/credentials           ├─ GET /credentials
    │  → [{name, description, has_value,    │  → [{name, description, value_exists}]
    │      created_at, updated_at}]         │
    │                                       │
    ├─ PUT /api/admin/credentials/{name}    │
    │  {value?, description?}               │
    │                                       │
    ├─ DELETE /api/admin/credentials/{name} │
    │                                       │
    └───────────────┬───────────────────────┘
                    │
            ┌───────▼────────┐
            │   SQLite DB    │
            │  credentials   │
            │  (AES-256)     │
            └───────┬────────┘
                    │
            ┌───────▼────────┐
            │  .secret file  │
            │  (encryption   │
            │   master key)  │
            └────────────────┘
```

---

## Tasks

### 1. Encryption Layer — `src/airlock/crypto.py` (new file)

Instance-level encryption for credential values.

```python
"""Credential encryption using AES-256-GCM with an instance-derived key."""

# Master key: 32 random bytes, generated once on first boot
# Stored at: {DATA_DIR}/.secret (file permissions 0o600)
# If the file is lost, all encrypted credentials become unrecoverable

def get_or_create_master_key(data_dir: Path) -> bytes:
    """Load master key from .secret file, or generate and save one."""
    secret_path = data_dir / ".secret"
    if secret_path.exists():
        return secret_path.read_bytes()
    key = os.urandom(32)
    secret_path.write_bytes(key)
    secret_path.chmod(0o600)
    return key

def encrypt_value(plaintext: str, master_key: bytes) -> bytes:
    """Encrypt a credential value. Returns nonce + ciphertext + tag as a single blob."""
    # Use AES-256-GCM (from cryptography package, already a dependency)
    # nonce (12 bytes) + ciphertext + tag (16 bytes) → stored as single BLOB

def decrypt_value(encrypted: bytes, master_key: bytes) -> str:
    """Decrypt a credential value blob back to plaintext string."""
    # Extract nonce (first 12 bytes), decrypt remainder
    # Raise on tampered/invalid data
```

Key details:
- Algorithm: AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`)
- Nonce: 12 bytes, randomly generated per encryption
- Storage format: `nonce (12B) || ciphertext || tag (16B)` — single BLOB column
- Master key loaded once at startup, held in memory for the process lifetime
- If `.secret` is missing and credentials exist in DB → they're unrecoverable (this is expected — documented in README)

### 2. Update Database Schema — `src/airlock/db.py`

The `credentials` table already exists from Spec 01. No schema change needed — it already has:

```sql
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    encrypted_value BLOB,          -- NULL when slot created by agent (no value yet)
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);
```

The `encrypted_value` being nullable is correct — agent-created slots won't have values until the user sets them via the web UI.

### 3. Credential Service — `src/airlock/services/credentials.py` (new file)

Business logic layer between API routes and database. Keeps routes thin.

```python
"""Credential management: CRUD operations with encryption."""

class CredentialInfo(TypedDict):
    """Credential metadata returned by list/get operations."""
    name: str
    description: str
    value_exists: bool  # True if encrypted_value is not NULL
    created_at: str
    updated_at: str | None

async def list_credentials(db: Connection) -> list[CredentialInfo]:
    """List all credentials with metadata. Never returns values."""

async def get_credential(db: Connection, name: str) -> CredentialInfo | None:
    """Get a single credential's metadata by name."""

async def create_credential(
    db: Connection, name: str, description: str,
    value: str | None, master_key: bytes
) -> CredentialInfo:
    """Create a credential. Value is optional (agent-created slots have no value).
    
    - name: unique key name (e.g., SIMPHONY_API_KEY)
    - description: what this credential is for
    - value: plaintext value to encrypt, or None for empty slot
    - Raises ValueError if name already exists
    """

async def update_credential(
    db: Connection, name: str,
    value: str | None = ...,  # sentinel = don't change
    description: str | None = ...,
    master_key: bytes | None = None
) -> CredentialInfo:
    """Update a credential's value and/or description.
    
    - Only fields provided are updated
    - value=None explicitly clears the value (sets encrypted_value to NULL)
    - Raises ValueError if credential doesn't exist
    """

async def delete_credential(db: Connection, name: str) -> None:
    """Delete a credential by name.
    
    - Raises ValueError if credential doesn't exist
    - Raises ValueError if credential is referenced by any LOCKED profile
      (unlocked profile refs are removed automatically)
    """

async def decrypt_credential_value(
    db: Connection, name: str, master_key: bytes
) -> str | None:
    """Decrypt and return a credential's value. Used internally for execution.
    Never exposed via API. Returns None if no value set."""

async def resolve_profile_credentials(
    db: Connection, profile_id: str, master_key: bytes
) -> dict[str, str]:
    """Resolve all credentials for a profile into a {name: value} dict.
    Used by the execution engine to inject settings.
    Only returns credentials that have values set.
    Raises ValueError if profile doesn't exist or isn't locked."""
```

Credential name validation rules:
- Must match `^[A-Za-z_][A-Za-z0-9_]*$` (valid as environment variable names)
- Max 128 characters
- Case-sensitive (`API_KEY` and `api_key` are different credentials)

### 4. Admin API — Update `src/airlock/api/admin.py`

Replace the stub `list_credentials` endpoint and add full CRUD:

#### `GET /api/admin/credentials` → 200

List all credentials (already exists as stub, replace with real implementation).

```json
{
  "credentials": [
    {
      "name": "SIMPHONY_API_KEY",
      "description": "Simphony REST API key",
      "has_value": true,
      "created_at": "2026-02-01T22:00:00",
      "updated_at": "2026-02-01T23:00:00"
    }
  ]
}
```

Note: Admin API uses `has_value` (boolean) rather than `value_exists` — same meaning, consistent with admin naming conventions. Agent API uses `value_exists`.

#### `POST /api/admin/credentials` → 201

Create a credential with value.

```json
Request:
{
  "name": "SIMPHONY_API_KEY",
  "value": "sk-live-abc123",
  "description": "Simphony REST API key"
}

Response:
{
  "name": "SIMPHONY_API_KEY",
  "description": "Simphony REST API key",
  "has_value": true,
  "created_at": "2026-02-01T22:00:00"
}
```

- `name` required, must match validation regex
- `value` optional (can create empty slot from admin UI too)
- `description` optional, defaults to `""`
- 409 if name already exists

#### `PUT /api/admin/credentials/{name}` → 200

Update a credential's value and/or description.

```json
Request:
{
  "value": "sk-live-new456",
  "description": "Updated Simphony key"
}

Response:
{
  "name": "SIMPHONY_API_KEY",
  "description": "Updated Simphony key",
  "has_value": true,
  "updated_at": "2026-02-01T23:00:00"
}
```

- Both fields optional — omit `value` to only update description, omit `description` to only update value
- 404 if credential doesn't exist

#### `DELETE /api/admin/credentials/{name}` → 204

Delete a credential.

- 404 if doesn't exist
- 409 if referenced by any **locked** profile (with error message listing the profile IDs)
- If referenced by **unlocked** profiles: remove the reference automatically, then delete the credential

### 5. Agent API — Update `src/airlock/api/agent.py`

Add two new endpoints. These are **not authenticated** — any agent can discover credentials and create slots. Profile-based auth is for execution only.

#### `GET /credentials` → 200

List all credentials with metadata. Never returns values.

```json
{
  "credentials": [
    {
      "name": "SIMPHONY_API_KEY",
      "description": "Simphony REST API key",
      "value_exists": true
    },
    {
      "name": "DB_HOST",
      "description": "Oracle DB hostname",
      "value_exists": false
    }
  ]
}
```

#### `POST /credentials` → 201

Create credential slots (name + description, no value). Agents use this to declare what credentials they need.

```json
Request:
{
  "credentials": [
    {"name": "REPORTING_DB_PASS", "description": "Read-only DB password for reporting"},
    {"name": "SMTP_KEY", "description": "SendGrid API key for email delivery"}
  ]
}

Response:
{
  "created": ["REPORTING_DB_PASS", "SMTP_KEY"],
  "skipped": []
}
```

- Accepts a list (batch creation)
- `name` required per item, must match validation regex
- `description` optional per item
- If a name already exists: skip it (add to `skipped` list), don't error
- Never accepts `value` field — if present in request body, ignore it silently

### 6. Wire Encryption into App Startup — `src/airlock/app.py`

Update the lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    
    # Load or generate encryption master key
    from airlock.crypto import get_or_create_master_key
    master_key = get_or_create_master_key(DATA_DIR)
    app.state.master_key = master_key  # available to routes via request.app.state.master_key
    
    # ... rest of startup (worker, etc.)
```

Routes access the master key via `request.app.state.master_key`.

### 7. Pydantic Models — Update `src/airlock/models.py`

Add request/response models for credential operations:

```python
# --- Credential Requests ---

class AdminCreateCredentialRequest(BaseModel):
    """Admin creates a credential with optional value."""
    name: str  # must match ^[A-Za-z_][A-Za-z0-9_]*$
    value: str | None = None
    description: str = ""

class AdminUpdateCredentialRequest(BaseModel):
    """Admin updates a credential's value and/or description."""
    value: str | None = None
    description: str | None = None

class AgentCreateCredentialItem(BaseModel):
    """Single credential slot for agent batch creation."""
    name: str
    description: str = ""

class AgentCreateCredentialsRequest(BaseModel):
    """Agent creates credential slots (no values)."""
    credentials: list[AgentCreateCredentialItem]

# --- Credential Responses ---

class AdminCredentialInfo(BaseModel):
    """Credential metadata for admin API."""
    name: str
    description: str
    has_value: bool
    created_at: str
    updated_at: str | None = None

class AgentCredentialInfo(BaseModel):
    """Credential metadata for agent API."""
    name: str
    description: str
    value_exists: bool

class AgentCreateCredentialsResponse(BaseModel):
    """Result of agent batch credential creation."""
    created: list[str]
    skipped: list[str]
```

---

## What Does NOT Change

- Web UI (Svelte app) — UI credential pages already exist as shells, they'll wire to these endpoints but that's a UI concern, not this spec
- Worker/execution engine
- Profile system (Phase 3)
- Health endpoint
- `GET /skill.md` (dynamic profiles come in Phase 7)
- LLM pause/resume
- Output sanitization

## What This Enables

After this spec:
- Users can store real API credentials (encrypted)
- Agents can declare what credentials they need
- Users can fill in values through the web UI
- The credential service can resolve profile→credentials for execution (Phase 3 + 4 will wire this up)
- The `.secret` file + encrypted DB means credentials survive restarts safely

---

## Tests

### Unit Tests — `tests/test_credentials.py` (new file)

#### Encryption
- Encrypt a value → decrypt → matches original
- Encrypt same value twice → different ciphertexts (random nonce)
- Decrypt with wrong key → raises error
- Decrypt tampered data → raises error

#### Admin API — Credential CRUD
- `POST /api/admin/credentials` → 201, credential created
- `POST /api/admin/credentials` with same name → 409
- `POST /api/admin/credentials` with invalid name (e.g., `"123bad"`, `"has spaces"`, `""`) → 422
- `POST /api/admin/credentials` without value → `has_value: false`
- `POST /api/admin/credentials` with value → `has_value: true`
- `GET /api/admin/credentials` → lists all, never returns values
- `PUT /api/admin/credentials/{name}` with value → `has_value: true`, `updated_at` set
- `PUT /api/admin/credentials/{name}` with description only → description updated, value unchanged
- `PUT /api/admin/credentials/nonexistent` → 404
- `DELETE /api/admin/credentials/{name}` → 204
- `DELETE /api/admin/credentials/nonexistent` → 404
- All admin endpoints without token → 401

#### Agent API — Credential Discovery
- `GET /credentials` → 200, lists all credentials with `value_exists`
- `GET /credentials` on empty DB → `{"credentials": []}`
- `POST /credentials` with two new names → both created
- `POST /credentials` with existing name → skipped, no error
- `POST /credentials` with invalid name → 422
- `POST /credentials` ignores `value` field if sneaked in

#### Credential Deletion with Profile References
- Delete credential not referenced by any profile → succeeds
- Delete credential referenced by unlocked profile → succeeds, reference removed
- Delete credential referenced by locked profile → 409 with profile IDs in error

#### Service Layer
- `resolve_profile_credentials` returns `{name: decrypted_value}` dict
- `resolve_profile_credentials` skips credentials with no value set
- `resolve_profile_credentials` on non-existent profile → raises ValueError

### Existing Tests

All existing tests must continue to pass unchanged:
- `test_health.py` — health endpoint
- `test_agent_api.py` — execution mock flow
- `test_admin_auth.py` — setup/login/auth
- `test_docker_execution.py` — Docker worker tests (skip without Docker)

---

## Implementation Order

1. `src/airlock/crypto.py` — encryption functions + master key management
2. `src/airlock/services/credentials.py` — business logic (CRUD + encryption + resolution)
3. Update `src/airlock/models.py` — add credential request/response models
4. Update `src/airlock/api/admin.py` — replace stubs with real credential CRUD
5. Update `src/airlock/api/agent.py` — add `GET /credentials` and `POST /credentials`
6. Update `src/airlock/app.py` — load master key at startup, store on `app.state`
7. `tests/test_credentials.py` — all tests from above
8. Verify all existing tests still pass

---

## Acceptance Criteria

- [ ] Master key generated on first boot, persisted at `{DATA_DIR}/.secret`
- [ ] `POST /api/admin/credentials` with value → stored encrypted in SQLite
- [ ] `GET /api/admin/credentials` → returns metadata, never values
- [ ] `PUT /api/admin/credentials/{name}` → updates value/description
- [ ] `DELETE /api/admin/credentials/{name}` → deletes (409 if locked profile refs)
- [ ] All admin endpoints require valid session token
- [ ] `GET /credentials` (agent) → lists credentials with `value_exists` flags
- [ ] `POST /credentials` (agent) → creates slots without values, skips duplicates
- [ ] Agent API never accepts or returns credential values
- [ ] Credential name validation enforced (regex + length)
- [ ] `resolve_profile_credentials` decrypts and returns `{name: value}` dict
- [ ] Encrypted values survive container restart (volume mount)
- [ ] All new tests pass
- [ ] All existing tests still pass

## Notes for CC

- The `credentials` table already exists in `db.py` — don't recreate it, just use it.
- `encrypted_value` is nullable — that's intentional for agent-created slots.
- Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM` — it's already a dependency.
- The master key goes on `app.state.master_key` so routes can access it via `request.app.state`.
- Create a new `src/airlock/services/` package (add `__init__.py`).
- Keep route handlers thin — all logic in the service layer.
- The `resolve_profile_credentials` function won't be called yet (profiles aren't real until Spec 04), but write it now so it's ready. The existing `profile_credentials` join table is what it queries.
- Admin field is `has_value`, agent field is `value_exists` — different naming, same boolean.
- For the deletion + profile reference tests: you'll need to insert profile rows directly into the DB in test fixtures (profiles aren't managed via API yet).
