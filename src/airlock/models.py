"""Pydantic request/response models for the Airlock API."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


# --- Requests ---


class ExecutionRequest(BaseModel):
    """Request to execute a Python script."""

    profile_id: str  # ark_... profile ID (acts as auth)
    script: str  # Python code to execute
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
