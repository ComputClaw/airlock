# Spec 02: Docker Worker Pool

## Goal

Replace mock execution with real Docker-based worker pools. Each project gets its own pool of long-running worker containers. Airlock API routes execution requests to idle workers.

## Prerequisites

- Spec 01 complete (API skeleton with all endpoints working)
- Docker installed and running on the host

## Architecture

```
Airlock API (FastAPI :8000)
    │
    ├── POST /execute
    │   └── find idle worker for project
    │       └── POST worker:8001/run {code, settings, memory}
    │
    ├── POST /projects/{name}/up
    │   └── build image → start N containers → register in pool
    │
    └── POST /projects/{name}/down
        └── stop containers → remove from pool
```

Each worker container:
- Runs a minimal FastAPI on port 8001
- Has a single endpoint: `POST /run`
- Executes code in a thread
- Has project secrets as environment variables
- Runs as non-root user
- Is on a project-specific Docker network

## Tasks

### 1. Worker Server — `src/airlock/worker/server.py`

A minimal FastAPI app that runs inside each worker container:

```python
POST /run
  Request:
    {
      "code": str,
      "settings": dict,    # non-secret settings
      "memory": dict,      # current memory state
      "timeout": int
    }
  
  Response:
    {
      "status": "completed" | "error" | "timeout" | "awaiting_llm",
      "result": Any | None,
      "stdout": str,
      "stderr": str,
      "error": str | None,
      "llm_request": {"prompt": str, "model": str} | None,
      "memory_updates": dict
    }
```

**Execution logic:**
1. Capture stdout/stderr with `io.StringIO` + `contextlib.redirect_stdout/stderr`
2. Create SDK objects (`settings`, `memory`, `llm`, `set_result`) and inject into the execution namespace
3. Run `exec(code, namespace)` in a thread with timeout
4. If `llm.complete()` is called, execution blocks on a `threading.Event`
5. Return response

**LLM pause mechanism:**
- `llm.complete()` sets a flag, stores the prompt/model, and blocks on an `Event`
- Worker server detects the pause and returns `{status: "awaiting_llm", llm_request: {...}}`
- A second endpoint `POST /resume` accepts `{response: str}`, sets the Event, unblocks the thread
- After resume, execution continues and the final result is returned

### 2. Script SDK — `src/airlock/worker/sdk.py`

Classes/functions injected into the script execution namespace:

```python
class Settings:
    def __init__(self, env_secrets: dict, payload_settings: dict):
        self._secrets = env_secrets        # from os.environ
        self._settings = payload_settings  # from request payload
    
    def get(self, key: str) -> str | None:
        # Settings payload wins for non-secrets, env wins for secrets
        return self._secrets.get(key) or self._settings.get(key)
    
    def keys(self) -> list[str]:
        return list(set(self._secrets.keys()) | set(self._settings.keys()))

class Memory:
    def __init__(self, initial: dict):
        self._data = initial.copy()
        self._updates = {}
    
    def get(self, category: str, key: str) -> Any:
        return self._data.get(f"{category}.{key}")
    
    def set(self, category: str, key: str, value: Any):
        self._updates[f"{category}.{key}"] = value
        self._data[f"{category}.{key}"] = value
    
    def get_updates(self) -> dict:
        return self._updates.copy()

class LLM:
    def __init__(self):
        self._event = threading.Event()
        self._request = None
        self._response = None
        self._awaiting = False
    
    def complete(self, prompt: str, model: str = "default") -> str:
        self._request = {"prompt": prompt, "model": model}
        self._awaiting = True
        self._event.clear()
        self._event.wait()  # blocks until resume
        self._awaiting = False
        return self._response

# set_result is a simple function that stores data on a shared object
```

### 3. Worker Dockerfile — `Dockerfile.worker`

