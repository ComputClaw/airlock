# Spec 03: Web UI for Credential & Profile Management

## Goal

Build the web UI that lets users manage credentials, create profiles, and view execution history. Served as static files from the FastAPI server on port 9090.

## Architecture Context

The web UI is the primary interface for **users** (not agents). It's how credentials get into Airlock and how profiles get created. Without the web UI, the agent API is useless — there are no credentials to inject and no profiles to authenticate with.

The UI is vanilla JS/HTML/CSS — no build step, no framework. Served as static files mounted at `/ui/*` by FastAPI, with API endpoints at `/api/*` backing the UI.

## Prerequisites

- Spec 01 complete (API skeleton)
- SQLite database layer (`db.py`) with tables for credentials, profiles, profile_credentials, executions
- Credential encryption (`crypto.py`) using Fernet

## Design

### First Boot Flow

1. On first startup, Airlock generates:
   - An instance secret key (for Fernet encryption, stored in SQLite or a local file)
   - An admin token (`atk_` + random string)
2. Admin token printed to console:
   ```
   ╔══════════════════════════════════════════════════════╗
   ║  Airlock admin token: atk_8f2k4m9xp3...             ║
   ║  Open http://localhost:9090 to configure             ║
   ╚══════════════════════════════════════════════════════╝
   ```
3. User opens `http://localhost:9090` → redirected to `/ui/`
4. Login screen → enter admin token
5. Token stored in browser localStorage, sent as `Authorization: Bearer atk_...` on all UI API calls

### UI Pages

#### Login (`/ui/` or `/ui/login`)
- Single input field for admin token
- "Login" button
- On success: store token in localStorage, redirect to dashboard

#### Credentials (`/ui/credentials`)
- Table of existing credentials: name, description, created date, actions
- "Add Credential" button → modal/form:
  - Name (e.g., `SIMPHONY_API_KEY`) — must be unique, uppercase + underscores
  - Value (password field)
  - Description (optional)
- Edit: update value or description
- Delete: with confirmation dialog
- Values are NEVER shown in the UI after creation — only `••••••••` with a "copy" button (if we want) or just hidden

#### Profiles (`/ui/profiles`)
- Table of existing profiles: ID (`ark_...`), description, credentials count, expiration, status (active/expired/revoked), actions
- "Create Profile" button → modal/form:
  - Description (e.g., "Read-only reporting for OpenClaw")
  - Select credentials (multi-select checkboxes from credential list)
  - Expiration date (optional date picker)
- Each profile shows its `ark_` ID with a "Copy" button
- Revoke button (sets `revoked = 1`, instant effect)
- Delete button (with confirmation)
- Edit: update description, change credential selection, update expiration

#### Execution History (`/ui/executions`)
- Table: execution ID, profile, status, duration, timestamp
- Click to expand: script code, stdout, result (JSON pretty-printed)
- Filter by: profile, status, date range
- Pagination (most recent first)

#### Stats (`/ui/stats`)
- Total executions (all time, last 24h, last 7d)
- Executions per profile (bar chart or simple table)
- Error rate (percentage)
- Average execution duration
- Active profiles count
- Could be simple HTML tables/numbers for v1 — charts can come later

### Navigation

Simple sidebar or top nav:
- Credentials
- Profiles
- Executions
- Stats
- (Logout)

## Tasks

### 1. Database Layer — `src/airlock/db.py`

SQLite database with tables:

```sql
CREATE TABLE IF NOT EXISTS instance (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Stores: admin_token, encryption_key, instance_id

CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    encrypted_value BLOB NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,           -- ark_...
    description TEXT DEFAULT '',
    expires_at TEXT,               -- ISO 8601 or NULL
    revoked INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_credentials (
    profile_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
    credential_id TEXT REFERENCES credentials(id) ON DELETE CASCADE,
    PRIMARY KEY (profile_id, credential_id)
);

CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,           -- exec_...
    profile_id TEXT REFERENCES profiles(id),
    script TEXT,
    status TEXT NOT NULL,
    result TEXT,                   -- JSON string
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    error TEXT,
    execution_time_ms INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
```

