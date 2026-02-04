"""Execution management: create, dispatch, poll, and list executions."""

import json
import uuid
from typing import Any, TypedDict

import aiosqlite


class ExecutionRecord(TypedDict):
    """Execution record from SQLite."""

    id: str
    profile_id: str
    status: str  # pending | running | completed | error | timeout
    result: Any | None  # JSON-decoded
    stdout: str
    stderr: str
    error: str | None
    execution_time_ms: int | None
    created_at: str
    completed_at: str | None


async def create_execution(
    db: aiosqlite.Connection,
    profile_id: str,
    script: str,
    timeout: int = 60,
) -> str:
    """Create a new execution record in pending state. Returns execution_id."""
    execution_id = f"exec_{uuid.uuid4().hex[:16]}"
    await db.execute(
        """INSERT INTO executions (id, profile_id, script, status)
           VALUES (?, ?, ?, 'pending')""",
        (execution_id, profile_id, script),
    )
    await db.commit()
    return execution_id


async def update_execution(
    db: aiosqlite.Connection,
    execution_id: str,
    status: str,
    result: Any | None = None,
    stdout: str = "",
    stderr: str = "",
    error: str | None = None,
    execution_time_ms: int | None = None,
) -> None:
    """Update an execution record with results."""
    await db.execute(
        """UPDATE executions
           SET status = ?, result = ?, stdout = ?, stderr = ?,
               error = ?, execution_time_ms = ?,
               completed_at = CASE WHEN ? IN ('completed', 'error', 'timeout')
                              THEN datetime('now') ELSE completed_at END
           WHERE id = ?""",
        (
            status,
            json.dumps(result) if result is not None else None,
            stdout,
            stderr,
            error,
            execution_time_ms,
            status,  # for the CASE expression
            execution_id,
        ),
    )
    await db.commit()


async def get_execution(
    db: aiosqlite.Connection, execution_id: str
) -> ExecutionRecord | None:
    """Get a single execution by ID."""
    cursor = await db.execute(
        """SELECT id, profile_id, status, result, stdout, stderr,
                  error, execution_time_ms, created_at, completed_at
           FROM executions WHERE id = ?""",
        (execution_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None

    return ExecutionRecord(
        id=row["id"],
        profile_id=row["profile_id"],
        status=row["status"],
        result=json.loads(row["result"]) if row["result"] else None,
        stdout=row["stdout"] or "",
        stderr=row["stderr"] or "",
        error=row["error"],
        execution_time_ms=row["execution_time_ms"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


async def list_executions(
    db: aiosqlite.Connection,
    profile_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ExecutionRecord]:
    """List executions with optional filtering.

    - profile_id: filter by profile
    - status: filter by status
    - limit/offset: pagination (default 50 per page)
    - Ordered by created_at DESC (newest first)
    """
    conditions: list[str] = []
    params: list[str | int] = []

    if profile_id:
        conditions.append("profile_id = ?")
        params.append(profile_id)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    cursor = await db.execute(
        f"""SELECT id, profile_id, status, result, stdout, stderr,
                   error, execution_time_ms, created_at, completed_at
            FROM executions {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?""",
        params,
    )
    rows = await cursor.fetchall()

    return [
        ExecutionRecord(
            id=row["id"],
            profile_id=row["profile_id"],
            status=row["status"],
            result=json.loads(row["result"]) if row["result"] else None,
            stdout=row["stdout"] or "",
            stderr=row["stderr"] or "",
            error=row["error"],
            execution_time_ms=row["execution_time_ms"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
        for row in rows
    ]
