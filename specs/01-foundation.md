# Spec 01: Foundation (Phase 1 → v0.1.0)

## Goal

A running container with admin auth, a web UI shell, all API endpoints stubbed, and CI in place. After this phase you can `docker run` it, log into the web UI, and hit every endpoint (with mock responses).

## Architecture Context

Airlock uses a **polling model** with **profile-based auth**:
1. Agent POSTs code + profile_id → gets 202 with `execution_id`
2. Agent polls `GET /executions/{id}` until terminal status
3. If script needs LLM, status shows `awaiting_llm` → agent provides response via POST
4. `GET /skill.md` returns dynamic skill document

Profile IDs (`ark_...`) are the sole authentication mechanism for the agent API. The web UI uses an admin token generated on first boot.

---

## Tasks

### 1. Project Structure

```
airlock/
├── src/
│   └── airlock/
│       ├── __init__.py
│       ├── __main__.py         # Entry point
│       ├── app.py              # FastAPI app factory
│       ├── api/
│       │   ├── __init__.py
│       │   ├── agent.py        # Agent-facing routes (/execute, /executions, /skill.md)
│       │   ├── admin.py        # Admin routes (web UI backend)
│       │   └── health.py       # /health
│       ├── models.py           # Pydantic models
│       ├── db.py               # SQLite setup + schema
│       ├── auth.py             # Admin token generation + validation
│       └── ui/                 # Static web UI files
│           ├── index.html      # Login page
│           ├── dashboard.html  # Dashboard shell (empty for now)
│           ├── css/
│           │   └── style.css
│           └── js/
│               └── app.js
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── test_health.py
│   ├── test_agent_api.py
│   └── test_admin_auth.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .github/
│   └── workflows/
│       └── ci.yml              # Lint + test + build image
├── .gitignore
└── .dockerignore
```

### 2. Dependencies — `pyproject.toml`

```toml
[project]
name = "airlock"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "pydantic>=2.0",
    "cryptography>=44.0",
    "aiosqlite>=0.21",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
    "httpx>=0.28",
    "ruff>=0.9",
]
```

### 3. Pydantic Models — `src/airlock/models.py`

```python
# --- Requests ---

class ExecutionRequest(BaseModel):
    profile_id: str                       # ark_... profile ID (acts as auth)
    script: str                           # Python code to execute
    timeout: int = 60                     # Max execution time (seconds)

class LLMResponse(BaseModel):
    response: str                         # LLM completion text

# --- Responses ---

class ExecutionStatus(str, Enum):
    pending = "pending"
    running = "running"
    awaiting_llm = "awaiting_llm"
    completed = "completed"
    error = "error"
    timeout = "timeout"

class ExecutionCreated(BaseModel):
    execution_id: str
    status: ExecutionStatus = ExecutionStatus.pending

class LLMRequest(BaseModel):
    prompt: str
    model: str = "default"

class ExecutionResult(BaseModel):
    execution_id: str
    status: ExecutionStatus
    result: Any | None = None             # From set_result()
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    llm_request: LLMRequest | None = None # Present when status == awaiting_llm
    execution_time_ms: int | None = None

class HealthResponse(BaseModel):
    status: str = "ok"
```

### 4. SQLite Schema — `src/airlock/db.py`

Initialize on startup. Tables are empty but ready for Phase 2+:

