# CLAUDE.md — Instructions for Claude Code

You are implementing **Airlock**, a Python code execution service that acts as a trust boundary between AI agents and authenticated infrastructure.

## Core Principle

> **Deterministic Execution: Same code + same source data = same numbers. Every time.**

All data work is deterministic Python. LLM is optional and only for presentation (summaries, narratives). Never use an LLM to compute data.

## Project Context

Read these first:
- `README.md` — what Airlock is and why
- `docs/architecture.md` — full technical design (profiles, web UI, agent API, execution engine, security)
- `SKILL.md` — the static skill document for agent discovery
- `specs/` — implementation tasks (do them in order)

## Architecture Summary

- **Single Container**: Everything runs in one Docker image on port 9090. Web UI + Agent API + Execution Engine.
- **Web UI**: Credential value management, profile locking, execution history, stats. Served as static files from FastAPI.
- **Credentials**: Global shared store. Both agents and users can create credential slots (name + description). Only users can set/edit values (via web UI). Updating a value propagates to all profiles referencing that credential.
- **Profiles**: The key innovation. Two states: **unlocked** (setup) → **locked** (production). Both agents and users can create profiles and add/remove credential references while unlocked. Only users can lock profiles (via web UI). Locked profiles can be used for execution. Each profile gets an `ark_` ID that agents use as auth.
- **Agent API**:
  - Credentials: `GET /credentials` (list all + `value_exists`), `POST /credentials` (create slots, no values)
  - Profiles: `GET /profiles`, `GET /profiles/{id}`, `POST /profiles`, `POST /profiles/{id}/credentials`, `DELETE /profiles/{id}/credentials`
  - Execution: `POST /execute` (returns `poll_url`), `GET /executions/{id}`, `POST /executions/{id}/respond`
  - Discovery: `GET /skill.md`
- **Two-Layer SKILL.md**: Static (GitHub/airlock.sh) for discovery + Dynamic (`GET /skill.md`) for self-onboarding.
- **Polling API**: Agent POSTs code → 202 with execution_id + poll_url → polls poll_url → gets result. Always use `poll_url` (load-balancer safe). No webhooks.
- **LLM via Polling**: Scripts can call `llm.complete()` which pauses execution. Agent sees `awaiting_llm` status, provides response via POST. Airlock holds zero LLM credentials.

## Tech Stack

- **Language:** Python 3.12
- **API framework:** FastAPI + uvicorn
- **Database:** SQLite (credentials, profiles, executions, stats)
- **Web UI:** Vanilla JS + HTML/CSS (served as static files from FastAPI) — keep it simple, no build step
- **Container runtime:** Docker (single image)
- **Credential encryption:** Fernet (cryptography library)
- **Tests:** pytest

### Web UI Approach

The web UI should be **simple vanilla JS/HTML/CSS** served as static files. No React, no Svelte, no build step. Reasons:
- Single Dockerfile with no frontend build stage
- Easy to modify and debug
- Minimal dependencies
- The UI is a management tool, not a consumer app — it doesn't need to be fancy

If complexity grows beyond what vanilla JS handles well, consider Alpine.js or htmx as lightweight alternatives before reaching for a full framework.

## Code Style

- Type hints everywhere
- Docstrings on public functions
- No classes where a function will do
- Keep files small and focused (<300 lines)
- Error messages should be helpful to an AI agent reading them

## Directory Structure

```
airlock/
├── src/
│   ├── airlock/
│   │   ├── __init__.py
│   │   ├── api.py           # FastAPI routes — agent-facing API
│   │   ├── web.py           # FastAPI routes — web UI API (CRUD for credentials, profiles)
│   │   ├── models.py        # Pydantic request/response models
│   │   ├── db.py            # SQLite database layer
│   │   ├── crypto.py        # Credential encryption/decryption
│   │   ├── profiles.py      # Profile resolution (ark_ ID → credentials)
│   │   ├── pool.py          # Worker pool management
│   │   ├── router.py        # Request routing to idle workers
│   │   ├── sanitizer.py     # Output secret redaction
│   │   ├── skill.py         # Dynamic SKILL.md generation
│   │   └── worker/          # Code that runs inside workers
│   │       ├── server.py    # Worker FastAPI (/run endpoint)
│   │       └── sdk.py       # Script SDK (settings, llm, set_result)
│   └── ...
├── static/                   # Web UI static files
│   ├── index.html
│   ├── app.js
│   └── style.css
├── tests/
├── specs/                    # Implementation tasks
├── docs/
├── SKILL.md                  # Static skill document (for GitHub / airlock.sh)
├── Dockerfile                # Single container image
├── pyproject.toml
└── README.md
```

## Key Decisions

- **Profile IDs are auth** — `ark_` + random string. No separate API keys or tokens for agents.
- **Credentials stored encrypted** — Fernet symmetric encryption in SQLite
- **Credentials are shared** — one credential can be referenced by many profiles. Update once, all profiles get it.
- **Agents create structure, users provide secrets** — agents can create credential slots and profiles, but only users set values and lock profiles.
- **Profile states: unlocked → locked** — one-way transition. Keys can only be added/removed while unlocked. Only locked profiles can execute.
- **Admin token on first boot** — printed to console, used to login to web UI
- **Secrets are NEVER logged, NEVER returned in responses** — redacted as `[REDACTED...last4]`
- **Single port (9090)** — web UI and agent API on the same port
- **SQLite, not YAML** — all state in SQLite (credentials, profiles, executions)
- **Polling, not callbacks** — agent polls for status, no webhooks needed. POST /execute returns `poll_url` for load-balancer affinity.
- **LLM credentials stay on the agent side** — Airlock is purely an execution service
- **Output sanitization runs BEFORE any response is sent**
- **DB export/import is UI-only** — no API endpoints for moving credential databases. Human in the loop.

## Script SDK (available inside workers)

```python
settings.get(key)              # Get a credential/setting value for the current profile
settings.keys()                # List available setting keys
llm.complete(prompt, model)    # Pause execution, request LLM from agent
set_result(data)               # Set the script's return value
```

## Database Schema (SQLite)

```sql
-- Stored API credentials (encrypted values)
CREATE TABLE credentials (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,       -- e.g., "SIMPHONY_API_KEY"
    encrypted_value BLOB,            -- NULL when agent creates slot without value
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

-- Access profiles
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,             -- ark_... opaque ID
    description TEXT DEFAULT '',
    locked INTEGER DEFAULT 0,        -- 0 = unlocked (setup), 1 = locked (production)
    expires_at TEXT,                  -- NULL = never expires
    revoked INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    last_used_at TEXT
);

-- Many-to-many: which credentials each profile can access
CREATE TABLE profile_credentials (
    profile_id TEXT REFERENCES profiles(id),
    credential_id TEXT REFERENCES credentials(id),
    PRIMARY KEY (profile_id, credential_id)
);

-- Execution history
CREATE TABLE executions (
    id TEXT PRIMARY KEY,             -- exec_...
    profile_id TEXT REFERENCES profiles(id),
    script TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/running/awaiting_llm/completed/error/timeout
    result TEXT,                     -- JSON
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    error TEXT,
    llm_request TEXT,               -- JSON (present when awaiting_llm)
    execution_time_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

-- Admin settings
CREATE TABLE admin (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

## Current Task

Check `specs/` for the next implementation task. Each spec is a self-contained unit of work.
