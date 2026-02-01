# Spec 01: Project Skeleton — API Server with Mock Responses

## Goal

Set up the project structure, dependencies, and a working FastAPI API server with all endpoints defined. Mock responses only — no Docker, no real workers yet.

## Architecture Context

Airlock uses a **polling model** with **profile-based auth**:
1. Agent POSTs code + profile_id → gets 202 with `execution_id`
2. Agent polls `GET /executions/{id}` until terminal status
3. If script needs LLM, status shows `awaiting_llm` → agent provides response via POST
4. `GET /skill.md` returns dynamic skill document

Profile IDs (`ark_...`) are the sole authentication mechanism for the agent API.

## Tasks

### 1. Create `pyproject.toml`

Project metadata and dependencies:
- fastapi
- uvicorn[standard]
- docker (docker-py SDK)
- pydantic
- cryptography (for Fernet credential encryption)
- pytest (dev)
- httpx (dev, for testing FastAPI)

### 2. Create Pydantic Models — `src/airlock/models.py`

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

### 3. Create API Routes — `src/airlock/api.py`

All agent-facing endpoints, with in-memory state for tracking executions:

#### `POST /execute` → 202

- Validate profile_id starts with `ark_`
- Generate a UUID execution_id (prefixed `exec_`)
- Store in an in-memory dict with status `pending`
- **Mock behavior**: immediately set status to `completed` with `result = {"echo": script}` and `stdout = script`
- Return `ExecutionCreated`

#### `GET /executions/{execution_id}` → 200

- Look up execution in the in-memory dict
- Return `ExecutionResult`
- 404 if not found

#### `POST /executions/{execution_id}/respond` → 200

- Accept `LLMResponse` body
- Only valid when status is `awaiting_llm` (return 409 otherwise)
- **Mock behavior**: set status to `completed`, store the LLM response in result
- Return `ExecutionResult`
- 404 if not found

#### `GET /skill.md` → 200

- Return a plain text mock skill document
- Content-Type: `text/markdown`
- **Mock behavior**: return a template with placeholder instance URL and no profiles

#### `GET /health` → 200

- Return `HealthResponse`

### 4. Create Entry Point — `src/airlock/__main__.py`

```python
import uvicorn
from airlock.api import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9090)
```

### 5. Create Tests — `tests/test_api.py`

Using `httpx.AsyncClient` with FastAPI's `TestClient`:

- **test_health**: GET /health returns 200 with `{"status": "ok"}`
- **test_execute_returns_202**: POST /execute with valid profile_id returns 202 with execution_id
- **test_execute_requires_profile**: POST /execute without profile_id returns 422
- **test_poll_execution**: POST /execute → GET /executions/{id} returns completed result
- **test_poll_not_found**: GET /executions/nonexistent returns 404
- **test_respond_requires_awaiting_llm**: POST /executions/{id}/respond on a completed execution returns 409
- **test_skill_md**: GET /skill.md returns text/markdown content
- **test_execution_id_format**: execution_id starts with `exec_`

### 6. Create `.gitignore`

Python defaults + `.env` + `__pycache__/` + `.pytest_cache/` + `*.egg-info` + `*.db`

## Acceptance Criteria

- `python -m airlock` starts the server on port 9090
- All endpoints respond correctly with proper status codes
- Full polling flow works: POST /execute → GET /executions/{id} → completed
- Profile ID is required and validated on /execute
- GET /skill.md returns markdown content
- Tests pass with `pytest`
- No Docker execution yet — all mock responses
- Clean Pydantic models for every request/response type

## Notes

- Keep it simple. This is the API skeleton.
- The mock execute endpoint should immediately complete so we can test the full polling flow.
- We'll add a separate mock for `awaiting_llm` status in a test helper so we can test the respond flow too.
- Port is 9090 (web UI and agent API share the same port).
