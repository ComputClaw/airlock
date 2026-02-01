# Spec 02: Docker Execution (mock+)

## Goal

Replace the mock execution with real Python code running inside a single long-running Docker container. Each execution request runs as a separate thread inside the worker.

**Before:** `POST /execute` → returns `{"echo": script[:100]}` (fake)
**After:** `POST /execute` → sends code to worker container → runs in a thread → returns real result

## Prerequisites

- Spec 01 complete
- Docker daemon running on host

## Architecture

```
Airlock API (FastAPI :9090)
    │
    POST /execute
    │
    └──► Worker Container (FastAPI :8001)
              │
              POST /run  →  thread per execution
              POST /resume →  unblock LLM wait (future)
```

One worker container. Started with the app, stopped on shutdown. Each incoming execution runs in its own thread inside the worker.

## Tasks

### 1. Worker Server — `src/airlock/worker/server.py`

Minimal FastAPI app running inside the worker container:

```
POST /run
  Request:  {"script": str, "settings": dict, "timeout": int}
  Response: {
    "status": "completed" | "error" | "timeout",
    "result": Any | null,
    "stdout": str,
    "stderr": str,
    "error": str | null,
    "execution_time_ms": int
  }
```

Execution logic:
1. Create SDK objects (`settings`, `set_result`) and inject into namespace
2. Capture stdout/stderr with `io.StringIO` + `contextlib.redirect_stdout/stderr`
3. Run `exec(script, namespace)` in a thread with timeout
4. Return captured output + result + timing

Thread timeout: use `threading.Thread` + `.join(timeout)`. If thread is still alive after timeout, return `{"status": "timeout"}`.

### 2. Script SDK — `src/airlock/worker/sdk.py`

Injected into the script namespace. Two things for now:

```python
class Settings:
    def __init__(self, data: dict):
        self._data = data

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def keys(self) -> list[str]:
        return list(self._data.keys())

class ResultHolder:
    def __init__(self):
        self.value = None

    def set_result(self, data):
        self.value = data
```

Script sees: `settings.get("API_KEY")`, `settings.keys()`, `set_result(data)`.

No `llm.complete()` yet — that's a future spec.

### 3. Worker Dockerfile — `Dockerfile.worker`

```dockerfile
FROM python:3.12-slim

RUN useradd -m -s /bin/bash worker

RUN pip install --no-cache-dir fastapi uvicorn

COPY src/airlock/worker/ /app/worker/

USER worker
WORKDIR /app

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "worker.server:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 4. Worker Manager — `src/airlock/worker_manager.py`

Manages the single worker container lifecycle:

```python
class WorkerManager:
    async def start(self):
        """Build worker image and start the container on a Docker network."""

    async def stop(self):
        """Stop and remove the worker container and network."""

    async def execute(self, script: str, settings: dict, timeout: int) -> dict:
        """POST /run to the worker container. Returns the response dict."""

    def is_running(self) -> bool:
        """Check if the worker container is alive."""
```

- Uses `docker` Python SDK (docker-py) or subprocess calls to `docker`
- Creates a bridge network for Airlock ↔ Worker communication
- Worker container name: `airlock-worker`
- Airlock reaches worker at `http://airlock-worker:8001`

### 5. Update Agent API — `src/airlock/api/agent.py`

Replace mock execution:

- `POST /execute`:
  - Validate `ark_` prefix (unchanged)
  - Store execution as `pending` in the in-memory dict
  - Resolve settings for the profile (stub for now — empty dict or hardcoded test data)
  - Kick off execution as a `BackgroundTask`:
    - Call `worker_manager.execute(script, settings, timeout)`
    - Update execution state with the result
  - Return 202 with `execution_id` + `poll_url`

- `GET /executions/{id}`: unchanged

- `POST /executions/{id}/respond`: unchanged (still returns 409)

### 6. Update App Lifespan — `src/airlock/app.py`

- Startup: init DB → init admin → **start worker container**
- Shutdown: **stop worker container** → close DB

### 7. Tests

Docker-dependent tests — skip in CI if Docker unavailable:

- **test_simple_execution**: Execute `set_result(2 + 2)` → poll → result is `4`
- **test_stdout_capture**: Execute `print("hello")` → stdout is `"hello\n"`
- **test_execution_error**: Execute `raise ValueError("boom")` → status "error", error contains "boom"
- **test_execution_timeout**: Execute `import time; time.sleep(999)` with timeout=2 → status "timeout"
- **test_settings_access**: Execute with settings `{"KEY": "val"}` → `set_result(settings.get("KEY"))` → result is `"val"`
- **test_settings_keys**: Execute `set_result(settings.keys())` → returns list of injected keys

Keep existing mock tests as a fast suite that runs without Docker.

## What Does NOT Change

- Web UI
- Admin auth (setup/login)
- Admin API stubs
- Health endpoint
- `GET /skill.md`
- LLM pause/resume (future spec)
- Output sanitization (future spec)
- Profile/credential resolution (stubs until Phase 2/3 are done)

## Acceptance Criteria

- [ ] `docker build -f Dockerfile.worker -t airlock-worker .` succeeds
- [ ] Worker container starts automatically with the app
- [ ] `POST /execute` → code runs in container → poll returns real result
- [ ] stdout/stderr captured correctly
- [ ] Errors return status "error" with message
- [ ] Timeouts return status "timeout"
- [ ] Settings injected and accessible via `settings.get()`
- [ ] Worker container cleaned up on app shutdown
- [ ] Existing non-Docker tests still pass

## Implementation Order

1. Worker SDK (`sdk.py`)
2. Worker server (`server.py`) — test standalone with `docker run`
3. `Dockerfile.worker` — build and verify
4. Worker manager — start/stop/execute
5. Wire into agent API + app lifespan
6. Integration tests
