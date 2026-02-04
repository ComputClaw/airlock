"""Agent-facing API routes: execute, poll, LLM respond, skill discovery."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from airlock.db import get_db
from airlock.models import (
    AgentCreateCredentialsRequest,
    AgentCreateCredentialsResponse,
    AgentCredentialInfo,
    ExecutionCreated,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    LLMResponse,
)
from airlock.services.credentials import (
    create_credential,
    list_credentials,
    validate_credential_name,
)

if TYPE_CHECKING:
    from airlock.worker_manager import WorkerManager

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory execution storage
_executions: dict[str, ExecutionResult] = {}

# Worker manager (set by app lifespan, None = mock mode)
_worker_manager: WorkerManager | None = None


def set_worker_manager(wm: WorkerManager | None) -> None:
    """Set (or clear) the worker manager used by the execute endpoint."""
    global _worker_manager  # noqa: PLW0603
    _worker_manager = wm


async def _run_execution(
    execution_id: str, script: str, settings: dict[str, str], timeout: int
) -> None:
    """Background task: run script via worker or fall back to mock."""
    _executions[execution_id] = _executions[execution_id].model_copy(
        update={"status": ExecutionStatus.running}
    )

    try:
        if _worker_manager is not None and _worker_manager.is_running():
            result = await _worker_manager.execute(script, settings, timeout)
            status = ExecutionStatus(result["status"])
            _executions[execution_id] = _executions[execution_id].model_copy(
                update={
                    "status": status,
                    "result": result.get("result"),
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "error": result.get("error"),
                }
            )
        else:
            # Mock fallback: echo the script
            _executions[execution_id] = _executions[execution_id].model_copy(
                update={
                    "status": ExecutionStatus.completed,
                    "result": {"echo": script[:100]},
                }
            )
    except Exception as exc:
        logger.exception("Execution %s failed", execution_id)
        _executions[execution_id] = _executions[execution_id].model_copy(
            update={
                "status": ExecutionStatus.error,
                "error": str(exc),
            }
        )


@router.get("/credentials")
async def agent_list_credentials() -> dict:
    """List all credentials with metadata. Never returns values."""
    db = await get_db()
    creds = await list_credentials(db)
    return {
        "credentials": [
            AgentCredentialInfo(
                name=c["name"],
                description=c["description"],
                value_exists=c["value_exists"],
            ).model_dump()
            for c in creds
        ]
    }


@router.post("/credentials", status_code=201, response_model=AgentCreateCredentialsResponse)
async def agent_create_credentials(
    body: AgentCreateCredentialsRequest, request: Request
) -> AgentCreateCredentialsResponse:
    """Create credential slots (name + description, no values)."""
    db = await get_db()
    master_key: bytes = request.app.state.master_key
    created: list[str] = []
    skipped: list[str] = []

    for item in body.credentials:
        try:
            validate_credential_name(item.name)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        try:
            await create_credential(db, item.name, item.description, None, master_key)
            created.append(item.name)
        except ValueError:
            # Name already exists — skip silently
            skipped.append(item.name)

    return AgentCreateCredentialsResponse(created=created, skipped=skipped)


@router.post("/execute", status_code=202, response_model=ExecutionCreated)
async def execute(request: ExecutionRequest, background: BackgroundTasks) -> ExecutionCreated:
    """Accept a script for execution. Returns 202 and runs in background."""
    if not request.profile_id.startswith("ark_"):
        raise HTTPException(status_code=401, detail="Invalid profile_id: must start with 'ark_'")

    execution_id = f"exec_{uuid.uuid4().hex}"
    poll_url = f"/executions/{execution_id}"

    _executions[execution_id] = ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.pending,
    )

    background.add_task(_run_execution, execution_id, request.script, {}, request.timeout)

    return ExecutionCreated(
        execution_id=execution_id,
        poll_url=poll_url,
        status=ExecutionStatus.pending,
    )


@router.get("/executions/{execution_id}", response_model=ExecutionResult)
async def get_execution(execution_id: str) -> ExecutionResult:
    """Poll execution status."""
    if execution_id not in _executions:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return _executions[execution_id]


@router.post("/executions/{execution_id}/respond", response_model=ExecutionResult)
async def respond_to_execution(execution_id: str, response: LLMResponse) -> ExecutionResult:
    """Provide an LLM response to a paused execution."""
    if execution_id not in _executions:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    execution = _executions[execution_id]
    if execution.status != ExecutionStatus.awaiting_llm:
        raise HTTPException(
            status_code=409,
            detail=f"Execution is '{execution.status.value}', not 'awaiting_llm'",
        )

    # Mock: complete with the LLM response
    _executions[execution_id] = execution.model_copy(
        update={
            "status": ExecutionStatus.completed,
            "result": {"llm_response": response.response},
            "llm_request": None,
        }
    )
    return _executions[execution_id]


@router.get("/skill.md", response_class=PlainTextResponse)
async def skill_md() -> PlainTextResponse:
    """Return the dynamic skill document."""
    content = """# Airlock — Code Execution Service

## Overview
Airlock executes Python scripts with access to configured credentials.

## Authentication
Use a profile ID (`ark_...`) as your authentication token.
Include it in the `profile_id` field of execution requests.

## Endpoints

- `POST /execute` — Submit a script for execution
- `GET /executions/{id}` — Poll execution status
- `POST /executions/{id}/respond` — Provide LLM response

## Available Profiles
No profiles configured yet. Ask your admin to set one up.
"""
    return PlainTextResponse(content=content, media_type="text/markdown")