```dockerfile
FROM python:3.12-slim

# Create non-root user
RUN useradd -m -s /bin/bash worker

# Install base dependencies
RUN pip install --no-cache-dir fastapi uvicorn

# Copy worker server code
COPY src/airlock/worker/ /app/worker/

# Project-specific packages installed at image build time
# (passed as build arg, handled by pool manager)
ARG PACKAGES=""
RUN if [ -n "$PACKAGES" ]; then pip install --no-cache-dir $PACKAGES; fi

USER worker
WORKDIR /app

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "worker.server:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 4. Pool Manager — `src/airlock/pool.py`

Manages Docker containers for each project:

```python
class WorkerPool:
    """Manages a pool of worker containers for a single project."""
    
    def __init__(self, project_name: str, project_config: dict):
        self.project_name = project_name
        self.config = project_config
        self.workers: list[WorkerInfo] = []  # container_id, url, status
    
    async def up(self, replicas: int):
        """Build image (if needed) and start N worker containers."""
        # 1. Build Docker image with project packages
        # 2. Create project-specific Docker network (with allowlist rules)
        # 3. Start N containers with secrets as env vars
        # 4. Wait for health checks
        # 5. Register workers
    
    async def down(self):
        """Stop and remove all workers and the project network."""
    
    def get_idle_worker(self) -> WorkerInfo | None:
        """Return an idle worker, or None if all busy."""
    
    def mark_busy(self, worker_id: str):
        """Mark a worker as busy (processing a request)."""
    
    def mark_idle(self, worker_id: str):
        """Mark a worker as idle (available for requests)."""

class PoolManager:
    """Manages all project pools."""
    
    pools: dict[str, WorkerPool] = {}
    
    async def get_pool(self, project: str) -> WorkerPool | None:
        ...
    
    async def start_pool(self, project: str, replicas: int):
        ...
    
    async def stop_pool(self, project: str):
        ...
```

### 5. Request Router — `src/airlock/router.py`

Routes execution requests to idle workers:

```python
async def route_execution(execution_id: str, request: ExecutionRequest):
    """
    1. Find idle worker in the project's pool
    2. Mark worker busy
    3. POST /run to the worker
    4. Handle response:
       - completed/error/timeout → update execution state
       - awaiting_llm → update execution state with llm_request
    5. Mark worker idle (or keep busy if awaiting_llm)
    """
```

### 6. Output Sanitizer — `src/airlock/sanitizer.py`

```python
def sanitize(text: str, secrets: dict[str, str]) -> str:
    """
    Replace secret values in text with [REDACTED...last4].
    
    - Exact match against all secret values
    - Longer secrets replaced first (avoid partial matches)
    - Last 4 chars preserved for debugging
    """
    for key, value in sorted(secrets.items(), key=lambda x: -len(x[1])):
        if len(value) > 4:
            redacted = f"[REDACTED...{value[-4:]}]"
        else:
            redacted = "[REDACTED]"
        text = text.replace(value, redacted)
    return text
```

### 7. Update API Routes — `src/airlock/api.py`

Replace mock implementations with real pool-backed execution:

- `POST /execute`: Queue execution, route to idle worker via `route_execution()`
- `GET /executions/{id}`: Return current state (unchanged from spec 01)
- `POST /executions/{id}/respond`: Forward LLM response to worker's `/resume` endpoint
- `POST /projects/{name}/up`: Call `pool_manager.start_pool()`
- `POST /projects/{name}/down`: Call `pool_manager.stop_pool()`
- `GET /projects`: Read from pool_manager state

### 8. Tests

- **test_pool_up_down**: Start pool → verify containers running → stop pool → verify containers gone
- **test_execute_in_worker**: Start pool → POST /execute with simple code → poll → verify result
- **test_execute_with_settings**: Verify settings.get() works in executed code
- **test_execute_with_memory**: Verify memory read/write and memory_updates in response
- **test_llm_pause_resume**: Execute code that calls llm.complete() → verify awaiting_llm → POST respond → verify completed
- **test_output_sanitization**: Execute code that prints a secret → verify output is redacted
- **test_execution_timeout**: Execute infinite loop → verify timeout status
- **test_no_idle_workers**: All workers busy → verify pending status or queue behavior

## Acceptance Criteria

- `POST /projects/test/up --replicas 2` starts 2 Docker containers
- `POST /execute` routes to an idle worker and returns real execution results
- LLM pause/resume flow works end-to-end through polling
- Secrets are injected as env vars, accessible via `settings.get()`
- Output sanitization redacts secret values
- `POST /projects/test/down` cleanly stops all containers
- All tests pass

## Implementation Order

1. Worker server + SDK (can test standalone)
2. Dockerfile.worker (can build and run manually)
3. Pool manager (Docker integration)
4. Request router
5. Output sanitizer
6. Wire into API routes
7. Integration tests

## Notes

- Workers communicate with Airlock API over Docker network — use container names for DNS
- The LLM pause/resume is the trickiest part — the worker thread blocks while Airlock holds the execution state
- Consider using `asyncio.Queue` for request routing if we want queuing behavior
- Start with a simple round-robin or first-idle routing strategy
