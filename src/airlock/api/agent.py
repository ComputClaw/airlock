"""Agent-facing API routes: execute, poll, LLM respond, skill discovery."""

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from airlock.models import (
    ExecutionCreated,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    LLMResponse,
)

router = APIRouter()

# In-memory execution storage for mock phase
_executions: dict[str, ExecutionResult] = {}


@router.post("/execute", status_code=202, response_model=ExecutionCreated)
async def execute(request: ExecutionRequest) -> ExecutionCreated:
    """Accept a script for execution. Mock: completes immediately with echo."""
    if not request.profile_id.startswith("ark_"):
        raise HTTPException(status_code=401, detail="Invalid profile_id: must start with 'ark_'")

    execution_id = f"exec_{uuid.uuid4().hex}"
    poll_url = f"/executions/{execution_id}"

    # Mock: immediately complete with echo of the script
    _executions[execution_id] = ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.completed,
        result={"echo": request.script[:100]},
    )

    return ExecutionCreated(
        execution_id=execution_id,
        poll_url=poll_url,
        status=ExecutionStatus.completed,
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
