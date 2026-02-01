# Spec 01: Project Skeleton — API Server with Mock Responses

## Goal

Set up the project structure, dependencies, and a working FastAPI API server with all endpoints defined. Mock responses only — no Docker, no real workers yet.

## Architecture Context

Airlock uses a **polling model**:
1. Agent POSTs code → gets 202 with `execution_id`
2. Agent polls `GET /executions/{id}` until terminal status
3. If script needs LLM, status shows `awaiting_llm` → agent provides response via POST

This spec implements the API skeleton with in-memory state and mock execution.

## Tasks

### 1. Create `pyproject.toml`

Project metadata and dependencies:
- fastapi
- uvicorn[standard]
- docker (docker-py SDK)
- pyyaml
- pydantic
- pytest (dev)
- httpx (dev, for testing FastAPI)

### 2. Create Pydantic Models — `src/airlock/models.py`

```python
# --- Requests ---

class ExecutionRequest(BaseModel):
    project: str                          # Project identifier
    code: str                             # Python code to execute
    timeout: int = 60                     # Max execution time (seconds)
    settings: dict[str, str] = {}         # Non-secret settings
    memory: dict[str, Any] = {}           # Current memory state

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
    memory_updates: dict[str, Any] = {}
    execution_time_ms: int | None = None

class ProjectInfo(BaseModel):
    name: str
    description: str
    status: str                           # "up" | "down"
    replicas: int = 0
    idle_workers: int = 0
    packages: list[str] = []

class ProjectList(BaseModel):
    projects: list[ProjectInfo]

class PoolRequest(BaseModel):
    replicas: int = 1

class PoolStatus(BaseModel):
    name: str
    status: str
    replicas: int

class HealthResponse(BaseModel):
    status: str = "ok"
```

### 3. Create API Routes — `src/airlock/api.py`

All endpoints, with in-memory state for tracking executions:

#### `POST /execute` → 202

- Generate a UUID execution_id
- Store in an in-memory dict with status `pending`
- **Mock behavior**: immediately set status to `completed` with `result = {"echo": code}` and `stdout = code`
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

#### `GET /projects` → 200

- Return `ProjectList` with one hardcoded example project:
  ```python
  ProjectInfo(
      name="mock-project",
      description="A mock project for testing",
      status="up",
      replicas=1,
      idle_workers=1,
      packages=["requests", "pandas"]
  )
  ```

#### `POST /projects/{name}/up` → 200

- Accept `PoolRequest` body
- **Mock behavior**: return `PoolStatus(name=name, status="up", replicas=request.replicas)`

#### `POST /projects/{name}/down` → 200

- **Mock behavior**: return `PoolStatus(name=name, status="down", replicas=0)`

#### `GET /health` → 200

- Return `HealthResponse`

### 4. Create Entry Point — `src/airlock/__main__.py`

```python
import uvicorn
from airlock.api import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 5. Create Tests — `tests/test_api.py`

Using `httpx.AsyncClient` with FastAPI's `TestClient`:

- **test_health**: GET /health returns 200 with `{"status": "ok"}`
- **test_execute_returns_202**: POST /execute returns 202 with execution_id
- **test_poll_execution**: POST /execute → GET /executions/{id} returns completed result
- **test_poll_not_found**: GET /executions/nonexistent returns 404
- **test_respond_requires_awaiting_llm**: POST /executions/{id}/respond on a completed execution returns 409
- **test_projects_list**: GET /projects returns a list with at least one project
- **test_project_up**: POST /projects/test/up returns status "up"
- **test_project_down**: POST /projects/test/down returns status "down" with 0 replicas

### 6. Create `.gitignore`

Python defaults + `.env` + `secrets/` + `__pycache__/` + `.pytest_cache/` + `*.egg-info`

## Acceptance Criteria

- `python -m airlock` starts the server on port 8000
- All seven endpoints respond correctly with proper status codes
- Full polling flow works: POST /execute → GET /executions/{id} → completed
- Tests pass with `pytest`
- No Docker execution yet — all mock responses
- Clean Pydantic models for every request/response type

## Notes

- Keep it simple. This is the API skeleton.
- The mock execute endpoint should immediately complete so we can test the full polling flow.
- We'll add a separate mock for `awaiting_llm` status in a test helper so we can test the respond flow too.
