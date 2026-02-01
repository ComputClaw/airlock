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
- **Web UI**: Credential management, profile creation, execution history, stats. Served as static files from FastAPI.
- **Profiles**: The key innovation. Users create profiles in the web UI → each profile gets an `ark_` ID → agents use the profile ID as auth. Profile maps to a subset of stored credentials.
- **Agent API**: Minimal — `POST /execute`, `GET /executions/{id}`, `POST /executions/{id}/respond`, `GET /skill.md`.
- **Two-Layer SKILL.md**: Static (GitHub/airlock.sh) for discovery + Dynamic (`GET /skill.md`) for self-onboarding.
- **Polling API**: Agent POSTs code → 202 with execution_id → polls GET /executions/{id} → gets result. No webhooks.
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
- **Admin token on first boot** — printed to console, used to login to web UI
- **Secrets are NEVER logged, NEVER returned in responses** — redacted as `[REDACTED...last4]`
- **Single port (9090)** — web UI and agent API on the same port
- **SQLite, not YAML** — all state in SQLite (credentials, profiles, executions)
- **Polling, not callbacks** — agent polls for status, no webhooks needed
- **LLM credentials stay on the agent side** — Airlock is purely an execution service
- **Output sanitization runs BEFORE any response is sent**

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
    encrypted_value BLOB NOT NULL,
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- Access profiles
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,             -- ark_... opaque ID
    description TEXT,
    expires_at TEXT,                  -- NULL = never expires
    revoked INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
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
    script TEXT,
    status TEXT,                     -- pending/running/awaiting_llm/completed/error/timeout
    result TEXT,                     -- JSON
    stdout TEXT,
    stderr TEXT,
    error TEXT,
    execution_time_ms INTEGER,
    created_at TEXT,
    completed_at TEXT
);
```

## Current Task

Check `specs/` for the next implementation task. Each spec is a self-contained unit of work.
