"""Agent-facing API routes: execute, poll, LLM respond, skill discovery."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from airlock.auth import ProfileAuth, require_profile
from airlock.db import get_db
from airlock.models import (
    AgentCreateCredentialsRequest,
    AgentCreateCredentialsResponse,
    AgentCredentialInfo,
    CreateProfileRequest,
    CredentialRefResponse,
    ExecutionCreated,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    LLMResponse,
    ProfileCredentialsRequest,
    ProfileResponse,
)
from airlock.services.credentials import (
    create_credential,
    list_credentials,
    resolve_profile_credentials,
    validate_credential_name,
)
from airlock.services.profiles import (
    add_credentials,
    create_profile,
    get_profile,
    list_profiles,
    remove_credentials,
    verify_script_hmac,
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


def _profile_response(info: dict) -> ProfileResponse:
    """Convert a ProfileInfo dict to a ProfileResponse."""
    return ProfileResponse(
        id=info["id"],
        description=info["description"],
        locked=info["locked"],
        key_id=info["key_id"],
        credentials=[
            CredentialRefResponse(**c) for c in info["credentials"]
        ],
        expires_at=info["expires_at"],
        revoked=info["revoked"],
        created_at=info["created_at"],
        updated_at=info["updated_at"],
    )


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


# --- Credential endpoints ---


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


# --- Profile endpoints ---


@router.get("/profiles")
async def agent_list_profiles() -> dict:
    """List all profiles with metadata."""
    db = await get_db()
    profiles = await list_profiles(db)
    return {"profiles": [_profile_response(p).model_dump() for p in profiles]}


@router.get("/profiles/{profile_id}")
async def agent_get_profile(profile_id: str) -> dict:
    """Get a single profile by internal ID."""
    db = await get_db()
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    return _profile_response(profile).model_dump()


@router.post("/profiles", status_code=201)
async def agent_create_profile(body: CreateProfileRequest) -> dict:
    """Create a new unlocked profile."""
    db = await get_db()
    profile = await create_profile(db, body.description)
    return _profile_response(profile).model_dump()


@router.post("/profiles/{profile_id}/credentials")
async def agent_add_credentials(
    profile_id: str, body: ProfileCredentialsRequest
) -> dict:
    """Add credential references to an unlocked profile."""
    db = await get_db()
    try:
        profile = await add_credentials(db, profile_id, body.credentials)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)
    return _profile_response(profile).model_dump()


@router.delete("/profiles/{profile_id}/credentials")
async def agent_remove_credentials(
    profile_id: str, body: ProfileCredentialsRequest
) -> dict:
    """Remove credential references from an unlocked profile."""
    db = await get_db()
    try:
        profile = await remove_credentials(db, profile_id, body.credentials)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)
    return _profile_response(profile).model_dump()


# --- Execution endpoints ---


@router.post("/execute", status_code=202, response_model=ExecutionCreated)
async def execute(
    body: ExecutionRequest,
    raw_request: Request,
    background: BackgroundTasks,
    profile: ProfileAuth = Depends(require_profile),
) -> ExecutionCreated:
    """Accept a script for execution. Authenticated by profile key."""
    if not verify_script_hmac(profile.secret, body.script, body.hash):
        raise HTTPException(
            status_code=403,
            detail="Script hash verification failed — HMAC mismatch",
        )

    execution_id = f"exec_{uuid.uuid4().hex}"
    poll_url = f"/executions/{execution_id}"

    _executions[execution_id] = ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.pending,
    )

    db = await get_db()
    master_key = raw_request.app.state.master_key
    settings = await resolve_profile_credentials(db, profile.profile_id, master_key)

    background.add_task(
        _run_execution, execution_id, body.script, settings, body.timeout
    )

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
Use a profile key (`ark_ID:SECRET`) for execution.
Include the key_id in `Authorization: Bearer ark_...` header.
Include HMAC-SHA256(secret, script) as the `hash` field in the request body.

## Endpoints

- `POST /execute` — Submit a script for execution (Bearer auth + HMAC)
- `GET /executions/{id}` — Poll execution status
- `POST /executions/{id}/respond` — Provide LLM response
- `GET /profiles` — List all profiles
- `POST /profiles` — Create a new profile
- `GET /credentials` — List all credentials

## Available Profiles
No profiles configured yet. Ask your admin to set one up.
"""
    return PlainTextResponse(content=content, media_type="text/markdown")
