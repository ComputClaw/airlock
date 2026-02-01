"""Admin API routes: setup, login, and authenticated management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from airlock.auth import (
    is_setup_complete,
    login_admin,
    require_admin,
    setup_admin,
)
from airlock.db import get_db

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
async def list_credentials() -> list:
    """List all stored credentials."""
    return []


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
