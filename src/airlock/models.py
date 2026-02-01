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
