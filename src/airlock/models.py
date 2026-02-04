"""Pydantic request/response models for the Airlock API."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


# --- Requests ---


class ExecutionRequest(BaseModel):
    """Request to execute a Python script.

    Profile authentication is via Authorization: Bearer ark_... header.
    The hash field proves code integrity via HMAC-SHA256(secret, script).
    """

    script: str  # Python code to execute
    hash: str  # HMAC-SHA256(secret, script) hex digest
    timeout: int = 60  # Max execution time (seconds)


class LLMResponse(BaseModel):
    """Agent-provided LLM completion for a paused execution."""

    response: str


# --- Responses ---


class ExecutionStatus(str, Enum):
    """Possible states of a script execution."""

    pending = "pending"
    running = "running"
    awaiting_llm = "awaiting_llm"
    completed = "completed"
    error = "error"
    timeout = "timeout"


class ExecutionCreated(BaseModel):
    """Returned when a new execution is accepted."""

    execution_id: str
    poll_url: str
    status: ExecutionStatus = ExecutionStatus.pending


class LLMRequest(BaseModel):
    """Present in execution result when status is awaiting_llm."""

    prompt: str
    model: str = "default"


class ExecutionResult(BaseModel):
    """Full execution state returned by the poll endpoint."""

    execution_id: str
    status: ExecutionStatus
    result: Any | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    llm_request: LLMRequest | None = None
    execution_time_ms: int | None = None


class ExecutionSummary(BaseModel):
    """Execution summary for list endpoints."""

    execution_id: str
    status: str
    execution_time_ms: int | None = None
    created_at: str
    completed_at: str | None = None


class ExecutionDetail(BaseModel):
    """Full execution detail."""

    execution_id: str
    profile_id: str
    status: str
    result: Any | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    execution_time_ms: int | None = None
    created_at: str
    completed_at: str | None = None


class AdminExecutionDetail(ExecutionDetail):
    """Admin execution detail (includes script)."""

    script: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"


# --- Credential Requests ---


class AdminCreateCredentialRequest(BaseModel):
    """Admin creates a credential with optional value."""

    name: str
    value: str | None = None
    description: str = ""


class AdminUpdateCredentialRequest(BaseModel):
    """Admin updates a credential's value and/or description."""

    value: str | None = None
    description: str | None = None


class AgentCreateCredentialItem(BaseModel):
    """Single credential slot for agent batch creation."""

    name: str
    description: str = ""


class AgentCreateCredentialsRequest(BaseModel):
    """Agent creates credential slots (no values)."""

    credentials: list[AgentCreateCredentialItem]


# --- Credential Responses ---


class AdminCredentialInfo(BaseModel):
    """Credential metadata for admin API."""

    name: str
    description: str
    has_value: bool
    created_at: str
    updated_at: str | None = None


class AgentCredentialInfo(BaseModel):
    """Credential metadata for agent API."""

    name: str
    description: str
    value_exists: bool


class AgentCreateCredentialsResponse(BaseModel):
    """Result of agent batch credential creation."""

    created: list[str]
    skipped: list[str]


# --- Profile Requests ---


class CreateProfileRequest(BaseModel):
    """Create a new profile (used by both admin and agent API)."""

    description: str = ""


class UpdateProfileRequest(BaseModel):
    """Update profile description and/or expiration (admin only)."""

    description: str | None = None
    expires_at: str | None = None


class ProfileCredentialsRequest(BaseModel):
    """Add or remove credential references from a profile."""

    credentials: list[str]


# --- Profile Responses ---


class CredentialRefResponse(BaseModel):
    """Credential reference within a profile."""

    name: str
    description: str
    value_exists: bool


class ProfileResponse(BaseModel):
    """Profile metadata (returned by most endpoints)."""

    id: str
    description: str
    locked: bool
    key_id: str | None = None
    credentials: list[CredentialRefResponse] = []
    expires_at: str | None = None
    revoked: bool = False
    created_at: str
    updated_at: str | None = None


class ProfileLockedResponse(BaseModel):
    """Returned by lock and regenerate-key (includes full key, shown once)."""

    id: str
    description: str
    locked: bool = True
    key_id: str
    key: str
    credentials: list[CredentialRefResponse] = []
    expires_at: str | None = None
    revoked: bool = False
    created_at: str
    updated_at: str | None = None