```sql
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    encrypted_value BLOB NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,              -- ark_...
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',  -- active | expired | revoked
    expires_at TEXT,                   -- ISO datetime, NULL = never
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS profile_credentials (
    profile_id TEXT NOT NULL REFERENCES profiles(id),
    credential_id TEXT NOT NULL REFERENCES credentials(id),
    PRIMARY KEY (profile_id, credential_id)
);

CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,              -- exec_...
    profile_id TEXT NOT NULL REFERENCES profiles(id),
    script TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,                       -- JSON
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    error TEXT,
    llm_request TEXT,                 -- JSON
    execution_time_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS admin (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

### 5. Admin Auth — `src/airlock/auth.py`

- On first boot: generate admin token (`atk_` + 32 random alphanumeric chars)
- Store hashed in `admin` table (key: `admin_token_hash`)
- Print to console:
  ```
  ╔══════════════════════════════════════════════════════╗
  ║  Airlock is running!                                 ║
  ║  Admin token: atk_8f2k4m9x...                       ║
  ║  Open http://localhost:9090 to configure              ║
  ╚══════════════════════════════════════════════════════╝
  ```
- On subsequent boots: token already exists, print reminder to check logs or reset
- Admin routes require `Authorization: Bearer atk_...` header
- Middleware or dependency injection for admin auth on `/api/admin/*` routes

### 6. Agent API Routes — `src/airlock/api/agent.py`

All mock responses for now. Real implementation comes in Phase 4.

#### `POST /execute` → 202

- Validate `profile_id` starts with `ark_`
- Generate `exec_` + UUID execution_id
- Store in-memory with status `pending`
- **Mock**: immediately set to `completed` with `result = {"echo": script[:100]}`
- Return `ExecutionCreated`

#### `GET /executions/{execution_id}` → 200

- Look up in-memory dict
- Return `ExecutionResult`
- 404 if not found

#### `POST /executions/{execution_id}/respond` → 200

- Accept `LLMResponse` body
- 409 if status isn't `awaiting_llm`
- **Mock**: set to `completed`, store response in result
- Return `ExecutionResult`
- 404 if not found

#### `GET /skill.md` → 200

- Return plain text mock skill document
- Content-Type: `text/markdown`
- Template with placeholder instance URL, no profiles listed

### 7. Admin API Routes — `src/airlock/api/admin.py`

Stubbed for Phase 2. All require admin auth.

#### `GET /api/admin/credentials` → 200
- Returns `[]` (empty list)

#### `GET /api/admin/profiles` → 200
- Returns `[]` (empty list)

#### `GET /api/admin/executions` → 200
- Returns `[]` (empty list)

#### `GET /api/admin/stats` → 200
- Returns `{"total_executions": 0, "active_profiles": 0, "stored_credentials": 0}`

### 8. Web UI — `src/airlock/ui/`

Static HTML/CSS/JS served by FastAPI's `StaticFiles`. Minimal but functional:

**Login page** (`/`):
- Clean centered form: "Enter admin token" + input + submit
- On submit: store token in sessionStorage, redirect to dashboard
- Dark theme, clean typography

**Dashboard** (`/dashboard`):
- Sidebar nav: Credentials, Profiles, Executions, Stats, Settings
- Main content area: "Welcome to Airlock" + summary cards (all showing 0)
- Each nav item leads to an empty placeholder page with "Coming in Phase 2/3/4"
- Token validation: redirect to login if no valid token

**Style:**
- Dark mode (matches Airlock's security vibe)
- No framework — vanilla HTML/CSS/JS
- Responsive but desktop-first
- Minimal animations, functional over flashy

### 9. Docker — `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/
COPY tests/ tests/

ENV AIRLOCK_DATA_DIR=/data
VOLUME /data

EXPOSE 9090

CMD ["python", "-m", "airlock"]
```

`docker-compose.yml`:
```yaml
services:
  airlock:
    build: .
    ports:
      - "9090:9090"
    volumes:
      - airlock-data:/data

volumes:
  airlock-data:
```

### 10. CI — `.github/workflows/ci.yml`

Triggered on push to `main` and PRs:

1. **Lint**: `ruff check src/ tests/`
2. **Test**: `pytest tests/ -v`
3. **Build**: `docker build .` (verify image builds, don't push yet)

### 11. Tests

#### `tests/test_health.py`
- `GET /health` → 200 `{"status": "ok"}`

#### `tests/test_agent_api.py`
- `POST /execute` with valid profile_id → 202 with `exec_` ID
- `POST /execute` without profile_id → 422
- `POST /execute` with profile_id not starting with `ark_` → 401
- `GET /executions/{id}` → returns completed mock result
- `GET /executions/nonexistent` → 404
- `POST /executions/{id}/respond` on completed → 409
- `GET /skill.md` → 200 with `text/markdown` content type

#### `tests/test_admin_auth.py`
- `GET /api/admin/credentials` without token → 401
- `GET /api/admin/credentials` with valid token → 200
- `GET /api/admin/credentials` with invalid token → 401

### 12. `.gitignore`

```
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
.ruff_cache/
*.db
.env
dist/
build/
```

---

## Acceptance Criteria

- [ ] `python -m airlock` starts server on :9090, prints admin token
- [ ] `docker build .` succeeds
- [ ] `docker run -p 9090:9090 airlock` → container starts, admin token in logs
- [ ] `curl localhost:9090/health` → `{"status": "ok"}`
- [ ] Full mock polling flow: `POST /execute` → `GET /executions/{id}` → completed
- [ ] Profile ID validated (must start with `ark_`)
- [ ] `GET /skill.md` returns markdown
- [ ] Web UI: login with admin token → dashboard with empty placeholder pages
- [ ] Admin API requires token, returns 401 without it
- [ ] SQLite database created in `/data/` with all tables
- [ ] Admin token persists across container restarts (volume mount)
- [ ] GitHub Actions CI: lint + test + build all pass
- [ ] All tests pass with `pytest`

## Notes for CC

- This is Phase 1 of 10. Keep it clean — every file you write will be built upon.
- Mock responses are intentional. Real execution comes in Phase 4.
- The web UI doesn't need to be beautiful yet, but it should be structured well (we'll iterate on design).
- Use `aiosqlite` for async SQLite access — FastAPI is async-first.
- Admin token hash in DB, never stored in plaintext.
- The `CLAUDE.md` in the repo root has your working guidelines.
