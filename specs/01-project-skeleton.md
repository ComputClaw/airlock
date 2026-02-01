# Spec 01: Project Skeleton

## Goal

Set up the project structure, dependencies, and a minimal working API that accepts an execution request and returns a mock response.

## Tasks

1. **Create `pyproject.toml`** with project metadata and dependencies:
   - fastapi
   - uvicorn[standard]
   - docker (docker-py SDK)
   - pyyaml
   - cryptography (for secret encryption)
   - pydantic
   - pytest (dev dependency)
   - httpx (dev dependency, for testing FastAPI)

2. **Create Pydantic models** in `src/airlock/models.py`:
   - `ExecutionRequest`: code (str), project (str), timeout (int, default 60)
   - `ExecutionResponse`: status (literal "success"/"error"/"timeout"), stdout (str), stderr (str), output_files (list), execution_time_ms (int), exit_code (int)
   - `ProjectInfo`: name (str), description (str), network_allowlist (list[str]), available_packages (list[str])

3. **Create API routes** in `src/airlock/api.py`:
   - `POST /execute` — accepts ExecutionRequest, returns ExecutionResponse (mock for now: just echo the code back in stdout)
   - `GET /projects` — returns list of ProjectInfo (hardcode one example project)
   - `GET /health` — returns `{"status": "ok"}`

4. **Create entry point** `src/airlock/__main__.py` that starts uvicorn

5. **Create a basic test** in `tests/test_api.py`:
   - Test health endpoint returns 200
   - Test execute endpoint accepts a request and returns a response
   - Test projects endpoint returns a list

6. **Create a `.gitignore`** (Python defaults + .env + secrets/)

## Acceptance Criteria

- `python -m airlock` starts the server on port 8000
- All three endpoints respond correctly
- Tests pass with `pytest`
- No actual Docker execution yet — just the API skeleton

## Notes

- Keep it simple. This is scaffolding.
- The mock execute endpoint should return the code in stdout so we can verify the request/response cycle works.
