"""Admin API routes: setup, login, and authenticated management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from airlock.auth import (
    is_setup_complete,
    login_admin,
    require_admin,
    setup_admin,
)
from airlock.db import get_db
from airlock.models import (
    AdminCreateCredentialRequest,
    AdminCredentialInfo,
    AdminUpdateCredentialRequest,
)
from airlock.services.credentials import (
    create_credential,
    delete_credential,
    list_credentials,
    update_credential,
    validate_credential_name,
)

router = APIRouter(prefix="/api/admin")


class SetupRequest(BaseModel):
    """First-time admin password setup."""
    password: str


class LoginRequest(BaseModel):
    """Admin login with password."""
    password: str


class TokenResponse(BaseModel):
    """Returned on successful setup or login."""
    token: str


class StatusResponse(BaseModel):
    """Admin setup status — unauthenticated, used by UI to pick login vs setup screen."""
    setup_required: bool


# --- Unauthenticated routes ---


@router.get("/status", response_model=StatusResponse)
async def admin_status() -> StatusResponse:
    """Check if admin password has been set. No auth required."""
    db = await get_db()
    setup_done = await is_setup_complete(db)
    return StatusResponse(setup_required=not setup_done)


@router.post("/setup", response_model=TokenResponse)
async def admin_setup(request: SetupRequest) -> TokenResponse:
    """Set admin password on first visit. Only works once."""
    db = await get_db()
    try:
        token = await setup_admin(db, request.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return TokenResponse(token=token)


@router.post("/login", response_model=TokenResponse)
async def admin_login(request: LoginRequest) -> TokenResponse:
    """Authenticate with admin password and get a session token."""
    db = await get_db()
    try:
        token = await login_admin(db, request.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return TokenResponse(token=token)


# --- Authenticated routes ---


@router.get("/credentials", dependencies=[Depends(require_admin)])
async def admin_list_credentials() -> dict:
    """List all stored credentials with metadata. Never returns values."""
    db = await get_db()
    creds = await list_credentials(db)
    return {
        "credentials": [
            AdminCredentialInfo(
                name=c["name"],
                description=c["description"],
                has_value=c["value_exists"],
                created_at=c["created_at"],
                updated_at=c["updated_at"],
            ).model_dump()
            for c in creds
        ]
    }


@router.post("/credentials", status_code=201, dependencies=[Depends(require_admin)])
async def admin_create_credential(
    body: AdminCreateCredentialRequest, request: Request
) -> dict:
    """Create a credential with optional value."""
    try:
        validate_credential_name(body.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    master_key: bytes = request.app.state.master_key
    try:
        cred = await create_credential(
            await get_db(), body.name, body.description, body.value, master_key
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return AdminCredentialInfo(
        name=cred["name"],
        description=cred["description"],
        has_value=cred["value_exists"],
        created_at=cred["created_at"],
        updated_at=cred["updated_at"],
    ).model_dump()


@router.put("/credentials/{name}", dependencies=[Depends(require_admin)])
async def admin_update_credential(
    name: str, body: AdminUpdateCredentialRequest, request: Request
) -> dict:
    """Update a credential's value and/or description."""
    master_key: bytes = request.app.state.master_key
    db = await get_db()

    kwargs: dict = {}
    if body.value is not None:
        kwargs["value"] = body.value
        kwargs["master_key"] = master_key
    if body.description is not None:
        kwargs["description"] = body.description

    try:
        cred = await update_credential(db, name, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return AdminCredentialInfo(
        name=cred["name"],
        description=cred["description"],
        has_value=cred["value_exists"],
        created_at=cred["created_at"],
        updated_at=cred["updated_at"],
    ).model_dump()


@router.delete("/credentials/{name}", status_code=204, dependencies=[Depends(require_admin)])
async def admin_delete_credential(name: str) -> None:
    """Delete a credential. 409 if referenced by locked profiles."""
    db = await get_db()
    try:
        await delete_credential(db, name)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)


@router.get("/profiles", dependencies=[Depends(require_admin)])
async def list_profiles() -> list:
    """List all profiles."""
    return []


@router.get("/executions", dependencies=[Depends(require_admin)])
async def list_executions() -> list:
    """List execution history."""
    return []


@router.get("/stats", dependencies=[Depends(require_admin)])
async def get_stats() -> dict:
    """Return dashboard statistics."""
    return {
        "total_executions": 0,
        "active_profiles": 0,
        "stored_credentials": 0,
    }