Functions:
- `init_db()` — create tables, generate admin token + encryption key on first run
- CRUD for credentials (encrypt on write, decrypt on read)
- CRUD for profiles
- Profile credential linking
- Execution logging
- Stats queries

### 2. Credential Encryption — `src/airlock/crypto.py`

```python
from cryptography.fernet import Fernet

def generate_key() -> bytes:
    return Fernet.generate_key()

def encrypt(value: str, key: bytes) -> bytes:
    return Fernet(key).encrypt(value.encode())

def decrypt(encrypted: bytes, key: bytes) -> str:
    return Fernet(key).decrypt(encrypted).decode()
```

### 3. Web UI API Routes — `src/airlock/web.py`

All routes prefixed with `/api/` and require admin token auth.

#### Auth
- Middleware/dependency that checks `Authorization: Bearer atk_...` against stored admin token
- Returns 401 if invalid

#### Credentials API
```
GET    /api/credentials           → list all (without values)
POST   /api/credentials           → create {name, value, description}
PUT    /api/credentials/{id}      → update {value?, description?}
DELETE /api/credentials/{id}      → delete
```

#### Profiles API
```
GET    /api/profiles              → list all
POST   /api/profiles              → create {description, credential_ids, expires_at?}
PUT    /api/profiles/{id}         → update {description?, credential_ids?, expires_at?}
POST   /api/profiles/{id}/revoke  → revoke
DELETE /api/profiles/{id}         → delete
```

#### Executions API
```
GET    /api/executions            → list (with pagination, filters)
GET    /api/executions/{id}       → detail
```

#### Stats API
```
GET    /api/stats                 → aggregate stats
```

### 4. Static Files — `static/`

#### `static/index.html`
- Shell HTML with nav, content area, script/style includes
- Single page app (hash-based routing: `#credentials`, `#profiles`, etc.)

#### `static/app.js`
- Hash router
- API client (fetch wrapper with auth header)
- Page renderers for each section
- Modal/form handling
- Keep it clean but don't over-engineer — this is a management tool

#### `static/style.css`
- Clean, minimal styling
- Dark theme (matches developer tools aesthetic)
- Responsive enough to work on tablets
- Tables, forms, modals, buttons, status badges

### 5. FastAPI Static File Mounting

In the main app:
```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")

@app.get("/")
async def root():
    return RedirectResponse(url="/ui/")
```

### 6. Tests

- **test_first_boot**: init_db creates admin token and encryption key
- **test_credential_crud**: create, read (no value), update, delete
- **test_credential_encryption**: stored values are encrypted, decrypted correctly
- **test_profile_crud**: create (generates ark_ ID), read, update, revoke, delete
- **test_profile_credential_linking**: profile → credentials mapping works
- **test_auth_required**: API endpoints return 401 without valid admin token
- **test_stats**: stats endpoint returns correct counts
- **test_execution_history**: executions listed with proper filters

## Acceptance Criteria

- Opening `http://localhost:9090` redirects to web UI
- First boot prints admin token to console
- Can login with admin token
- Can add/edit/delete credentials (values never shown after creation)
- Can create profiles with selected credentials and optional expiration
- Can revoke profiles
- Can view execution history
- Can view basic stats
- All UI API endpoints require admin auth
- Credentials stored encrypted in SQLite
- No build step for the frontend — just static files

## Notes

- The web UI is the user's primary interface. Make it functional and clear.
- Don't over-invest in polish for v1 — correctness and usability first.
- The admin token is NOT the same as profile IDs. Admin token = manage Airlock. Profile IDs = execute code.
- Consider adding a "Quick Start" section to the UI that shows the user what to do after first login.
