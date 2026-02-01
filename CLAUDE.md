# CLAUDE.md — Instructions for Claude Code

You are implementing **Airlock**, a Python code execution service that acts as a trust boundary between AI agents and authenticated infrastructure.

## Core Principle

> **Deterministic Execution: Same code + same source data = same numbers. Every time.**

All data work is deterministic Python. LLM is optional and only for presentation (summaries, narratives). Never use an LLM to compute data.

## Project Context

Read these first:
- `README.md` — what Airlock is and why
- `docs/architecture.md` — full technical design (worker pool, polling API, LLM integration, security)
- `specs/` — implementation tasks (do them in order)

## Architecture Summary

- **Worker Pool**: Per-project pools of long-running Docker containers. Each worker runs a minimal FastAPI on `:8001` with a `/run` endpoint. Airlock API routes requests to idle workers.
- **Polling API**: Agent POSTs code → 202 with execution_id → polls GET /executions/{id} → gets result. No webhooks.
- **LLM via Polling**: Scripts can call `llm.complete()` which pauses execution. Agent sees `awaiting_llm` status, provides response via POST. Airlock holds zero LLM credentials.
- **Settings vs Memory**: Settings are user config (read-only). Memory is agent state (read-write). Settings wins on conflict.

## Tech Stack

- **Language:** Python 3.12
- **API framework:** FastAPI + uvicorn
- **Container runtime:** Docker (via docker-py SDK)
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
│   │   ├── api.py           # FastAPI routes (the router/manager)
│   │   ├── models.py        # Pydantic request/response models
│   │   ├── pool.py          # Worker pool management
│   │   ├── router.py        # Request routing to idle workers
│   │   ├── sanitizer.py     # Output secret redaction
│   │   ├── secrets.py       # Secret resolution
│   │   ├── projects.py      # Project config loading
│   │   └── worker/          # Code that runs inside workers
│   │       ├── server.py    # Worker FastAPI (/run endpoint)
│   │       └── sdk.py       # Script SDK (settings, memory, llm, set_result)
│   └── ...
├── projects/                 # Project config YAML files
├── tests/
├── specs/                    # Implementation tasks
├── docs/
├── Dockerfile.worker         # Worker container image
├── pyproject.toml
└── README.md
```

## Key Decisions

- **Secrets are NEVER logged, NEVER returned in responses** — redacted as `[REDACTED...last4]`
- **Workers are long-running** — warm pool, not ephemeral containers
- **Per-project isolation** — separate pools, separate Docker networks, separate secrets
- **Polling, not callbacks** — agent polls for status, no webhooks needed
- **LLM credentials stay on the agent side** — Airlock is purely an execution service
- **Output sanitization runs BEFORE any response is sent**
- **Memory updates are atomic** — applied only after successful execution

## Script SDK (available inside workers)

```python
settings.get(key)              # Get a setting (secrets from env, non-secrets from payload)
settings.keys()                # List available setting keys
memory.get(category, key)      # Read persistent memory
memory.set(category, key, val) # Write persistent memory (applied after execution)
llm.complete(prompt, model)    # Pause execution, request LLM from agent
set_result(data)               # Set the script's return value
```

## Current Task

Check `specs/` for the next implementation task. Each spec is a self-contained unit of work.
