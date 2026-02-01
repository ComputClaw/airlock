# CLAUDE.md — Instructions for Claude Code

You are implementing **Airlock**, a Python code execution service that acts as a trust boundary between AI agents and authenticated infrastructure.

## Project Context

Read these first:
- `README.md` — what Airlock is and why
- `docs/architecture.md` — the full technical design
- `specs/` — implementation tasks (do them in order)

## Tech Stack

- **Language:** Python 3.12
- **API framework:** FastAPI + uvicorn
- **Container runtime:** Docker (via docker-py SDK)
- **Secret storage:** Encrypted YAML (Phase 1)
- **Config format:** YAML for project configs
- **Tests:** pytest

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
│   │   ├── api.py           # FastAPI routes
│   │   ├── executor.py      # Docker container management
│   │   ├── sanitizer.py     # Output secret redaction
│   │   ├── secrets.py       # Secret store (load/decrypt)
│   │   ├── projects.py      # Project config loading
│   │   └── models.py        # Pydantic request/response models
│   └── ...
├── projects/                 # Project config YAML files
├── tests/
├── specs/                    # Implementation tasks from Comput
├── docs/
├── Dockerfile                # Base execution image
├── docker-compose.yml        # Airlock service itself
├── pyproject.toml
└── README.md
```

## Key Decisions

- Secrets are NEVER logged, NEVER returned in responses, NEVER included in error messages
- Every Docker container is ephemeral — created, used, destroyed
- Network allowlisting is mandatory per project
- Output sanitization runs BEFORE any response is sent
- The agent calling Airlock should NEVER need to know secret values

## Current Task

Check `specs/` for the next implementation task. Each spec is a self-contained unit of work.
