"""Admin API routes: setup, login, and authenticated management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
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
    CreateProfileRequest,
    CredentialRefResponse,
    ProfileCredentialsRequest,
    ProfileLockedResponse,
    ProfileResponse,
    UpdateProfileRequest,
)
from airlock.services.credentials import (
    create_credential,
    delete_credential,
    list_credentials,
    update_credential,
    validate_credential_name,
)
from airlock.services.profiles import (
    add_credentials,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    lock_profile,
    regenerate_key,
    remove_credentials,
    revoke_profile,
    update_profile,
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


@router.get("/profiles", dependencies=[Depends(require_admin)])
async def admin_list_profiles() -> dict:
    """List all profiles."""
    db = await get_db()
    profiles = await list_profiles(db)
    return {"profiles": [_profile_response(p).model_dump() for p in profiles]}


@router.get("/profiles/{profile_id}", dependencies=[Depends(require_admin)])
async def admin_get_profile(profile_id: str) -> dict:
    """Get a single profile by internal ID."""
    db = await get_db()
    profile = await get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    return _profile_response(profile).model_dump()


@router.post("/profiles", status_code=201, dependencies=[Depends(require_admin)])
async def admin_create_profile(body: CreateProfileRequest) -> dict:
    """Create a new profile."""
    db = await get_db()
    profile = await create_profile(db, body.description)
    return _profile_response(profile).model_dump()


@router.put("/profiles/{profile_id}", dependencies=[Depends(require_admin)])
async def admin_update_profile(profile_id: str, body: UpdateProfileRequest) -> dict:
    """Update a profile's description and/or expiration date."""
    db = await get_db()
    kwargs: dict = {}
    if body.description is not None:
        kwargs["description"] = body.description
    if body.expires_at is not None:
        kwargs["expires_at"] = body.expires_at
    try:
        profile = await update_profile(db, profile_id, **kwargs)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)
    return _profile_response(profile).model_dump()


@router.post("/profiles/{profile_id}/credentials", dependencies=[Depends(require_admin)])
async def admin_add_credentials(
    profile_id: str, body: ProfileCredentialsRequest
) -> dict:
    """Add credential references to a profile."""
    db = await get_db()
    try:
        profile = await add_credentials(db, profile_id, body.credentials)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)
    return _profile_response(profile).model_dump()


@router.delete("/profiles/{profile_id}/credentials", dependencies=[Depends(require_admin)])
async def admin_remove_credentials(
    profile_id: str, body: ProfileCredentialsRequest
) -> dict:
    """Remove credential references from a profile."""
    db = await get_db()
    try:
        profile = await remove_credentials(db, profile_id, body.credentials)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)
    return _profile_response(profile).model_dump()


@router.post("/profiles/{profile_id}/lock", dependencies=[Depends(require_admin)])
async def admin_lock_profile(profile_id: str, request: Request) -> dict:
    """Lock a profile and generate the two-part key."""
    db = await get_db()
    master_key: bytes = request.app.state.master_key
    try:
        result = await lock_profile(db, profile_id, master_key)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)

    profile = result["profile"]
    return ProfileLockedResponse(
        id=profile["id"],
        description=profile["description"],
        locked=profile["locked"],
        key_id=profile["key_id"],
        key=result["key"],
        credentials=[CredentialRefResponse(**c) for c in profile["credentials"]],
        expires_at=profile["expires_at"],
        revoked=profile["revoked"],
        created_at=profile["created_at"],
        updated_at=profile["updated_at"],
    ).model_dump()


@router.post("/profiles/{profile_id}/revoke", dependencies=[Depends(require_admin)])
async def admin_revoke_profile(profile_id: str) -> dict:
    """Revoke a profile. Instant, irreversible."""
    db = await get_db()
    try:
        profile = await revoke_profile(db, profile_id)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)
    return _profile_response(profile).model_dump()


@router.post("/profiles/{profile_id}/regenerate-key", dependencies=[Depends(require_admin)])
async def admin_regenerate_key(profile_id: str, request: Request) -> dict:
    """Regenerate the key pair for a locked profile."""
    db = await get_db()
    master_key: bytes = request.app.state.master_key
    try:
        result = await regenerate_key(db, profile_id, master_key)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)

    profile = result["profile"]
    return ProfileLockedResponse(
        id=profile["id"],
        description=profile["description"],
        locked=profile["locked"],
        key_id=profile["key_id"],
        key=result["key"],
        credentials=[CredentialRefResponse(**c) for c in profile["credentials"]],
        expires_at=profile["expires_at"],
        revoked=profile["revoked"],
        created_at=profile["created_at"],
        updated_at=profile["updated_at"],
    ).model_dump()


@router.delete("/profiles/{profile_id}", status_code=204, dependencies=[Depends(require_admin)])
async def admin_delete_profile(profile_id: str) -> Response:
    """Delete a profile. Cannot delete locked (non-revoked) profiles."""
    db = await get_db()
    try:
        await delete_profile(db, profile_id)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=409, detail=detail)
    return Response(status_code=204)


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
