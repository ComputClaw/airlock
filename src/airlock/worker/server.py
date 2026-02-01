"""Worker FastAPI server: executes Python scripts inside the container."""

import contextlib
import io
import threading
import traceback
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from worker.sdk import ResultHolder, Settings

app = FastAPI(title="Airlock Worker")


class RunRequest(BaseModel):
    """Request to execute a script."""

    script: str
    settings: dict[str, str] = {}
    timeout: int = 60


class RunResponse(BaseModel):
    """Result of script execution."""

    status: str  # completed | error | timeout
    result: Any | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse)
async def run(request: RunRequest) -> RunResponse:
    """Execute a Python script with captured output."""
    settings = Settings(request.settings)
    result_holder = ResultHolder()

    namespace: dict[str, Any] = {
        "settings": settings,
        "set_result": result_holder.set_result,
    }

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exec_error: list[str] = []  # mutable container for thread communication

    def _run_script() -> None:
        try:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                exec(request.script, namespace)  # noqa: S102
        except Exception:
            exec_error.append(traceback.format_exc())

    thread = threading.Thread(target=_run_script, daemon=True)
    thread.start()
    thread.join(timeout=request.timeout)

    if thread.is_alive():
        return RunResponse(
            status="timeout",
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            error=f"Script exceeded {request.timeout}s timeout",
        )

    if exec_error:
        return RunResponse(
            status="error",
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            error=exec_error[0],
        )

    return RunResponse(
        status="completed",
        result=result_holder.value,
        stdout=stdout_buf.getvalue(),
        stderr=stderr_buf.getvalue(),
    )
