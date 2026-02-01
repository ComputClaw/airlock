"""Docker worker container lifecycle management."""

import asyncio
import os
from pathlib import Path
from typing import Any

import httpx


CONTAINER_NAME = "airlock-worker"
IMAGE_NAME = "airlock-worker"
NETWORK_NAME = "airlock-net"
WORKER_PORT = 8001


def _get_project_root() -> Path:
    """Locate the project root (contains Dockerfile.worker)."""
    env_root = os.environ.get("AIRLOCK_PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    # Default: three levels up from this file (src/airlock/worker_manager.py)
    return Path(__file__).resolve().parent.parent.parent


async def _run_docker(*args: str) -> tuple[int, str, str]:
    """Run a docker CLI command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "docker", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()


class WorkerManager:
    """Manages the Docker worker container lifecycle."""

    def __init__(self) -> None:
        self._started = False
        self._client = httpx.AsyncClient(base_url=f"http://localhost:{WORKER_PORT}")

    async def start(self) -> None:
        """Build the worker image, create network, start container, wait for health."""
        # Clean up any leftover container
        await _run_docker("rm", "-f", CONTAINER_NAME)

        # Create network (ignore if exists)
        await _run_docker("network", "create", NETWORK_NAME)

        # Build the worker image
        project_root = _get_project_root()
        rc, out, err = await _run_docker(
            "build", "-f", str(project_root / "Dockerfile.worker"),
            "-t", IMAGE_NAME, str(project_root),
        )
        if rc != 0:
            raise RuntimeError(f"Failed to build worker image: {err}")

        # Run the container
        rc, out, err = await _run_docker(
            "run", "-d",
            "--name", CONTAINER_NAME,
            "--network", NETWORK_NAME,
            "-p", f"{WORKER_PORT}:{WORKER_PORT}",
            IMAGE_NAME,
        )
        if rc != 0:
            raise RuntimeError(f"Failed to start worker container: {err}")

        await self._wait_for_ready()
        self._started = True

    async def stop(self) -> None:
        """Stop and remove the worker container."""
        if self._started:
            await _run_docker("stop", CONTAINER_NAME)
            await _run_docker("rm", "-f", CONTAINER_NAME)
            self._started = False
        await self._client.aclose()

    async def execute(
        self, script: str, settings: dict[str, str] | None = None, timeout: int = 60
    ) -> dict[str, Any]:
        """Send a script to the worker for execution."""
        http_timeout = timeout + 10  # give worker time to report its own timeout
        resp = await self._client.post(
            "/run",
            json={"script": script, "settings": settings or {}, "timeout": timeout},
            timeout=http_timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def is_running(self) -> bool:
        """Check if the worker container was started."""
        return self._started

    async def _wait_for_ready(self, retries: int = 30, interval: float = 0.5) -> None:
        """Poll the worker health endpoint until it responds."""
        for i in range(retries):
            try:
                resp = await self._client.get("/health", timeout=2)
                if resp.status_code == 200:
                    return
            except httpx.ConnectError:
                pass
            await asyncio.sleep(interval)
        raise RuntimeError(
            f"Worker container did not become ready after {retries * interval}s"
        )
